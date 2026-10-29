#!/usr/bin/env python3
"""Prepare a metadata-only common manifest from the IAMD Archive audit.

The Phase 1 resolver only proves that Archive metadata was observed.  This
adapter deliberately emits no local ``audio_path`` and never grants release
rights: every row remains pending asset-level provenance and licence review.
It is therefore safe to run before any audio pilot download.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote


LOSSLESS_FORMATS = {"WAV", "FLAC", "AIFF"}
SELECTIONS = {"technical", "provenance", "redistributable"}


def read_jsonl(path: Path):
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
            yield row


def _index(rows, field: str, path: Path) -> dict[str, dict]:
    result = {}
    for row in rows:
        key = str(row.get(field) or "")
        if not key:
            raise ValueError(f"missing {field} in {path}")
        if key in result:
            raise ValueError(f"duplicate {field} {key!r} in {path}")
        result[key] = row
    return result


def _archive_url(identifier: str, name: str | None = None) -> str:
    base = "https://archive.org/details/" + quote(identifier, safe="")
    return base if not name else "https://archive.org/download/" + quote(identifier, safe="") + "/" + quote(name, safe="/")


def _files_by_identifier(files_path: Path) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for row in read_jsonl(files_path):
        identifier = str(row.get("identifier") or "")
        if not identifier:
            raise ValueError(f"file row has no identifier in {files_path}")
        result.setdefault(identifier, []).append(row)
    return result


def _strict_files(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        fmt = str(row.get("format") or "").upper()
        if fmt not in LOSSLESS_FORMATS or row.get("status") != "strict_original" or row.get("private"):
            continue
        result.append({
            "name": row.get("name"),
            "format": fmt,
            "archive_format": row.get("archive_format"),
            "source": row.get("source"),
            "status": row.get("status"),
            "size_bytes": row.get("size_bytes"),
            "length_s": row.get("length_s"),
            "sha1": row.get("sha1"),
            "md5": row.get("md5"),
            "download_url": row.get("download_url"),
        })
    return result


def prepare(candidates_path: Path, items_path: Path, files_path: Path,
            selection: str = "provenance") -> tuple[list[dict], dict]:
    if selection not in SELECTIONS:
        raise ValueError(f"selection must be one of {sorted(SELECTIONS)}")
    candidates = _index(read_jsonl(candidates_path), "identifier", candidates_path)
    items = _index(read_jsonl(items_path), "identifier", items_path)
    files = _files_by_identifier(files_path)
    output = []
    skipped = {}
    for identifier in sorted(candidates):
        item = items.get(identifier)
        if item is None or item.get("status") != "resolved":
            skipped["metadata_unresolved"] = skipped.get("metadata_unresolved", 0) + 1
            continue
        strict = _strict_files(files.get(identifier, []))
        if not strict:
            skipped["no_strict_original"] = skipped.get("no_strict_original", 0) + 1
            continue
        eligible = {
            "technical": item.get("technical_candidate") is True,
            "provenance": item.get("provenance_candidate") is True,
            # The Phase 1 field is only a metadata heuristic; it is never
            # copied into the common manifest's release candidate flag.
            "redistributable": item.get("redistributable_candidate") is True,
        }
        if not eligible[selection]:
            skipped[f"not_{selection}_candidate"] = skipped.get(f"not_{selection}_candidate", 0) + 1
            continue
        candidate = candidates[identifier]
        creator = item.get("creator") or "; ".join(candidate.get("creators") or []) or None
        collection = item.get("collection") or "; ".join(candidate.get("collections") or []) or None
        license_url = item.get("archive_license_url") or ((candidate.get("license_urls") or [None])[0])
        archive_files = []
        for file in strict:
            archive_files.append({**file, "download_url": file.get("download_url") or
                                  _archive_url(identifier, file.get("name"))})
        metadata = {
            "title": item.get("title") or identifier,
            "creator": creator,
            "genre": item.get("genre") or "; ".join(candidate.get("genres") or []) or "[unknown]",
            "collection": collection or "[unknown]",
            "tags": item.get("tags") or candidate.get("tags") or [],
            "archive_identifier": identifier,
            "archive_item_url": _archive_url(identifier),
            "archive_license_label": item.get("archive_license_label"),
            "archive_licence_category": item.get("archive_licence_category"),
            "archive_retrieval_method": item.get("retrieval_method"),
        }
        rights = {
            "license_label": item.get("archive_license_label") or license_url,
            "license_url": license_url,
            "attribution": creator,
            "evidence_url": _archive_url(identifier),
            "review_status": "metadata_candidate_pending_asset_review",
            "rights_status": "metadata_candidate_pending_asset_review",
            "allow_commercial": None,
            "allow_redistribution": None,
            "allow_derivatives": None,
            "provenance_approved": False,
            "redistribution_approved": False,
            "source_status": "archive_original_declared_unverified",
            "provenance_note": "Archive metadata only; uploader/title/licence and source codec require asset review.",
        }
        output.append({
            "schema": "openrestor-clean-manifest-v1",
            "dataset": "iamd_archive",
            "source_id": identifier,
            "source_key": f"iamd_archive:{identifier}",
            "audio_path": None,
            "source_sha256": None,
            "original_format": sorted({file["format"] for file in strict}),
            "sample_rate": None,
            "channels": None,
            # An item may expose several alternate original files.  Do not
            # add their durations as if they were distinct sources; retain the
            # longest declared member as a conservative item-level estimate.
            "duration_seconds": max((float(file["length_s"]) for file in strict
                                      if file.get("length_s") is not None), default=None),
            "lossless_status": "archive_declared_original_unverified",
            "technical_candidate": eligible["technical"],
            "provenance_candidate": eligible["provenance"],
            "redistributable_candidate": False,
            "metadata": metadata,
            "rights": rights,
            "archive_original_files": archive_files,
            "phase1": {
                "selection": selection,
                "metadata_only": True,
                "archive_technical_candidate": eligible["technical"],
                "archive_provenance_candidate": eligible["provenance"],
                "archive_redistributable_candidate": eligible["redistributable"],
            },
        })
    report = {
        "schema_version": "iamd-archive-manifest-audit-v1",
        "input_candidates": len(candidates),
        "resolved_items": sum(item.get("status") == "resolved" for item in items.values()),
        "output_sources": len(output),
        "selection": selection,
        "metadata_only": True,
        "audio_downloaded": False,
        "redistribution_approved": False,
        "counts_skipped": dict(sorted(skipped.items())),
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--files", type=Path, required=True)
    parser.add_argument("--selection", choices=sorted(SELECTIONS), default="provenance")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    rows, report = prepare(args.candidates, args.items, args.files, args.selection)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                        for row in rows), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Prepared {len(rows)} metadata-only IAMD manifest rows: {args.out}")


if __name__ == "__main__":
    main()
