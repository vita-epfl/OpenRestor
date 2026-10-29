"""Source-grouped review splits and transparent, small-sample evaluation."""

from __future__ import annotations

import collections
import csv
import hashlib
import math
import statistics
from pathlib import Path

from .features import read_jsonl, write_jsonl_atomic


LABEL_FIELDS = ("content_type", "audio_quality", "source_nature", "capture_quality",
                "degradation_reason", "provenance", "pool_suitability",
                "source_level_label", "notes")
VALID_LABELS = {
    "content_type": {"music", "speech_dominant", "noise_or_sound_effect", "ambiguous"},
    "audio_quality": {"acceptable", "degraded", "ambiguous"},
    "source_nature": {"likely_real_recording", "likely_midi_or_synthetic_render", "ambiguous"},
    "capture_quality": {"clean", "distant_or_reverberant", "noisy_or_hissy",
                         "distorted_or_clipped", "bandwidth_limited", "ambiguous"},
    "degradation_reason": {"distance_reverb", "background_noise", "hiss_hum",
                            "clipping_distortion", "bandwidth_cutoff", "speech_or_nonmusic",
                            "synthetic_or_midi", "other", "ambiguous"},
    "provenance": {"unreviewed", "plausible", "needs_verification", "blocked", "ambiguous"},
    "pool_suitability": {"suitable", "unsuitable_style", "ambiguous"},
    "source_level_label": {"suitable", "unsuitable", "ambiguous"},
}
NEGATIVE_CONTENT = {"speech_dominant", "noise_or_sound_effect"}
METRICS = ("PQ", "PC", "CE", "CU", "AST Music", "AST Speech",
           "CLAP music-minus-nonmusic", "CLAP music-minus-rudimentary",
           "bandwidth_hz", "clipped_ratio", "dynamic_range_db", "rolloff_85_hz",
           "hiss_proxy", "hum_tonality_proxy")


def import_reviews(path: Path, source_keys: set[str], *, identifier_column: str = "source_key",
                   dataset: str | None = None) -> dict[str, dict]:
    """Import sparse old IAMD or generic listener CSV without inventing labels."""
    reviews = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if identifier_column not in (reader.fieldnames or []):
            raise ValueError(f"review CSV lacks {identifier_column}")
        for line_number, raw in enumerate(reader, 2):
            if None in raw:
                raise ValueError(f"extra CSV fields on line {line_number}")
            identifier = (raw.get(identifier_column) or "").strip()
            key = f"{dataset}:{identifier}" if dataset else identifier
            if key not in source_keys or key in reviews:
                raise ValueError(f"unknown or duplicate review identifier on line {line_number}: {identifier}")
            row = {field: (raw.get(field) or "").strip() for field in LABEL_FIELDS}
            for field, choices in VALID_LABELS.items():
                if row[field] and row[field] not in choices:
                    raise ValueError(f"invalid {field} on line {line_number}: {row[field]}")
            row["scope"] = (raw.get("scope") or "primary_clip_only").strip()
            if row["scope"] not in {"primary_clip_only", "all_sampled_passages", "whole_source"}:
                raise ValueError(f"invalid scope on line {line_number}: {row['scope']}")
            if any(row[field] for field in LABEL_FIELDS):
                row["source_key"] = key
                row["human_class"], row["rejection_reasons"] = human_class(row)
                reviews[key] = row
    return reviews


def import_blind_reviews(path: Path, order_path: Path,
                         source_keys: set[str]) -> dict[str, dict]:
    """Map opaque blind CSV labels through the immutable order file.

    Blank rows remain unresolved and are ignored; no missing annotation is
    treated as a positive or negative label.
    """
    order = list(read_jsonl(order_path))
    by_blind = {}
    for row in order:
        blind_id = str(row.get("blind_id") or "")
        key = str(row.get("source_key") or "")
        if not blind_id or not key or blind_id in by_blind:
            raise ValueError("blind order must contain unique blind_id/source_key pairs")
        if key not in source_keys:
            raise ValueError(f"blind order contains source absent from features: {key}")
        by_blind[blind_id] = (key, row.get("blind_rank"))
    reviews = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if "blind_id" not in (reader.fieldnames or []):
            raise ValueError("blind review CSV lacks blind_id")
        for line_number, raw in enumerate(reader, 2):
            if None in raw:
                raise ValueError(f"extra CSV fields on line {line_number}")
            blind_id = (raw.get("blind_id") or "").strip()
            if blind_id not in by_blind:
                raise ValueError(f"unknown or duplicate blind_id on line {line_number}: {blind_id}")
            key, rank = by_blind[blind_id]
            if key in reviews:
                raise ValueError(f"duplicate blind_id on line {line_number}: {blind_id}")
            row = {field: (raw.get(field) or "").strip() for field in LABEL_FIELDS}
            for field, choices in VALID_LABELS.items():
                if row[field] and row[field] not in choices:
                    raise ValueError(f"invalid {field} on line {line_number}: {row[field]}")
            row["scope"] = (raw.get("scope") or "primary_clip_only").strip()
            if row["scope"] not in {"primary_clip_only", "all_sampled_passages", "whole_source"}:
                raise ValueError(f"invalid scope on line {line_number}: {row['scope']}")
            if any(row[field] for field in LABEL_FIELDS):
                row["source_key"] = key
                row["blind_id"] = blind_id
                row["blind_rank"] = rank
                row["human_class"], row["rejection_reasons"] = human_class(row)
                reviews[key] = row
    return reviews


def import_iamd_reviews(path: Path, source_keys: set[str]) -> dict[str, dict]:
    return import_reviews(path, source_keys, identifier_column="identifier", dataset="iamd")


def human_class(row: dict) -> tuple[str, list[str]]:
    """Blank is unknown; notes are preserved, never silently parsed as labels."""
    reasons = []
    if row.get("content_type") in NEGATIVE_CONTENT:
        reasons.append(row["content_type"])
    if row.get("audio_quality") == "degraded":
        reasons.append("degraded")
    if row.get("capture_quality") not in {None, "", "clean", "ambiguous"}:
        reasons.append(row["capture_quality"])
    if row.get("degradation_reason") not in {None, "", "ambiguous"}:
        reasons.append(row["degradation_reason"])
    if row.get("source_nature") == "likely_midi_or_synthetic_render":
        reasons.append("rudimentary_render")
    if row.get("pool_suitability") == "unsuitable_style":
        reasons.append("unsuitable_style")
    if row.get("source_level_label") == "unsuitable":
        reasons.append("source_level_unsuitable")
    if reasons:
        return "negative_clip_evidence", reasons
    if any(row.get(field) == "ambiguous" for field in
           ("content_type", "audio_quality", "source_nature", "pool_suitability", "source_level_label")):
        return "unresolved", []
    if row.get("content_type") == "music" and row.get("audio_quality") == "acceptable":
        return "positive_clip_evidence", []
    return "unresolved", []


def fixed_split(source_keys: set[str], reviewed: set[str], path: Path, *, seed: str = "curation-v1") -> dict[str, str]:
    """Freeze prospective unreviewed sources and hash groups, never excerpts."""
    if path.exists():
        rows = list(read_jsonl(path))
        result = {row["source_key"]: row["role"] for row in rows}
        if len(result) != len(rows) or set(result) != source_keys:
            raise ValueError("split lock does not match exact source keys")
        if any(role not in {"calibration", "validation", "prospective"} for role in result.values()):
            raise ValueError("invalid split role")
        return result
    result = {}
    for key in sorted(source_keys):
        if key not in reviewed:
            role = "prospective"
        else:
            bucket = int(hashlib.sha256((seed + "|" + key.split(":", 1)[1]).encode()).hexdigest()[:8], 16) % 10
            role = "calibration" if bucket < 7 else "validation"
        result[key] = role
    write_jsonl_atomic(path, [{"source_key": key, "role": role, "seed": seed}
                              for key, role in sorted(result.items())])
    return result


def primary_segment(record: dict) -> dict:
    segments = record.get("segments") or []
    if not segments:
        raise ValueError(f"source without segments: {record.get('source_key')}")
    return segments[len(segments) // 2]


def metric_values(record: dict) -> dict[str, float | None]:
    segment = primary_segment(record)
    acoustic = segment.get("acoustic") or {}
    aesthetics = segment.get("aesthetics") or {}
    ast = (segment.get("ast") or {}).get("interest_labels") or {}
    clap = (segment.get("clap") or {}).get("group_scores") or {}
    music_clap = max((clap.get("produced_music"), clap.get("legitimate_electronic_music")),
                     default=None) if all(clap.get(k) is not None for k in ("produced_music", "legitimate_electronic_music")) else None
    return {"PQ": aesthetics.get("PQ"), "PC": aesthetics.get("PC"),
            "CE": aesthetics.get("CE"), "CU": aesthetics.get("CU"),
            "AST Music": ast.get("Music"), "AST Speech": ast.get("Speech"),
            "CLAP music-minus-nonmusic": music_clap - clap["non_music"]
            if music_clap is not None and clap.get("non_music") is not None else None,
            "CLAP music-minus-rudimentary": music_clap - clap["rudimentary_synthetic"]
            if music_clap is not None and clap.get("rudimentary_synthetic") is not None else None,
            "bandwidth_hz": acoustic.get("bandwidth_hz"),
            "clipped_ratio": acoustic.get("clipped_sample_ratio_channels"),
            "dynamic_range_db": acoustic.get("dynamic_range_db"),
            "rolloff_85_hz": acoustic.get("rolloff_85_hz"),
            "hiss_proxy": acoustic.get("hiss_proxy"),
            "hum_tonality_proxy": acoustic.get("hum_tonality_proxy")}


def distributions(records: dict[str, dict], reviews: dict[str, dict], split: dict[str, str], role: str) -> dict:
    result = {}
    for label in ("positive_clip_evidence", "negative_clip_evidence"):
        keys = [key for key, review in reviews.items()
                if split.get(key) == role and review["human_class"] == label]
        stats = {}
        for metric in METRICS:
            values = sorted(float(value) for key in keys
                            if (value := metric_values(records[key]).get(metric)) is not None and math.isfinite(value))
            if values:
                stats[metric] = {"n": len(values), "median": statistics.median(values),
                                 "q10": values[round((len(values) - 1) * .1)],
                                 "q90": values[round((len(values) - 1) * .9)]}
        result[label] = {"n": len(keys), "metrics": stats}
    positive_keys = [key for key, review in reviews.items()
                     if split.get(key) == role and review["human_class"] == "positive_clip_evidence"]
    negative_keys = [key for key, review in reviews.items()
                     if split.get(key) == role and review["human_class"] == "negative_clip_evidence"]
    ranking = {}
    for metric in METRICS:
        positive = [float(value) for key in positive_keys
                    if (value := metric_values(records[key]).get(metric)) is not None and math.isfinite(value)]
        negative = [float(value) for key in negative_keys
                    if (value := metric_values(records[key]).get(metric)) is not None and math.isfinite(value)]
        if positive and negative:
            wins = sum(1 if p > n else .5 if p == n else 0 for p in positive for n in negative)
            ranking[metric] = {"auc_positive_higher": wins / (len(positive) * len(negative)),
                               "positive_n": len(positive), "negative_n": len(negative)}
    result["univariate_ranking"] = ranking
    return result


def wilson(successes: int, trials: int) -> list[float] | None:
    if trials == 0:
        return None
    z = 1.959963984540054
    p = successes / trials
    center = (p + z * z / (2 * trials)) / (1 + z * z / trials)
    radius = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / (1 + z * z / trials)
    return [max(0.0, center - radius), min(1.0, center + radius)]


def evaluate_decisions(records: dict[str, dict], reviews: dict[str, dict], split: dict[str, str],
                       decisions: dict[str, dict], role: str) -> dict:
    keys = [key for key in sorted(reviews) if split.get(key) == role]
    labelled = [key for key in keys if reviews[key]["human_class"] != "unresolved"]
    positive = [key for key in labelled if reviews[key]["human_class"] == "positive_clip_evidence"]
    negative = [key for key in labelled if reviews[key]["human_class"] == "negative_clip_evidence"]
    accepted = [key for key in labelled if decisions[key]["decision"] == "auto_accept"]
    correct_accept = [key for key in accepted if key in positive]
    bad_accept = [key for key in accepted if key in negative]
    good_reject = [key for key in positive if decisions[key]["decision"] == "auto_reject"]
    reviewed = [key for key in keys if decisions[key]["decision"] == "manual_review"]
    group_stats = {}
    for field in ("genre", "collection", "creator"):
        groups = collections.defaultdict(lambda: {"annotated": 0, "positive": 0, "negative": 0,
                                                  "auto_accept": 0, "bad_auto_accept": 0, "manual_review": 0})
        for key in keys:
            name = str((records[key].get("metadata") or {}).get(field) or "[unknown]")
            group = groups[name]
            group["annotated"] += 1
            group["positive"] += key in positive
            group["negative"] += key in negative
            group["auto_accept"] += decisions[key]["decision"] == "auto_accept"
            group["bad_auto_accept"] += key in bad_accept
            group["manual_review"] += key in reviewed
        group_stats[field] = dict(sorted(groups.items(), key=lambda item: (-item[1]["annotated"], item[0])))
    by_content = collections.defaultdict(lambda: collections.Counter())
    for key in keys:
        by_content[reviews[key]["content_type"] or "unassessed"][decisions[key]["decision"]] += 1
    error_reasons = collections.Counter(reason for key in bad_accept
                                        for reason in reviews[key].get("rejection_reasons", []))
    return {
        "annotated": len(keys), "binary_labelled": len(labelled),
        "positive_clip_evidence": len(positive), "negative_clip_evidence": len(negative),
        "unresolved": len(keys) - len(labelled),
        "decisions": dict(collections.Counter(decisions[key]["decision"] for key in keys)),
        "auto_accept_precision_on_binary_labels": len(correct_accept) / len(accepted) if accepted else None,
        "auto_accept_precision_95pct_wilson": wilson(len(correct_accept), len(accepted)),
        "auto_accept_binary_denominator": len(accepted),
        "unresolved_auto_accepted": sum(reviews[key]["human_class"] == "unresolved"
                                        and decisions[key]["decision"] == "auto_accept" for key in keys),
        "unresolved_auto_accepted_keys": [key for key in keys
                                          if reviews[key]["human_class"] == "unresolved"
                                          and decisions[key]["decision"] == "auto_accept"],
        "bad_clip_auto_accept_rate": len(bad_accept) / len(negative) if negative else None,
        "bad_clip_auto_accept_rate_95pct_wilson": wilson(len(bad_accept), len(negative)),
        "good_clip_auto_reject_rate": len(good_reject) / len(positive) if positive else None,
        "good_clip_auto_reject_rate_95pct_wilson": wilson(len(good_reject), len(positive)),
        "manual_review_fraction": len(reviewed) / len(keys) if keys else None,
        "bad_auto_accept_keys": bad_accept, "good_auto_reject_keys": good_reject,
        "by_content_type": {key: dict(value) for key, value in by_content.items()},
        "by_group": group_stats, "error_reason_counts": dict(error_reasons),
    }


def logistic_diagnostic(records: dict[str, dict], reviews: dict[str, dict], split: dict[str, str]) -> dict[str, dict] | None:
    """Small L2 baseline, fitted on calibration only; never a release gate."""
    features = ("PQ", "PC", "CE", "CU", "AST Music", "AST Speech",
                "CLAP music-minus-nonmusic", "CLAP music-minus-rudimentary", "bandwidth_hz")
    calibration = [key for key in sorted(reviews) if split.get(key) == "calibration"
                   and reviews[key]["human_class"] != "unresolved"]
    if len(calibration) < 40 or min(collections.Counter(reviews[key]["human_class"]
                                                       for key in calibration).values()) < 15:
        return None
    def vector(key):
        values = metric_values(records[key])
        return [values[name] for name in features]
    calibration = [key for key in calibration if all(value is not None for value in vector(key))]
    if len(calibration) < 40:
        return None
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return None

    model = make_pipeline(StandardScaler(), LogisticRegression(C=.2, class_weight="balanced",
                                                               solver="liblinear", random_state=42,
                                                               max_iter=1000))
    labels = [int(reviews[key]["human_class"] == "positive_clip_evidence") for key in calibration]
    model.fit([vector(key) for key in calibration], labels)
    result = {}
    for key in records:
        values = vector(key)
        if any(value is None for value in values):
            result[key] = {"decision": "manual_review", "reasons": ["missing_logistic_features"]}
            continue
        probability = float(model.predict_proba([values])[0, 1])
        decision = "auto_accept" if probability >= .85 else "auto_reject" if probability <= .15 else "manual_review"
        result[key] = {"decision": decision, "clean_score": probability,
                       "reasons": ["diagnostic_logistic_probability_not_calibrated"]}
    return result
