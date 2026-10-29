#!/usr/bin/env python3
"""Normalize heterogeneous dataset indexes into the OpenRestore curation manifest.

The adapter is deliberately metadata-only: it never downloads or copies audio.
It accepts existing JSONL indexes from different datasets and emits the fields
consumed by ``openrestor-curate extract``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from openrestor.validation.core import validate_clean_manifest


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {path}:{number}") from error


def first(row: dict, *names: str):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _numeric(value, field: str, *, integer: bool = False):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric, got {value!r}") from error
    if integer:
        if not number.is_integer() or number < 1:
            raise ValueError(f"{field} must be a positive integer, got {value!r}")
        return int(number)
    if number < 0:
        raise ValueError(f"{field} must be non-negative, got {value!r}")
    return number


def normalize(row: dict, dataset_override: str | None = None) -> dict:
    dataset = str(dataset_override or first(row, "dataset", "dataset_name") or "unknown")
    source_id = first(row, "source_id", "identifier", "id", "track_id", "filename")
    if source_id in (None, ""):
        raise ValueError("manifest row has no source_id/identifier/id/track_id/filename")
    source_id = str(source_id)
    audio_path = first(row, "audio_path", "local_audio_path", "path", "file", "filename_path")
    metadata = dict(row.get("metadata") or {})
    for target, names in {
        "title": ("title", "track_title", "name"),
        "creator": ("creator", "artist", "artist_name", "composer"),
        "genre": ("genre", "genres", "tags"),
        "collection": ("collection", "collections", "album"),
    }.items():
        value = first(row, *names)
        if value is not None and target not in metadata:
            metadata[target] = value
    rights = dict(row.get("rights") or {})
    for field in ("license_label", "license_url", "review_status", "allow_commercial",
                  "allow_redistribution", "allow_derivatives", "evidence_url", "attribution"):
        if field in row and field not in rights:
            rights[field] = row[field]
    result = {
        "dataset": dataset,
        "source_id": source_id,
        "source_key": f"{dataset}:{source_id}",
        "audio_path": str(audio_path) if audio_path else None,
        "metadata": metadata,
        "rights": rights,
        "source_sha256": first(row, "source_sha256", "sha256", "original_sha256"),
        "sample_rate": _numeric(first(row, "sample_rate", "samplerate"), "sample_rate", integer=True),
        "channels": _numeric(first(row, "channels", "channel_count"), "channels", integer=True),
        "duration_seconds": _numeric(
            first(row, "duration_seconds", "duration", "length_seconds"),
            "duration_seconds",
        ),
        "original_format": first(row, "original_format", "format", "codec", "file_format"),
        "split": first(row, "split", "role"),
        "license_source": first(row, "license_source", "evidence_url"),
    }
    # Keep the provenance trail without copying arbitrary source-specific blobs.
    for field in ("lossless_status", "technical_candidate", "provenance_candidate",
                  "redistributable_candidate", "indexed_audio_path", "original_extension"):
        if field in row:
            result[field] = row[field]
    # Curation artifacts are part of the common contract.  Preserve them when
    # an upstream index already contains cached features, sampled segments or
    # human decisions; normalization must not silently erase review history.
    for field in ("features", "segments", "segment_decisions", "source_decision",
                  "curation_decision", "pipeline_decision", "pipeline_reasons",
                  "clean_score", "annotations", "annotation_history", "curation"):
        if field in row:
            result[field] = row[field]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--dataset", help="Override dataset name for all input rows")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = {}
    for path in args.input:
        for row in read_jsonl(path):
            normalized = normalize(row, args.dataset)
            key = normalized["source_key"]
            if key in rows and rows[key] != normalized:
                raise ValueError(f"conflicting duplicate source key: {key}")
            rows[key] = normalized
    ordered = [rows[key] for key in sorted(rows)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ordered)
    args.out.write_text(payload, encoding="utf-8")
    validate_clean_manifest(args.out)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(f"Normalized {len(ordered)} sources to {args.out} (sha256={digest})")


if __name__ == "__main__":
    main()
