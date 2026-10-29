#!/usr/bin/env python3
"""Export a private, metadata-only asset-level rights review queue.

The queue is a convenience view over common clean manifests.  It never copies
audio, exposes local paths, or changes a rights decision.  Missing permissions
remain ``null`` and must be approved separately by the rights workflow.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            yield row


def queue_row(source: dict) -> dict:
    dataset = str(source.get("dataset") or "")
    source_id = str(source.get("source_id") or "")
    if not dataset or not source_id:
        raise ValueError("manifest row needs dataset and source_id")
    metadata = source.get("metadata") or {}
    rights = source.get("rights") or {}
    zenodo = source.get("zenodo") if isinstance(source.get("zenodo"), dict) else {}
    return {
        "source_key": str(source.get("source_key") or f"{dataset}:{source_id}"),
        "dataset": dataset,
        "source_id": source_id,
        "title": metadata.get("title"),
        # ``creator`` is the asset performer/owner when the adapter knows it.
        # Dataset authors stay separate so a reviewer never mistakes record
        # attribution for ownership of every audio member.
        "creator": metadata.get("creator"),
        "dataset_creators": metadata.get("dataset_creators"),
        "collection": metadata.get("collection"),
        "archive_record_id": metadata.get("archive_record_id") or metadata.get("zenodo_record_id"),
        "archive_record_url": metadata.get("archive_record_url") or metadata.get("zenodo_record_url"),
        "archive_key": metadata.get("archive_key") or zenodo.get("archive_key"),
        "archive_url": metadata.get("archive_url"),
        "member_name": metadata.get("member_name") or metadata.get("archive_member"),
        "member_url": metadata.get("member_url"),
        "member_crc32": metadata.get("member_crc32"),
        "member_compressed_size_bytes": metadata.get("member_compressed_size_bytes"),
        "member_uncompressed_size_bytes": metadata.get("member_uncompressed_size_bytes"),
        "identity": metadata.get("identity") or source_id,
        "original_format": source.get("original_format"),
        "sample_rate": source.get("sample_rate"),
        "channels": source.get("channels"),
        "duration_seconds": source.get("duration_seconds"),
        "source_sha256": source.get("source_sha256"),
        "license_label": rights.get("license_label"),
        "license_id": rights.get("license_id"),
        "license_url": rights.get("license_url"),
        "attribution": rights.get("attribution"),
        "evidence_url": rights.get("evidence_url"),
        "evidence_date": rights.get("evidence_date"),
        "review_status": rights.get("review_status"),
        "rights_status": rights.get("rights_status"),
        "source_status": rights.get("source_status"),
        "provenance_approved": rights.get("provenance_approved"),
        "redistribution_approved": rights.get("redistribution_approved"),
        "allow_commercial": rights.get("allow_commercial"),
        "allow_redistribution": rights.get("allow_redistribution"),
        "allow_derivatives": rights.get("allow_derivatives"),
        "technical_candidate": source.get("technical_candidate"),
        "provenance_candidate": source.get("provenance_candidate"),
        "redistributable_candidate": source.get("redistributable_candidate"),
        "audio_path_omitted": True,
    }


def _source_key_selection(path: Path) -> set[str]:
    selected: set[str] = set()
    for row in read_jsonl(path):
        key = str(row.get("source_key") or "")
        if not key:
            raise ValueError(f"source-key selection row lacks source_key: {path}")
        if key in selected:
            raise ValueError(f"duplicate source_key in selection: {key}")
        selected.add(key)
    if not selected:
        raise ValueError(f"source-key selection is empty: {path}")
    return selected


def build(inputs: list[Path], out: Path, report: Path,
          source_keys_path: Path | None = None) -> dict:
    rows: dict[str, dict] = {}
    for path in inputs:
        for source in read_jsonl(path):
            row = queue_row(source)
            key = row["source_key"]
            if key in rows and rows[key] != row:
                raise ValueError(f"conflicting duplicate source key: {key}")
            rows[key] = row
    selected_keys = _source_key_selection(source_keys_path) if source_keys_path else None
    if selected_keys is not None:
        unknown = sorted(selected_keys - set(rows))
        if unknown:
            raise ValueError(f"source-key selection contains unknown key: {unknown[0]}")
        ordered = [rows[key] for key in sorted(selected_keys)]
    else:
        ordered = [rows[key] for key in sorted(rows)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                  for row in ordered), encoding="utf-8")
    by_dataset = collections.Counter(row["dataset"] for row in ordered)
    by_license = collections.Counter(str(row["license_label"]) for row in ordered)
    by_status = collections.Counter(str(row["review_status"]) for row in ordered)
    by_rights_status = collections.Counter(str(row["rights_status"]) for row in ordered)
    result = {
        "schema_version": "clean-rights-review-queue-v1",
        "input_sources": len(rows),
        "sources": len(ordered),
        "selection_source_keys": str(source_keys_path) if source_keys_path else None,
        "by_dataset": dict(sorted(by_dataset.items())),
        "by_license": dict(sorted(by_license.items())),
        "by_review_status": dict(sorted(by_status.items())),
        "by_rights_status": dict(sorted(by_rights_status.items())),
        "all_redistribution_approved": all(row["redistribution_approved"] is True for row in ordered),
        "all_provenance_approved": all(row["provenance_approved"] is True for row in ordered),
        "audio_paths_included": False,
        "rights_are_not_inferred": True,
        "note": "Review queue only; no permission is granted by this artifact.",
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-keys", type=Path,
                        help="Optional JSONL containing source_key rows to retain")
    args = parser.parse_args()
    result = build(args.input, args.out, args.report, args.source_keys)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
