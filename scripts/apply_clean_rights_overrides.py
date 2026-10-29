#!/usr/bin/env python3
"""Apply reviewed rights overrides to a manifest without touching audio.

The input manifest is copied row by row.  Only the ``rights`` object, the
verified top-level source checksum, and a rights-review history entry can
change.  The command is deliberately fail-closed: malformed JSONL, duplicate
source keys, unknown override keys, and invalid approved records abort before
the output is written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path


DECISIONS = {"approved", "rejected", "pending"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROTECTED_OVERRIDE_FIELDS = {
    "dataset", "source_id", "audio_path", "metadata", "features", "segments",
    "split", "technical_candidate", "provenance_candidate",
    "redistributable_candidate", "lossless_status",
}


def read_jsonl(path: Path, label: str) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"{label} row {number} is not an object")
            rows.append(row)
    return rows


def _required_string(row: dict, field: str) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _validate_override(row: dict) -> None:
    key = _required_string(row, "media_key")
    if any(field in row for field in PROTECTED_OVERRIDE_FIELDS):
        fields = sorted(field for field in PROTECTED_OVERRIDE_FIELDS if field in row)
        raise ValueError(f"override {key} contains protected fields: {', '.join(fields)}")
    decision = _required_string(row, "review_status").lower()
    if decision not in DECISIONS:
        raise ValueError(f"override {key} has invalid review_status: {decision}")
    _required_string(row, "reviewer")
    evidence_date = _required_string(row, "evidence_date")
    if not DATE_RE.fullmatch(evidence_date):
        raise ValueError(f"override {key} evidence_date must use YYYY-MM-DD")
    if decision != "approved":
        return
    required = ("license_label", "license_url", "attribution", "evidence_url")
    for field in required:
        _required_string(row, field)
    if row.get("provenance_approved") is not True:
        raise ValueError(f"approved override {key} requires provenance_approved=true")
    if row.get("redistribution_approved") is not True:
        raise ValueError(f"approved override {key} requires redistribution_approved=true")
    source_sha256 = _required_string(row, "source_sha256").lower()
    if not SHA256_RE.fullmatch(source_sha256):
        raise ValueError(f"approved override {key} source_sha256 must be a 64-character SHA-256")


def _digest(row: dict) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _history_entry(old_rights: dict, override: dict, digest: str, label: str,
                   applied_at: str) -> dict:
    return {
        "label": label,
        "override_sha256": digest,
        "applied_at": applied_at,
        "previous_review_status": old_rights.get("review_status"),
        "new_review_status": override.get("review_status"),
        "reviewer": override.get("reviewer"),
        "evidence_date": override.get("evidence_date"),
    }


def apply_overrides(manifest: Path, overrides: Path, out: Path, report: Path,
                    history_label: str = "rights_review_override",
                    applied_at: str | None = None) -> dict:
    manifest_rows = read_jsonl(manifest, "manifest")
    override_rows = read_jsonl(overrides, "override")
    manifest_by_key: dict[str, dict] = {}
    for number, row in enumerate(manifest_rows, 1):
        key = str(row.get("source_key") or "").strip()
        if not key:
            raise ValueError(f"manifest row {number} lacks source_key")
        if key in manifest_by_key:
            raise ValueError(f"duplicate manifest source_key: {key}")
        manifest_by_key[key] = row

    overrides_by_key: dict[str, dict] = {}
    for number, row in enumerate(override_rows, 1):
        _validate_override(row)
        key = str(row["media_key"])
        if key in overrides_by_key:
            raise ValueError(f"duplicate override media_key: {key}")
        if key not in manifest_by_key:
            raise ValueError(f"override media_key is not in manifest: {key}")
        overrides_by_key[key] = row

    timestamp = applied_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("applied_at must be a non-empty string")
    output_rows: list[dict] = []
    applied = 0
    idempotent = 0
    before_status: dict[str, int] = {}
    after_status: dict[str, int] = {}
    for original in manifest_rows:
        row = dict(original)
        old_rights = row.get("rights")
        if old_rights is None:
            old_rights = {}
        if not isinstance(old_rights, dict):
            raise ValueError(f"manifest rights must be an object: {row['source_key']}")
        rights = dict(old_rights)
        key = row["source_key"]
        before_status[str(rights.get("review_status") or "unknown")] = \
            before_status.get(str(rights.get("review_status") or "unknown"), 0) + 1
        override = overrides_by_key.get(key)
        if override is not None:
            digest = _digest(override)
            history = rights.get("rights_review_history")
            if history is None:
                history = []
            if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
                raise ValueError(f"rights_review_history must be a list of objects: {key}")
            already_present = any(item.get("label") == history_label and
                                  item.get("override_sha256") == digest for item in history)
            for field, value in override.items():
                if field != "media_key":
                    rights[field] = value
            if not already_present:
                history = [*history, _history_entry(old_rights, override, digest,
                                                     history_label, timestamp)]
                applied += 1
            else:
                idempotent += 1
            rights["rights_review_history"] = history
            if override.get("source_sha256"):
                row["source_sha256"] = str(override["source_sha256"]).lower()
        row["rights"] = rights
        after = str(rights.get("review_status") or "unknown")
        after_status[after] = after_status.get(after, 0) + 1
        output_rows.append(row)

    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(out.name + ".tmp")
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                       for row in output_rows)
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, out)
    manifest_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    result = {
        "schema_version": "clean-rights-overrides-application-v1",
        "manifest": str(manifest),
        "overrides": str(overrides),
        "output": str(out),
        "input_sources": len(manifest_rows),
        "override_rows": len(override_rows),
        "applied_rows": applied,
        "idempotent_rows": idempotent,
        "unreviewed_rows": len(manifest_rows) - len(overrides_by_key),
        "before_review_status": dict(sorted(before_status.items())),
        "after_review_status": dict(sorted(after_status.items())),
        "output_sha256": manifest_digest,
        "audio_paths_changed": False,
        "audio_copied": False,
        "rights_are_not_inferred": True,
        "history_label": history_label,
        "applied_at": timestamp,
        "note": "Only reviewed rights fields and review history are changed; audio and curation scores are untouched.",
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--history-label", default="rights_review_override")
    parser.add_argument("--applied-at", help="Stable ISO timestamp for the history entry")
    args = parser.parse_args()
    result = apply_overrides(args.manifest, args.overrides, args.out, args.report,
                             history_label=args.history_label, applied_at=args.applied_at)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
