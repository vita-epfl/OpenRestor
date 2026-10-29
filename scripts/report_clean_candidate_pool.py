#!/usr/bin/env python3
"""Summarize a clean-corpus candidate manifest without implying permission.

The report is metadata-only. Missing duration, format, creator and rights stay
explicitly unknown; no catalogue row is promoted to an audio candidate by this
command.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{number}")
            rows.append(row)
    return rows


def _metadata(row: dict) -> dict:
    return row.get("metadata") if isinstance(row.get("metadata"), dict) else {}


def _value(row: dict, *names: str):
    metadata = _metadata(row)
    rights = row.get("rights") if isinstance(row.get("rights"), dict) else {}
    for name in names:
        for container in (row, metadata, rights):
            value = container.get(name)
            if value not in (None, "", [], {}):
                return value
    return None


def _labels(value, *, split_semicolon: bool = False) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = [item for item in value if item not in (None, "")]
    elif value in (None, ""):
        values = []
    else:
        values = [value]
    labels = []
    for item in values:
        pieces = str(item).split(";") if split_semicolon else [str(item)]
        labels.extend(piece.strip() for piece in pieces if piece.strip())
    return labels or ["[unknown]"]


def _distribution(rows: list[dict], *names: str, split_semicolon: bool = False) -> dict[str, int]:
    counter = collections.Counter()
    for row in rows:
        counter.update(_labels(_value(row, *names), split_semicolon=split_semicolon))
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0].casefold())))


def _concentration(distribution: dict[str, int]) -> dict:
    groups = len(distribution)
    total = sum(distribution.values())
    if not total or not groups:
        return {"groups": groups, "unknown_items": distribution.get("[unknown]", 0),
                "top_1_count": 0, "top_1_share": 0.0, "top_5_share": 0.0,
                "effective_groups": 0.0}
    counts = sorted(distribution.values(), reverse=True)
    probabilities = [count / total for count in counts]
    return {
        "groups": groups,
        "unknown_items": distribution.get("[unknown]", 0),
        "top_1_count": counts[0],
        "top_1_share": round(counts[0] / total, 6),
        "top_5_share": round(sum(counts[:5]) / total, 6),
        "effective_groups": round(1.0 / sum(probability * probability for probability in probabilities), 3),
    }


def summarize(rows: list[dict]) -> dict:
    keys = [str(row.get("source_key") or "") for row in rows]
    if any(not key for key in keys):
        raise ValueError("every row needs source_key")
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate source_key")
    known_durations = [row.get("duration_seconds") for row in rows
                       if row.get("duration_seconds") is not None]
    duration_seconds = sum(float(value) for value in known_durations)
    # Zenodo ZIP member sizes live in metadata, while other adapters may keep
    # them at the top level. Missing sizes are unknown, not zero-byte files.
    known_sizes = [_value(row, "member_uncompressed_size_bytes", "size_bytes") for row in rows]
    estimated_bytes = sum(int(value) for value in known_sizes if value is not None)
    rights = [row.get("rights") if isinstance(row.get("rights"), dict) else {} for row in rows]
    formats = _distribution(rows, "original_format", "format")
    status = collections.Counter(str(right.get("review_status") or right.get("rights_status") or "unknown")
                                 for right in rights)
    source_status = collections.Counter(str(right.get("source_status") or "unknown") for right in rights)
    counts = {
        "technical_candidate": sum(row.get("technical_candidate") is True for row in rows),
        "provenance_candidate": sum(row.get("provenance_candidate") is True for row in rows),
        "redistributable_candidate": sum(row.get("redistributable_candidate") is True for row in rows),
        "clean_lossless": sum(row.get("lossless_status") == "clean_lossless" for row in rows),
        "clean_lossy_hq": sum(row.get("lossless_status") == "clean_lossy_hq" for row in rows),
    }
    distributions = {
        "dataset": _distribution(rows, "dataset"),
        "license": _distribution(rows, "license_label"),
        "format": formats,
        "genre": _distribution(rows, "genre", "genres", "tags", split_semicolon=True),
        "collection": _distribution(rows, "collection"),
        "creator": _distribution(rows, "creator", "artist", "artist_name", "composer"),
    }
    return {
        "schema_version": "clean-candidate-pool-report-v1",
        "source_count": len(rows),
        "estimated_hours": round(duration_seconds / 3600, 6),
        "duration_known_sources": len(known_durations),
        "duration_unknown_sources": len(rows) - len(known_durations),
        "estimated_uncompressed_bytes": estimated_bytes,
        "size_known_sources": sum(value is not None for value in known_sizes),
        "size_unknown_sources": sum(value is None for value in known_sizes),
        "candidate_counts": counts,
        "rights_review_status": dict(sorted(status.items())),
        "source_status": dict(sorted(source_status.items())),
        "distributions": distributions,
        "concentration": {name: _concentration(values)
                          for name, values in distributions.items()},
        "audio_accessed": False,
        "rights_inferred": False,
        "unknowns_are_explicit": True,
        "note": "Catalogue rows, technical candidates and redistributable candidates are separate; missing fields are not approvals.",
    }


def markdown(report: dict, source: Path) -> str:
    lines = [f"# Clean candidate pool report\n\n", f"Input: `{source}`\n\n",
             "This is a metadata-only report; it does not grant rights or validate audio.\n\n",
             "## Summary\n\n", f"- Sources: **{report['source_count']:,}**\n",
             f"- Known duration from metadata: **{report['estimated_hours']:.3f} h** "
             f"({report['duration_known_sources']:,}/{report['source_count']:,} sources)\n",
             f"- Known uncompressed bytes: **{report['estimated_uncompressed_bytes']:,}** "
             f"({report['size_known_sources']:,}/{report['source_count']:,} sources; "
             "remaining sizes unknown)\n",
             f"- Technical candidates: **{report['candidate_counts']['technical_candidate']:,}**\n",
             f"- Provenance candidates: **{report['candidate_counts']['provenance_candidate']:,}**\n",
             f"- Redistributable candidates: **{report['candidate_counts']['redistributable_candidate']:,}**\n",
             "\n## Distributions\n\n"]
    for name, values in report["distributions"].items():
        lines.append(f"### {name}\n")
        lines.append("| Value | Count |\n| --- | ---: |\n")
        lines.extend(f"| {value} | {count:,} |\n" for value, count in list(values.items())[:20])
        lines.append("\n")
    lines.append("## Concentration\n\n")
    lines.append("| Dimension | Groups | Top 1 share | Top 5 share | Effective groups | Unknown |\n| --- | ---: | ---: | ---: | ---: | ---: |\n")
    for name, values in report["concentration"].items():
        lines.append(f"| {name} | {values['groups']:,} | {values['top_1_share']:.1%} | "
                     f"{values['top_5_share']:.1%} | {values['effective_groups']:.1f} | "
                     f"{values['unknown_items']:,} |\n")
    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    rows = read_jsonl(args.input)
    report = summarize(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown(report, args.input), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
