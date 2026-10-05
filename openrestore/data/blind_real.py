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


# --- Selection: deduplicate, cap, rank, freeze -------------------------------------

LICENCE_TIER = {"CC0": 3, "BY": 2, "BY-SA": 1}

# Strong evidence is a structured field or a phrase that is hard to produce by accident;
# weak evidence is a bare keyword in free text, which a studio release can easily carry.
STRONG_LIVE_FIELDS = ("is_live", "venue", "location")
STRONG_LIVE_PHRASES = ("recorded live", "live at", "live in", "soundboard", "audience", "taper", "bootleg")


def live_evidence(row: dict[str, Any]) -> dict[str, Any]:
    """Describe *why* a row looks live, so the ranking can prefer better evidence."""
    structured = [f for f in STRONG_LIVE_FIELDS if row.get(f) not in (None, "", 0, 0.0)]
    hits: list[str] = []
    for field in LIVE_TEXT_FIELDS:
        value = row.get(field)
        if not value:
            continue
        for match in _LIVE_PATTERN.finditer(str(value).lower()):
            hits.append(f"{field}:{match.group(0)}")
    phrases = [h for h in hits if any(p in h for p in STRONG_LIVE_PHRASES)]
    score = 3 * len(structured) + 2 * len(phrases) + len({h.split(":", 1)[0] for h in hits})
    return {"structured_fields": structured, "keyword_hits": sorted(set(hits)), "strong_phrases": sorted(set(phrases)), "evidence_score": score}


def _quality_score(row: dict[str, Any]) -> float:
    """Prefer candidates whose source audio is likely to be high fidelity."""
    score = 0.0
    try:
        rate = float(str(row.get("sample_rate") or 0).split()[0])
        score += 2.0 if rate >= 88200 else 1.0 if rate >= 44100 else 0.0
    except (TypeError, ValueError):
        pass
    try:
        score += 1.0 if float(row.get("bit_depth") or 0) >= 24 else 0.0
    except (TypeError, ValueError):
        pass
    try:
        score += 1.0 if float(row.get("channels") or 0) >= 2 else 0.0
    except (TypeError, ValueError):
        pass
    score += 0.5 * sum(1 for f in ("venue", "city", "country", "date", "artist") if row.get(f))
    return score


def rank_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score every candidate automatically, best first. No listening involved."""
    ranked = []
    for row in rows:
        evidence = live_evidence(row)
        licence = LICENCE_TIER.get(str(row.get("license_type") or "").strip(), 0)
        ranked.append({
            **row,
            "live_evidence": evidence,
            "licence_tier": licence,
            "quality_score": _quality_score(row),
            "rank_score": 10.0 * licence + 2.0 * evidence["evidence_score"] + _quality_score(row),
        })
    ranked.sort(key=lambda r: (-r["rank_score"], str(r.get("identifier")), str(r.get("key"))))
    return ranked


def select_candidates(
    rows: Iterable[dict[str, Any]],
    target: int = 400,
    cap_per_identifier: int = 2,
) -> list[dict[str, Any]]:
    """Deduplicate by Internet Archive identifier, cap per item, then take the best.

    One Internet Archive item can yield dozens of segments, so without a cap a handful
    of concerts would dominate the set. The cap is what buys acoustic variety.
    """
    if cap_per_identifier < 1:
        raise ValueError("cap_per_identifier must be at least 1")
    taken: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    for row in rank_candidates(rows):
        identifier = str(row.get("identifier"))
        if taken.get(identifier, 0) >= cap_per_identifier:
            continue
        taken[identifier] = taken.get(identifier, 0) + 1
        selected.append(row)
        if len(selected) >= target:
            break
    return selected


def freeze_candidate_list(
    selected: list[dict[str, Any]], excerpt_seconds: float = 20.0
) -> list[dict[str, Any]]:
    """Turn ranked candidates into a frozen, auditable Blind-Real item list.

    Each row records where the audio comes from, under what terms, and why it was
    picked. There is no clean reference and no degradation label, by design.
    """
    frozen = []
    for position, row in enumerate(selected):
        identifier = str(row.get("identifier"))
        frozen.append({
            "id": f"blind_real--{identifier}--{position:04d}",
            "dataset": "blind_real",
            "split": "blind_real_test",
            "internet_archive_identifier": identifier,
            "internet_archive_metadata": internet_archive_metadata_url(identifier),
            "iamd_key": row.get("key"),
            "iamd_segment_path": row.get("segment_path"),
            "excerpt_seconds": excerpt_seconds,
            "license_type": row.get("license_type"),
            "license_url": row.get("license_url"),
            "license_source": row.get("license_source"),
            "attribution": row.get("artist") or row.get("creator") or row.get("uploader"),
            "title": row.get("title"),
            "venue": row.get("venue"),
            "city": row.get("city"),
            "country": row.get("country"),
            "date": row.get("date") or row.get("year"),
            "collection": row.get("collection"),
            "source_sample_rate": row.get("sample_rate"),
            "source_bit_depth": row.get("bit_depth"),
            "source_channels": row.get("channels"),
            "selection": {
                "rank_position": position,
                "rank_score": round(float(row.get("rank_score", 0.0)), 3),
                "licence_tier": row.get("licence_tier"),
                "live_evidence": row.get("live_evidence"),
                "qa_listened": False,
                "qa_verdict": None,
            },
        })
    return frozen


def selection_statistics(frozen: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter

    licences = Counter(str(r.get("license_type")) for r in frozen)
    identifiers = Counter(r["internet_archive_identifier"] for r in frozen)
    structured = sum(1 for r in frozen if r["selection"]["live_evidence"]["structured_fields"])
    phrases = sum(1 for r in frozen if r["selection"]["live_evidence"]["strong_phrases"])
    return {
        "items": len(frozen),
        "distinct_identifiers": len(identifiers),
        "max_per_identifier": max(identifiers.values()) if identifiers else 0,
        "licence_distribution": dict(licences.most_common()),
        "with_structured_live_evidence": structured,
        "with_strong_live_phrase": phrases,
        "weak_evidence_only": len(frozen) - structured - phrases,
    }


# --- Confidence tiers and source-disjoint splits ------------------------------------

# A bare keyword in free text is not evidence. IAMD's is_live column is empty across the
# probe and venue is set on 14 of 703 rows, so "live" appearing somewhere carries very
# little signal and the weak tier is excluded from the track by default.
CONFIDENCE_TIERS = ("structured", "strong_phrase", "weak_keyword", "none")


def confidence_tier(row: dict[str, Any]) -> str:
    """Grade why a row looks live, from a populated field down to a bare keyword."""
    evidence = row.get("live_evidence") or live_evidence(row)
    if evidence["structured_fields"]:
        return "structured"
    if evidence["strong_phrases"]:
        return "strong_phrase"
    if evidence["keyword_hits"]:
        return "weak_keyword"
    return "none"


def select_high_confidence(
    rows: Iterable[dict[str, Any]],
    accept_tiers: tuple[str, ...] = ("structured", "strong_phrase"),
) -> list[dict[str, Any]]:
    """Keep only candidates whose live evidence is better than a bare keyword."""
    return [row for row in rows if confidence_tier(row) in accept_tiers]


def assign_source_disjoint_splits(
    rows: Iterable[dict[str, Any]],
    seed: int = 20260714,
    validation_identifiers: int = 0,
    test_identifiers: int = 0,
    validation_fraction: float = 0.15,
    test_fraction: float = 0.15,
) -> list[dict[str, Any]]:
    """Split by Internet Archive identifier, never by clip.

    Positions within one concert are not independent samples, so an identifier that
    crossed splits would leak. Identifiers are partitioned first and their clips follow.
    Absolute counts override the fractions when given, which is how a target of a few
    hundred validation and test clips is met without reshaping the train split.
    """
    from .core import stable_fraction

    row_list = list(rows)
    identifiers = sorted({str(row["internet_archive_identifier"] if "internet_archive_identifier" in row else row["identifier"]) for row in row_list})
    if not identifiers:
        return []
    ordered = sorted(identifiers, key=lambda i: stable_fraction(i, seed))

    if validation_identifiers or test_identifiers:
        n_val, n_test = validation_identifiers, test_identifiers
    else:
        n_val = max(1, int(round(len(ordered) * validation_fraction)))
        n_test = max(1, int(round(len(ordered) * test_fraction)))
    if n_val + n_test >= len(ordered):
        raise ValueError(
            f"validation and test would consume all {len(ordered)} identifiers, leaving no train split"
        )
    assignment = {i: "blind_real_validation" for i in ordered[:n_val]}
    assignment.update({i: "blind_real_test" for i in ordered[n_val : n_val + n_test]})
    assignment.update({i: "blind_real_train" for i in ordered[n_val + n_test :]})

    assigned = []
    for row in row_list:
        identifier = str(row.get("internet_archive_identifier") or row.get("identifier"))
        assigned.append({**row, "split": assignment[identifier]})
    return assigned


def validate_source_disjoint(rows: Iterable[dict[str, Any]]) -> None:
    """Fail loudly if any identifier appears in more than one split."""
    seen: dict[str, str] = {}
    for row in rows:
        identifier = str(row.get("internet_archive_identifier") or row.get("identifier"))
        split = str(row.get("split"))
        if identifier in seen and seen[identifier] != split:
            raise ValueError(f"identifier {identifier!r} leaks across {seen[identifier]!r} and {split!r}")
        seen[identifier] = split


def scan_report(rows: Iterable[dict[str, Any]], cap_per_identifier: int = 2) -> dict[str, Any]:
    """The catalogue report: what the scan actually found, and what sizes it supports."""
    from collections import Counter

    total = 0
    licences: Counter[str] = Counter()
    collections: Counter[str] = Counter()
    permissive_ids: set[str] = set()
    tiers: Counter[str] = Counter()
    tier_ids: dict[str, set[str]] = {t: set() for t in CONFIDENCE_TIERS}
    allowed = set(PERMISSIVE_LICENCES)
    for row in rows:
        total += 1
        licence = str(row.get("license_type") or "unknown")
        licences[licence] += 1
        collections[str(row.get("collection") or "unknown")] += 1
        if licence not in allowed:
            continue
        identifier = str(row.get("identifier"))
        permissive_ids.add(identifier)
        tier = confidence_tier(row)
        tiers[tier] += 1
        tier_ids[tier].add(identifier)

    usable_ids = tier_ids["structured"] | tier_ids["strong_phrase"]
    capped = len(usable_ids) * cap_per_identifier
    # Identifiers, not clips, are what the split policy partitions.
    val = test = min(300, max(1, len(usable_ids) // 6))
    return {
        "segments_scanned": total,
        "licence_distribution": dict(licences.most_common()),
        "permissive_segments": sum(licences[l] for l in PERMISSIVE_LICENCES),
        "permissive_distinct_identifiers": len(permissive_ids),
        "live_candidates_by_confidence": dict(tiers.most_common()),
        "distinct_identifiers_by_confidence": {t: len(ids) for t, ids in tier_ids.items()},
        "high_confidence_identifiers": len(usable_ids),
        "clips_after_cap": capped,
        "top_collections": dict(collections.most_common(25)),
        "achievable_sizes": {
            "note": "identifier-level, cap of %d clip(s) each, source-disjoint" % cap_per_identifier,
            "validation_identifiers": val,
            "test_identifiers": test,
            "train_identifiers": max(0, len(usable_ids) - val - test),
            "validation_clips": val * cap_per_identifier,
            "test_clips": test * cap_per_identifier,
            "train_clips": max(0, len(usable_ids) - val - test) * cap_per_identifier,
        },
    }
