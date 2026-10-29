#!/usr/bin/env python3
"""Select a deterministic, metadata-only rights-review batch.

The selector is a convenience view over an existing rights queue.  It does
not infer a licence, change permissions, include audio paths, or promote a
source to a publication profile.  Selection is greedy and deterministic: it
balances dataset first, then licence, collection and creator, while keeping
unknown values as explicit strata.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path


UNKNOWN = "[unknown]"
SCHEMA_VERSION = "clean-rights-review-batch-v1"


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


def _source_key(row: dict) -> str:
    key = str(row.get("source_key") or "")
    if not key:
        raise ValueError("every queue row needs source_key")
    return key


def _stratum(row: dict, field: str) -> str:
    value = row.get(field)
    if value in (None, "", [], {}):
        return UNKNOWN
    return str(value)


def _distribution(rows: list[dict], field: str) -> dict[str, int]:
    counts = collections.Counter(_stratum(row, field) for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold())))


def _digest(rows: list[dict]) -> str:
    payload = "\n".join(_source_key(row) for row in rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select(rows: list[dict], size: int, *, technical_only: bool = False,
           licenses: set[str] | None = None) -> tuple[list[dict], dict]:
    if size <= 0:
        raise ValueError("size must be positive")
    seen: set[str] = set()
    eligible: list[dict] = []
    skipped = collections.Counter()
    allowed = licenses or set()
    for row in rows:
        key = _source_key(row)
        if key in seen:
            raise ValueError(f"duplicate source_key: {key}")
        seen.add(key)
        if row.get("audio_path") not in (None, ""):
            raise ValueError(f"audio path must not be present in rights queue: {key}")
        if str(row.get("review_status") or "") == "approved":
            skipped["already_approved"] += 1
            continue
        if technical_only and row.get("technical_candidate") is not True:
            skipped["not_technical_candidate"] += 1
            continue
        if allowed and str(row.get("license_label") or UNKNOWN) not in allowed:
            skipped["license_not_selected"] += 1
            continue
        eligible.append(row)
    if not eligible:
        raise ValueError("no eligible rights-review rows")

    fields = ("dataset", "license_label", "collection", "creator")
    counts = {field: collections.Counter() for field in fields}
    remaining = sorted(eligible, key=lambda row: _source_key(row).casefold())
    selected: list[dict] = []
    for rank in range(1, min(size, len(remaining)) + 1):
        # Dataset is the primary balance axis. The following dimensions break
        # ties and prevent one collection or creator from filling a stratum.
        chosen = min(remaining, key=lambda row: tuple(
            counts[field][_stratum(row, field)] for field in fields
        ) + (_source_key(row).casefold(),))
        remaining.remove(chosen)
        output = dict(chosen)
        output["review_batch_rank"] = rank
        output["review_batch_strata"] = {field: _stratum(chosen, field) for field in fields}
        output["selection_basis"] = "deterministic_greedy_stratification"
        selected.append(output)
        for field in fields:
            counts[field][_stratum(chosen, field)] += 1

    report = {
        "schema_version": SCHEMA_VERSION,
        "input_sources": len(rows),
        "eligible_sources": len(eligible),
        "selected_sources": len(selected),
        "size_requested": size,
        "technical_only": technical_only,
        "license_filter": sorted(allowed),
        "skipped": dict(sorted(skipped.items())),
        "selected_by_dataset": _distribution(selected, "dataset"),
        "selected_by_license": _distribution(selected, "license_label"),
        "selected_by_collection": _distribution(selected, "collection"),
        "selected_by_creator": _distribution(selected, "creator"),
        "selected_source_keys_sha256": _digest(selected),
        "audio_paths_included": False,
        "rights_are_not_inferred": True,
        "permissions_changed": False,
        "note": "Selection is a private review batch, not a publication or licence decision.",
    }
    return selected, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--technical-only", action="store_true")
    parser.add_argument("--license", dest="licenses", action="append", default=[])
    args = parser.parse_args()
    selected, report = select(read_jsonl(args.input), args.size,
                              technical_only=args.technical_only,
                              licenses=set(args.licenses))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                        for row in selected), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
