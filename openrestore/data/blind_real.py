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


def stream_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Yield rows one at a time. The catalogue is gigabytes; materialising it is not viable."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


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
        if is_non_music_collection(row.get("collection")):
            continue
        if has_doubtful_licence_collection(row.get("collection")):
            continue
        if require_live and not looks_live(row):
            continue
        kept.append(row)
    return kept


# Collections that are field recording or spoken word rather than music. Excluded
# wholesale: radio aporee is a soundscape project, and its titles trip the live-capture
# keywords precisely because they describe crowds and venues.
NON_MUSIC_COLLECTIONS = ("radio-aporee-maps", "radio-aporee", "spokenword", "audio_bookspoetry", "oralliterature")


# Collections whose Creative Commons declarations are not credible. This is a licence
# problem, not a content one: the audio is music, but it is commercially released music
# uploaded under a claim the uploader does not hold. Fingerprinting matched 6 of the 8
# hifidelity_potpourri items in one pass to released recordings by Metallica, Green Day,
# Guns N' Roses, Vulfpeck and the Emerson String Quartet, so the whole collection goes
# rather than only the items AcoustID happened to know.
DOUBTFUL_LICENCE_COLLECTIONS = ("hifidelity_potpourri", "hifidelity")


def is_non_music_collection(collection: Any) -> bool:
    text = str(collection or "").lower()
    return any(c in text for c in NON_MUSIC_COLLECTIONS)


def has_doubtful_licence_collection(collection: Any) -> bool:
    text = str(collection or "").lower()
    return any(c in text for c in DOUBTFUL_LICENCE_COLLECTIONS)


def load_rejections(path: Path) -> dict[str, str]:
    """Read verdicts rejected by listening, as `key<TAB>reason` lines.

    A key is either an Internet Archive identifier, rejecting the whole item, or a clip
    id such as `blind_real--<identifier>--00`, rejecting one excerpt. Both are needed:
    listening found an item whose first excerpt was not music while its second was fine,
    which an identifier-only list cannot express.

    Keeping verdicts as data rather than code means a pass can be applied, audited and
    revisited without touching the selection logic.
    """
    rejected: dict[str, str] = {}
    if not path.is_file():
        return rejected
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t", 1)
        rejected[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else "rejected on listening"
    return rejected


def is_rejected(rejections: dict[str, str], identifier: str, clip_id: str | None = None) -> str | None:
    """Return the rejection reason for an item or one of its clips, if any."""
    if identifier in rejections:
        return rejections[identifier]
    if clip_id and clip_id in rejections:
        return rejections[clip_id]
    return None


def verdicts_to_rejections(csv_path: Path) -> dict[str, str]:
    """Turn an annotated listening sheet into rejection keys.

    A verdict is a rejection when it is not empty and not an approval, so a sheet only
    has to carry the rejections. A clip rejected on its own becomes a clip-level key; an
    item rejected on every clip collapses to one item-level key.
    """
    import csv as _csv
    from collections import defaultdict

    approvals = {"", "ok", "oui", "yes", "keep", "garde"}
    per_item: dict[str, set[str]] = defaultdict(set)
    rejected_clips: dict[str, str] = {}
    totals: dict[str, int] = defaultdict(int)
    with csv_path.open(encoding="utf-8") as handle:
        for row in _csv.DictReader(handle):
            identifier = str(row.get("identifier", "")).strip()
            clip = str(row.get("clip_id") or row.get("fichier") or "").strip()
            if not identifier:
                continue
            totals[identifier] += 1
            verdict = str(row.get("verdict", "")).strip().lower()
            if verdict in approvals:
                continue
            reason = str(row.get("note", "")).strip() or "rejected on listening"
            per_item[identifier].add(clip)
            rejected_clips[clip or f"{identifier}::unknown"] = reason

    out: dict[str, str] = {}
    for identifier, clips in per_item.items():
        if len(clips) >= totals[identifier]:
            out[identifier] = next(iter(rejected_clips[c] for c in clips if c in rejected_clips), "rejected on listening")
        else:
            for clip in clips:
                if clip in rejected_clips:
                    out[clip] = rejected_clips[clip]
    return out


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
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for item in metadata.get("files", []):
        name = str(item.get("name", ""))
        if item.get("source") not in (None, "original"):
            continue
        suffix = next((p for p in preference if name.lower().endswith(p)), None)
        if suffix is None:
            continue
        candidates.append((preference.index(suffix), -int(item.get("size") or 0), name, item))
    if not candidates:
        return None
    # An item is often a whole concert split into tracks, so a tie-break is needed and it
    # must not depend on the order the API happens to return. Best format first, then the
    # longest file, then the name: reproducible from the metadata alone.
    candidates.sort(key=lambda c: c[:3])
    return candidates[0][3]


# Filenames that announce themselves as something other than a performance. A concert
# upload often carries an interview, a soundcheck or crowd noise alongside the music.
NON_MUSIC_NAME_PATTERNS = (
    "interview", "intro", "outro", "banter", "announce", "soundcheck", "sound check",
    "tuning", "crowd", "applause", "audience noise", "between", "talk", "speech",
    "encore break", "stage", "mc ", "intermission",
)


_NON_MUSIC_PATTERN = re.compile(
    r"(?<![a-z])(?:" + "|".join(re.escape(p) for p in sorted(NON_MUSIC_NAME_PATTERNS, key=len, reverse=True)) + r")(?![a-z])"
)


def looks_non_music_filename(name: str) -> bool:
    """Flag a filename that announces itself as something other than a performance.

    Matched on word boundaries: a bare substring made "speech" hit a band called
    secretspeech, the same mistake the live-keyword filter made before it.
    """
    return bool(_NON_MUSIC_PATTERN.search(Path(name).stem.lower().replace("_", " ")))


def ranked_original_files(
    metadata: dict[str, Any], limit: int = 5, preferred_stems: Iterable[str] = ()
) -> list[dict[str, Any]]:
    """The best original files in preference order, so a broken one can be skipped.

    An Internet Archive item sometimes serves 500 for one file and 200 for its
    neighbour, and an item should not be lost over that.

    `preferred_stems` are the file stems IAMD itself segmented for this item. They come
    first, because IAMD's pipeline only segmented what it treated as music: picking the
    largest file instead once selected a track named "09 Interview", which is exactly
    what a listener then heard.
    """
    preference = [".flac", ".wav", ".aiff", ".aif", ".shn", ".ape", ".m4a", ".ogg", ".mp3"]
    wanted = {str(s) for s in preferred_stems}
    candidates: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for item in metadata.get("files", []):
        name = str(item.get("name", ""))
        if item.get("source") not in (None, "original"):
            continue
        suffix = next((p for p in preference if name.lower().endswith(p)), None)
        if suffix is None:
            continue
        segmented = 0 if (wanted and Path(name).stem in wanted) else 1
        suspect = 1 if looks_non_music_filename(name) else 0
        candidates.append((suspect, segmented, preference.index(suffix), name, item))
    if not candidates:
        return []
    # A name that announces an interview or a soundcheck outranks IAMD's own choice,
    # because IAMD is not a reliable music filter here: for one item it segmented only
    # the intro and the outro and left the two actual music tracks alone, so preferring
    # its selection first picked an interview over the music. Then IAMD-segmented, then
    # best format, then the longest file, then the name.
    candidates.sort(key=lambda c: (c[0], c[1], c[2], -int(c[4].get("size") or 0), c[3]))
    return [c[4] for c in candidates[:limit]]


# --- Selection: deduplicate, cap, rank, freeze -------------------------------------

LICENCE_TIER = {"CC0": 3, "BY": 2, "BY-SA": 1}

# Strong evidence is a structured field or a phrase that is hard to produce by accident;
# weak evidence is a bare keyword in free text, which a studio release can easily carry.
# `location` is deliberately not here: a field recording of a street has a location,
# which says nothing about live music capture. Only an explicit is_live flag or a named
# venue counts as structured evidence.
STRONG_LIVE_FIELDS = ("is_live", "venue")
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
    # Tiers are mutually exclusive, unlike the underlying predicates: an item can carry
    # both a structured field and a strong phrase, so counting predicates double-counts.
    tiers = Counter(confidence_tier(r["selection"]) if "selection" in r else confidence_tier(r) for r in frozen)
    return {
        "items": len(frozen),
        "distinct_identifiers": len(identifiers),
        "max_per_identifier": max(identifiers.values()) if identifiers else 0,
        "licence_distribution": dict(licences.most_common()),
        "confidence_tiers": {t: tiers.get(t, 0) for t in CONFIDENCE_TIERS},
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


# --- Resolving candidates to Internet Archive originals -----------------------------

def fetch_item_metadata(identifier: str, timeout: float = 60.0) -> dict[str, Any]:
    """Fetch one Internet Archive item's metadata. No audio is transferred."""
    import urllib.request

    with urllib.request.urlopen(internet_archive_metadata_url(identifier), timeout=timeout) as response:
        return json.load(response)


def original_download_url(identifier: str, filename: str) -> str:
    import urllib.parse

    return f"https://archive.org/download/{identifier}/{urllib.parse.quote(filename)}"


def resolve_originals(
    identifiers: Iterable[str],
    workers: int = 6,
    progress: bool = True,
    segmented_stems: dict[str, Iterable[str]] | None = None,
) -> list[dict[str, Any]]:
    """Resolve identifiers to their best original audio file, without downloading it.

    Run before any download so the volume is known in advance: a single concert in
    lossless form can be hundreds of megabytes, and the choice of file matters more
    than the choice of item.
    """
    identifiers = list(dict.fromkeys(identifiers))
    stems = segmented_stems or {}
    resolved: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_item_metadata, i): i for i in identifiers}
        for done, future in enumerate(as_completed(futures), start=1):
            identifier = futures[future]
            try:
                metadata = future.result()
            except Exception as error:  # noqa: BLE001 - one bad item must not end the pass
                resolved.append({"identifier": identifier, "status": f"metadata-failed: {type(error).__name__}"})
                continue
            ranked = ranked_original_files(metadata, limit=8, preferred_stems=stems.get(identifier, ()))
            if not ranked:
                resolved.append({"identifier": identifier, "status": "no-usable-original"})
                continue
            best = ranked[0]
            item = metadata.get("metadata", {})
            resolved.append({
                "identifier": identifier,
                "status": "resolved",
                "file_name": best.get("name"),
                "file_format": best.get("format"),
                "file_size_bytes": int(best.get("size") or 0),
                "file_sha1": best.get("sha1"),
                "download_url": original_download_url(identifier, str(best.get("name"))),
                "item_licenseurl": item.get("licenseurl"),
                "item_title": item.get("title"),
                "item_creator": item.get("creator"),
                "item_date": item.get("date"),
                "item_collection": item.get("collection"),
                # Distinct tracks of the same item, so two excerpts can come from two
                # songs instead of two places in one song, which sound the same.
                "distinct_tracks": [
                    {"name": f.get("name"), "size_bytes": int(f.get("size") or 0),
                     "sha1": f.get("sha1"), "format": f.get("format"),
                     "download_url": original_download_url(identifier, str(f.get("name")))}
                    for f in ranked
                ],
                "fallback_files": [
                    {"name": f.get("name"), "size_bytes": int(f.get("size") or 0),
                     "sha1": f.get("sha1"), "format": f.get("format"),
                     "download_url": original_download_url(identifier, str(f.get("name")))}
                    for f in ranked[1:]
                ],
            })
            if progress and (done % 20 == 0 or done == len(identifiers)):
                print(f"[resolve] {done}/{len(identifiers)}", flush=True)
    resolved.sort(key=lambda r: r["identifier"])
    return resolved


def resolve_summary(resolved: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter

    status = Counter(r["status"] for r in resolved)
    ok = [r for r in resolved if r["status"] == "resolved"]
    sizes = sorted(r["file_size_bytes"] for r in ok)
    formats = Counter(str(r.get("file_format")) for r in ok)
    return {
        "identifiers": len(resolved),
        "status": dict(status),
        "total_download_bytes": sum(sizes),
        "total_download_gb": round(sum(sizes) / 1e9, 2),
        "median_file_mb": round(sizes[len(sizes) // 2] / 1e6, 1) if sizes else 0.0,
        "largest_file_mb": round(sizes[-1] / 1e6, 1) if sizes else 0.0,
        "formats": dict(formats.most_common()),
    }


def download_originals(
    resolved: Iterable[dict[str, Any]],
    destination: Path,
    workers: int = 4,
    retries: int = 3,
    progress: bool = True,
) -> list[dict[str, Any]]:
    """Download each resolved original and verify it against the Archive's own SHA-1.

    The checksum check is the point: a truncated download is otherwise indistinguishable
    from a short recording. A file already present and matching is left alone, so an
    interrupted pass resumes.
    """
    import hashlib
    import time
    import urllib.request

    destination.mkdir(parents=True, exist_ok=True)
    rows = [r for r in resolved if r.get("status") == "resolved"]

    def sha1(path: Path) -> str:
        digest = hashlib.sha1()  # noqa: S324 - matching the Archive's own checksum
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def fetch(row: dict[str, Any]) -> dict[str, Any]:
        identifier = str(row["identifier"])
        suffix = Path(str(row["file_name"])).suffix.lower()
        target = destination / f"{identifier}{suffix}"
        expected = row.get("file_sha1")
        if target.is_file() and (not expected or sha1(target) == expected):
            return {**row, "local_path": target.name, "download_status": "present"}
        # The chosen file first, then this item's other originals: a single broken file
        # should not cost the whole item.
        options = [{"name": row["file_name"], "download_url": row["download_url"], "sha1": expected,
                    "format": row.get("file_format"), "size_bytes": row.get("file_size_bytes")}]
        options += list(row.get("fallback_files") or [])
        last = ""
        for position, option in enumerate(options):
            want = option.get("sha1")
            suffix = Path(str(option["name"])).suffix.lower()
            attempt_target = destination / f"{identifier}{suffix}"
            for attempt in range(1, retries + 1):
                try:
                    with urllib.request.urlopen(option["download_url"], timeout=300) as response, attempt_target.open("wb") as out:
                        while chunk := response.read(1 << 20):
                            out.write(chunk)
                    got = sha1(attempt_target)
                    if want and got != want:
                        last = f"sha1 mismatch on {option['name']}"
                        time.sleep(attempt * 3)
                        continue
                    return {
                        **row, "local_path": attempt_target.name, "local_sha1": got,
                        "used_file_name": option["name"], "used_fallback_rank": position,
                        "used_file_format": option.get("format"),
                        "download_status": "downloaded" if position == 0 else f"downloaded-fallback-{position}",
                    }
                except Exception as error:  # noqa: BLE001 - retry, then fall back
                    last = f"{type(error).__name__}: {error} on {option['name']}"
                    time.sleep(attempt * 3)
            attempt_target.unlink(missing_ok=True)
        return {**row, "download_status": f"failed: {last}"}

    out_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, row) for row in rows]
        for done, future in enumerate(as_completed(futures), start=1):
            out_rows.append(future.result())
            if progress and (done % 10 == 0 or done == len(futures)):
                failed = sum(1 for r in out_rows if r["download_status"].startswith("failed"))
                print(f"[download] {done}/{len(futures)}, {failed} failed", flush=True)
    out_rows.sort(key=lambda r: r["identifier"])
    return out_rows


def download_distinct_tracks(
    resolved: Iterable[dict[str, Any]],
    destination: Path,
    tracks_per_item: int = 2,
    workers: int = 4,
    retries: int = 3,
    progress: bool = True,
) -> list[dict[str, Any]]:
    """Fetch up to N distinct tracks per item, one returned row per track.

    Two excerpts of one song sound alike however far apart they are taken, so the cap of
    two clips per item only buys variety if the two come from different tracks. This
    returns a row per track, which the clip extractor then pairs with a clip index.
    """
    import hashlib
    import time
    import urllib.request

    destination.mkdir(parents=True, exist_ok=True)

    def sha1(path: Path) -> str:
        digest = hashlib.sha1()  # noqa: S324 - matching the Archive's own checksum
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    jobs: list[tuple[str, int, dict[str, Any], dict[str, Any]]] = []
    for row in resolved:
        if row.get("status") != "resolved":
            continue
        tracks = list(row.get("distinct_tracks") or [])
        if not tracks:
            tracks = [{"name": row.get("file_name"), "download_url": row.get("download_url"),
                       "sha1": row.get("file_sha1"), "format": row.get("file_format")}]
        for index, track in enumerate(tracks[:tracks_per_item]):
            jobs.append((str(row["identifier"]), index, track, row))

    def fetch(job: tuple[str, int, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
        identifier, index, track, row = job
        suffix = Path(str(track["name"])).suffix.lower()
        target = destination / f"{identifier}__t{index}{suffix}"
        expected = track.get("sha1")
        base = {"identifier": identifier, "track_index": index, "track_name": track["name"],
                "track_format": track.get("format"), "local_path": target.name,
                "item_licenseurl": row.get("item_licenseurl"), "item_title": row.get("item_title"),
                "item_creator": row.get("item_creator"), "item_date": row.get("item_date"),
                "item_collection": row.get("item_collection")}
        if target.is_file() and (not expected or sha1(target) == expected):
            return {**base, "download_status": "present"}
        last = ""
        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(track["download_url"], timeout=300) as response, target.open("wb") as out:
                    while chunk := response.read(1 << 20):
                        out.write(chunk)
                got = sha1(target)
                if expected and got != expected:
                    last = "sha1 mismatch"
                    time.sleep(attempt * 3)
                    continue
                return {**base, "local_sha1": got, "download_status": "downloaded"}
            except Exception as error:  # noqa: BLE001 - retry, then report
                last = f"{type(error).__name__}: {error}"
                time.sleep(attempt * 3)
        target.unlink(missing_ok=True)
        return {**base, "local_path": None, "download_status": f"failed: {last}"}

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, job) for job in jobs]
        for done, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if progress and (done % 25 == 0 or done == len(futures)):
                failed = sum(1 for r in rows if r["download_status"].startswith("failed"))
                print(f"[tracks] {done}/{len(futures)}, {failed} failed", flush=True)
    rows.sort(key=lambda r: (r["identifier"], r["track_index"]))
    return rows


# --- Licence screening by audio fingerprint -----------------------------------------

ACOUSTID_LOOKUP = "https://api.acoustid.org/v2/lookup"


def require_fpcalc(fpcalc: str = "fpcalc") -> str:
    """Fail before screening rather than after, if the fingerprinter is missing.

    Without this, a missing binary turns into one FileNotFoundError per item, caught by
    the per-item handler, and the run reports "0 commercial matches" -- a total failure
    presented as a clean result. A screen that could not run must say so.
    """
    import shutil

    found = shutil.which(fpcalc) or (fpcalc if Path(fpcalc).is_file() else None)
    if not found:
        raise FileNotFoundError(
            f"{fpcalc} not found. The AcoustID screen needs Chromaprint's fpcalc; install it "
            f"and put it on PATH, or pass its path. Without it no copyright screen has run, "
            f"and an unscreened set must not be treated as screened."
        )
    return found


def fingerprint_file(path: Path, fpcalc: str = "fpcalc", length: int = 120) -> dict[str, Any]:
    """Compute a Chromaprint fingerprint of an audio file."""
    import subprocess

    result = subprocess.run(
        [fpcalc, "-json", "-length", str(length), str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def acoustid_lookup(fingerprint: str, duration: int, api_key: str, timeout: float = 30.0) -> dict[str, Any]:
    """Ask AcoustID what commercially released recording this audio matches.

    This is the screen the declared licence cannot provide. An Internet Archive
    uploader can mark a file CC BY without holding those rights, and metadata gives no
    sign of it: the item that prompted this screen declares CC BY 3.0, carries no
    MusicBrainz id, and is a DJ mix of commercial tracks. A fingerprint looks at the
    signal instead of the claim.
    """
    import urllib.parse
    import urllib.request

    body = urllib.parse.urlencode({
        "client": api_key, "format": "json", "duration": str(int(duration)),
        "fingerprint": fingerprint, "meta": "recordings releasegroups",
    }).encode()
    request = urllib.request.Request(ACOUSTID_LOOKUP, data=body,
                                     headers={"User-Agent": "OpenRestore-benchmark/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def screen_for_commercial_release(
    items: list[tuple[str, Path]],
    api_key: str,
    fpcalc: str = "fpcalc",
    min_score: float = 0.85,
    pause_seconds: float = 0.4,
    progress: bool = True,
) -> list[dict[str, Any]]:
    """Fingerprint each file and report any commercially released match.

    A match is evidence that the audio is a known released recording, which makes a
    Creative Commons declaration on an Internet Archive upload doubtful. It is evidence
    rather than proof: a band's own live recording of its own song can match its studio
    release, so a hit is a reason to look, not an automatic rejection.
    """
    import time

    fpcalc = require_fpcalc(fpcalc)
    out: list[dict[str, Any]] = []
    for position, (identifier, path) in enumerate(items, start=1):
        row: dict[str, Any] = {"identifier": identifier, "file": path.name}
        try:
            printed = fingerprint_file(path, fpcalc)
            answer = acoustid_lookup(printed["fingerprint"], printed["duration"], api_key)
            if answer.get("status") != "ok":
                row["status"] = f"lookup-error: {str(answer.get('error'))[:80]}"
            else:
                results = answer.get("results") or []
                best = max(results, key=lambda r: r.get("score", 0.0)) if results else None
                row["status"] = "ok"
                row["score"] = best.get("score") if best else 0.0
                recordings = (best or {}).get("recordings") or []
                row["matches"] = [
                    {"title": rec.get("title"),
                     "artists": [a.get("name") for a in (rec.get("artists") or [])],
                     "release_groups": [g.get("title") for g in (rec.get("releasegroups") or [])][:3]}
                    for rec in recordings[:3]
                ]
                row["commercial_match"] = bool(recordings) and (row["score"] or 0) >= min_score
        except Exception as error:  # noqa: BLE001 - one failure must not end the screen
            row["status"] = f"failed: {type(error).__name__}: {error}"
        out.append(row)
        time.sleep(pause_seconds)
        if progress and (position % 25 == 0 or position == len(items)):
            hits = sum(1 for r in out if r.get("commercial_match"))
            print(f"[acoustid] {position}/{len(items)}, {hits} commercial matches", flush=True)
    return out


# Diversity cap ---------------------------------------------------------------------
#
# Source-disjointness by Internet Archive identifier is not enough. One artist can hold
# many identifiers: before this cap, "Ambient Samurai - Ichiro NAKAGAWA" held 14 of 113
# items, 13% of the clips, and Daniel Romano held 8 more under three different spellings
# of the credit. A test set where one recording setup is 13% of the score rewards a system
# for suiting that one microphone, which is not what the benchmark claims to measure.

_CREDIT_SPLIT = re.compile(r"[;,/]| & | and | feat\.? | with ", re.IGNORECASE)


def artist_names(row: dict[str, Any]) -> list[str]:
    """Split a credit string into normalised individual names.

    Archive credits are free text: "Daniel Romano's Outfit; Carson McHone" and
    "Carson McHone; Daniel Romano's Outfit" are the same two acts in either order.
    """
    # Covers both shapes a row can have here: a built manifest row carries "attribution",
    # a downloaded row "item_creator", and a raw catalogue row "artist" or "creator".
    raw = str(row.get("attribution") or row.get("item_creator")
              or row.get("artist") or row.get("creator") or "").strip()
    names = [part.strip().strip("-").lower() for part in _CREDIT_SPLIT.split(raw)]
    return sorted({name for name in names if len(name) > 2})


def artist_groups(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Group identifiers that share any credited name, returning identifier -> group key.

    Grouping on the whole credit string would leave the three Daniel Romano spellings as
    three separate acts, so items are joined whenever they share a single name. The group
    key is the name credited on the most items in the group, which names the group after
    its main act rather than after whichever collaborator sorts first.
    """
    by_identifier: dict[str, list[str]] = {}
    for row in rows:
        identifier = str(row.get("internet_archive_identifier") or row.get("identifier"))
        by_identifier.setdefault(identifier, [])
        for name in artist_names(row):
            if name not in by_identifier[identifier]:
                by_identifier[identifier].append(name)

    parent: dict[str, str] = {}

    def find(key: str) -> str:
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for identifier, names in by_identifier.items():
        union(f"id:{identifier}", f"id:{identifier}")
        for name in names:
            union(f"id:{identifier}", f"name:{name}")

    frequency: dict[str, int] = {}
    for names in by_identifier.values():
        for name in names:
            frequency[name] = frequency.get(name, 0) + 1

    groups: dict[str, str] = {}
    for identifier in by_identifier:
        root = find(f"id:{identifier}")
        members = sorted(k[5:] for k in parent if k.startswith("name:") and find(k) == root)
        groups[identifier] = (
            min(members, key=lambda n: (-frequency[n], n)) if members else f"unknown:{identifier}"
        )
    return groups


def cap_items_per_artist(
    rows: list[dict[str, Any]], cap: int = 3
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep at most ``cap`` identifiers per artist group, and report what was dropped.

    Within a group, identifiers that yielded more clips are kept first: they carry more
    usable material. Ties break on the identifier so the choice is reproducible.
    """
    clips_per_identifier: dict[str, int] = {}
    first_row: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier = str(row["internet_archive_identifier"])
        clips_per_identifier[identifier] = clips_per_identifier.get(identifier, 0) + 1
        first_row.setdefault(identifier, row)

    groups = artist_groups(first_row.values())
    members: dict[str, list[str]] = {}
    for identifier, group in groups.items():
        members.setdefault(group, []).append(identifier)

    keep: set[str] = set()
    dropped: list[dict[str, Any]] = []
    for group in sorted(members):
        ordered = sorted(members[group], key=lambda i: (-clips_per_identifier[i], i))
        keep.update(ordered[:cap])
        for identifier in ordered[cap:]:
            dropped.append({"identifier": identifier, "artist_group": group,
                            "clips": clips_per_identifier[identifier]})

    kept_rows = [row for row in rows if str(row["internet_archive_identifier"]) in keep]
    report = {
        "cap_per_artist": cap,
        "artist_groups": len(members),
        "identifiers_before": len(clips_per_identifier),
        "identifiers_after": len(keep),
        "clips_before": len(rows),
        "clips_after": len(kept_rows),
        "dropped": sorted(dropped, key=lambda d: (d["artist_group"], d["identifier"])),
        "largest_groups": sorted(
            ({"artist_group": g, "identifiers": len(m)} for g, m in members.items()),
            key=lambda d: (-d["identifiers"], d["artist_group"]),
        )[:5],
    }
    return kept_rows, report


# Round two: selecting without the live proxy ----------------------------------------
#
# "Live" was never the requirement. The requirement is that the degradation came from the
# recording's own history, and live capture was a proxy for it -- one that cost 98% of the
# permissive pool (131 identifiers kept out of 9,759 music items) and still let through 27
# recordings a listener judged to need no restoration at all.
#
# Nothing automatic replaces it. The format fields that would show band limiting are
# empty: sample_rate is filled on 7 of 12,405 permissive items, bitrate on 12, channels on
# none. Measurement on the audio does not work either -- the no-reference descriptors were
# tested against a listener's own keep/too-clean verdicts and separated them at chance
# (AUC 0.35 to 0.56, with the noise floor pointing the wrong way, because "clean" to an
# ear means well captured and well mixed rather than quiet).
#
# So listening stays the arbiter, and selection's job is only to spend that listening
# well: exclude what is reliably predictable, and spread the rest.

# Tags and genres of music whose own aesthetic is noise, drone or texture. On the judged
# items this caught 94% of the recordings a listener rejected as noise rather than music,
# against 13% of the ones kept. It is deliberately a lossy filter: with a pool 75 times
# larger than the set needs, precision is worth more than recall.
_AMBIENT_NOISE_PATTERN = re.compile(
    r"\b(noise|ambient|ambeint|drone|dark\s?ambient|experimental|field.?recording|"
    r"soundscape|sound.?art|musique.?concrete|harsh|improvis\w*|improv)\b",
    re.IGNORECASE,
)
_AMBIENT_TEXT_FIELDS = ("genre", "tags", "title", "album", "notes", "audio_type")

# Buckets so broad they say nothing about the material, so they must not drive the
# round-robin: nearly every Internet Archive audio upload lands in several of them.
GENERIC_COLLECTIONS = ("community", "opensource_audio", "ourmedia", "audio_music",
                       "audio", "folksoundomy", "iarchive", "additional_collections")


def looks_ambient_or_noise(row: dict[str, Any]) -> bool:
    text = " ".join(str(row.get(field) or "") for field in _AMBIENT_TEXT_FIELDS)
    return bool(_AMBIENT_NOISE_PATTERN.search(text))


def primary_collection(row: dict[str, Any]) -> str:
    """The most specific collection an item belongs to, for spreading the selection."""
    parts = [c.strip().lower() for c in re.split(r"[;,]\s*", str(row.get("collection") or "")) if c.strip()]
    specific = [c for c in parts if c not in GENERIC_COLLECTIONS]
    return (specific or parts or ["unknown"])[0]


def select_diverse_candidates(
    rows: Iterable[dict[str, Any]],
    target: int,
    cap_per_identifier: int = 2,
    cap_per_artist: int = 3,
    exclude_identifiers: Iterable[str] = (),
    seed: int = 20261009,
) -> list[dict[str, Any]]:
    """Pick items spread across collections and artists, with no quality ranking.

    There is deliberately no ranking by estimated fidelity here. The metadata that
    ``rank_candidates`` scores is absent on this pool, and ranking by it would only
    reward items that happen to be well described. Collections are visited round-robin
    so one large bucket cannot fill the list, and the order within a collection is a
    stable hash, so the choice is reproducible without being correlated with anything.
    """
    from .core import stable_fraction

    excluded = {str(i) for i in exclude_identifiers}
    by_identifier: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        identifier = str(row.get("identifier"))
        if identifier in excluded:
            continue
        by_identifier.setdefault(identifier, []).append(row)

    buckets: dict[str, list[str]] = {}
    for identifier, group in by_identifier.items():
        buckets.setdefault(primary_collection(group[0]), []).append(identifier)
    for collection in buckets:
        buckets[collection].sort(key=lambda i: (stable_fraction(i, seed), i))

    artists: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    order = sorted(buckets, key=lambda c: (-len(buckets[c]), c))
    cursor = {c: 0 for c in order}
    while len(selected) < target:
        progressed = False
        for collection in order:
            if len(selected) >= target:
                break
            while cursor[collection] < len(buckets[collection]):
                identifier = buckets[collection][cursor[collection]]
                cursor[collection] += 1
                progressed = True
                group = by_identifier[identifier]
                names = artist_names(group[0]) or [f"unknown:{identifier}"]
                if any(artists.get(name, 0) >= cap_per_artist for name in names):
                    continue
                for name in names:
                    artists[name] = artists.get(name, 0) + 1
                for row in group[:cap_per_identifier]:
                    selected.append({**row, "primary_collection": collection})
                break
        if not progressed:
            break
    return selected


def acoustid_artist_agreement(credited: Any, screen_row: dict[str, Any]) -> str:
    """Say whether a fingerprint match names the same artist the item credits.

    What an AcoustID match means depends entirely on the pool. For an audience recording
    a match is a red flag: it says the audio is the studio release rather than a capture.
    For netlabel and self-released music a match is expected and benign, because the
    artist's own Creative Commons release is catalogued in MusicBrainz like any other.
    Rejecting on the match alone would have deleted 22 legitimate items of round two,
    among them Photophob, Magrudergrind and Jellica releasing their own work.

    So the signal is agreement, not existence: "same_artist" is the artist's own
    catalogued release, "different_artist" is worth a look, and neither is a verdict.
    """
    if not screen_row.get("matches"):
        return "no_match"
    mine = re.sub(r"[^a-z0-9]+", "", str(credited or "").lower())
    for match in screen_row["matches"]:
        for name in match.get("artists") or []:
            theirs = re.sub(r"[^a-z0-9]+", "", str(name or "").lower())
            if mine and theirs and (mine in theirs or theirs in mine):
                return "same_artist"
    return "different_artist"
