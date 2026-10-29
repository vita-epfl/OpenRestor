#!/usr/bin/env python3
"""Export rights-profile views of a normalized clean manifest.

This command is metadata-only: it never copies audio and never turns a
dataset-level licence claim into release approval.  Rows lacking a complete,
approved per-asset rights record are written only to the blocked report.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openrestor.rights import media_key, pack_family


PROFILES = ("public_research", "public_commercial", "internal_research", "blocked")


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {path}:{number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"manifest row is not an object at {path}:{number}")
            yield row


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                      for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def rights_record(row: dict) -> dict:
    rights = row.get("rights")
    if not isinstance(rights, dict):
        raise ValueError("missing rights object")
    dataset = str(row.get("dataset") or "")
    source_id = str(row.get("source_id") or "")
    if not dataset or not source_id:
        raise ValueError("missing dataset/source_id")
    result = {
        "media_key": media_key(dataset, source_id),
        "dataset": dataset,
        "source_id": source_id,
        "license_label": rights.get("license_label"),
        "license_url": rights.get("license_url"),
        "attribution": rights.get("attribution"),
        "evidence_url": rights.get("evidence_url") or rights.get("evidence_source"),
        "evidence_date": rights.get("evidence_date"),
        "review_status": rights.get("review_status") or rights.get("status") or "pending",
        "reviewer": rights.get("reviewer"),
        "allow_commercial": rights.get("allow_commercial"),
        "allow_redistribution": rights.get("allow_redistribution"),
        "allow_derivatives": rights.get("allow_derivatives"),
        "share_alike": rights.get("share_alike"),
        "redistribution_approved": rights.get("redistribution_approved"),
    }
    # Provenance and redistribution approval are deliberately separate from the
    # acoustic candidate flag and from one another.
    result["provenance_approved"] = rights.get("provenance_approved")
    result["redistribution_approved"] = rights.get("redistribution_approved")
    return result


def classify(row: dict) -> tuple[str, str | None, dict | None]:
    """Return profile, pack family, and validated rights record."""
    try:
        record = rights_record(row)
        if record.get("provenance_approved") is not True:
            return "blocked", None, record
        family = pack_family(record, "commercial_compatible")
        if family is not None:
            return "public_commercial", family, record
        family = pack_family(record, "academic_noncommercial")
        if family is not None:
            return "public_research", family, record
        if record.get("review_status") == "approved" and row.get("audio_path"):
            return "internal_research", None, record
        return "blocked", None, record
    except (TypeError, ValueError, KeyError) as error:
        return "blocked", f"invalid_or_incomplete_rights:{type(error).__name__}", None


def filter_rows(rows: list[dict], require_technical: bool = True) -> tuple[dict[str, list[dict]], dict]:
    outputs = {profile: [] for profile in PROFILES}
    blocked_reasons = collections.Counter()
    seen: set[str] = set()
    for row in rows:
        key = f"{row.get('dataset')}:{row.get('source_id')}"
        if key in seen:
            raise ValueError(f"duplicate manifest source key: {key}")
        seen.add(key)
        if require_technical and row.get("technical_candidate") is not True:
            outputs["blocked"].append({**row, "rights_profile": "blocked",
                                        "blocked_reason": "technical_candidate_false"})
            blocked_reasons["technical_candidate_false"] += 1
            continue
        profile, family, record = classify(row)
        if profile == "blocked":
            reason = "rights_not_approved"
            if record is None:
                reason = "invalid_or_incomplete_rights"
            elif record.get("provenance_approved") is not True:
                reason = "provenance_not_approved"
            elif record.get("redistribution_approved") is not True:
                reason = "redistribution_not_approved"
            outputs[profile].append({**row, "rights_profile": profile,
                                     "blocked_reason": reason})
            blocked_reasons[reason] += 1
            continue
        outputs[profile].append({**row, "rights_profile": profile,
                                 "rights_family": family})
        if profile == "public_commercial":
            # Public profiles are eligibility views, not mutually exclusive
            # partitions: a commercially usable asset is also usable by a
            # noncommercial research recipient. The NC-only extension remains
            # absent from the commercial view.
            research_family = pack_family(record, "academic_noncommercial")
            if research_family is None:
                raise AssertionError("commercial eligibility must imply research eligibility")
            outputs["public_research"].append({**row, "rights_profile": "public_research",
                                               "rights_family": research_family})
    for profile in outputs:
        outputs[profile].sort(key=lambda row: f"{row.get('dataset')}:{row.get('source_id')}")
    report = {
        "schema_version": "clean-corpus-rights-profiles-v2",
        "input_sources": len(rows),
        "counts_by_profile": {profile: len(outputs[profile]) for profile in PROFILES},
        "unique_public_sources": len(outputs["public_research"]),
        "public_profile_overlap": len(outputs["public_commercial"]),
        "blocked_reasons": dict(sorted(blocked_reasons.items())),
        "require_technical": require_technical,
        "audio_copied": False,
        "rights_are_asset_level": True,
        "provenance_required": True,
        "note": "Acoustic acceptance and redistribution approval remain independent gates.",
    }
    return outputs, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--require-technical", action="store_true", default=True,
                        help="Require a verified technical candidate (default).")
    parser.add_argument("--allow-unverified-technical", action="store_false",
                        dest="require_technical",
                        help="Metadata triage only; never use this mode for a release profile.")
    args = parser.parse_args()
    rows = list(read_jsonl(args.input))
    outputs, report = filter_rows(rows, require_technical=args.require_technical)
    for profile, values in outputs.items():
        write_jsonl(args.out_dir / f"{profile}.jsonl", values)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False,
                                                       indent=2, sort_keys=True) + "\n",
                                                encoding="utf-8")
    print(f"Wrote rights profiles for {len(rows)} sources: {args.out_dir}")


if __name__ == "__main__":
    main()
