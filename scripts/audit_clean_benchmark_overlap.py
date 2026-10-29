#!/usr/bin/env python3
"""Audit candidate sources against frozen benchmark and evaluation identities.

Metadata only: exact dataset/source IDs, Internet Archive identifiers and
original-source SHA-256 values are compared. Clip hashes are deliberately not
treated as source hashes. The safe output excludes every observed overlap;
unknown identities fail instead of silently passing.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

try:
    from scripts.prepare_clean_corpus_splits import read_jsonl, write_jsonl
except ModuleNotFoundError:  # direct ``python scripts/...`` invocation
    from prepare_clean_corpus_splits import read_jsonl, write_jsonl


def identities(row: dict) -> set[str]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    dataset = str(row.get("dataset") or "").strip().casefold()
    source_id = str(row.get("source_id") or "").strip()
    tokens = set()
    if dataset and source_id:
        canonical = "iamd" if dataset in {"iamd", "iamd_archive"} else dataset
        tokens.add(f"source:{canonical}:{source_id}")
    archive_id = (row.get("internet_archive_identifier") or metadata.get("archive_identifier")
                  or (row.get("identifier") if dataset in {"iamd", "iamd_archive"} else None))
    if archive_id:
        tokens.add(f"archive:{archive_id}")
    elif dataset in {"iamd", "iamd_archive"} and source_id:
        tokens.add(f"archive:{source_id}")
    source_hash = row.get("source_sha256") or row.get("original_sha256")
    if source_hash and len(str(source_hash)) == 64:
        tokens.add(f"sha256:{str(source_hash).casefold()}")
    return tokens


def audit(candidates: list[dict], references: dict[str, list[dict]]) -> tuple[list[dict], list[dict], dict]:
    index: dict[str, set[str]] = collections.defaultdict(set)
    reference_counts = {}
    for label, rows in references.items():
        if not label or not rows:
            raise ValueError(f"empty benchmark reference: {label}")
        reference_counts[label] = len(rows)
        for number, row in enumerate(rows, 1):
            tokens = identities(row)
            if not tokens:
                raise ValueError(f"reference {label} row {number} lacks stable identity")
            for token in tokens:
                index[token].add(label)
    safe, overlaps = [], []
    labels = collections.Counter()
    types = collections.Counter()
    seen = set()
    for number, row in enumerate(candidates, 1):
        key = row.get("source_key") or (f"{row.get('dataset')}:{row.get('source_id')}"
                                        if row.get("dataset") and row.get("source_id") else None)
        if not key or key in seen:
            raise ValueError(f"candidate row {number} has missing/duplicate source key: {key}")
        seen.add(key)
        tokens = identities(row)
        if not tokens:
            raise ValueError(f"candidate {key} lacks stable identity")
        matched = sorted(token for token in tokens if token in index)
        if matched:
            matched_labels = sorted(set().union(*(index[token] for token in matched)))
            labels.update(matched_labels)
            types.update(token.split(":", 1)[0] for token in matched)
            overlaps.append({"source_key": key, "reference_labels": matched_labels,
                             "match_tokens": matched})
        else:
            safe.append(row)
    report = {
        "schema_version": "clean-benchmark-overlap-v1",
        "candidate_sources": len(candidates),
        "safe_sources": len(safe),
        "overlap_sources": len(overlaps),
        "reference_rows": reference_counts,
        "overlap_sources_by_reference": dict(sorted(labels.items())),
        "match_tokens_by_type": dict(sorted(types.items())),
        "audio_accessed": False,
        "rights_inferred": False,
        "note": "Exact identity audit only; acoustic near-duplicates still need the separate fingerprint audit.",
    }
    return safe, overlaps, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--reference", action="append", required=True,
                        help="LABEL=JSONL; repeat for every benchmark/test manifest")
    parser.add_argument("--safe-out", type=Path, required=True)
    parser.add_argument("--overlap-out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    references = {}
    for spec in args.reference:
        label, separator, raw_path = spec.partition("=")
        if not separator or not label or not raw_path or label in references:
            raise ValueError(f"reference must be unique LABEL=PATH: {spec}")
        references[label] = list(read_jsonl(Path(raw_path)))
    safe, overlaps, report = audit(list(read_jsonl(args.candidates)), references)
    write_jsonl(args.safe_out, safe)
    write_jsonl(args.overlap_out, overlaps)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Benchmark overlap: {len(overlaps)} excluded, {len(safe)} remaining")


if __name__ == "__main__":
    main()
