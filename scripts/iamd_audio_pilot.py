#!/usr/bin/env python3
"""Bounded, private IAMD Phase 1b audio pilot. No benchmark writes.

Stages: plan, download, extract, score, annotate-import, report.
All mutable output is below build/iamd_feasibility/phase1b by default.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_iamd_lossless_feasibility import OUT as PHASE1  # noqa: E402

DEFAULT_OUT = PHASE1 / "phase1b"
ANNOTATION_CONTEXT = ["segment_id", "clip_path", "identifier", "name", "creator", "collection",
                      "start_s", "duration_s", "license_url"]
ANNOTATION_FIELDS = ["segment_id", "clean_quality", "content", "instruments", "use_global_eq",
                     "use_denoising", "use_brass", "use_drums", "defects", "rejection_reasons", "notes"]
QUALITY = {"acceptable", "degraded", "uncertain"}
CONTENT = {"recorded_instruments", "synthetic", "mixed", "noise_experimental", "other"}
UTILITY = {"yes", "no", "uncertain"}
GIB = 1024 ** 3


def rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_jsonl(path: Path, values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)


def digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def safe_name(name: str) -> bool:
    path = Path(name)
    return bool(name and not path.is_absolute() and len(path.parts) == 1 and name not in {".", ".."})


def population(phase1: Path, min_seconds: float = 40.0) -> list[dict]:
    items = {r["identifier"]: r for r in rows(phase1 / "items.jsonl")
             if r.get("redistributable_candidate") and r.get("provenance_candidate")}
    result = []
    for file in rows(phase1 / "files.jsonl"):
        item = items.get(file["identifier"])
        if not item or not file.get("redistributable_file_candidate"):
            continue
        if file.get("status") != "strict_original" or file.get("source") != "original" or file.get("private"):
            continue
        if file.get("format") not in {"WAV", "FLAC", "AIFF"} or not safe_name(file.get("name", "")):
            continue
        if not (file.get("sha1") or file.get("md5")) or not file.get("size_bytes"):
            continue
        duration = file.get("length_s")
        if duration is None or duration < min_seconds:
            continue
        result.append({"identifier": file["identifier"], "name": file["name"],
                       "format": file["format"], "source": file["source"],
                       "archive_format": file["archive_format"], "size_bytes": file["size_bytes"],
                       "length_s_metadata": duration, "sha1": file.get("sha1"), "md5": file.get("md5"),
                       "collection": item["collection"], "creator": item["creator"],
                       "genre": item["genre"], "tags": item.get("tags", []),
                       "title": item["title"], "license_url": item["archive_license_url"],
                       "archive_rights": item.get("archive_rights"),
                       "licence_status": item["licence_status"],
                       "download_url": "https://archive.org/download/{}/{}".format(
                           urllib.parse.quote(file["identifier"], safe=""),
                           urllib.parse.quote(file["name"], safe=""))})
    return sorted(result, key=lambda r: (r["collection"], r["identifier"], r["name"]))


def allocation(counts: dict[str, int], n: int, top_strata: int = 12) -> dict[str, int]:
    """Fixed, reproducible strata: top collections plus a pooled 'other'."""
    top = {name for name, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_strata]}
    strata = {name: counts[name] for name in top}
    other = sum(value for name, value in counts.items() if name not in top)
    if other:
        strata["[other collections]"] = other
    if n < len(strata):
        raise ValueError(f"sample size {n} smaller than {len(strata)} collection strata")
    allocated = {key: 1 for key in strata}
    while sum(allocated.values()) < n:
        # Priority by remaining square-root allocation; deterministic ties.
        key = max((key for key in strata if allocated[key] < strata[key]),
                  key=lambda k: (math.sqrt(strata[k]) / (allocated[k] + 1), k))
        allocated[key] += 1
    return allocated


def make_plan(phase1: Path, out: Path, count: int, seed: int, max_new_gib: float,
              passages: int, passage_seconds: float) -> dict:
    if count < 1 or count > 200 or passages not in {2, 3} or not 15 <= passage_seconds <= 20:
        raise ValueError("require 1..200 tracks, 2 or 3 passages, and 15..20 seconds")
    if not 0 < max_new_gib <= 10:
        raise ValueError("new-download cap must be >0 and <=10 GiB")
    if (out / "plan.json").exists():
        raise FileExistsError(f"Plan already exists at {out}; reuse it for resuming")
    pool = population(phase1, min_seconds=passage_seconds * passages + 2)
    if not pool:
        raise ValueError("no Phase 1 lossless candidates with sufficient declared duration")
    count = min(count, len(pool))
    collection_sizes = collections.Counter(row["collection"] for row in pool)
    top = {name for name, _ in sorted(collection_sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:12]}
    strata = collections.defaultdict(list)
    for row in pool:
        stratum = row["collection"] if row["collection"] in top else "[other collections]"
        strata[stratum].append(row)
    quotas = allocation(collection_sizes, count)
    rng = random.Random(seed)
    selected = []
    for stratum in sorted(strata):
        N, n = len(strata[stratum]), quotas[stratum]
        for row in rng.sample(strata[stratum], n):
            row = dict(row)
            row["stratum"] = stratum
            row["stratum_population_tracks"] = N
            row["stratum_sample_tracks"] = n
            row["selection_probability"] = n / N
            row["inverse_probability_weight"] = N / n
            row["track_id"] = hashlib.sha256((row["identifier"] + "\0" + row["name"]).encode()).hexdigest()[:16]
            row["audio_review_status"] = "audio_review_pending"
            selected.append(row)
    selected.sort(key=lambda r: (r["stratum"], r["identifier"], r["name"]))
    summary = json.loads((phase1 / "summary.json").read_text(encoding="utf-8"))
    plan = {"schema_version": 1, "seed": seed, "population_tracks": len(pool),
            "population_archive_items": len({r["identifier"] for r in pool}),
            "phase1_coverage": summary["funnel"], "sampling_unit": "Archive audio file (track)",
            "design": "SRSWOR within 12 largest collection strata and one pooled other stratum; fixed allocation; pi=n_h/N_h",
            "strata": {key: {"N": len(value), "n": quotas[key]} for key, value in sorted(strata.items())},
            "selected_tracks": len(selected), "selected_archive_items": len({r["identifier"] for r in selected}),
            "selected_creators": len({r["creator"] for r in selected}),
            "selected_collections": len({r["collection"] for r in selected}),
            "selected_metadata_bytes": sum(r["size_bytes"] for r in selected),
            "max_new_download_bytes": int(max_new_gib * GIB),
            "passages_per_track": passages, "passage_seconds": passage_seconds,
            "limitations": ["Population is resolved Phase 1 candidates only; no inference to unresolved items.",
                            "Minimum duration is required to fit non-overlapping passages.",
                            "Archive rights are assertions, not release approval.",
                            "Download failure or budget censoring creates nonresponse, not rejection."]}
    write_json(out / "plan.json", plan)
    write_jsonl(out / "tracks.jsonl", selected)
    return plan


def local_original(out: Path, row: dict) -> Path:
    return out / "originals" / row["track_id"] / row["name"]


def verified(path: Path, row: dict) -> bool:
    return (path.is_file() and path.stat().st_size == row["size_bytes"] and
            (digest(path, "sha1") == row["sha1"] if row.get("sha1") else digest(path, "md5") == row["md5"]))


def transfer(out: Path, row: dict, ledger: dict, cap: int, *, runner=subprocess.run) -> dict:
    target = local_original(out, row)
    status = {"track_id": row["track_id"], "identifier": row["identifier"], "name": row["name"]}
    if verified(target, row):
        return {**status, "status": "verified", "downloaded_new_bytes_this_run": 0}
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    ledger.setdefault("reserved_bytes", 0)
    if row["size_bytes"] > cap - ledger["new_bytes"] - ledger["reserved_bytes"]:
        return {**status, "status": "budget_deferred", "needed_bytes": row["size_bytes"]}
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > row["size_bytes"]:
            return {**status, "status": "error", "error": "partial larger than metadata size"}
        reservation = row["size_bytes"] - offset
        if reservation > cap - ledger["new_bytes"] - ledger["reserved_bytes"]:
            return {**status, "status": "budget_deferred", "needed_bytes": reservation}
        ledger["reserved_bytes"] += reservation
        write_json(out / "download_ledger.json", ledger)
        try:
            response = runner(["curl", "--location", "--fail", "--silent", "--show-error",
                               "--connect-timeout", "20", "--max-time", "180", "--retry", "0",
                               "--continue-at", "-", "--max-filesize", str(reservation),
                               "--user-agent", "OpenRestor-IAMD-audio-pilot/0.1",
                               "--write-out", "%{size_download}", "--output", str(partial),
                               row["download_url"]], capture_output=True, text=True, check=False)
            transferred = max(int(float(response.stdout.strip() or "0")),
                              max(0, partial.stat().st_size - offset) if partial.exists() else 0)
            if transferred < 0 or transferred > reservation:
                raise ValueError("curl transfer exceeded reservation")
            ledger["new_bytes"] += transferred
            ledger["reserved_bytes"] -= reservation
            write_json(out / "download_ledger.json", ledger)
            if response.returncode:
                raise RuntimeError(response.stderr.strip() or f"curl exit {response.returncode}")
            if verified(partial, row):
                os.replace(partial, target)
                return {**status, "status": "verified", "downloaded_new_bytes_cumulative": ledger["new_bytes"]}
            if partial.stat().st_size == row["size_bytes"]:
                return {**status, "status": "error", "error": "size correct but digest mismatch"}
            if ledger["new_bytes"] + ledger["reserved_bytes"] >= cap:
                return {**status, "status": "budget_deferred", "error": "cap reached during transfer"}
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            # If curl did not return parsable accounting, keep its preflight
            # reservation charged: conservative across crashes and exceptions.
            if attempt == 2:
                return {**status, "status": "error", "error": f"{type(error).__name__}: {error}"}
            time.sleep(min(2 ** attempt, 4))
    return {**status, "status": "error", "error": "incomplete after retries"}


def download(out: Path, limit: int | None = None) -> None:
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    tracks = list(rows(out / "tracks.jsonl"))
    ledger_path = out / "download_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {
        "new_bytes": sum(p.stat().st_size for p in (out / "originals").rglob("*.part")),
        "reserved_bytes": 0,
    }
    statuses = {r["track_id"]: r for r in rows(out / "download_status.jsonl")} if (out / "download_status.jsonl").exists() else {}
    cap = plan["max_new_download_bytes"]
    for index, row in enumerate(tracks[:limit] if limit else tracks, 1):
        result = transfer(out, row, ledger, cap)
        statuses[row["track_id"]] = result
        write_jsonl(out / "download_status.jsonl", [statuses[key] for key in sorted(statuses)])
        print(f"[{index}/{min(limit or len(tracks),len(tracks))}] {result['status']} {row['identifier']}/{row['name']} ; new={ledger['new_bytes'] / GIB:.3f} GiB", flush=True)


def passage_windows(duration: float, seconds: float, count: int) -> list[float]:
    if duration < count * seconds + 2:
        return []
    # First, middle, late; deterministic positions, no content-based cherry-picking.
    fractions = [0.1, 0.5, 0.9] if count == 3 else [0.2, 0.8]
    starts = [max(0.0, min(duration - seconds, duration * frac - seconds / 2)) for frac in fractions]
    if any(b < a + seconds for a, b in zip(starts, starts[1:])):
        starts = [(duration - seconds) * (i + 0.5) / count for i in range(count)]
    return starts


def extract(out: Path) -> None:
    import soundfile as sf
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    output = []
    failures = []
    for row in rows(out / "tracks.jsonl"):
        source = local_original(out, row)
        if not verified(source, row):
            continue
        try:
            with sf.SoundFile(source) as audio:
                duration = len(audio) / audio.samplerate
                starts = passage_windows(duration, plan["passage_seconds"], plan["passages_per_track"])
                if not starts:
                    raise ValueError("verified source too short for planned windows")
                for index, start in enumerate(starts, 1):
                    audio.seek(round(start * audio.samplerate))
                    samples = audio.read(round(plan["passage_seconds"] * audio.samplerate), dtype="float32", always_2d=True)
                    if len(samples) < 0.95 * plan["passage_seconds"] * audio.samplerate:
                        raise ValueError("short read during extraction")
                    segment_id = f"{row['track_id']}-p{index}"
                    path = out / "clips" / f"{segment_id}.flac"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not path.exists():
                        sf.write(path, samples, audio.samplerate, format="FLAC", subtype="PCM_24")
                    output.append({"segment_id": segment_id, "track_id": row["track_id"],
                                   "identifier": row["identifier"], "name": row["name"],
                                   "creator": row["creator"], "collection": row["collection"],
                                   "license_url": row["license_url"], "original_sha1": row["sha1"],
                                   "original_md5": row["md5"], "original_path": str(source),
                                   "clip_path": str(path), "clip_sha256": digest(path, "sha256"),
                                   "start_s": round(start, 4), "duration_s": len(samples) / audio.samplerate,
                                   "sample_rate": audio.samplerate, "channels": audio.channels,
                                   "audio_review_status": "audio_review_pending",
                                   "note": "Passage only; does not certify entire track."})
        except (OSError, RuntimeError, ValueError) as error:
            failures.append({"track_id": row["track_id"], "error": f"{type(error).__name__}: {error}"})
    write_jsonl(out / "segments.jsonl", output)
    write_jsonl(out / "extraction_errors.jsonl", failures)
    csv_path = out / "annotation_template.csv"
    if not csv_path.exists():
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=ANNOTATION_CONTEXT + ANNOTATION_FIELDS[1:])
            writer.writeheader()
            writer.writerows({key: r.get(key, "") for key in ANNOTATION_CONTEXT} for r in output)
    print(f"[extract] {len(output)} passages, {len(failures)} errors; {csv_path}")


def descriptors(path: Path) -> dict:
    import numpy as np
    import soundfile as sf
    from openrestor.metrics.blind_real import no_reference_descriptors
    with sf.SoundFile(path) as audio:
        data = audio.read(dtype="float32", always_2d=True)
        sr = audio.samplerate
    mono = data.mean(axis=1)
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
    silence = float(np.mean(np.abs(mono) < 0.001))
    analysis = no_reference_descriptors(data, sr)
    return {**analysis, "sample_rate": sr, "channels": data.shape[1],
            "duration_s": len(data) / sr, "peak_dbfs": 20 * math.log10(max(float(np.abs(data).max()), 1e-12)),
            "rms_dbfs": 20 * math.log10(max(rms, 1e-12)),
            "near_silent_sample_ratio": silence,
            "status": "measured_not_quality_verdict"}


def score(out: Path, with_pq: bool = False) -> None:
    segments = list(rows(out / "segments.jsonl"))
    prior = {r["segment_id"]: r for r in rows(out / "scores.jsonl")} if (out / "scores.jsonl").exists() else {}
    predictor = None
    if with_pq:
        try:
            os.environ.setdefault("HF_HOME", str(ROOT / "build/metric_tools/hf_cache"))
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from audiobox_aesthetics.infer import initialize_predictor
            predictor = initialize_predictor()
        except (ImportError, RuntimeError, OSError) as error:
            raise SystemExit(f"Audiobox PQ unavailable; install perceptual dependencies on GPU node: {error}") from error
    for segment in segments:
        sid = segment["segment_id"]
        if sid in prior and (not with_pq or prior[sid].get("audiobox_pq") is not None):
            continue
        path = Path(segment["clip_path"])
        try:
            row = {"segment_id": sid, "track_id": segment["track_id"], **descriptors(path),
                   "audiobox_pq": None, "audiobox_status": "not_run"}
            if predictor is not None:
                result = predictor.forward([{"path": str(path)}])[0]
                row["audiobox_pq"] = float(result["PQ"])
                row["audiobox_status"] = "measured_not_quality_verdict"
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            row = {"segment_id": sid, "track_id": segment["track_id"],
                   "status": "score_failed", "error": f"{type(error).__name__}: {error}",
                   "audiobox_pq": None, "audiobox_status": "failed" if with_pq else "not_run"}
        prior[sid] = row
        write_jsonl(out / "scores.jsonl", [prior[key] for key in sorted(prior)])
    print(f"[score] {len(prior)} passage descriptors; Audiobox PQ={'measured' if with_pq else 'not run'}")


def import_annotations(out: Path, csv_path: Path) -> None:
    known = {r["segment_id"] for r in rows(out / "segments.jsonl")}
    result = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(ANNOTATION_FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("annotation CSV lacks required fields")
        for line_number, row in enumerate(reader, 2):
            sid = row["segment_id"]
            if sid not in known or sid in result:
                raise ValueError(f"unknown or duplicate segment_id at line {line_number}: {sid}")
            quality = (row["clean_quality"] or "").strip().lower()
            if not quality:
                continue
            content = (row["content"] or "").strip().lower()
            if quality not in QUALITY or content not in CONTENT:
                raise ValueError(f"invalid quality/content at line {line_number}")
            for field in ("use_global_eq", "use_denoising", "use_brass", "use_drums"):
                row[field] = (row[field] or "").strip().lower()
                if row[field] not in UTILITY:
                    raise ValueError(f"{field} must be yes/no/uncertain at line {line_number}")
            result[sid] = {field: row[field] for field in ANNOTATION_FIELDS}
    write_jsonl(out / "annotations.jsonl", [result[key] for key in sorted(result)])
    print(f"[annotate-import] {len(result)}/{len(known)} annotated passages")


def weighted_yield(tracks: list[dict], segments: list[dict], annotations: dict[str, dict]) -> dict | None:
    if not segments or len(annotations) != len(segments):
        return None
    by_track = collections.defaultdict(list)
    for segment in segments:
        by_track[segment["track_id"]].append(segment)
    complete = [track for track in tracks if track["track_id"] in by_track]
    if len(complete) != len(tracks):
        return None
    outcomes = []
    for track in tracks:
        excerpts = by_track[track["track_id"]]
        x = sum(r["duration_s"] for r in excerpts)
        y = sum(r["duration_s"] for r in excerpts
                if annotations[r["segment_id"]]["clean_quality"] == "acceptable")
        outcomes.append({"stratum": track["stratum"], "x": x, "y": y,
                         "N": track["stratum_population_tracks"],
                         "n": track["stratum_sample_tracks"]})
    total_y = sum(r["y"] * r["N"] / r["n"] for r in outcomes)
    total_x = sum(r["x"] * r["N"] / r["n"] for r in outcomes)
    ratio = total_y / total_x if total_x else None
    # Stratified SRSWOR Taylor variance for ratio. Singleton strata cannot estimate variance.
    var = 0.0
    insufficient = []
    for stratum, group in collections.defaultdict(list, ((k, [r for r in outcomes if r["stratum"] == k])
                                                  for k in {r["stratum"] for r in outcomes})).items():
        N, n = group[0]["N"], len(group)
        if n == 1 and N > 1:
            insufficient.append(stratum)
            continue
        residuals = [r["y"] - ratio * r["x"] for r in group]
        if n > 1:
            mean = sum(residuals) / n
            var += N * N * (1 - n / N) * sum((r - mean) ** 2 for r in residuals) / (n * (n - 1))
    se = math.sqrt(max(var, 0)) / total_x if total_x else None
    return {"clean_acceptable_passage_duration_fraction": ratio,
            "approx_95pct_ci": [max(0, ratio - 1.96 * se), min(1, ratio + 1.96 * se)]
            if se is not None and not insufficient else None,
            "variance_unestimable_singleton_strata": insufficient,
            "observed_accepted_excerpt_hours": sum(r["y"] for r in outcomes) / 3600,
            "observed_excerpt_hours": sum(r["x"] for r in outcomes) / 3600,
            "estimated_population_accepted_passage_hours": total_y / 3600,
            "interpretation": "Passage duration at sampled positions only; NOT full-track usable hours."}


def report(out: Path) -> dict:
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    tracks = list(rows(out / "tracks.jsonl"))
    segments = list(rows(out / "segments.jsonl")) if (out / "segments.jsonl").exists() else []
    annotations = {r["segment_id"]: r for r in rows(out / "annotations.jsonl")} if (out / "annotations.jsonl").exists() else {}
    statuses = {r["track_id"]: r for r in rows(out / "download_status.jsonl")} if (out / "download_status.jsonl").exists() else {}
    ledger = json.loads((out / "download_ledger.json").read_text(encoding="utf-8")) if (out / "download_ledger.json").exists() else {"new_bytes": 0}
    score_rows = list(rows(out / "scores.jsonl")) if (out / "scores.jsonl").exists() else []
    verified_tracks = [r for r in tracks if verified(local_original(out, r), r)]
    reviewed_tracks = len({r["track_id"] for r in segments if r["segment_id"] in annotations})
    yield_ = weighted_yield(tracks, segments, annotations)
    content = collections.Counter(a["content"] for a in annotations.values())
    instruments = collections.Counter(name.strip().lower() for a in annotations.values()
                                      for name in a["instruments"].split(";") if name.strip())
    accepted_ids = {r["identifier"] for r in segments if r["segment_id"] in annotations and
                    annotations[r["segment_id"]]["clean_quality"] == "acceptable"}
    accepted_creators = collections.Counter(r["creator"] for r in tracks if r["identifier"] in accepted_ids)
    accepted_collections = collections.Counter(r["collection"] for r in tracks if r["identifier"] in accepted_ids)
    data = {"phase1_resolution": plan["phase1_coverage"], "population_tracks": plan["population_tracks"],
            "population_archive_items": plan["population_archive_items"],
            "selected_tracks": len(tracks), "selected_archive_items": len({r["identifier"] for r in tracks}),
            "verified_tracks": len(verified_tracks), "verified_archive_items": len({r["identifier"] for r in verified_tracks}),
            "download_statuses": dict(collections.Counter(r["status"] for r in statuses.values())),
            "new_bytes_downloaded": ledger["new_bytes"], "max_new_download_bytes": plan["max_new_download_bytes"],
            "segments": len(segments), "annotated_segments": len(annotations),
            "audio_review_pending_segments": max(0, len(segments) - len(annotations)),
            "tracks_with_any_review": reviewed_tracks,
            "audiobox_pq_measured_segments": sum(r.get("audiobox_pq") is not None for r in score_rows),
            "content_distribution_reviewed_passages": dict(content),
            "instrument_distribution_reviewed_passages": dict(instruments),
            "accepted_excerpt_item_collections": dict(accepted_collections),
            "accepted_excerpt_item_creators": dict(accepted_creators),
            "weighted_clean_passage_yield": yield_,
            "bytes_per_observed_accepted_excerpt_hour": ledger["new_bytes"] / yield_["observed_accepted_excerpt_hours"]
            if yield_ and yield_["observed_accepted_excerpt_hours"] else None,
            "audio_verdict": "pending_human_review",
            "notes": ["Lossless availability, audio quality and task relevance are distinct.",
                      "A passage does not validate an entire song.",
                      "Unresolved Phase 1 items and download nonresponse are not extrapolated.",
                      "Electronic, MIDI-like and brass-free material is not automatically rejected.",
                      "No audio is approved for public redistribution by this pilot."]}
    write_json(out / "report.json", data)
    md = ["# IAMD Phase 1b — qualification audio", "",
          f"Résolution Archive Phase 1 : {plan['phase1_coverage']['metadata_resolved']:,}/"
          f"{plan['phase1_coverage']['initial_candidates']:,} items, "
          f"{plan['phase1_coverage']['metadata_failed']:,} échecs.",
          f"Population d'inférence (résolue seulement) : {plan['population_tracks']:,} pistes / "
          f"{plan['population_archive_items']:,} items ; échantillon : {len(tracks)} pistes / "
          f"{data['selected_archive_items']} items, {plan['selected_collections']} collections, "
          f"{plan['selected_creators']} créateurs.",
          f"Originaux vérifiés : {len(verified_tracks)} pistes ; passages : {len(segments)} ; "
          f"annotés : {len(annotations)} ; en attente : {data['audio_review_pending_segments']}.",
          f"Nouveaux octets téléchargés : {ledger['new_bytes']:,} / {plan['max_new_download_bytes']:,} "
          f"({ledger['new_bytes']/GIB:.2f} Gio).", "",
          "Échantillonnage : 12 plus grandes collections + autres, tirage aléatoire simple sans remise "
          "dans chaque strate ; seed 42 par défaut. `tracks.jsonl` contient N, n et pi pour chaque piste.", "",
          "Les mesures automatiques ne sont que des indices pour prioriser l'écoute ; aucun seuil clean "
          "n'est appliqué. Audiobox PQ mesuré sur " + str(data["audiobox_pq_measured_segments"]) + " passages.", ""]
    if yield_:
        md += [f"Rendement pondéré des **passages aux positions échantillonnées** : "
               f"{100 * yield_['clean_acceptable_passage_duration_fraction']:.1f} %. "
               f"Durée acceptée observée : {yield_['observed_accepted_excerpt_hours']:.2f} h d'extraits. "
               "Cela ne prédit pas des heures de morceaux entiers."]
        md += [f"IC 95 % approximatif : {yield_['approx_95pct_ci']}; "
               f"strates sans variance estimable : {yield_['variance_unestimable_singleton_strata']}."]
    else:
        md += ["**Rendement clean, durée utilisable, coût par heure retenue et verdict audio : en attente "
               "d'annotations humaines complètes.**"]
    md += ["", "Répartition de contenu observée : " + json.dumps(dict(content), ensure_ascii=False),
           "Instruments observés : " + json.dumps(dict(instruments), ensure_ascii=False),
           "Concentration après tri : voir `report.json` (en attente d'annotations pour une conclusion).", "",
           "Les métadonnées CC0/CC BY et l'empreinte du fichier ne démontrent pas la titularité de l'uploader. "
           "Aucune diffusion publique autorisée par ce rapport.", ""]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["plan", "download", "extract", "score", "annotate-import", "report"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--phase1", type=Path, default=PHASE1)
    parser.add_argument("--tracks", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-gib", type=float, default=10.0)
    parser.add_argument("--passages", type=int, default=3)
    parser.add_argument("--passage-seconds", type=float, default=18.0)
    parser.add_argument("--limit", type=int, help="Download at most this many planned tracks for a smoke run")
    parser.add_argument("--with-pq", action="store_true", help="Run Audiobox PQ if installed on a GPU node")
    parser.add_argument("--csv", type=Path, help="Completed human annotation CSV")
    args = parser.parse_args()
    if args.stage == "plan":
        print(json.dumps(make_plan(args.phase1, args.out, args.tracks, args.seed,
                                   args.max_new_gib, args.passages, args.passage_seconds), indent=2))
    elif args.stage == "download":
        download(args.out, args.limit)
    elif args.stage == "extract":
        extract(args.out)
    elif args.stage == "score":
        score(args.out, args.with_pq)
    elif args.stage == "annotate-import":
        if not args.csv:
            parser.error("annotate-import requires --csv")
        import_annotations(args.out, args.csv)
    else:
        print(json.dumps(report(args.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
