#!/usr/bin/env python3
"""Resolve Zenodo record metadata without downloading dataset files.

The resolver is intentionally metadata-only.  It records the archive-level
licence and checksums, but never opens an audio archive and never marks an
asset as technically or legally releasable.  Output is JSONL and is updated
after each record so timeouts do not discard completed resolutions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


LICENSE_URLS = {
    "cc0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc-by-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "cc-by-sa-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "cc-by-nc-4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
    "cc-by-nc-sa-4.0": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
}


def fetch_record(record: str, timeout: float = 30.0) -> dict:
    """Fetch one official Zenodo API record; redirects are followed by urllib."""
    request = Request(
        f"https://zenodo.org/api/records/{record}",
        headers={"Accept": "application/json", "User-Agent": "OpenRestore-metadata-audit/1"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _license_id(metadata: dict) -> str | None:
    value = metadata.get("license")
    if isinstance(value, dict):
        value = value.get("id") or value.get("title")
    return str(value) if value not in (None, "") else None


def summarize_record(payload: dict, requested_record: str | None = None,
                     evidence_date: str | None = None) -> dict:
    """Convert a Zenodo response into a fail-closed, metadata-only row."""
    metadata = payload.get("metadata") or {}
    record_id = payload.get("id")
    license_id = _license_id(metadata)
    files = []
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            continue
        links = item.get("links") or {}
        files.append({
            "key": item.get("key"),
            "size_bytes": item.get("size"),
            "checksum": item.get("checksum"),
            # These are archive/API URLs only; this script does not request them.
            "download_url": links.get("content") or links.get("self"),
        })
    status = payload.get("status")
    access_right = metadata.get("access_right")
    published = status == "published"
    has_license = bool(license_id)
    rights_status = (
        "metadata_confirmed_pending_asset_review"
        if published and access_right == "open" and has_license
        else "metadata_incomplete_or_restricted"
    )
    total_bytes = sum(item["size_bytes"] for item in files
                      if isinstance(item.get("size_bytes"), int))
    return {
        "schema_version": "zenodo-metadata-resolution-v1",
        "requested_record": str(requested_record or record_id or ""),
        "record_id": record_id,
        "concept_record_id": payload.get("conceptrecid"),
        "record_url": f"https://zenodo.org/records/{record_id}" if record_id else None,
        "evidence_date": evidence_date,
        "doi": payload.get("doi"),
        "version": metadata.get("version"),
        "title": metadata.get("title"),
        "published": published,
        "access_right": access_right,
        "license_id": license_id,
        "license_url": LICENSE_URLS.get(license_id),
        "creators": metadata.get("creators") or [],
        "contributors": metadata.get("contributors") or [],
        "description": metadata.get("description"),
        "files": files,
        "file_count": len(files),
        "total_archive_bytes": total_bytes,
        "archive_members_inspected": False,
        "audio_downloaded": False,
        "metadata_only": True,
        "technical_candidate": False,
        "provenance_candidate": published and has_license,
        "redistributable_candidate": False,
        "rights_status": rights_status,
        "notes": (
            "Archive-level metadata and checksums only; audio members, source format, "
            "per-asset attribution and provenance still require review."
        ),
    }


def _write_jsonl(path: Path, rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(rows[key], ensure_ascii=False, sort_keys=True) + "\n"
                    for key in sorted(rows))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def resolve_records(records: list[str], out: Path, timeout: float = 30.0,
                    refresh: bool = False) -> list[dict]:
    """Resolve records incrementally; errors are retained as rows and do not abort the batch."""
    existing: dict[str, dict] = {}
    if out.exists():
        for number, line in enumerate(out.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid resolution JSONL at {out}:{number}") from error
            key = str(row.get("requested_record") or "")
            if key:
                existing[key] = row
    for record in records:
        key = str(record)
        if key in existing and not refresh:
            continue
        try:
            existing[key] = summarize_record(
                fetch_record(key, timeout=timeout), key,
                datetime.now(timezone.utc).date().isoformat(),
            )
        except Exception as error:  # retain progress across HTTP errors/timeouts
            existing[key] = {
                "schema_version": "zenodo-metadata-resolution-v1",
                "requested_record": key,
                "metadata_only": True,
                "audio_downloaded": False,
                "technical_candidate": False,
                "provenance_candidate": False,
                "redistributable_candidate": False,
                "rights_status": "resolution_error",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        _write_jsonl(out, existing)
    return [existing[str(record)] for record in records]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="append", required=True,
                        help="Zenodo record or concept record ID; may be repeated")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--refresh", action="store_true",
                        help="Re-query records already present in the output")
    args = parser.parse_args()
    if len(set(args.record)) != len(args.record):
        raise SystemExit("duplicate --record values are not allowed")
    rows = resolve_records(args.record, args.out, timeout=args.timeout, refresh=args.refresh)
    print(f"Resolved {len(rows)} Zenodo records (metadata only): {args.out}")


if __name__ == "__main__":
    main()
