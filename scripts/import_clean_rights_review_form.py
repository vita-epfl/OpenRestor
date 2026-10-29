#!/usr/bin/env python3
"""Convert completed rights-review CSV rows into private JSONL overrides.

Blank decisions are skipped and reported; they are never converted into
positive or negative labels.  Approved rows require exact licence, evidence,
permission, provenance and verified-source fields so that the downstream
rights registry can remain fail-closed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


DECISIONS = {"approved", "rejected", "pending"}
REQUIRED_COLUMNS = {"source_key", "decision"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _required(row: dict, field: str) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _bool(row: dict, field: str, *, required: bool) -> bool | None:
    value = str(row.get(field) or "").strip().lower()
    if not value:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if value not in {"true", "false"}:
        raise ValueError(f"{field} must be true or false")
    return value == "true"


def _date(row: dict, field: str) -> str:
    value = _required(row, field)
    if not DATE_RE.fullmatch(value):
        raise ValueError(f"{field} must use YYYY-MM-DD")
    return value


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - set(columns))
        if missing:
            raise ValueError(f"missing CSV columns: {', '.join(missing)}")
        rows = [dict(row) for row in reader]
    return columns, rows


def _expected_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid expected JSONL at {path}:{number}") from error
            key = str(row.get("source_key") or "") if isinstance(row, dict) else ""
            if not key:
                raise ValueError(f"expected queue row {number} lacks source_key")
            if key in keys:
                raise ValueError(f"duplicate expected source_key: {key}")
            keys.add(key)
    if not keys:
        raise ValueError("expected queue is empty")
    return keys


def _override(row: dict[str, str]) -> dict:
    key = _required(row, "source_key")
    decision = _required(row, "decision").lower()
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    reviewer = _required(row, "reviewer")
    review_date = _date(row, "review_date")
    result = {
        "media_key": key,
        "review_status": decision,
        "reviewer": reviewer,
        "evidence_date": review_date,
    }
    reason = str(row.get("reason") or "").strip()
    if decision == "approved":
        result.update({
            "license_label": _required(row, "verified_license_label"),
            "license_url": _required(row, "verified_license_url"),
            "attribution": _required(row, "verified_attribution"),
            "evidence_url": (_required(row, "evidence_url_override")
                             if str(row.get("evidence_url_override") or "").strip()
                             else _required(row, "evidence_url")),
            "allow_commercial": _bool(row, "allow_commercial", required=True),
            "allow_redistribution": _bool(row, "allow_redistribution", required=True),
            "allow_derivatives": _bool(row, "allow_derivatives", required=True),
            "share_alike": _bool(row, "share_alike", required=True),
            "provenance_approved": _bool(row, "provenance_approved", required=True),
            "redistribution_approved": _bool(row, "redistribution_approved", required=True),
            "source_status": _required(row, "source_status_verified"),
            "source_sha256": _required(row, "verified_source_sha256").lower(),
        })
        if result["source_status"] != "original_verified":
            raise ValueError("approved source_status_verified must be original_verified")
        if not SHA256_RE.fullmatch(result["source_sha256"]):
            raise ValueError("verified_source_sha256 must be a 64-character SHA-256")
        if result["provenance_approved"] is not True or result["redistribution_approved"] is not True:
            raise ValueError("approved rows require both explicit approvals")
    else:
        result.update({
            "provenance_approved": False if decision == "rejected" else None,
            "redistribution_approved": False if decision == "rejected" else None,
            "provenance_note": reason or "Rights review remains incomplete.",
        })
    return result


def import_form(path: Path, out: Path, report: Path,
                expected_queue: Path | None = None,
                allow_subset: bool = False) -> dict:
    columns, rows = _read(path)
    seen: set[str] = set()
    overrides: list[dict] = []
    blank = 0
    for number, row in enumerate(rows, 2):
        key = str(row.get("source_key") or "").strip()
        decision = str(row.get("decision") or "").strip()
        if not key and not decision:
            blank += 1
            continue
        if not key:
            raise ValueError(f"row {number}: source_key is required")
        if key in seen:
            raise ValueError(f"duplicate source_key at row {number}: {key}")
        seen.add(key)
        if not decision:
            blank += 1
            continue
        try:
            overrides.append(_override(row))
        except ValueError as error:
            raise ValueError(f"row {number} ({key}): {error}") from error
    expected = _expected_keys(expected_queue) if expected_queue else None
    missing_keys = sorted(expected - seen) if expected is not None else []
    unknown_keys = sorted(seen - expected) if expected is not None else []
    if unknown_keys:
        raise ValueError(f"CSV contains source_key outside expected queue: {unknown_keys[0]}")
    if missing_keys and not allow_subset:
        raise ValueError(f"CSV is missing expected source_key: {missing_keys[0]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                                  for item in overrides), encoding="utf-8")
    digest = hashlib.sha256("\n".join(item["media_key"] for item in overrides).encode()).hexdigest()
    result = {
        "schema_version": "clean-rights-review-overrides-v1",
        "input_rows": len(rows),
        "override_rows": len(overrides),
        "blank_or_unreviewed_rows": blank,
        "columns": columns,
        "expected_queue": str(expected_queue) if expected_queue else None,
        "expected_sources": len(expected) if expected is not None else None,
        "missing_expected_sources": len(missing_keys),
        "unknown_sources": len(unknown_keys),
        "source_keys_match_expected": expected is None or not missing_keys and not unknown_keys,
        "allow_subset": allow_subset,
        "override_media_keys_sha256": digest,
        "audio_paths_included": False,
        "rights_are_not_inferred": True,
        "note": "Only nonblank decisions are emitted; blank rows remain unreviewed.",
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
    parser.add_argument("--expected-queue", type=Path,
                        help="Optional JSONL queue whose source_key set must match")
    parser.add_argument("--allow-subset", action="store_true",
                        help="Allow a CSV containing only a subset of expected keys")
    args = parser.parse_args()
    result = import_form(args.input, args.out, args.report,
                         expected_queue=args.expected_queue,
                         allow_subset=args.allow_subset)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
