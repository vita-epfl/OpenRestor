"""Local, resumable clean-music curation; no downloads or benchmark edits."""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import html
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .evaluation import (distributions, evaluate_decisions, fixed_split, import_blind_reviews,
                         import_iamd_reviews, import_reviews, LABEL_FIELDS, VALID_LABELS,
                         logistic_diagnostic, wilson)
from .features import (EXTRACTOR_VERSION, enrich_local_acoustics, extract_local_source,
                       import_iamd_pilot, normalise_metadata, read_jsonl,
                       refresh_manifest_fields, source_key, write_jsonl_atomic)
from .models import OfflineProbes, needs_probe
from .policy import (DEFAULTS, V2_DEFAULTS, V21_DEFAULTS, score_source,
                     score_source_v2, score_source_v21)


def _records(path: Path) -> dict[str, dict]:
    rows = list(read_jsonl(path))
    result = {row["source_key"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate source_key in {path}")
    return result


def _decision_records(path: Path) -> dict[str, dict]:
    """Read internal decisions or explainable ``pipeline_judgments`` exports.

    The evaluator needs a top-level ``decision`` field, while the human-facing
    export deliberately calls it ``pipeline_decision``.  Normalising that one
    field here keeps the two artifacts interchangeable without changing either
    immutable file on disk.
    """
    rows = list(read_jsonl(path))
    result = {}
    for row in rows:
        key = row.get("source_key")
        if not key:
            raise ValueError(f"decision row lacks source_key in {path}")
        if key in result:
            raise ValueError(f"duplicate source_key in {path}")
        normalized = dict(row)
        if "decision" not in normalized:
            if "pipeline_decision" not in normalized:
                raise ValueError(f"decision row lacks decision/pipeline_decision in {path}: {key}")
            normalized["decision"] = normalized["pipeline_decision"]
        result[key] = normalized
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _key_digest(keys) -> str:
    payload = "\n".join(sorted(keys)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock.json")


def _write_immutable(path: Path, content: str) -> str:
    """Create an artifact once; reruns may only reproduce identical bytes."""
    encoded = content.encode("utf-8")
    if path.exists():
        existing = path.read_bytes()
        if existing != encoded:
            raise ValueError(f"refusing to overwrite frozen artifact: {path}")
        return hashlib.sha256(existing).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)
    return hashlib.sha256(encoded).hexdigest()


def _write_immutable_json(path: Path, value: dict) -> str:
    return _write_immutable(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_or_validate_lock(path: Path, value: dict) -> str:
    """Keep the original timestamp while checking all reproducibility fields on rerun."""
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"invalid existing freeze lock: {path}") from error
        comparable = {key: item for key, item in value.items() if key != "frozen_at_utc"}
        old_comparable = {key: item for key, item in existing.items() if key != "frozen_at_utc"}
        if old_comparable != comparable:
            raise ValueError(f"existing freeze lock does not match artifact: {path}")
        return _sha256_file(path)
    return _write_immutable_json(path, value)


def _config(path: Path | None) -> dict:
    if path is None:
        return DEFAULTS.copy()
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    known = set(DEFAULTS) | set(V2_DEFAULTS) | set(V21_DEFAULTS)
    if not isinstance(value, dict) or set(value) - known:
        raise ValueError("curation config must contain only known numeric policy fields")
    if any(isinstance(number, bool) or not isinstance(number, (int, float))
           or not math.isfinite(number) for number in value.values()):
        raise ValueError("curation policy values must be finite numbers")
    return {**DEFAULTS, **value}


def command_enrich_acoustics(args) -> None:
    records = list(read_jsonl(args.features))
    keys = [row.get("source_key") for row in records]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate source_key in feature input")
    start, stop = args.offset, args.offset + args.limit if args.limit else len(records)
    selected = records[start:stop]
    existing = _records(args.out) if args.out.exists() else {}
    result = dict(existing)
    result.update({row["source_key"]: row for row in enrich_local_acoustics(selected,
                                                                          only_missing=not args.recompute)})
    if args.limit and len(result) < len(records):
        # Partial invocations are intentionally resumable; later invocations merge
        # their rows into the same JSONL without touching already enriched sources.
        print(f"Enriched batch {start}:{stop} ({len(selected)} sources); {len(result)}/{len(records)} present")
    elif set(result) != set(keys):
        raise ValueError("output contains an incomplete source set; rerun batches until complete")
    write_jsonl_atomic(args.out, [result[key] for key in sorted(result)])
    if not args.limit:
        print(f"Enriched {len(result)} sources with local acoustic v2 descriptors: {args.out}")


def command_import_iamd(args) -> None:
    records = import_iamd_pilot(args.pilot_dir)
    write_jsonl_atomic(args.out, records)
    print(f"Imported {len(records)} existing IAMD sources into {args.out}")


def command_extract(args) -> None:
    manifest = list(read_jsonl(args.manifest))
    existing = _records(args.out) if args.out.exists() else {}
    result = {}
    for number, row in enumerate(manifest, 1):
        key = source_key(str(row.get("dataset") or ""), str(row.get("source_id") or ""))
        if key in result:
            raise ValueError(f"duplicate source_key in input manifest: {key}")
        path = Path(str(row.get("audio_path") or ""))
        if not path.is_file():
            raise FileNotFoundError(f"missing local audio for {key}: {path}")
        rights = row.get("rights") or {}
        if not isinstance(rights, dict):
            raise ValueError(f"rights must be an object for {key}")
        stat = path.stat()
        old = existing.get(key)
        if (old and old.get("file_fingerprint", {}).get("path") == str(path.resolve())
                and old["file_fingerprint"].get("size_bytes") == stat.st_size
                and old["file_fingerprint"].get("mtime_ns") == stat.st_mtime_ns
                and old.get("extractor", {}).get("version") == EXTRACTOR_VERSION
                and old.get("extractor", {}).get("segment_seconds") == args.segment_seconds
                and old.get("segments")
                and all(Path(segment["clip_path"]).is_file() for segment in old["segments"])):
            result[key] = {**old, "metadata": normalise_metadata(row.get("metadata")),
                           "rights": rights}
            # Refresh non-scoring manifest fields even when the audio/clip cache
            # is reused; rights and checksum edits must never be hidden by cache.
            refresh_manifest_fields(result[key], row)
        else:
            result[key] = extract_local_source(row, args.clips_dir, seconds=args.segment_seconds)
        write_jsonl_atomic(args.out, [result[name] for name in sorted(result)])
        print(f"[extract {number}/{len(manifest)}] {key}", flush=True)
    if set(existing) - set(result):
        raise ValueError("output contains old sources absent from current manifest; use a new output path")


def command_probe(args) -> None:
    records = _records(args.features)
    if args.out.exists():
        resumed = _records(args.out)
        if set(resumed) != set(records):
            raise ValueError("probe output source keys differ from input; choose a new output")
        for key in records:
            original, previous = records[key], resumed[key]
            if (original.get("file_fingerprint") != previous.get("file_fingerprint")
                    or [part.get("clip_path") for part in original["segments"]]
                    != [part.get("clip_path") for part in previous["segments"]]):
                raise ValueError(f"source or segment changed since probe cache: {key}")
            previous["metadata"] = original.get("metadata") or {}
            previous["rights"] = original.get("rights") or {}
            refresh_manifest_fields(previous, original)
        records = resumed
    selected = set(records)
    if args.only_reviewed:
        with args.only_reviewed.open(encoding="utf-8-sig", newline="") as stream:
            selected = {"iamd:" + row["identifier"] for row in csv.DictReader(stream)
                        if any((row.get(key) or "").strip() for key in
                               ("content_type", "audio_quality", "source_nature", "pool_suitability", "notes"))}
        if selected - set(records):
            raise ValueError("review CSV contains source absent from feature manifest")
    models = [name.strip() for name in args.models.split(",") if name.strip()]
    if not models or set(models) - {"ast", "clap", "aesthetics"}:
        raise ValueError("models must be a comma-separated subset of ast,clap,aesthetics")
    import torch

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    probe = OfflineProbes(args.cache_dir)
    attempted = 0
    for number, key in enumerate(sorted(selected), 1):
        record = records[key]
        for segment in record["segments"]:
            clip = Path(segment["clip_path"])
            if not clip.is_file():
                raise FileNotFoundError(f"clip absent for {key}: {clip}")
            for model in models:
                if not needs_probe(segment, model):
                    continue
                attempted += 1
                try:
                    result = getattr(probe, model)(clip)
                    segment[model if model != "aesthetics" else "aesthetics"] = result
                    segment.get("probe_errors", {}).pop(model, None)
                except (OSError, RuntimeError, ValueError, KeyError, ImportError) as error:
                    segment.setdefault("probe_errors", {})[model] = f"{type(error).__name__}: {error}"
                write_jsonl_atomic(args.out, [records[name] for name in sorted(records)])
        print(f"[probe {number}/{len(selected)}] {key}", flush=True)
    # Persist refreshed metadata/rights even when every model score came from
    # the existing probe cache and the inner loop performed no write.
    write_jsonl_atomic(args.out, [records[name] for name in sorted(records)])
    print(f"Attempted {attempted} missing segment-model scores; output {args.out}")


def command_score(args) -> None:
    records = _records(args.features)
    cfg = _config(args.config)
    scorer = {"v1": score_source, "v2": score_source_v2,
              "v21": score_source_v21}[args.policy]
    decisions = [scorer(records[key], cfg) for key in sorted(records)]
    for row in decisions:
        row["config_sha256"] = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    write_jsonl_atomic(args.out, decisions)
    counts = collections.Counter(row["decision"] for row in decisions)
    print(f"Scored {len(decisions)} sources: {dict(counts)}; output {args.out}")


def command_freeze_predictions(args) -> None:
    """Freeze a policy output and its exact feature/config provenance before annotation."""
    expected_versions = {"v2": "clean-music-v2", "v21": "clean-music-v2.1"}
    expected = expected_versions[args.policy]
    features = _records(args.features)
    decisions = _records(args.decisions)
    if set(features) != set(decisions):
        raise ValueError("feature and decision source keys differ; cannot freeze predictions")
    rows = [decisions[key] for key in sorted(decisions)]
    observed = {str(row.get("policy_version")) for row in rows}
    if observed != {expected}:
        raise ValueError(f"expected policy_version={expected!r}, found {sorted(observed)}")
    if args.config:
        cfg = _config(args.config)
        config_sha = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
        mismatched = [key for key, row in decisions.items()
                      if row.get("config_sha256") not in {None, config_sha}]
        if mismatched:
            raise ValueError(f"decision config hash differs from supplied config for {len(mismatched)} sources")
    else:
        config_sha = rows[0].get("config_sha256") if rows else None
    output_lines = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    decision_sha = _write_immutable(args.out, output_lines)
    feature_sha = _sha256_file(args.features)
    lock = {
        "schema_version": "curation-freeze-v1",
        "artifact_type": "predictions",
        "label": args.label or args.policy,
        "policy": args.policy,
        "policy_version": expected,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_count": len(rows),
        "source_key_sha256": _key_digest(features),
        "features_path": str(args.features),
        "features_sha256": feature_sha,
        "decisions_path": str(args.decisions),
        "decisions_sha256": _sha256_file(args.decisions),
        "frozen_predictions_sha256": decision_sha,
        "config_sha256": config_sha,
        "annotation_locked": True,
        "prediction_reveal_locked": True,
        "rights_not_approved": True,
    }
    lock_sha = _write_or_validate_lock(_lock_path(args.out), lock)
    print(f"Frozen {len(rows)} {args.policy} predictions: {args.out} ({decision_sha[:12]})")
    print(f"Lock: {_lock_path(args.out)} ({lock_sha[:12]})")


def command_prepare_blind_listen(args) -> None:
    """Freeze an opaque, source-disjoint listening order without exposing predictions."""
    manifest = list(read_jsonl(args.manifest))
    if not manifest:
        raise ValueError("blind manifest is empty")
    keys = [str(row.get("source_key") or "") for row in manifest]
    if any(not key for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("blind manifest must contain unique non-empty source_key values")
    forbidden = {"decision", "clean_score", "segments", "policy_version"}
    if any(forbidden & set(row) for row in manifest):
        raise ValueError("blind manifest contains prediction/audio feature fields")
    ordered_keys = sorted(keys, key=lambda key: hashlib.sha256(
        f"openrestor-blind-v1|{args.seed}|{key}".encode("utf-8")).hexdigest())
    rows = [{"blind_id": f"blind-{index:04d}", "blind_rank": index,
             "validation_id": next(row.get("validation_id") for row in manifest
                                    if row.get("source_key") == key),
             "source_key": key}
            for index, key in enumerate(ordered_keys, 1)]
    output_lines = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    order_sha = _write_immutable(args.out, output_lines)
    fields = ["blind_id", "content_type", "audio_quality", "source_nature", "capture_quality",
              "degradation_reason", "provenance", "pool_suitability", "scope",
              "source_level_label", "notes"]
    template_lines = [",".join(fields)] + [f'{row["blind_id"]},,,,,,,,,,' for row in rows]
    template = args.out.with_name(args.out.stem + "_annotations.csv")
    template_sha = _write_immutable(template, "\n".join(template_lines) + "\n")
    manifest_sha = _sha256_file(args.manifest)
    lock = {
        "schema_version": "curation-blind-order-v1",
        "artifact_type": "blind_listening_order",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "source_count": len(rows),
        "source_key_sha256": _key_digest(keys),
        "manifest_path": str(args.manifest),
        "manifest_sha256": manifest_sha,
        "order_sha256": order_sha,
        "annotation_template": str(template),
        "annotation_template_sha256": template_sha,
        "blind_metadata_hidden": True,
        "predictions_hidden": True,
        "prediction_reveal_locked": True,
        "audio_download_performed": False,
        "mapping_is_operator_only": True,
    }
    lock_sha = _write_or_validate_lock(_lock_path(args.out), lock)
    print(f"Prepared immutable blind order for {len(rows)} sources: {args.out}")
    print(f"Annotation template (blind IDs only): {template}")
    print(f"Lock: {_lock_path(args.out)} ({lock_sha[:12]})")


def command_evaluate_v2(args) -> None:
    """Compare v1/v2 and an acoustic-feature ablation on calibration/validation only."""
    records = _records(args.features)
    old_records = _records(args.features_without_enrichment) if args.features_without_enrichment else records
    reviews = import_iamd_reviews(args.reviews_csv, set(records))
    locked = {row["source_key"]: row["role"] for row in read_jsonl(args.locked_split)}
    split = {key: locked.get(key, "out_of_scope") for key in records}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cfg = _config(args.config)
    v1 = _records(args.v1_decisions)
    v2 = _records(args.v2_decisions)
    base_v2 = {key: score_source_v2(old_records[key], cfg) for key in records}
    approaches = {"curation_v1": v1, "curation_v2": v2, "v2_without_acoustic_enrichment": base_v2}
    if args.v21_decisions:
        approaches["curation_v2_1"] = _records(args.v21_decisions)
        approaches["v2_1_without_clap_guard"] = {
            key: score_source_v21(record, {**cfg, "v21_min_clap_degraded_margin": -1.0})
            for key, record in records.items()}
        approaches["v2_1_without_metadata_guard"] = {
            key: score_source_v21(record, {**cfg, "v21_enable_metadata_guard": 0.0})
            for key, record in records.items()}
        approaches["v2_1_without_acoustic_guards"] = {
            key: score_source_v21(record, {**cfg, "v21_enable_acoustic_guard": 0.0})
            for key, record in records.items()}
    by_role = {role: {name: evaluate_decisions(records, reviews, split, proposal, role)
                      for name, proposal in approaches.items()}
               for role in ("calibration", "validation")}
    report = {
        "policy": "v2 thresholds are selected from calibration only; prospective is excluded",
        "annotation_counts": dict(collections.Counter(review["human_class"] for review in reviews.values())),
        "split_counts": dict(collections.Counter(split.values())),
        "by_role": by_role,
        "ablation": {"v2_with_enriched_acoustics": "features input",
                     "v2_without_enriched_acoustics": "features_without_enrichment input"},
        "limitations": [
            "Les 50 prospectifs et les exemples hors cohorte ne servent pas au réglage.",
            "La validation interne provient d'annotations déjà consultées en agrégat et ne remplace pas une validation indépendante.",
            "Les labels portent souvent sur un extrait ; les cases vides ne sont pas des positifs.",
            "Aucun score acoustique ne vaut autorisation de redistribution.",
        ],
    }
    if args.v21_decisions:
        report["ablation"]["v2_1_without_clap_guard"] = "v21_min_clap_degraded_margin=-1"
        report["ablation"]["v2_1_without_metadata_guard"] = "v21_enable_metadata_guard=0"
        report["ablation"]["v2_1_without_acoustic_guards"] = "v21_enable_acoustic_guard=0"
    (args.out_dir / "evaluation_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                        encoding="utf-8")
    lines = ["# Curation clean v2 — comparaison ciblée", "",
             "Le réglage est limité à la calibration ; le prospectif reste hors évaluation v2.", "",
             "| Approche | Split | Acceptations binaires | Précision | Mauvaises acceptations | Bons rejets | Revue |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for role in ("calibration", "validation"):
        for name, result in by_role[role].items():
            fmt = lambda value: "n/a" if value is None else f"{value:.1%}"
            lines.append(f"| {name} | {role} | {result['auto_accept_binary_denominator']} | "
                         f"{fmt(result['auto_accept_precision_on_binary_labels'])} | "
                         f"{fmt(result['bad_clip_auto_accept_rate'])} | "
                         f"{fmt(result['good_clip_auto_reject_rate'])} | {fmt(result['manual_review_fraction'])} |")
    lines += ["", "## Interprétation", "",
              "Les acceptations d'avis incomplets sont rapportées séparément et ne sont pas des positifs.",
              "Les signaux acoustiques enrichis sont des proxies de capture ; ils bloquent l'acceptation automatique dans les cas à risque, sans exclure une esthétique électronique ou ambient.", "",
              "## Limites", "", *[f"- {item}" for item in report["limitations"]]]
    (args.out_dir / "evaluation_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    queue_decisions = _records(args.v21_decisions) if args.v21_decisions else v2
    candidates = []
    for key, review in reviews.items():
        role = split.get(key)
        if role not in {"calibration", "validation"}:
            continue
        decision = queue_decisions[key]
        if review["human_class"] != "unresolved" and decision["decision"] != "manual_review":
            continue
        score = decision.get("clean_score")
        reasons = decision.get("reasons") or []
        priority = (0 if review["human_class"] == "unresolved" else 1,
                    0 if "passage_disagreement" in reasons else 1,
                    abs((score if score is not None else .5) - cfg.get("v2_auto_accept_score", .76)))
        candidates.append((priority, {"source_key": key, "split_role": role,
                                      "primary_clip": records[key]["segments"][len(records[key]["segments"]) // 2]["clip_path"],
                                      "other_clips": [part["clip_path"] for part in records[key]["segments"]],
                                      "clean_score": score, "decision": decision["decision"],
                                      "reasons": reasons, "human_class": review["human_class"],
                                      "human_note": review.get("notes", ""),
                                      "reason": "active_learning_uncertainty_or_contradiction"}))
    write_jsonl_atomic(args.out_dir / "active_review_queue_v2.jsonl",
                       [row for _, row in sorted(candidates, key=lambda item: item[0])])
    suggestions = []
    for key, review in reviews.items():
        if review["human_class"] != "unresolved":
            continue
        note = (review.get("notes") or "").lower()
        suggested = {}
        evidence = []
        if "distant" in note or "remote" in note:
            suggested.update(capture_quality="distant_or_reverberant", degradation_reason="distance_reverb")
            evidence.append("explicit human note")
        if "ai generated" in note or "ai-generated" in note:
            suggested.update(source_nature="likely_midi_or_synthetic_render", provenance="needs_verification")
            evidence.append("explicit human note")
        if review.get("audio_quality") == "acceptable" and not review.get("content_type"):
            suggested["content_type"] = "music"
            evidence.append("audio_quality=acceptable; content still requires listening confirmation")
        suggestions.append({"source_key": key, "split_role": split.get(key),
                             "suggested_fields": suggested, "evidence": evidence,
                             "machine_decision": queue_decisions[key].get("decision"),
                             "machine_reasons": queue_decisions[key].get("reasons", []),
                             "human_class": review["human_class"],
                             "requires_human_confirmation": True,
                             "notes": review.get("notes", "")})
    write_jsonl_atomic(args.out_dir / "annotation_suggestions_v2.jsonl", suggestions)
    print(f"Wrote {args.out_dir / 'evaluation_v2.md'} and JSON")


def _independent_metrics(records: dict[str, dict], reviews: dict[str, dict],
                         decisions: dict[str, dict], *, level: str) -> dict:
    """Evaluate labels at their declared scope; primary labels never certify a source."""
    if level == "primary_passage":
        labels = {}
        proposals = {}
        for key, review in reviews.items():
            parts = records[key].get("segments") or []
            scored = decisions[key].get("segments") or []
            if len(parts) != len(scored):
                raise ValueError(f"segment count differs for {key}")
            index = len(parts) // 2
            if parts[index].get("segment_id") != scored[index].get("segment_id"):
                raise ValueError(f"segment order differs for {key}")
            labels[key] = review["human_class"]
            proposals[key] = scored[index]["decision"]
        caveat = "Labels concernent le passage principal annoté uniquement."
    elif level == "source_decision":
        labels = {key: review["human_class"] for key, review in reviews.items()}
        proposals = {key: decisions[key]["decision"] for key in reviews}
        caveat = ("Les labels restent des labels de passage principal : cette table ne valide "
                  "jamais automatiquement la source entière.")
    else:
        raise ValueError(f"unknown independent evaluation level: {level}")
    labelled = [key for key in labels if labels[key] != "unresolved"]
    positive = [key for key in labelled if labels[key] == "positive_clip_evidence"]
    negative = [key for key in labelled if labels[key] == "negative_clip_evidence"]
    accepted = [key for key in labelled if proposals[key] == "auto_accept"]
    correct_accept = [key for key in accepted if key in positive]
    bad_accept = [key for key in accepted if key in negative]
    good_reject = [key for key in positive if proposals[key] == "auto_reject"]
    reviewed = [key for key in labels if proposals[key] == "manual_review"]
    return {
        "level": level,
        "caveat": caveat,
        "annotated": len(labels),
        "binary_labelled": len(labelled),
        "positive_clip_evidence": len(positive),
        "negative_clip_evidence": len(negative),
        "unresolved": len(labels) - len(labelled),
        "decisions_all": dict(collections.Counter(proposals.values())),
        "decisions_binary_labelled": dict(collections.Counter(proposals[key] for key in labelled)),
        "auto_accept_precision": len(correct_accept) / len(accepted) if accepted else None,
        "auto_accept_precision_95pct_wilson": wilson(len(correct_accept), len(accepted)),
        "auto_accept_binary_denominator": len(accepted),
        "bad_clip_auto_accept_rate": len(bad_accept) / len(negative) if negative else None,
        "bad_clip_auto_accept_rate_95pct_wilson": wilson(len(bad_accept), len(negative)),
        "good_clip_auto_reject_rate": len(good_reject) / len(positive) if positive else None,
        "good_clip_auto_reject_rate_95pct_wilson": wilson(len(good_reject), len(positive)),
        "manual_review_fraction_all": len(reviewed) / len(labels) if labels else None,
        "manual_review_fraction_binary_labelled": len([key for key in labelled
                                                       if proposals[key] == "manual_review"]) / len(labelled)
        if labelled else None,
        "bad_auto_accept_keys": bad_accept,
        "good_auto_reject_keys": good_reject,
    }


def command_evaluate_independent(args) -> None:
    """Evaluate frozen policies on source-independent, blind human labels."""
    records = _records(args.features)
    reviews = _records(args.reviews)
    v2 = _decision_records(args.v2_decisions)
    v21 = _decision_records(args.v21_decisions)
    if set(records) != set(reviews) or set(records) != set(v2) or set(records) != set(v21):
        raise ValueError("independent features, reviews and decisions must have identical source keys")
    if any(review.get("human_class") not in {"positive_clip_evidence", "negative_clip_evidence", "unresolved"}
           for review in reviews.values()):
        raise ValueError("invalid human_class in independent reviews")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    approaches = {"v2": v2, "v21": v21}
    report = {
        "source_count": len(records),
        "annotation_class_counts": dict(collections.Counter(review["human_class"]
                                                             for review in reviews.values())),
        "unresolved_excluded_from_binary_metrics": True,
        "scope": "primary_clip_only",
        "approaches": {
            name: {"primary_passage": _independent_metrics(records, reviews, decisions,
                                                            level="primary_passage"),
                   "source_decision_control": _independent_metrics(records, reviews, decisions,
                                                                    level="source_decision")}
            for name, decisions in approaches.items()},
        "limitations": [
            "Les labels sont principalement des passages ; un bon passage ne valide pas la source entière.",
            "Les 7 avis unresolved restent hors des dénominateurs binaires.",
            "Les scores ne sont pas des autorisations de redistribution.",
            "Les politiques et prompts restent ceux gelés avant annotation.",
        ],
    }
    (args.out_dir / "independent_evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    def pct(value):
        return "n/a" if value is None else f"{value:.1%}"
    lines = ["# Évaluation indépendante de la curation clean", "",
             f"Sources : {len(records)} ; classes : {report['annotation_class_counts']}.",
             "Les 7 avis `unresolved` sont exclus des métriques binaires.", "",
             "## Passage principal annoté", "",
             "| Politique | Acceptations binaires | Précision | Mauvais acceptés | Bons rejetés | Revue (toutes sources) |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, values in report["approaches"].items():
        result = values["primary_passage"]
        lines.append(f"| {name} | {result['auto_accept_binary_denominator']} | "
                     f"{pct(result['auto_accept_precision'])} "
                     f"({result['auto_accept_precision_95pct_wilson']}) | "
                     f"{pct(result['bad_clip_auto_accept_rate'])} "
                     f"({result['bad_clip_auto_accept_rate_95pct_wilson']}) | "
                     f"{pct(result['good_clip_auto_reject_rate'])} "
                     f"({result['good_clip_auto_reject_rate_95pct_wilson']}) | "
                     f"{pct(result['manual_review_fraction_all'])} |")
    lines += ["", "## Décision source (contrôle conservateur)", "",
              "Cette table applique la décision source aux labels du passage principal ; "
              "elle ne constitue pas une validation de la source entière.", "",
              "| Politique | Acceptations binaires | Précision passage | Mauvais acceptés | Bons rejetés | Revue |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, values in report["approaches"].items():
        result = values["source_decision_control"]
        lines.append(f"| {name} | {result['auto_accept_binary_denominator']} | "
                     f"{pct(result['auto_accept_precision'])} | "
                     f"{pct(result['bad_clip_auto_accept_rate'])} | "
                     f"{pct(result['good_clip_auto_reject_rate'])} | "
                     f"{pct(result['manual_review_fraction_all'])} |")
    lines += ["", "## Limites", "", *[f"- {item}" for item in report["limitations"]]]
    (args.out_dir / "independent_evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.out_dir / 'independent_evaluation.md'} and JSON")


def _adjudication_corrections(value: dict) -> list[dict]:
    """Read the explicit correction list; nested legacy sections are not inferred."""
    corrections = value.get("corrections")
    if not isinstance(corrections, list) or not corrections:
        raise ValueError("adjudication must contain a non-empty corrections list")
    result = []
    for item in corrections:
        if not isinstance(item, dict) or not item.get("source_key") or not isinstance(item.get("fields"), dict):
            raise ValueError("each adjudication correction needs source_key and fields")
        fields = item["fields"]
        allowed = set(LABEL_FIELDS) | {"human_class", "rejection_reasons"}
        if set(fields) - allowed:
            raise ValueError(f"unsupported adjudication fields for {item['source_key']}: {set(fields) - allowed}")
        if fields.get("human_class") not in {"positive_clip_evidence", "negative_clip_evidence", "unresolved", None}:
            raise ValueError(f"invalid adjudicated human_class for {item['source_key']}")
        for field, choices in VALID_LABELS.items():
            if field in fields and fields[field] not in choices and fields[field] not in {None, ""}:
                raise ValueError(f"invalid adjudicated {field} for {item['source_key']}")
        result.append(item)
    if len({item["source_key"] for item in result}) != len(result):
        raise ValueError("duplicate source_key in adjudication corrections")
    return result


def command_apply_adjudication(args) -> None:
    """Create definitive annotations and an append-only-style correction history."""
    reviews = _records(args.reviews)
    adjudication_bytes = args.adjudication.read_bytes()
    adjudication = json.loads(adjudication_bytes)
    corrections = _adjudication_corrections(adjudication)
    definitive = {key: dict(row) for key, row in reviews.items()}
    history = []
    for correction in corrections:
        key = correction["source_key"]
        if key not in definitive:
            raise ValueError(f"adjudication references unknown review source: {key}")
        row = definitive[key]
        fields = correction["fields"]
        old_values = {field: row.get(field) for field in fields}
        row.update(fields)
        row["annotation_version"] = args.version
        history.append({"source_key": key, "fields": fields, "old_values": old_values,
                        "note": correction.get("note", ""),
                        "adjudication_sha256": hashlib.sha256(adjudication_bytes).hexdigest(),
                        "base_reviews_sha256": _sha256_file(args.reviews),
                        "version": args.version})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    definitive_content = "".join(json.dumps(definitive[key], ensure_ascii=False, sort_keys=True) + "\n"
                                    for key in sorted(definitive))
    definitive_sha = _write_immutable(args.out, definitive_content)
    history_content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                for row in history)
    history_sha = _write_immutable(args.history_out, history_content)
    _write_or_validate_lock(_lock_path(args.out), {
        "schema_version": "curation-annotation-freeze-v1",
        "artifact_type": "definitive_annotations",
        "version": args.version,
        "source_count": len(definitive),
        "correction_count": len(corrections),
        "base_reviews_sha256": _sha256_file(args.reviews),
        "adjudication_sha256": hashlib.sha256(adjudication_bytes).hexdigest(),
        "definitive_sha256": definitive_sha,
        "history_sha256": history_sha,
    })
    print(f"Applied {len(corrections)} explicit adjudications to {len(definitive)} annotations: {args.out}")


def command_export_judgments(args) -> None:
    """Export direct, explainable pipeline judgments for every source."""
    features = _records(args.features)
    decisions = _records(args.decisions)
    if set(features) != set(decisions):
        raise ValueError("feature and decision source keys differ")
    reviews = _records(args.reviews) if args.reviews else {}
    if set(reviews) - set(features):
        raise ValueError("review source keys are absent from features")
    rows = []
    for key in sorted(features):
        record, decision = features[key], decisions[key]
        metadata = record.get("metadata") or {}
        rights = decision.get("rights") or record.get("rights") or {}
        segments = []
        for segment, scored in zip(record.get("segments", []), decision.get("segments", []), strict=True):
            segments.append({"segment_id": segment.get("segment_id"),
                             "clean_score": scored.get("clean_score"),
                             "decision": scored.get("decision"),
                             "reasons": scored.get("reasons", [])})
        row = {"source_key": key, "dataset": record.get("dataset"),
               "source_id": record.get("source_id"), "title": metadata.get("title"),
               "creator": metadata.get("creator"), "genre": metadata.get("genre"),
               "asset_role": metadata.get("asset_role"),
               "pipeline_decision": decision.get("decision"),
               "pipeline_clean_score": decision.get("clean_score"),
               "pipeline_reasons": decision.get("reasons", []),
               "accepted_segment_ids": decision.get("accepted_segment_ids", []),
               "segments": segments,
               "rights": rights,
               "rights_status": (rights.get("status") or rights.get("rights_status") or
                                 rights.get("review_status")),
               "rights_provenance_candidate": rights.get(
                   "provenance_candidate", record.get("provenance_candidate")),
               "technical_candidate": record.get("technical_candidate"),
               "redistributable_candidate": record.get("redistributable_candidate")}
        if key in reviews:
            row["human_class"] = reviews[key].get("human_class")
            row["annotation_scope"] = reviews[key].get("scope")
        rows.append(row)
    write_jsonl_atomic(args.out, rows)
    print(f"Exported {len(rows)} explainable pipeline judgments: {args.out}")


def command_export_segments(args) -> None:
    """Export only v2.1-approved passages; mixed sources stay source-level manual."""
    records = _records(args.features)
    decisions = _records(args.decisions)
    if set(records) != set(decisions):
        raise ValueError("feature and decision source keys differ")
    rows = []
    for key in sorted(records):
        decision = decisions[key]
        for segment, segment_decision in zip(records[key]["segments"], decision.get("segments", []), strict=True):
            if segment_decision.get("decision") != "auto_accept":
                continue
            rows.append({"source_key": key, "dataset": records[key]["dataset"],
                         "source_id": records[key]["source_id"], "segment_id": segment["segment_id"],
                         "clip_path": segment["clip_path"], "start_s": segment["start_s"],
                         "duration_s": segment["duration_s"], "clean_score": segment_decision.get("clean_score"),
                         "source_level_decision": decision.get("decision"),
                         "partial_source": decision.get("decision") != "auto_accept",
                         "acoustic_candidate_only": True, "redistribution_approved": False,
                         "rights": records[key].get("rights") or {}})
    write_jsonl_atomic(args.out, rows)
    print(f"Exported {len(rows)} v2.1 segment candidates; no rights approval or audio copying")


def command_prepare_independent_validation(args) -> None:
    """Create a metadata-only, source-disjoint validation plan; never downloads audio."""
    import random

    items = list(read_jsonl(args.items))
    if len({row.get("identifier") for row in items}) != len(items):
        raise ValueError("items catalog must be deduplicated by identifier")
    pilot = {row["source_id"] for row in read_jsonl(args.exclude_features)}
    blind = set()
    blind_paths = args.blind_real_manifest or []
    if isinstance(blind_paths, Path):
        blind_paths = [blind_paths]
    for blind_path in blind_paths:
        if blind_path.exists():
            blind.update(str(row.get("internet_archive_identifier") or row.get("identifier"))
                         for row in read_jsonl(blind_path))
    catalog = {}
    if args.catalog and args.catalog.exists():
        for row in read_jsonl(args.catalog):
            identifier = row.get("identifier")
            if identifier and identifier not in catalog:
                catalog[identifier] = row
    original_files = {}
    if args.files and args.files.exists():
        for row in read_jsonl(args.files):
            if row.get("identifier") not in original_files and row.get("status") == "strict_original":
                original_files[row["identifier"]] = row
    candidates = []
    for row in items:
        identifier = row.get("identifier")
        if identifier in pilot or identifier in blind:
            continue
        if row.get("metadata_status") != "ok" or row.get("technical_candidate") is not True:
            continue
        if row.get("redistributable_candidate") is not True:
            continue
        extra = catalog.get(identifier) or {}
        collection_value = extra.get("collections") or row.get("collection") or "[unknown]"
        genres = extra.get("genres") or extra.get("tags") or row.get("genre") or "[unknown]"
        creators = extra.get("artists") or extra.get("creators") or row.get("creator") or "[unknown]"
        def first(value):
            if isinstance(value, list): value = value[0] if value else "[unknown]"
            text = str(value or "[unknown]").replace(",", ";")
            return text.split(";", 1)[0].strip() or "[unknown]"
        candidates.append({**row, "catalog_collection": first(collection_value),
                          "catalog_genre": first(genres), "catalog_creator": first(creators)})
    if len(candidates) < args.target:
        raise ValueError(f"only {len(candidates)} independent candidates remain; need {args.target}")
    rng = random.Random(args.seed)
    candidates.sort(key=lambda row: (row["catalog_collection"], row["catalog_genre"],
                                     row["catalog_creator"], row["identifier"]))
    # Round-robin over collection/genre/creator strata, with small caps to avoid
    # letting one prolific uploader dominate the blind validation set.
    groups = collections.defaultdict(list)
    for row in candidates:
        groups[(row["catalog_collection"], row["catalog_genre"], row["catalog_creator"])].append(row)
    for values in groups.values():
        rng.shuffle(values)
    ordered_groups = sorted(groups.values(), key=lambda values: (len(values), values[0]["identifier"]))
    chosen, used_creator, used_collection = [], collections.Counter(), collections.Counter()
    while len(chosen) < args.target and ordered_groups:
        progress = False
        for group in list(ordered_groups):
            if not group:
                ordered_groups.remove(group); continue
            row = group[0]
            creator, collection = row["catalog_creator"], row["catalog_collection"]
            if used_creator[creator] >= args.max_per_creator or used_collection[collection] >= args.max_per_collection:
                group.pop(0); progress = True; continue
            chosen.append(group.pop(0)); used_creator[creator] += 1; used_collection[collection] += 1; progress = True
            if len(chosen) >= args.target: break
        if not progress: break
    if len(chosen) < args.target:
        raise ValueError(f"stratification caps selected only {len(chosen)} of {args.target}; increase caps")
    chosen.sort(key=lambda row: row["identifier"])
    output = []
    for index, row in enumerate(chosen, 1):
        original = original_files.get(row["identifier"]) or {}
        output.append({"validation_id": f"iamd-independent-{index:03d}",
                       "dataset": "iamd", "source_id": row["identifier"],
                       "source_key": "iamd:" + row["identifier"],
                       "collection": row["catalog_collection"], "genre": row["catalog_genre"],
                       "creator": row["catalog_creator"], "title": row.get("title"),
                       "license_category": row.get("archive_licence_category"),
                       "license_url": row.get("archive_license_url"),
                       "format": original.get("format"), "original_file_name": original.get("name"),
                       "original_file_size_bytes": original.get("size_bytes"),
                       "original_duration_s": original.get("length_s"),
                       "audio_url": original.get("download_url"), "audio_required": True,
                       "source_disjoint_from_pilot": True,
                       "source_disjoint_from_blind_real": row["identifier"] not in blind,
                       "annotation_status": "unreviewed"})
    write_jsonl_atomic(args.out, output)
    template = args.out.with_name(args.out.stem + "_review_template.csv")
    fields = ["source_key", "content_type", "audio_quality", "source_nature", "capture_quality",
              "degradation_reason", "provenance", "pool_suitability", "scope", "source_level_label", "notes"]
    with template.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in output: writer.writerow({"source_key": row["source_key"]})
    report = args.out.with_suffix(".md")
    report.write_text("# Independent clean-curation validation plan\n\n"
                      f"Sources: {len(output)}. Audio downloaded: 0.\n\n"
                      "This manifest is source-disjoint from the pilot and Blind-Real. "
                      "It is metadata-only until an explicit audio-download decision.\n\n"
                      f"Collections: {dict(collections.Counter(row['collection'] for row in output))}\n\n"
                      f"Genres: {dict(collections.Counter(row['genre'] for row in output))}\n\n"
                      "After local clips exist, run `curation listen --blind --source-keys ...` and annotate the generated CSV.\n",
                      encoding="utf-8")
    print(f"Prepared {len(output)} independent metadata-only sources: {args.out}")


def _baseline(path: Path) -> dict[str, dict]:
    labels = {"accept_candidate": "auto_accept", "review": "manual_review",
              "reject_candidate": "auto_reject"}
    result = {}
    for row in read_jsonl(path):
        if row.get("pilot_batch") != "expand_200":
            continue
        key = "iamd:" + row["identifier"]
        result[key] = {"decision": labels[row["classification"]],
                       "reasons": row.get("reasons") or []}
    return result


def command_evaluate(args) -> None:
    records = _records(args.features)
    decisions = _records(args.decisions)
    baseline = _baseline(args.baseline)
    new = {key: record for key, record in records.items()
           if key.startswith("iamd:") and key in baseline}
    if len(new) != 150 or not set(new) <= set(decisions):
        raise ValueError("IAMD evaluation needs exactly 150 held-out sources and their decisions")
    reviews = import_iamd_reviews(args.reviews_csv, set(new))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    split = fixed_split(set(new), set(reviews), args.out_dir / "split_locked.jsonl")
    logistic = logistic_diagnostic(new, reviews, split)
    approaches = {"frozen_200_rule": baseline, "curation_v1": decisions}
    if logistic is not None:
        approaches["logistic_diagnostic"] = logistic
    by_role = {role: {name: evaluate_decisions(new, reviews, split, proposal, role)
                      for name, proposal in approaches.items()}
               for role in ("calibration", "validation", "prospective")}
    # Sweep only a single predeclared score cut on calibration; this is a
    # workload/precision diagnostic, not a second tuning pass on validation.
    config = _config(args.config)
    tradeoff = {}
    for cutoff in (.65, .70, .75, .78, .80, .85, .90):
        proposal = {key: score_source(record, {**config, "auto_accept_score": cutoff})
                    for key, record in new.items() if split[key] == "calibration"}
        tradeoff[f"{cutoff:.2f}"] = evaluate_decisions(new, reviews, split, proposal, "calibration")
    report = {
        "annotation_counts": dict(collections.Counter(review["human_class"] for review in reviews.values())),
        "split_counts": dict(collections.Counter(split.values())),
        "all_200_decisions": dict(collections.Counter(row["decision"] for row in decisions.values())),
        "decision_counts_by_split": {
            role: dict(collections.Counter(decisions[key]["decision"] for key in new if split[key] == role))
            for role in ("calibration", "validation", "prospective")},
        "calibration_distributions": distributions(new, reviews, split, "calibration"),
        "calibration_score_cut_sweep": tradeoff,
        "by_role": by_role,
        "limitations": ["Labels concernent surtout un extrait central, pas la source complète.",
                        "Les cases vides ne sont jamais des positifs.",
                        "Les 100 avis ont déjà été inspectés en agrégat : la validation interne n'est pas une étude prospective intacte.",
                        "Les 50 sources encore sans avis sont gelées comme validation prospective.",
                        "Les droits et la provenance restent distincts des décisions acoustiques."],
    }
    (args.out_dir / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    write_jsonl_atomic(args.out_dir / "review_import.jsonl",
                       [reviews[key] for key in sorted(reviews)])
    lines = ["# Curation clean v1 — évaluation sur le pilot IAMD", "",
             f"Avis explicites : {len(reviews)}/150 ; classes humaines : {report['annotation_counts']}.",
             f"Séparation figée par `source_id` : {report['split_counts']}.",
             f"Décisions sur les 200 sources : {report['all_200_decisions']}.",
             f"Décisions par split des 150 sources : {report['decision_counts_by_split']}.",
             "Les résultats de calibration servent au réglage ; la validation interne est rapportée séparément.", "",
             "| Approche | Split | Positifs / négatifs | Acceptés automatiques (étiquetés) | Précision accept. | Mauvais acceptés | Bons rejetés | Revue humaine |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for role in ("calibration", "validation"):
        for name, result in by_role[role].items():
            precision = result["auto_accept_precision_on_binary_labels"]
            prec = "n/a" if precision is None else f"{precision:.1%}"
            bad = result["bad_clip_auto_accept_rate"]
            good = result["good_clip_auto_reject_rate"]
            review = result["manual_review_fraction"]
            lines.append(f"| {name} | {role} | {result['positive_clip_evidence']} / {result['negative_clip_evidence']} | "
                         f"{result['auto_accept_binary_denominator']} | {prec} | "
                         f"{'n/a' if bad is None else f'{bad:.1%}'} | "
                         f"{'n/a' if good is None else f'{good:.1%}'} | "
                         f"{'n/a' if review is None else f'{review:.1%}'} |")
    lines.extend(["", "Précision = bons clips parmi les acceptations avec étiquette binaire. "
                  "Les acceptations d'avis incomplets sont comptées séparément dans le JSON.",
                  "Intervalles de Wilson à 95 % et erreurs par genre, collection et contenu : voir `evaluation.json`.",
                  "Aucune acceptation acoustique n'est une autorisation de redistribution.", "",
                  "## Distributions sur calibration uniquement", "",
                  "| Signal (extrait central) | Positif médiane [q10, q90] | Négatif médiane [q10, q90] |",
                  "| --- | ---: | ---: |"])
    positive = report["calibration_distributions"]["positive_clip_evidence"]["metrics"]
    negative = report["calibration_distributions"]["negative_clip_evidence"]["metrics"]
    for metric in sorted(positive.keys() | negative.keys()):
        def fmt(values):
            item = values.get(metric)
            return "n/a" if item is None else f"{item['median']:.3g} [{item['q10']:.3g}, {item['q90']:.3g}]"
        lines.append(f"| {metric} | {fmt(positive)} | {fmt(negative)} |")
    lines.extend(["", "Classement univarié sur calibration (AUC si le score augmente avec les clips jugés bons ; "
                  "0,5 = aucun tri), descriptif uniquement :", "",
                  "| Signal | AUC | n+ / n− |", "| --- | ---: | ---: |"])
    for metric, ranking in sorted(report["calibration_distributions"]["univariate_ranking"].items(),
                                  key=lambda item: abs(item[1]["auc_positive_higher"] - .5), reverse=True):
        lines.append(f"| {metric} | {ranking['auc_positive_higher']:.3f} | "
                     f"{ranking['positive_n']} / {ranking['negative_n']} |")
    lines.extend(["", "## Limites", "", *[f"- {value}" for value in report["limitations"]]])
    (args.out_dir / "evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Prioritize already heard but unresolved clips; keep prospective sources untouched.
    unresolved = [key for key in reviews if reviews[key]["human_class"] == "unresolved"]
    queue = sorted(unresolved, key=lambda key: (decisions[key]["decision"] != "auto_accept",
                                               abs((decisions[key].get("clean_score") or .5) - .78)))
    write_jsonl_atomic(args.out_dir / "active_review_queue.jsonl", [
        {"source_key": key, "primary_clip": new[key]["segments"][len(new[key]["segments"]) // 2]["clip_path"],
         "clean_score": decisions[key].get("clean_score"), "decision": decisions[key]["decision"],
         "human_note": reviews[key]["notes"], "reason": "incomplete_or_ambiguous_human_label"}
        for key in queue])
    write_jsonl_atomic(args.out_dir / "prospective_blind_queue.jsonl", [
        {"source_key": key,
         "primary_clip": new[key]["segments"][len(new[key]["segments"]) // 2]["clip_path"],
         "other_clips": [part["clip_path"] for part in new[key]["segments"]
                         if part is not new[key]["segments"][len(new[key]["segments"]) // 2]],
         "split_role": "prospective", "annotation_scope": "primary_clip_only"}
        for key in sorted(new) if split[key] == "prospective"])
    print(f"Wrote {args.out_dir / 'evaluation.md'} and JSON; {len(queue)} unresolved clips in review queue")


def command_evaluate_prospective(args) -> None:
    """Evaluate a generic prospective CSV without tuning the frozen policy."""
    records = _records(args.features)
    decisions = _records(args.decisions)
    if set(records) != set(decisions):
        raise ValueError("feature and decision source keys differ")
    reviews = import_reviews(args.reviews_csv, set(records))
    locked = {row["source_key"]: row["role"] for row in read_jsonl(args.locked_split)}
    if set(locked) - set(records):
        raise ValueError("locked split contains a source absent from features")
    # The locked file covers the 150-source annotation cohort. The original
    # smoke-50 sources are outside this prospective experiment, not silently
    # part of its denominator.
    split = {key: locked.get(key, "out_of_scope") for key in records}
    if any(split[key] != "prospective" for key in reviews):
        raise ValueError("prospective CSV contains a source already assigned to calibration/validation")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl_atomic(args.out_dir / "split_all_200_locked.jsonl",
                       [{"source_key": key, "role": split[key], "seed": "curation-v1+prospective"}
                        for key in sorted(split)])
    result = evaluate_decisions(records, reviews, split, decisions, "prospective")
    counts = collections.Counter(review["human_class"] for review in reviews.values())
    report = {"annotation_counts": dict(counts), "split_counts": dict(collections.Counter(split.values())),
              "decision_counts": dict(collections.Counter(decisions[key]["decision"] for key in reviews)),
              "evaluation": result,
              "policy": "decisions_v1.jsonl was generated before these annotations and was not retuned",
              "limitations": ["Labels concernent des extraits et non nécessairement toute la source.",
                              "Les avis incomplets ne sont pas des positifs.",
                              "Les droits/provenance ne sont pas évalués par ce rapport."]}
    (args.out_dir / "prospective_evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Évaluation prospective IAMD — 50 annotations", "",
             f"Annotations importées : {len(reviews)} ; classes : {dict(counts)}.",
             f"Décisions v1 sur ces sources : {report['decision_counts']}.", "",
             "| Mesure | Résultat |", "| --- | ---: |",
             f"| Acceptations automatiques avec label binaire | {result['auto_accept_binary_denominator']} |",
             f"| Précision des acceptations automatiques | {result['auto_accept_precision_on_binary_labels'] if result['auto_accept_precision_on_binary_labels'] is not None else 'n/a'} |",
             f"| Mauvais audios acceptés | {result['bad_clip_auto_accept_rate'] if result['bad_clip_auto_accept_rate'] is not None else 'n/a'} |",
             f"| Bons audios rejetés | {result['good_clip_auto_reject_rate'] if result['good_clip_auto_reject_rate'] is not None else 'n/a'} |",
             f"| Revue humaine | {result['manual_review_fraction'] if result['manual_review_fraction'] is not None else 'n/a'} |",
             f"| Avis incomplets acceptés automatiquement | {result['unresolved_auto_accepted']} |", "",
             "## Erreurs", "",
             f"Mauvaises acceptations : `{', '.join(result['bad_auto_accept_keys']) or 'aucune'}`.",
             f"Bons rejets : `{', '.join(result['good_auto_reject_keys']) or 'aucun'}`.", "",
             "Les détails par genre, collection, créateur, type de contenu et les intervalles de Wilson sont dans `prospective_evaluation.json`.",
             "Ces résultats mesurent la règle v1 figée ; aucun seuil n'a été ajusté sur ces 50 sources.", "",
             *[f"- {item}" for item in report["limitations"]]]
    (args.out_dir / "prospective_evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.out_dir / 'prospective_evaluation.md'} and JSON")


def command_export(args) -> None:
    records = _records(args.features)
    decisions = _records(args.decisions)
    if set(records) != set(decisions):
        raise ValueError("feature and decision source keys differ")
    candidates = []
    for key in sorted(records):
        decision = decisions[key]
        if decision["decision"] != "auto_accept":
            continue
        for segment, segment_decision in zip(records[key]["segments"], decision["segments"], strict=True):
            if segment_decision["decision"] != "auto_accept":
                raise ValueError(f"source accepted with nonaccepted segment: {key}")
            candidates.append({"source_key": key, "dataset": records[key]["dataset"],
                               "source_id": records[key]["source_id"],
                               "segment_id": segment["segment_id"], "clip_path": segment["clip_path"],
                               "start_s": segment["start_s"], "duration_s": segment["duration_s"],
                               "clean_score": segment_decision["clean_score"],
                               "acoustic_candidate_only": True,
                               "redistribution_approved": False,
                               "rights": records[key].get("rights") or {}})
    write_jsonl_atomic(args.out, candidates)
    print(f"Exported {len(candidates)} local acoustic candidate clips; no rights approval or audio copying")


def command_import_reviews(args) -> None:
    records = _records(args.features)
    reviews = import_reviews(args.csv, set(records))
    write_jsonl_atomic(args.out, [reviews[key] for key in sorted(reviews)])
    print(f"Imported {len(reviews)} sparse human reviews into {args.out}")


def command_import_blind_reviews(args) -> None:
    records = _records(args.features)
    reviews = import_blind_reviews(args.csv, args.order, set(records))
    write_jsonl_atomic(args.out, [reviews[key] for key in sorted(reviews)])
    print(f"Imported {len(reviews)} sparse blind human reviews into {args.out}")


def command_listen(args) -> None:
    records = _records(args.features)
    order_rows = None
    order_path = getattr(args, "order_file", None)
    if order_path:
        if not args.blind:
            raise ValueError("--order-file requires --blind")
        order_rows = list(read_jsonl(order_path))
        if not order_rows or len({row.get("source_key") for row in order_rows}) != len(order_rows):
            raise ValueError("blind order must contain unique source_key values")
        if any(not row.get("blind_id") or not row.get("blind_rank") for row in order_rows):
            raise ValueError("blind order must contain blind_id and blind_rank")
    if args.source_keys:
        selected = {row["source_key"] for row in read_jsonl(args.source_keys)}
        if selected - set(records):
            raise ValueError("listening selection contains unknown source_key")
        records = {key: records[key] for key in sorted(selected)}
    if order_rows is not None:
        order_keys = {row["source_key"] for row in order_rows}
        if order_keys != set(records):
            raise ValueError("blind order and feature selection contain different source keys")
    decisions = _records(args.decisions) if args.decisions else {}
    cards = []
    if order_rows is not None:
        order_rows = sorted(order_rows, key=lambda row: int(row["blind_rank"]))
        ordered = [row["source_key"] for row in order_rows]
        opaque_ids = {row["source_key"]: row["blind_id"] for row in order_rows}
    else:
        ordered = (sorted(records, key=lambda key: hashlib.sha256(("curation-v1-blind|" + key).encode()).hexdigest())
                   if args.blind else sorted(records))
        opaque_ids = {key: f"blind-{index:04d}" for index, key in enumerate(ordered, 1)}
    for index, key in enumerate(ordered, 1):
        record = records[key]
        clips = []
        for segment in record["segments"]:
            relative = os.path.relpath(segment["clip_path"], args.out.parent)
            clips.append(f'<audio controls preload="none" src="{html.escape(relative, quote=True)}"></audio>')
        metadata = record.get("metadata") or {}
        hint = decisions.get(key, {}).get("decision", "") if args.show_predictions and not args.blind else ""
        display_name = f"Source {index}" if args.blind else key
        card_id = opaque_ids[key] if args.blind else key
        metadata_html = "" if args.blind else (
            f'<details><summary>Métadonnées</summary>{html.escape(str(metadata.get("title") or ""))} '
            f'· {html.escape(str(metadata.get("creator") or ""))} · '
            f'{html.escape(str(metadata.get("genre") or ""))}</details>')
        cards.append(f'<section class="card" data-id="{html.escape(card_id, quote=True)}">'
                     f'<h2>{index}/{len(records)} · {html.escape(display_name)}</h2>{clips[len(clips)//2]}'
                     f'<details><summary>Autres passages</summary>{"".join(clips[:len(clips)//2] + clips[len(clips)//2+1:])}</details>'
                     + metadata_html
                     + f'<small>{html.escape(hint)}</small>'
                     + ''.join(f'<label>{label}<select name="{field}"><option value=""></option>'
                               + ''.join(f'<option value="{value}">{value}</option>' for value in options)
                               + '</select></label>' for field, label, options in (
                                   ("content_type", "Contenu", ("music", "speech_dominant", "noise_or_sound_effect", "ambiguous")),
                                   ("audio_quality", "Qualité", ("acceptable", "degraded", "ambiguous")),
                                   ("source_nature", "Nature", ("likely_real_recording", "likely_midi_or_synthetic_render", "ambiguous")),
                                   ("capture_quality", "Capture", ("clean", "distant_or_reverberant", "noisy_or_hissy", "distorted_or_clipped", "bandwidth_limited", "ambiguous")),
                                   ("degradation_reason", "Dégradation", ("distance_reverb", "background_noise", "hiss_hum", "clipping_distortion", "bandwidth_cutoff", "speech_or_nonmusic", "synthetic_or_midi", "other", "ambiguous")),
                                   ("provenance", "Provenance", ("unreviewed", "plausible", "needs_verification", "blocked", "ambiguous")),
                                   ("pool_suitability", "Adéquation", ("suitable", "unsuitable_style", "ambiguous")),
                                   ("scope", "Portée de l'écoute", ("primary_clip_only", "all_sampled_passages")),
                                   ("source_level_label", "Source après plusieurs passages", ("suitable", "unsuitable", "ambiguous"))))
                     + '<label>Notes<input name="notes"></label></section>')
    export_key = "blind_id" if args.blind else "source_key"
    storage_prefix = "openrestor-curation-blind-" if args.blind else "openrestor-curation-v1-"
    markup = '''<!doctype html><html lang="fr"><meta charset="utf-8"><title>OpenRestor clean curation</title>
<style>body{font:15px system-ui;max-width:900px;margin:auto;padding:1rem}.card{padding:1rem;margin:1rem 0;border:1px solid #ccc}audio{display:block;margin:.5rem 0}label{display:inline-block;margin:.5rem}select{display:block}header{position:sticky;top:0;background:white}</style>
<header><h1>Écoute clean</h1><p>Étiquettes du clip central ; les autres passages ne valident la source que s'ils sont écoutés.</p><button id="export">Exporter CSV</button> <span id="count"></span></header>'''+''.join(cards)+'''<script>
const cards=[...document.querySelectorAll('.card')],key='__STORAGE_PREFIX__'+location.pathname;
let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
function update(){let n=0;for(const card of cards){const v=saved[card.dataset.id]||{};for(const input of card.querySelectorAll('select,input'))if(v[input.name]!==undefined)input.value=v[input.name];if(['content_type','audio_quality','source_nature','capture_quality','degradation_reason','provenance','pool_suitability','source_level_label','notes'].some(k=>v[k]))n++}document.getElementById('count').textContent=n+'/'+cards.length}
for(const card of cards)for(const input of card.querySelectorAll('select,input'))input.addEventListener('change',()=>{const id=card.dataset.id;saved[id]??={};saved[id][input.name]=input.value;localStorage.setItem(key,JSON.stringify(saved));update()});update();
document.getElementById('export').onclick=()=>{const fields=['__EXPORT_KEY__','content_type','audio_quality','source_nature','capture_quality','degradation_reason','provenance','pool_suitability','scope','source_level_label','notes'];const quote=x=>'"'+String(x??'').replaceAll('"','""')+'"';const lines=[fields.map(quote).join(',')];for(const card of cards){const v=saved[card.dataset.id]||{};lines.push(fields.map(k=>quote(k==='__EXPORT_KEY__'?card.dataset.id:v[k])).join(','))}const blob=new Blob([lines.join('\\r\\n')+'\\r\\n'],{type:'text/csv'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='curation_reviews.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
</script></html>'''
    markup = markup.replace("__STORAGE_PREFIX__", storage_prefix).replace("__EXPORT_KEY__", export_key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markup, encoding="utf-8")
    print(f"Wrote {args.out}")


def command_prepare_error_listen(args) -> None:
    """Prepare an explicit listening page for frozen prediction errors."""
    features = _records(args.features)
    decisions = _records(args.decisions)
    reviews = _records(args.reviews)
    if set(features) != set(decisions):
        raise ValueError("feature and decision source keys differ")
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    try:
        bucket = evaluation["approaches"][args.policy][args.level]
        bad = set(bucket["bad_auto_accept_keys"])
        good = set(bucket["good_auto_reject_keys"])
    except (KeyError, TypeError) as error:
        raise ValueError("evaluation JSON does not contain the requested error lists") from error
    selected = sorted(bad | good)
    if set(selected) - set(features):
        missing = sorted(set(selected) - set(features))
        raise ValueError(f"evaluation references missing feature sources: {missing}")
    rows = []
    for key in selected:
        category = "bad_auto_accept" if key in bad else "good_auto_reject"
        rows.append({"source_key": key, "review_category": category,
                     "policy": args.policy, "evaluation_level": args.level})
    if args.selection_out:
        write_jsonl_atomic(args.selection_out, rows)

    cards = []
    for index, row in enumerate(rows, 1):
        key = row["source_key"]
        record = features[key]
        decision = decisions[key]
        review = reviews.get(key, {})
        metadata = record.get("metadata") or {}
        category_label = "Mauvais accepté" if row["review_category"] == "bad_auto_accept" else "Bon rejeté"
        clips = []
        for segment in record.get("segments", []):
            clip = Path(str(segment.get("clip_path") or ""))
            relative = os.path.relpath(clip, args.out.parent)
            segment_decision = next((item for item in decision.get("segments", [])
                                     if item.get("segment_id") == segment.get("segment_id")), {})
            clips.append(
                f'<div class="passage"><b>{html.escape(str(segment.get("segment_id", "")))}</b> '
                f'<audio controls preload="none" src="{html.escape(relative, quote=True)}"></audio>'
                f'<small>score={html.escape(str(segment_decision.get("clean_score", "n/a")))}; '
                f'décision={html.escape(str(segment_decision.get("decision", "n/a")))}; '
                f'motifs={html.escape(", ".join(segment_decision.get("reasons", [])) or "-")}</small></div>')
        cards.append(
            f'<section class="card {html.escape(row["review_category"])}">'
            f'<h2>{index}/{len(rows)} · {category_label}</h2>'
            f'<p><code>{html.escape(key)}</code></p>'
            f'<p><b>Décision source :</b> {html.escape(str(decision.get("decision", "")))} · '
            f'<b>score source :</b> {html.escape(str(decision.get("clean_score", "n/a")))} · '
            f'<b>motifs :</b> {html.escape(", ".join(decision.get("reasons", [])) or "-")}</p>'
            f'<p><b>Titre :</b> {html.escape(str(metadata.get("title") or "-"))} · '
            f'<b>Créateur :</b> {html.escape(str(metadata.get("creator") or "-"))} · '
            f'<b>Genre :</b> {html.escape(str(metadata.get("genre") or "-"))}</p>'
            f'<p><b>Annotation humaine du passage principal :</b> '
            f'{html.escape(str(review.get("human_class") or "-"))} · '
            f'contenu={html.escape(str(review.get("content_type") or "-"))} · '
            f'qualité={html.escape(str(review.get("audio_quality") or "-"))}</p>'
            + "".join(clips) + '</section>')
    markup = ('<!doctype html><html lang="fr"><meta charset="utf-8">'
              '<title>OpenRestor — erreurs de curation</title>'
              '<style>body{font:15px system-ui;max-width:1050px;margin:auto;padding:1rem}'
              '.card{padding:1rem;margin:1rem 0;border:2px solid #aaa;border-radius:8px}'
              '.bad_auto_accept{border-color:#c44;background:#fff8f8}'
              '.good_auto_reject{border-color:#4a7;background:#f7fff9}'
              'audio{display:block;margin:.5rem 0}.passage{padding:.45rem 0;border-top:1px solid #ddd}'
              'code{user-select:all}</style><h1>Écoute ciblée des erreurs</h1>'
              f'<p>Politique <b>{html.escape(args.policy)}</b>, niveau <b>{html.escape(args.level)}</b>. '
              'Les annotations concernent le passage principal ; elles ne valident pas toute la source. '
              'Les 7 avis indéterminés restent hors de cette liste.</p>'
              + "".join(cards) + '</html>')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markup, encoding="utf-8")
    print(f"Wrote {args.out} ({len(rows)} sources)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    imported = sub.add_parser("import-iamd", help="Reuse the existing 200-source pilot features")
    imported.add_argument("--pilot-dir", type=Path, default=Path("build/iamd_feasibility/phase2_pilot"))
    imported.add_argument("--out", type=Path, required=True)
    imported.set_defaults(action=command_import_iamd)
    enrich = sub.add_parser("enrich-acoustics", help="Recompute local no-reference acoustic v2 descriptors")
    enrich.add_argument("--features", type=Path, required=True)
    enrich.add_argument("--out", type=Path, required=True)
    enrich.add_argument("--recompute", action="store_true")
    enrich.add_argument("--offset", type=int, default=0)
    enrich.add_argument("--limit", type=int)
    enrich.set_defaults(action=command_enrich_acoustics)
    extract = sub.add_parser("extract", help="Extract local lossless audio with resumable cache")
    extract.add_argument("--manifest", type=Path, required=True)
    extract.add_argument("--out", type=Path, required=True)
    extract.add_argument("--clips-dir", type=Path, required=True)
    extract.add_argument("--segment-seconds", type=float, default=24.0)
    extract.set_defaults(action=command_extract)
    probe = sub.add_parser("probe", help="Add optional cached model scores offline")
    probe.add_argument("--features", type=Path, required=True)
    probe.add_argument("--out", type=Path, required=True)
    probe.add_argument("--models", default="ast,clap,aesthetics")
    probe.add_argument("--cache-dir", type=Path, default=Path("build/metric_tools/hf_cache"))
    probe.add_argument("--only-reviewed", type=Path)
    probe.set_defaults(action=command_probe)
    score = sub.add_parser("score", help="Make local acoustic/content decisions")
    score.add_argument("--features", type=Path, required=True)
    score.add_argument("--out", type=Path, required=True)
    score.add_argument("--config", type=Path)
    score.add_argument("--policy", choices=("v1", "v2", "v21"), default="v1")
    score.set_defaults(action=command_score)
    freeze = sub.add_parser("freeze-predictions",
                            help="Freeze policy predictions and provenance before annotation")
    freeze.add_argument("--features", type=Path, required=True)
    freeze.add_argument("--decisions", type=Path, required=True)
    freeze.add_argument("--policy", choices=("v2", "v21"), required=True)
    freeze.add_argument("--config", type=Path)
    freeze.add_argument("--label")
    freeze.add_argument("--out", type=Path, required=True)
    freeze.set_defaults(action=command_freeze_predictions)
    evaluate_v2 = sub.add_parser("evaluate-v2", help="Compare v1/v2 on calibration and internal validation")
    evaluate_v2.add_argument("--features", type=Path, required=True)
    evaluate_v2.add_argument("--features-without-enrichment", dest="features_without_enrichment", type=Path)
    evaluate_v2.add_argument("--v1-decisions", type=Path, required=True)
    evaluate_v2.add_argument("--v2-decisions", type=Path, required=True)
    evaluate_v2.add_argument("--v21-decisions", type=Path,
                             help="Optional frozen v2.1 decisions to include in the comparison")
    evaluate_v2.add_argument("--reviews-csv", type=Path, required=True)
    evaluate_v2.add_argument("--locked-split", type=Path, required=True)
    evaluate_v2.add_argument("--config", type=Path)
    evaluate_v2.add_argument("--out-dir", type=Path, required=True)
    evaluate_v2.set_defaults(action=command_evaluate_v2)
    independent_eval = sub.add_parser("evaluate-independent",
                                      help="Evaluate frozen policies on independent blind annotations")
    independent_eval.add_argument("--features", type=Path, required=True)
    independent_eval.add_argument("--reviews", type=Path, required=True)
    independent_eval.add_argument("--v2-decisions", type=Path, required=True)
    independent_eval.add_argument("--v21-decisions", type=Path, required=True)
    independent_eval.add_argument("--out-dir", type=Path, required=True)
    independent_eval.set_defaults(action=command_evaluate_independent)
    segments = sub.add_parser("export-segments", help="Export only v2.1-approved segment candidates")
    segments.add_argument("--features", type=Path, required=True)
    segments.add_argument("--decisions", type=Path, required=True)
    segments.add_argument("--out", type=Path, required=True)
    segments.set_defaults(action=command_export_segments)
    independent = sub.add_parser("prepare-independent-validation",
                                  help="Prepare a source-disjoint metadata-only validation manifest")
    independent.add_argument("--items", type=Path, required=True)
    independent.add_argument("--catalog", type=Path)
    independent.add_argument("--files", type=Path,
                              help="Optional resolved original-file catalog; metadata only")
    independent.add_argument("--exclude-features", type=Path, required=True)
    independent.add_argument("--blind-real-manifest", type=Path, action="append")
    independent.add_argument("--out", type=Path, required=True)
    independent.add_argument("--target", type=int, default=120)
    independent.add_argument("--max-per-creator", type=int, default=3)
    independent.add_argument("--max-per-collection", type=int, default=35)
    independent.add_argument("--seed", type=int, default=20261027)
    independent.set_defaults(action=command_prepare_independent_validation)
    blind = sub.add_parser("prepare-blind-listen",
                           help="Freeze an opaque annotation order for a metadata-only validation plan")
    blind.add_argument("--manifest", type=Path, required=True)
    blind.add_argument("--out", type=Path, required=True)
    blind.add_argument("--seed", type=int, default=20261027)
    blind.set_defaults(action=command_prepare_blind_listen)
    evaluate = sub.add_parser("evaluate-iamd", help="Compare with frozen pilot on grouped reviews")
    evaluate.add_argument("--features", type=Path, required=True)
    evaluate.add_argument("--decisions", type=Path, required=True)
    evaluate.add_argument("--reviews-csv", type=Path, required=True)
    evaluate.add_argument("--baseline", type=Path, required=True)
    evaluate.add_argument("--config", type=Path)
    evaluate.add_argument("--out-dir", type=Path, required=True)
    evaluate.set_defaults(action=command_evaluate)
    prospective = sub.add_parser("evaluate-prospective", help="Evaluate a generic prospective review CSV")
    prospective.add_argument("--features", type=Path, required=True)
    prospective.add_argument("--decisions", type=Path, required=True)
    prospective.add_argument("--reviews-csv", type=Path, required=True)
    prospective.add_argument("--locked-split", type=Path, required=True)
    prospective.add_argument("--out-dir", type=Path, required=True)
    prospective.set_defaults(action=command_evaluate_prospective)
    exported = sub.add_parser("export", help="Write candidate clip manifest, never audio")
    exported.add_argument("--features", type=Path, required=True)
    exported.add_argument("--decisions", type=Path, required=True)
    exported.add_argument("--out", type=Path, required=True)
    exported.set_defaults(action=command_export)
    review_import = sub.add_parser("import-reviews", help="Import generic listener CSV with blank fields left unresolved")
    review_import.add_argument("--features", type=Path, required=True)
    review_import.add_argument("--csv", type=Path, required=True)
    review_import.add_argument("--out", type=Path, required=True)
    review_import.set_defaults(action=command_import_reviews)
    blind_review_import = sub.add_parser(
        "import-blind-reviews", help="Map opaque blind CSV labels through a frozen order file")
    blind_review_import.add_argument("--features", type=Path, required=True)
    blind_review_import.add_argument("--csv", type=Path, required=True)
    blind_review_import.add_argument("--order", type=Path, required=True)
    blind_review_import.add_argument("--out", type=Path, required=True)
    blind_review_import.set_defaults(action=command_import_blind_reviews)
    listen = sub.add_parser("listen", help="Make a simple local review HTML")
    listen.add_argument("--features", type=Path, required=True)
    listen.add_argument("--decisions", type=Path)
    listen.add_argument("--out", type=Path, required=True)
    listen.add_argument("--source-keys", type=Path,
                        help="JSONL queue/manifest with source_key, for a subset listening page")
    listen.add_argument("--order-file", type=Path,
                        help="Frozen blind order JSONL produced by prepare-blind-listen")
    listen.add_argument("--show-predictions", action="store_true")
    listen.add_argument("--blind", action="store_true", help="Hide visible identifiers and metadata; fixed random order")
    listen.set_defaults(action=command_listen)
    error_listen = sub.add_parser("prepare-error-listen",
                                  help="Prepare a listening page for frozen false accepts and good rejects")
    error_listen.add_argument("--features", type=Path, required=True)
    error_listen.add_argument("--decisions", type=Path, required=True)
    error_listen.add_argument("--reviews", type=Path, required=True)
    error_listen.add_argument("--evaluation", type=Path, required=True)
    error_listen.add_argument("--policy", choices=("v2", "v21"), default="v21")
    error_listen.add_argument("--level", choices=("primary_passage", "source_decision_control"),
                              default="source_decision_control")
    error_listen.add_argument("--selection-out", type=Path)
    error_listen.add_argument("--out", type=Path, required=True)
    error_listen.set_defaults(action=command_prepare_error_listen)
    adjudicate = sub.add_parser("apply-adjudication",
                                help="Create versioned definitive annotations from explicit corrections")
    adjudicate.add_argument("--reviews", type=Path, required=True)
    adjudicate.add_argument("--adjudication", type=Path, required=True)
    adjudicate.add_argument("--out", type=Path, required=True)
    adjudicate.add_argument("--history-out", type=Path, required=True)
    adjudicate.add_argument("--version", required=True)
    adjudicate.set_defaults(action=command_apply_adjudication)
    judgments = sub.add_parser("export-judgments",
                               help="Export explainable per-source pipeline judgments")
    judgments.add_argument("--features", type=Path, required=True)
    judgments.add_argument("--decisions", type=Path, required=True)
    judgments.add_argument("--reviews", type=Path)
    judgments.add_argument("--out", type=Path, required=True)
    judgments.set_defaults(action=command_export_judgments)
    args = parser.parse_args()
    args.action(args)


if __name__ == "__main__":
    main()
