#!/usr/bin/env python3
"""Merge common Clean manifests without silently losing asset records.

Inputs are read in order.  Identical duplicate rows are collapsed.  A
different duplicate requires ``--allow-overrides``; when enabled, the later
manifest wins and the report records the replaced source key.  This is useful
for replacing a metadata-only row with a bounded, checksum-verified pilot row
while keeping the operation reproducible and auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from openrestor.validation.core import validate_clean_manifest


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"manifest row is not an object at {path}:{line_number}")
            yield row


def source_key(row: dict, path: Path, line_number: int) -> str:
    key = row.get("source_key")
    if not key:
        dataset = str(row.get("dataset") or "")
        source_id = str(row.get("source_id") or "")
        key = f"{dataset}:{source_id}" if dataset and source_id else ""
    if not key or key == ":":
        raise ValueError(f"manifest row has no source key at {path}:{line_number}")
    return str(key)


def merge(inputs: list[Path], allow_overrides: bool = False) -> tuple[list[dict], dict]:
    rows: dict[str, dict] = {}
    origins: dict[str, str] = {}
    duplicate_identical = 0
    overrides: list[dict] = []
    input_counts: dict[str, int] = {}
    for path in inputs:
        count = 0
        for line_number, row in enumerate(read_jsonl(path), 1):
            count += 1
            key = source_key(row, path, line_number)
            if key not in rows:
                rows[key] = row
                origins[key] = str(path)
                continue
            if rows[key] == row:
                duplicate_identical += 1
                continue
            if not allow_overrides:
                raise ValueError(
                    f"conflicting duplicate source key {key}: {origins[key]} vs {path}"
                )
            overrides.append({"source_key": key, "replaced": origins[key], "with": str(path)})
            rows[key] = row
            origins[key] = str(path)
        input_counts[str(path)] = count
    ordered = [rows[key] for key in sorted(rows)]
    report = {
        "schema_version": "clean-manifest-merge-v1",
        "input_counts": input_counts,
        "output_count": len(ordered),
        "duplicate_identical_count": duplicate_identical,
        "override_count": len(overrides),
        "overrides": overrides,
        "allow_overrides": allow_overrides,
        "output_sha256": hashlib.sha256(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                    for row in ordered).encode("utf-8")
        ).hexdigest(),
    }
    return ordered, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True,
                        help="Manifest JSONL; repeat in precedence order")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-overrides", action="store_true",
                        help="Let later inputs replace conflicting duplicate keys")
    args = parser.parse_args()
    rows, report = merge(args.input, args.allow_overrides)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    validate_clean_manifest(args.out)
    report["schema_validated"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Merged {len(rows)} sources: {args.out}")


if __name__ == "__main__":
    main()
