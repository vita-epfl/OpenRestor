#!/usr/bin/env python3
"""Report curation decisions and rights without inventing human labels.

This report-only adapter joins a feature JSONL and a decision JSONL by
``source_key``.  It summarizes the primary passage and preserves the source
scope explicitly: a passage decision is not a whole-source validation.  Rights
and acoustic/content decisions remain independent.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            rows.append(row)
    return rows


def _index(rows: list[dict], path: Path) -> dict[str, dict]:
    result = {}
    for row in rows:
        key = str(row.get("source_key") or "")
        if not key:
            raise ValueError(f"missing source_key in {path}")
        if key in result:
            raise ValueError(f"duplicate source_key in {path}: {key}")
        result[key] = row
    return result


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _primary(feature: dict) -> dict:
    segments = feature.get("segments") or []
    if not segments:
        raise ValueError(f"source without segments: {feature.get('source_key')}")
    return segments[len(segments) // 2]


def _metrics(segment: dict) -> dict:
    acoustic = segment.get("acoustic") or {}
    aesthetics = segment.get("aesthetics") or {}
    ast = (segment.get("ast") or {}).get("interest_labels") or {}
    clap = (segment.get("clap") or {}).get("group_scores") or {}
    produced = [clap.get(name) for name in ("produced_music", "legitimate_electronic_music")]
    produced = [float(value) for value in produced if _finite(value) is not None]
    music = max(produced) if produced else None
    nonmusic = _finite(clap.get("non_music"))
    rudimentary = _finite(clap.get("rudimentary_synthetic"))
    return {
        "PQ": _finite(aesthetics.get("PQ")),
        "PC": _finite(aesthetics.get("PC")),
        "CE": _finite(aesthetics.get("CE")),
        "CU": _finite(aesthetics.get("CU")),
        "ast_music": _finite(ast.get("Music")),
        "ast_speech": _finite(ast.get("Speech")),
        "clap_music_minus_nonmusic": music - nonmusic if music is not None and nonmusic is not None else None,
        "clap_music_minus_rudimentary": music - rudimentary if music is not None and rudimentary is not None else None,
        "bandwidth_hz": _finite(acoustic.get("bandwidth_hz")),
        "clipped_sample_ratio": _finite(acoustic.get("clipped_sample_ratio_channels")),
        "dynamic_range_db": _finite(acoustic.get("dynamic_range_db")),
        "rolloff_85_hz": _finite(acoustic.get("rolloff_85_hz")),
        "hiss_proxy": _finite(acoustic.get("hiss_proxy")),
        "hum_tonality_proxy": _finite(acoustic.get("hum_tonality_proxy")),
    }


def _passage_metrics(feature: dict) -> dict:
    """Summarize every sampled passage, preserving intra-source variation."""
    values_by_metric = collections.defaultdict(list)
    for segment in feature.get("segments") or []:
        for name, value in _metrics(segment).items():
            if value is not None:
                values_by_metric[name].append(value)
    result = {}
    for name, values in sorted(values_by_metric.items()):
        values = sorted(values)
        result[name] = {"n": len(values), "median": statistics.median(values),
                        "min": min(values), "max": max(values)}
    return result


def _metadata(feature: dict) -> dict:
    value = feature.get("metadata")
    return value if isinstance(value, dict) else {}


def _row(feature: dict, decision: dict) -> dict:
    if feature.get("source_key") != decision.get("source_key"):
        raise ValueError("feature/decision source key mismatch")
    primary = _primary(feature)
    metadata = _metadata(feature)
    rights = feature.get("rights") if isinstance(feature.get("rights"), dict) else {}
    return {
        "source_key": feature["source_key"],
        "dataset": feature.get("dataset"),
        "source_id": feature.get("source_id"),
        "audio_path": feature.get("audio_path"),
        "source_sha256": feature.get("source_sha256"),
        "title": metadata.get("title"),
        "creator": metadata.get("creator"),
        "genre": metadata.get("genre") or metadata.get("genres") or "[unknown]",
        "collection": metadata.get("collection") or "[unknown]",
        "member_name": metadata.get("member_name"),
        "duration_seconds": _finite(feature.get("duration_s") or feature.get("duration_seconds")),
        "segment_count": len(feature.get("segments") or []),
        "decision_scope": "source_decision_from_sampled_passages",
        "decision": decision.get("decision"),
        "clean_score": _finite(decision.get("clean_score")),
        "reasons": list(decision.get("reasons") or []),
        "accepted_segment_ids": list(decision.get("accepted_segment_ids") or []),
        "primary_metrics": _metrics(primary),
        "passage_metrics": _passage_metrics(feature),
        "technical_candidate": feature.get("technical_candidate") is True,
        "provenance_candidate": feature.get("provenance_candidate") is True,
        "redistributable_candidate": feature.get("redistributable_candidate") is True,
        "rights_status": rights.get("rights_status") or rights.get("review_status") or "unknown",
        "provenance_approved": rights.get("provenance_approved") is True,
        "redistribution_approved": rights.get("redistribution_approved") is True,
        "license_label": rights.get("license_label"),
    }


def _group(rows: list[dict], field: str) -> dict[str, dict]:
    groups = collections.defaultdict(list)
    for row in rows:
        value = row.get(field)
        if isinstance(value, list):
            value = "; ".join(str(item) for item in value)
        groups[str(value or "[unknown]")].append(row)
    result = {}
    for name, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        result[name] = {
            "sources": len(members),
            "auto_accept": sum(row["decision"] == "auto_accept" for row in members),
            "manual_review": sum(row["decision"] == "manual_review" for row in members),
            "auto_reject": sum(row["decision"] == "auto_reject" for row in members),
            "provenance_approved": sum(row["provenance_approved"] for row in members),
        }
    return result


def _summary(rows: list[dict]) -> dict:
    decisions = collections.Counter(str(row.get("decision") or "unknown") for row in rows)
    rights = collections.Counter(str(row.get("rights_status") or "unknown") for row in rows)
    metric_names = sorted({name for row in rows for name in row["primary_metrics"]})
    metric_summary = {}
    for name in metric_names:
        values = sorted(row["primary_metrics"][name] for row in rows
                        if row["primary_metrics"].get(name) is not None)
        if values:
            metric_summary[name] = {
                "n": len(values), "median": statistics.median(values),
                "min": min(values), "max": max(values),
            }
    return {
        "schema_version": "clean-curation-report-v1",
        "sources": len(rows),
        "decisions": dict(sorted(decisions.items())),
        "rights_status": dict(sorted(rights.items())),
        "technical_candidate": sum(row["technical_candidate"] for row in rows),
        "provenance_candidate": sum(row["provenance_candidate"] for row in rows),
        "redistributable_candidate": sum(row["redistributable_candidate"] for row in rows),
        "provenance_approved": sum(row["provenance_approved"] for row in rows),
        "redistribution_approved": sum(row["redistribution_approved"] for row in rows),
        "metric_summary_primary_passage": metric_summary,
        "by_dataset": _group(rows, "dataset"),
        "by_collection": _group(rows, "collection"),
        "by_creator": _group(rows, "creator"),
        "rights_and_audio_are_independent": True,
        "human_labels_inferred": False,
        "decision_scope": "source_decision_from_sampled_passages; not whole-source validation",
    }


def _markdown(rows: list[dict], summary: dict) -> str:
    lines = ["# Clean curation report", "",
             "This report is descriptive. It does not infer human labels or redistribution rights.",
             "Decisions are source-level aggregates from sampled passages, not full-source validation.", "",
             "## Summary", "",
             f"- Sources: {summary['sources']}",
             f"- Decisions: `{json.dumps(summary['decisions'], sort_keys=True)}`",
             f"- Redistributable candidates: {summary['redistributable_candidate']}",
             f"- Provenance approved: {summary['provenance_approved']}", "",
             "## Sources", "",
             "| Dataset | Source | Decision | Score | Segments | Reasons | Rights |", "| --- | --- | --- | ---: | ---: | --- | --- |"]
    for row in rows:
        reasons = ", ".join(row["reasons"]) or "—"
        score = "—" if row["clean_score"] is None else f"{row['clean_score']:.4f}"
        lines.append(f"| {row['dataset'] or '—'} | `{row['source_id']}` | `{row['decision'] or 'unknown'}` | {score} | {row['segment_count']} | {reasons} | {row['rights_status']} |")
    lines += ["", "## Scope", "", "The report keeps acoustic/content scoring separate from licence and provenance review."]
    return "\n".join(lines) + "\n"


def build(features_path: Path, decisions_path: Path) -> tuple[list[dict], dict]:
    features = _index(read_jsonl(features_path), features_path)
    decisions = _index(read_jsonl(decisions_path), decisions_path)
    if set(features) != set(decisions):
        missing_features = sorted(set(decisions) - set(features))
        missing_decisions = sorted(set(features) - set(decisions))
        raise ValueError(f"feature/decision keys differ: missing_features={missing_features[:3]}, missing_decisions={missing_decisions[:3]}")
    rows = [_row(features[key], decisions[key]) for key in sorted(features)]
    return rows, _summary(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="JSON report")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown report")
    args = parser.parse_args()
    rows, summary = build(args.features, args.decisions)
    payload = {"summary": summary, "sources": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(_markdown(rows, summary), encoding="utf-8")
    print(f"Reported {len(rows)} sources: {args.out}")


if __name__ == "__main__":
    main()
