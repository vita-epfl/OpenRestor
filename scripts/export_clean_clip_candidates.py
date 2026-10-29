#!/usr/bin/env python3
"""Export deterministic clean-clip candidates from cached features and decisions.

This command is metadata-only: it never copies or downloads audio and never
infers redistribution rights from an acoustic decision.  A row represents one
sampled segment, not validation of the complete source.  Segments from a
``manual_review`` source are retained only when the source decision is included
explicitly and remain marked as requiring source-level review.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from openrestor.curation.features import read_jsonl, write_jsonl_atomic


SOURCE_DECISIONS = {"auto_accept", "manual_review", "auto_reject"}
SEGMENT_DECISIONS = {"auto_accept", "manual_review", "auto_reject"}


def _index(path: Path) -> dict[str, dict]:
    rows = list(read_jsonl(path))
    result: dict[str, dict] = {}
    for line_number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
        key = str(row.get("source_key") or "")
        if not key:
            raise ValueError(f"missing source_key at {path}:{line_number}")
        if key in result:
            raise ValueError(f"duplicate source_key in {path}: {key}")
        result[key] = row
    return result


def _segment_index(row: dict, *, field: str) -> dict[str, dict]:
    segments = row.get("segments") or []
    if not isinstance(segments, list):
        raise ValueError(f"{field} segments must be a list for {row.get('source_key')}")
    result: dict[str, dict] = {}
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError(f"{field} segment is not an object for {row.get('source_key')}")
        segment_id = str(segment.get("segment_id") or "")
        if not segment_id:
            raise ValueError(f"{field} segment lacks segment_id for {row.get('source_key')}")
        if segment_id in result:
            raise ValueError(f"duplicate segment_id in {field}: {segment_id}")
        result[segment_id] = segment
    return result


def _rights_gate(rights: object) -> tuple[bool, str]:
    if not isinstance(rights, dict):
        return False, "missing_rights_object"
    if rights.get("provenance_approved") is not True:
        return False, "provenance_not_approved"
    if rights.get("redistribution_approved") is not True:
        return False, "redistribution_not_approved"
    if rights.get("allow_redistribution") is not True:
        return False, "allow_redistribution_not_true"
    if rights.get("allow_derivatives") is not True:
        return False, "allow_derivatives_not_true"
    return True, "approved_asset_level_rights"


def export_candidates(features_path: Path, decisions_path: Path,
                       *, source_decisions: set[str] | None = None,
                       segment_decision: str = "auto_accept",
                       exclude_asset_roles: set[str] | None = None) -> tuple[list[dict], dict]:
    """Join feature and decision caches and export accepted sampled segments."""
    allowed_sources = {"auto_accept", "manual_review"} if source_decisions is None else set(source_decisions)
    if not allowed_sources or not allowed_sources <= SOURCE_DECISIONS:
        raise ValueError(f"invalid source decisions: {sorted(allowed_sources)}")
    if segment_decision not in SEGMENT_DECISIONS:
        raise ValueError(f"invalid segment decision: {segment_decision}")

    features = _index(features_path)
    decisions = _index(decisions_path)
    if set(features) != set(decisions):
        missing_features = sorted(set(decisions) - set(features))
        missing_decisions = sorted(set(features) - set(decisions))
        raise ValueError(
            "feature/decision source keys differ: "
            f"missing_features={missing_features[:3]}, "
            f"missing_decisions={missing_decisions[:3]}"
        )

    rows: list[dict] = []
    excluded_asset_role_counts: collections.Counter[str] = collections.Counter()
    source_decision_counts: collections.Counter[str] = collections.Counter()
    rights_gate_counts: collections.Counter[str] = collections.Counter()
    selected_sources: set[str] = set()
    for key in sorted(features):
        feature = features[key]
        decision = decisions[key]
        if feature.get("source_key") != decision.get("source_key"):
            raise ValueError(f"feature/decision key mismatch for {key}")
        source_decision = str(decision.get("decision") or "")
        if source_decision not in SOURCE_DECISIONS:
            raise ValueError(f"invalid source decision for {key}: {source_decision}")
        source_decision_counts[source_decision] += 1

        feature_segments = _segment_index(feature, field="feature")
        decision_segments = _segment_index(decision, field="decision")
        if set(feature_segments) != set(decision_segments):
            raise ValueError(f"feature/decision segment keys differ for {key}")

        accepted_ids = decision.get("accepted_segment_ids")
        if accepted_ids is None:
            accepted_ids = [segment_id for segment_id, segment in decision_segments.items()
                            if segment.get("decision") == segment_decision]
        if not isinstance(accepted_ids, list):
            raise ValueError(f"accepted_segment_ids must be a list for {key}")
        if len(set(accepted_ids)) != len(accepted_ids):
            raise ValueError(f"duplicate accepted_segment_ids for {key}")
        unknown = sorted(set(accepted_ids) - set(feature_segments))
        if unknown:
            raise ValueError(f"accepted segment absent from features for {key}: {unknown[0]}")

        if source_decision not in allowed_sources:
            continue
        rights = feature.get("rights") if isinstance(feature.get("rights"), dict) else {}
        metadata = feature.get("metadata") if isinstance(feature.get("metadata"), dict) else {}
        asset_role = metadata.get("asset_role")
        if asset_role and asset_role in (exclude_asset_roles or set()):
            excluded_asset_role_counts[str(asset_role)] += len(accepted_ids)
            continue
        rights_ok, rights_reason = _rights_gate(rights)
        commercial_ok = rights_ok and rights.get("allow_commercial") is True
        rights_gate_counts["public_research" if rights_ok else rights_reason] += len(accepted_ids)
        if commercial_ok:
            rights_gate_counts["public_commercial"] += len(accepted_ids)
        for segment_id in sorted(accepted_ids):
            scored = decision_segments[segment_id]
            if scored.get("decision") != segment_decision:
                raise ValueError(
                    f"accepted_segment_ids contains {segment_id} with decision "
                    f"{scored.get('decision')!r}, expected {segment_decision!r}"
                )
            segment = feature_segments[segment_id]
            selected_sources.add(key)
            rows.append({
                "schema_version": "clean-clip-candidates-v1",
                "candidate_scope": "sampled_segment_candidate",
                "source_validation_required": True,
                "source_key": key,
                "dataset": feature.get("dataset"),
                "source_id": feature.get("source_id"),
                "audio_path": feature.get("audio_path"),
                "source_sha256": feature.get("source_sha256"),
                "clip_path": segment.get("clip_path"),
                "segment_id": segment_id,
                "start_s": segment.get("start_s"),
                "duration_s": segment.get("duration_s"),
                "sample_rate": feature.get("sample_rate"),
                "format": feature.get("format"),
                "lossless_status": feature.get("lossless_status"),
                "metadata": {
                    "title": metadata.get("title"),
                    "creator": metadata.get("creator"),
                    "genre": metadata.get("genre") or metadata.get("genres"),
                    "collection": metadata.get("collection"),
                    "asset_role": metadata.get("asset_role"),
                },
                "source_decision": source_decision,
                "source_clean_score": decision.get("clean_score"),
                "source_reasons": list(decision.get("reasons") or []),
                "segment_decision": scored.get("decision"),
                "segment_clean_score": scored.get("clean_score"),
                "segment_reasons": list(scored.get("reasons") or []),
                "rights_gate_passed": rights_ok,
                "rights_gate_reason": rights_reason,
                "public_research_eligible": rights_ok,
                "public_commercial_eligible": commercial_ok,
                "rights": rights,
                "rights_status": rights.get("rights_status") or rights.get("review_status") or "unknown",
                "provenance_approved": rights.get("provenance_approved") is True,
                "redistribution_approved": rights.get("redistribution_approved") is True,
                "technical_candidate": feature.get("technical_candidate") is True,
                "provenance_candidate": feature.get("provenance_candidate") is True,
                "redistributable_candidate": feature.get("redistributable_candidate") is True,
            })

    rows.sort(key=lambda row: (str(row.get("dataset") or ""), str(row.get("source_id") or ""), row["segment_id"]))
    rights_gate_counts.setdefault("public_research", 0)
    rights_gate_counts.setdefault("public_commercial", 0)
    summary = {
        "schema_version": "clean-clip-candidate-summary-v1",
        "features_sources": len(features),
        "decision_sources": len(decisions),
        "source_decisions_allowed": sorted(allowed_sources),
        "segment_decision": segment_decision,
        "selected_sources": len(selected_sources),
        "selected_segments": len(rows),
        "source_decisions": dict(sorted(source_decision_counts.items())),
        "rights_gate_by_selected_segment": dict(sorted(rights_gate_counts.items())),
        "excluded_asset_role_segments": dict(sorted(excluded_asset_role_counts.items())),
        "rights_inferred": False,
        "audio_copied": False,
        "scope": "sampled_segments_only; source validation and rights approval remain separate",
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--source-decisions", default="auto_accept,manual_review",
                        help="comma-separated source decisions to retain")
    parser.add_argument("--segment-decision", choices=sorted(SEGMENT_DECISIONS), default="auto_accept")
    parser.add_argument("--exclude-asset-roles",
                        default="isolated_stem_raw,isolated_stem_mixed,isolated_stem_mixed_dry",
                        help="comma-separated metadata asset roles excluded from clean candidates")
    args = parser.parse_args()
    source_decisions = {value.strip() for value in args.source_decisions.split(",") if value.strip()}
    rows, summary = export_candidates(args.features, args.decisions,
                                      source_decisions=source_decisions,
                                      segment_decision=args.segment_decision,
                                      exclude_asset_roles={value.strip() for value in args.exclude_asset_roles.split(",")
                                                           if value.strip()})
    write_jsonl_atomic(args.out, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(f"Exported {len(rows)} sampled clip candidates from {summary['selected_sources']} sources")


if __name__ == "__main__":
    main()
