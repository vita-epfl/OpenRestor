#!/usr/bin/env python3
"""Select one preferred representation from acoustic duplicate groups.

This is a metadata-only post-processing step. It never deletes or copies audio,
changes rights, or changes the underlying curation decisions. Candidate rows
from sources that are acoustically duplicated are grouped using the report from
``audit_clean_audio_duplicates.py``; a deterministic asset-role preference
chooses the representation retained for a clean-pool manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_ROLE_ORDER = (
    "full_mix_stereo_master",
    "full_mix_example",
    "full_mix_immersive_master",
    "isolated_stem_mixed",
    "isolated_stem_mixed_dry",
    "isolated_stem_raw",
)


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            yield row


def _role(row: dict) -> str | None:
    metadata = row.get("metadata")
    return metadata.get("asset_role") if isinstance(metadata, dict) else None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _jsonl_text(rows: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def select(candidates: list[dict], dedup_rows: list[dict],
           role_order: tuple[str, ...] = DEFAULT_ROLE_ORDER) -> tuple[list[dict], dict]:
    candidate_sources = {str(row.get("source_key") or "") for row in candidates}
    if "" in candidate_sources:
        raise ValueError("candidate row lacks source_key")
    groups: dict[str, set[str]] = {}
    source_group: dict[str, str] = {}
    for row in dedup_rows:
        source = str(row.get("source_key") or "")
        group = str(row.get("acoustic_dedup_group_id") or "")
        members = row.get("acoustic_duplicate_source_keys") or []
        if not source or not group or not isinstance(members, list):
            raise ValueError("dedup row lacks group metadata")
        members_set = {str(value) for value in members}
        if source not in members_set:
            raise ValueError(f"dedup row source is absent from its group: {source}")
        if group in groups and groups[group] != members_set:
            raise ValueError(f"inconsistent duplicate group: {group}")
        groups[group] = members_set
        for member in members_set:
            previous = source_group.get(member)
            if previous and previous != group:
                raise ValueError(f"source belongs to multiple duplicate groups: {member}")
            source_group[member] = group

    role_rank = {role: index for index, role in enumerate(role_order)}
    candidate_by_source: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        candidate_by_source[str(row["source_key"])].append(row)

    selected_sources: set[str] = set()
    excluded_sources: dict[str, str] = {}
    group_choices = []
    for group, members in sorted(groups.items()):
        present = sorted(members & candidate_sources)
        if not present:
            continue
        chosen = min(present, key=lambda source: (
            role_rank.get(next((_role(row) for row in candidate_by_source[source]
                               if _role(row) is not None), None), len(role_order)),
            source,
        ))
        selected_sources.add(chosen)
        for source in present:
            if source != chosen:
                excluded_sources[source] = f"duplicate_group:{group};preferred:{chosen}"
        group_choices.append({"group": group, "candidates": present,
                              "selected": chosen,
                              "selected_role": next((_role(row) for row in candidate_by_source[chosen]
                                                      if _role(row) is not None), None)})

    # Sources absent from a duplicate report pass through unchanged.
    selected_sources.update(candidate_sources - set(source_group))
    output = [row for row in candidates if str(row["source_key"]) in selected_sources]
    output.sort(key=lambda row: (str(row.get("source_key")), str(row.get("segment_id"))))
    report = {
        "schema_version": "clean-deduplicated-candidates-v1",
        "input_segments": len(candidates),
        "output_segments": len(output),
        "input_sources": len(candidate_sources),
        "output_sources": len(selected_sources),
        "excluded_sources": len(excluded_sources),
        "excluded_source_reasons": dict(sorted(excluded_sources.items())),
        "duplicate_groups_considered": len(group_choices),
        "group_choices": group_choices,
        "selected_roles": dict(sorted(Counter(_role(row) or "[unknown]"
                                                for row in output).items())),
        "role_order": list(role_order),
        "audio_copied": False,
        "rights_changed": False,
        "human_verification_required": True,
        "note": "Acoustic duplicate groups are candidates; the role preference is deterministic but not legal or scientific validation.",
    }
    return output, report


def write_selection(candidates_path: Path, dedup_path: Path, out_path: Path,
                    report_path: Path,
                    role_order: tuple[str, ...] = DEFAULT_ROLE_ORDER) -> dict:
    """Write a reproducible selection and report, including input/output hashes."""
    candidates_bytes = candidates_path.read_bytes()
    dedup_bytes = dedup_path.read_bytes()
    candidates = list(read_jsonl(candidates_path))
    dedup_rows = list(read_jsonl(dedup_path))
    output, report = select(candidates, dedup_rows, role_order)
    output_text = _jsonl_text(output)
    report.update({
        "input_candidates_path": str(candidates_path),
        "input_candidates_sha256": _sha256_bytes(candidates_bytes),
        "input_dedup_path": str(dedup_path),
        "input_dedup_sha256": _sha256_bytes(dedup_bytes),
        "output_sha256": _sha256_bytes(output_text.encode("utf-8")),
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output_text, encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                      sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--dedup", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--role-order", default=",".join(DEFAULT_ROLE_ORDER))
    args = parser.parse_args()
    role_order = tuple(value.strip() for value in args.role_order.split(",") if value.strip())
    report = write_selection(args.candidates, args.dedup, args.out, args.report, role_order)
    print(f"Selected {report['output_segments']} deduplicated candidate segments from {report['output_sources']} sources")


if __name__ == "__main__":
    main()
