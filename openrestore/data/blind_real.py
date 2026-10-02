"""Blind-Real track: discovery and curation over Internet Archive originals.

This track has no clean reference. Its items are real recordings degraded by their
own history, not by our code, so the whole task here is finding and vetting them.

The Internet Archive Music Dataset (IAMD) is used as a *catalogue*, never as audio:
it indexes millions of 30-second segments with the Internet Archive identifier,
per-item licence and venue metadata we need to filter on, but its own segments are
re-encoded MP3. Candidates are resolved to their Internet Archive identifier and the
best available original is fetched instead.

The scan reads only metadata columns from the IAMD parquet shards. Parquet is
columnar, so the embedded audio column is never transferred.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

IAMD_REPO = "Telecom-Paris/iamd_v0"
IAMD_SHARD_URL = f"https://huggingface.co/datasets/{IAMD_REPO}/resolve/main/data/iamd-{{index:05d}}.parquet"

# Everything except the audio column. Columns we do not name are never read.
CATALOGUE_COLUMNS = (
    "key", "identifier", "segment_path", "duration",
    "license_type", "license_version", "license_url", "license_source", "rights",
    "is_live", "venue", "city", "country", "location",
    "collection", "mediatype", "uploader", "publicdate",
    "title", "artist", "creator", "album", "date", "year", "genre", "tags",
    "recording_mode", "audio_type", "sample_rate", "bitrate", "bit_depth", "channels",
    "equipment", "credits", "notes",
)

# Licences that permit commercial use and redistribution. CC0 and BY are preferred;
# BY-SA is listed separately because share-alike would propagate to the release.
PERMISSIVE_LICENCES = ("CC0", "BY")
SHARE_ALIKE_LICENCES = ("BY-SA",)

# Signals that a recording is a live or amateur capture rather than a studio release.
# Matched on word boundaries, not as substrings: "aud" inside "opensource_audio" and
# "live" inside "delivery" would otherwise pass nearly everything.
LIVE_KEYWORDS = (
    "live", "concert", "concerts", "audience", "taper", "tapers", "soundboard", "sbd", "aud",
    "festival", "gig", "bootleg", "matrix", "cassette", "dat", "reel",
    "recorded live", "live at", "live in",
)
LIVE_TEXT_FIELDS = ("collection", "tags", "title", "album", "notes", "equipment", "credits", "recording_mode", "audio_type")


def shard_urls(count: int, start: int = 0) -> list[str]:
    return [IAMD_SHARD_URL.format(index=i) for i in range(start, start + count)]


def read_shard_catalogue(url: str, columns: Iterable[str] = CATALOGUE_COLUMNS) -> list[dict[str, Any]]:
    """Read one shard's metadata columns, leaving its embedded audio untouched."""
    import fsspec
    import pyarrow.parquet as pq

    with fsspec.open(url) as handle:
        table = pq.ParquetFile(handle)
        available = set(table.schema_arrow.names)
        wanted = [c for c in columns if c in available]
        return table.read(columns=wanted).to_pylist()


def scan_catalogue(
    output: Path,
    shard_count: int,
    workers: int = 12,
    start: int = 0,
    progress: bool = True,
) -> int:
    """Scan IAMD shards into one local JSONL catalogue of metadata rows.

    Shards are independent, so this parallelises cleanly. Each shard that fails is
    reported and skipped rather than aborting the scan, because a single transient
    HTTP error should not cost an hour of work.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    urls = shard_urls(shard_count, start)
    written = 0
    failures: list[str] = []
    with output.open("w", encoding="utf-8") as sink, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(read_shard_catalogue, url): url for url in urls}
        for done, future in enumerate(as_completed(futures), start=1):
            url = futures[future]
            try:
                rows = future.result()
            except Exception as error:  # noqa: BLE001 - a bad shard must not end the scan
                failures.append(f"{url}: {type(error).__name__}: {error}")
                continue
            for row in rows:
                sink.write(json.dumps(row, default=str) + "\n")
            written += len(rows)
            if progress and (done % 25 == 0 or done == len(urls)):
                print(f"[blind-real] {done}/{len(urls)} shards, {written} rows, {len(failures)} failed", flush=True)
    if failures and progress:
        print(f"[blind-real] {len(failures)} shard(s) failed; first: {failures[0]}", flush=True)
    return written


_LIVE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in sorted(LIVE_KEYWORDS, key=len, reverse=True)) + r")\b"
)


def looks_live(row: dict[str, Any]) -> bool:
    """Decide whether a catalogue row looks like a live or amateur capture.

    IAMD's own `is_live` column is sparsely populated, so this falls back to keyword
    evidence across the free-text fields, matched on word boundaries. It is
    recall-oriented on purpose: the result is a shortlist a human still has to vet,
    not a final selection.
    """
    if row.get("is_live") in (1, 1.0, True):
        return True
    for field in LIVE_TEXT_FIELDS:
        value = row.get(field)
        if value and _LIVE_PATTERN.search(str(value).lower()):
            return True
    return False


def filter_candidates(
    rows: Iterable[dict[str, Any]],
    allow_share_alike: bool = False,
    require_live: bool = True,
) -> list[dict[str, Any]]:
    """Keep rows whose licence permits redistribution and that look like live capture."""
    allowed = set(PERMISSIVE_LICENCES) | (set(SHARE_ALIKE_LICENCES) if allow_share_alike else set())
    kept = []
    for row in rows:
        if str(row.get("license_type") or "").strip() not in allowed:
            continue
        if require_live and not looks_live(row):
            continue
        kept.append(row)
    return kept


def catalogue_statistics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarise a catalogue so the filters can be judged before any audio is fetched."""
    from collections import Counter

    total = 0
    licences: Counter[str] = Counter()
    collections: Counter[str] = Counter()
    live_by_licence: Counter[str] = Counter()
    identifiers: set[str] = set()
    live_identifiers: set[str] = set()
    for row in rows:
        total += 1
        licence = str(row.get("license_type") or "unknown")
        licences[licence] += 1
        collections[str(row.get("collection") or "unknown")] += 1
        identifiers.add(str(row.get("identifier")))
        if looks_live(row):
            live_by_licence[licence] += 1
            live_identifiers.add(str(row.get("identifier")))
    permissive_live = sum(live_by_licence[l] for l in PERMISSIVE_LICENCES)
    return {
        "segments": total,
        "distinct_identifiers": len(identifiers),
        "licence_distribution": dict(licences.most_common()),
        "live_looking_by_licence": dict(live_by_licence.most_common()),
        "live_looking_distinct_identifiers": len(live_identifiers),
        "permissive_live_segments": permissive_live,
        "top_collections": dict(collections.most_common(25)),
    }


def internet_archive_metadata_url(identifier: str) -> str:
    """The Internet Archive metadata endpoint, which lists an item's original files."""
    return f"https://archive.org/metadata/{identifier}"


def best_original_file(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Pick the highest-quality original audio file from an Internet Archive item.

    Preference order follows fidelity: lossless originals first, then high-rate lossy.
    Derivative files the Archive generated itself are skipped, since the point of
    resolving the identifier is to get behind IAMD's re-encoded segments.
    """
    preference = [".flac", ".wav", ".aiff", ".aif", ".shn", ".ape", ".m4a", ".ogg", ".mp3"]
    best: tuple[int, int, dict[str, Any]] | None = None
    for item in metadata.get("files", []):
        name = str(item.get("name", "")).lower()
        if item.get("source") not in (None, "original"):
            continue
        suffix = next((p for p in preference if name.endswith(p)), None)
        if suffix is None:
            continue
        rank = preference.index(suffix)
        size = int(item.get("size") or 0)
        if best is None or rank < best[0]:
            best = (rank, size, item)
    return best[2] if best else None
