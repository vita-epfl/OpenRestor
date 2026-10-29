#!/usr/bin/env python3
"""Select a deterministic, metadata-only Zenodo member pilot.

The input is the manifest produced by ``prepare_zenodo_archive_manifest.py``.
This command only writes JSON metadata; it never downloads, opens, or copies an
audio member.  Selection is round-robin by archive and track group so that a
large stems archive cannot consume the whole pilot.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


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


def _member_name(row: dict) -> str:
    return str((row.get("metadata") or {}).get("archive_member") or "")


def _archive_key(row: dict) -> str:
    return str((row.get("zenodo") or {}).get("archive_key") or
               (row.get("metadata") or {}).get("collection") or "")


def _track_group(row: dict) -> str:
    """Return a stable track-ish group without treating stems as performers."""
    name = _member_name(row)
    parts = [part for part in name.split("/") if part]
    archive = _archive_key(row).lower()
    if "stems_raw" in archive and len(parts) >= 2:
        return parts[1]
    if parts:
        candidate = parts[-1]
        match = re.search(r"(?:song)?(\d{1,2})(?:\b|\s|[-_])",
                          candidate, re.IGNORECASE)
        if match:
            return match.group(1).zfill(2)
        return candidate
    return "[unknown]"


def _archive_priority(archive: str) -> tuple[int, str]:
    lower = archive.lower()
    for index, token in enumerate(("masters_stereo", "masters_7.1.4",
                                   "example_usage", "stems_raw")):
        if token in lower:
            return index, archive
    return 99, archive


def select(rows: list[dict], max_items: int,
           max_total_compressed_bytes: int) -> tuple[list[dict], dict]:
    if max_items < 1:
        raise ValueError("max_items must be positive")
    if max_total_compressed_bytes < 1:
        raise ValueError("max_total_compressed_bytes must be positive")

    groups: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    seen: set[str] = set()
    skipped = Counter()
    for row in rows:
        source_key = str(row.get("source_key") or "")
        if not source_key:
            skipped["missing_source_key"] += 1
            continue
        if source_key in seen:
            raise ValueError(f"duplicate source_key: {source_key}")
        seen.add(source_key)
        archive = _archive_key(row)
        if not archive:
            skipped["missing_archive_key"] += 1
            continue
        groups[archive][_track_group(row)].append(row)

    for tracks in groups.values():
        for values in tracks.values():
            values.sort(key=lambda row: str(row.get("source_key")))

    archives = sorted(groups, key=_archive_priority)
    cursors = {archive: 0 for archive in archives}
    track_lists = {
        archive: sorted(tracks)
        for archive, tracks in groups.items()
    }
    selected: list[dict] = []
    selected_keys: set[str] = set()
    compressed_total = 0
    deferred_budget = 0

    # One member from each archive per round, then the next track in that
    # archive. This keeps stems_raw from dominating a small pilot.
    while len(selected) < max_items:
        progress = False
        for archive in archives:
            tracks = track_lists[archive]
            cursor = cursors[archive]
            if cursor >= len(tracks):
                continue
            track = tracks[cursor]
            cursors[archive] += 1
            candidates = groups[archive][track]
            row = candidates[0]
            # If a track contains multiple stems, choose the smallest member
            # first; the pilot is for provenance/quality probing, not a full
            # stem download.
            row = min(candidates,
                      key=lambda item: (int((item.get("metadata") or {}).get(
                          "member_compressed_size_bytes") or 0),
                          str(item.get("source_key"))))
            source_key = str(row["source_key"])
            if source_key in selected_keys:
                continue
            compressed = int((row.get("metadata") or {}).get(
                "member_compressed_size_bytes") or 0)
            if compressed > max_total_compressed_bytes - compressed_total:
                deferred_budget += 1
                continue
            copy = dict(row)
            copy["pilot_selection"] = {
                "selection_policy": "round_robin_archive_track_v1",
                "archive": archive,
                "track_group": track,
                "estimated_compressed_bytes": compressed,
                "audio_downloaded": False,
                "technical_candidate": False,
                "redistributable_candidate": False,
            }
            selected.append(copy)
            selected_keys.add(source_key)
            compressed_total += compressed
            progress = True
            if len(selected) >= max_items:
                break
        if not progress:
            break

    selected.sort(key=lambda row: str(row.get("source_key")))
    report = {
        "schema_version": "zenodo-member-pilot-selection-v1",
        "metadata_only": True,
        "audio_downloaded": False,
        "input_rows": len(rows),
        "selected_rows": len(selected),
        "max_items": max_items,
        "max_total_compressed_bytes": max_total_compressed_bytes,
        "estimated_compressed_bytes": compressed_total,
        "estimated_uncompressed_bytes": sum(
            int((row.get("metadata") or {}).get("member_uncompressed_size_bytes") or 0)
            for row in selected),
        "by_archive": dict(sorted(Counter(_archive_key(row) for row in selected).items())),
        "by_track_group": dict(sorted(Counter(_track_group(row) for row in selected).items())),
        "skipped": dict(sorted(skipped.items())),
        "deferred_for_budget": deferred_budget,
        "note": "Selection is metadata-only; exact file, codec, original status and rights still require review.",
    }
    return selected, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-items", type=int, default=12)
    parser.add_argument("--max-total-compressed-bytes", type=int,
                        default=750 * 1024 * 1024)
    args = parser.parse_args()
    rows, report = select(list(read_jsonl(args.manifest)), args.max_items,
                          args.max_total_compressed_bytes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                        for row in rows), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                      sort_keys=True) + "\n", encoding="utf-8")
    print(f"Selected {len(rows)} metadata-only pilot members: {args.out}")


if __name__ == "__main__":
    main()

