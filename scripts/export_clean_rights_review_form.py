#!/usr/bin/env python3
"""Export a private CSV form for asset-level rights review.

The form contains catalogue evidence and blank decision fields.  It never
includes audio paths and never fills permissions from a catalogue licence.
Use ``import_clean_rights_review_form.py`` to convert completed rows into the
private JSONL override format consumed by the rights registry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


FORM_FIELDS = (
    "review_batch_rank", "source_key", "dataset", "source_id", "title",
    "collection", "creator", "dataset_creators", "original_format",
    "source_status", "technical_candidate", "provenance_candidate",
    "license_label", "license_url", "evidence_url", "evidence_date",
    "archive_url", "member_url", "member_crc32", "source_sha256",
    "decision", "reviewer", "review_date", "verified_license_label",
    "verified_license_url", "verified_attribution", "evidence_url_override",
    "allow_commercial", "allow_redistribution", "allow_derivatives",
    "share_alike", "provenance_approved", "redistribution_approved",
    "source_status_verified", "verified_source_sha256", "reason",
)


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
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
            rows.append(row)
    return rows


def _cell(value: object) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return str(value)


def _digest(rows: list[dict]) -> str:
    payload = "\n".join(str(row.get("source_key") or "") for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export_form(rows: list[dict], out: Path, report: Path) -> dict:
    seen: set[str] = set()
    prepared: list[dict[str, str]] = []
    for row in rows:
        key = str(row.get("source_key") or "")
        if not key:
            raise ValueError("every queue row needs source_key")
        if key in seen:
            raise ValueError(f"duplicate source_key: {key}")
        seen.add(key)
        if row.get("audio_path") not in (None, ""):
            raise ValueError(f"audio path must not be exported: {key}")
        prepared_row = {field: "" for field in FORM_FIELDS}
        prepared_row.update({
            "review_batch_rank": _cell(row.get("review_batch_rank")),
            "source_key": key,
            "dataset": _cell(row.get("dataset")),
            "source_id": _cell(row.get("source_id")),
            "title": _cell(row.get("title")),
            "collection": _cell(row.get("collection")),
            "creator": _cell(row.get("creator")),
            "dataset_creators": _cell(row.get("dataset_creators")),
            "original_format": _cell(row.get("original_format")),
            "source_status": _cell(row.get("source_status")),
            "technical_candidate": _cell(row.get("technical_candidate")),
            "provenance_candidate": _cell(row.get("provenance_candidate")),
            "license_label": _cell(row.get("license_label")),
            "license_url": _cell(row.get("license_url")),
            "evidence_url": _cell(row.get("evidence_url")),
            "evidence_date": _cell(row.get("evidence_date")),
            "archive_url": _cell(row.get("archive_url")),
            "member_url": _cell(row.get("member_url")),
            "member_crc32": _cell(row.get("member_crc32")),
            "source_sha256": _cell(row.get("source_sha256")),
        })
        prepared.append(prepared_row)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FORM_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(prepared)
    result = {
        "schema_version": "clean-rights-review-form-v1",
        "input_sources": len(rows),
        "form_rows": len(prepared),
        "blank_decisions": len(prepared),
        "fields": list(FORM_FIELDS),
        "source_keys_sha256": _digest(rows),
        "audio_paths_included": False,
        "rights_are_not_inferred": True,
        "permissions_changed": False,
        "note": "Blank decisions are not labels and never grant permission.",
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = export_form(read_jsonl(args.input), args.out, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
