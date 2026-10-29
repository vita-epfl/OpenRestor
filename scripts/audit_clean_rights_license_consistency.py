#!/usr/bin/env python3
"""Audit declared licence labels against their exact URLs.

This is a metadata-only consistency check.  A matching CC label and URL are
still only a provenance lead: the command never approves redistribution,
derivatives, commercial use or source originality.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openrestor.rights import cc_terms  # noqa: E402


LABEL_RE = re.compile(
    r"^(?:CC[-\s]*)?(?P<code>0|BY(?:[- ]NC)?(?:[- ]ND|-SA)?)[- ](?P<version>\d+\.\d+)$",
    re.IGNORECASE,
)
URL_LABEL_RE = re.compile(r"^https?://creativecommons\.org/", re.IGNORECASE)


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {path}:{number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{number}")
            rows.append(row)
    return rows


def _label_terms(value: object) -> str | None:
    label = str(value or "").strip()
    if not label:
        return None
    if URL_LABEL_RE.match(label):
        return cc_terms(label).get("license_label")
    match = LABEL_RE.fullmatch(label.replace("_", "-"))
    if not match:
        return None
    code = match.group("code").upper().replace(" ", "-")
    return f"CC0 {match.group('version')}" if code == "0" else f"CC {code} {match.group('version')}"


def audit(rows: list[dict]) -> tuple[list[dict], dict]:
    seen: set[str] = set()
    audited: list[dict] = []
    status_counts = collections.Counter()
    match_counts = collections.Counter()
    by_dataset = collections.defaultdict(collections.Counter)
    for row in rows:
        key = str(row.get("source_key") or "")
        if not key:
            raise ValueError("every row needs source_key")
        if key in seen:
            raise ValueError(f"duplicate source_key: {key}")
        seen.add(key)
        label = row.get("license_label")
        url = row.get("license_url")
        parsed = cc_terms(str(url)) if url not in (None, "") else {}
        url_label = parsed.get("license_label")
        declared_label = _label_terms(label)
        if url in (None, ""):
            url_status = "missing_url"
        elif url_label is None:
            url_status = "unknown_url"
        else:
            url_status = "recognized_cc"
        if declared_label is None:
            label_status = "missing_or_unrecognized_label"
        elif url_label is None:
            label_status = "label_without_recognized_url"
        elif declared_label != url_label:
            label_status = "label_url_conflict"
        else:
            label_status = "label_url_match"
        if url_status == "recognized_cc" and label_status == "label_url_match":
            consistency = "consistent_cc"
        elif url_status == "missing_url":
            consistency = "missing_url"
        elif url_status == "unknown_url":
            consistency = "unknown_url"
        else:
            consistency = "contradictory_label_url"
        result = {
            "source_key": key,
            "dataset": row.get("dataset"),
            "license_label": label,
            "license_url": url,
            "normalized_label": declared_label,
            "url_license_label": url_label,
            "url_status": url_status,
            "label_status": label_status,
            "consistency": consistency,
            "rights_review_status": row.get("review_status"),
            "technical_candidate": row.get("technical_candidate") is True,
            "provenance_candidate": row.get("provenance_candidate") is True,
        }
        audited.append(result)
        status_counts[consistency] += 1
        match_counts[label_status] += 1
        by_dataset[str(row.get("dataset") or "[unknown]")][consistency] += 1
    report = {
        "schema_version": "clean-rights-license-consistency-v1",
        "source_count": len(rows),
        "consistent_cc": status_counts["consistent_cc"],
        "missing_url": status_counts["missing_url"],
        "unknown_url": status_counts["unknown_url"],
        "contradictory_label_url": status_counts["contradictory_label_url"],
        "label_status": dict(sorted(match_counts.items())),
        "by_dataset": {key: dict(sorted(value.items()))
                        for key, value in sorted(by_dataset.items())},
        "audio_accessed": False,
        "rights_inferred": False,
        "approvals_changed": False,
        "note": "Consistency is not provenance or redistribution approval.",
    }
    return audited, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    audited, report = audit(read_jsonl(args.input))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                  for row in audited), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
