#!/usr/bin/env python3
"""Prepare and analyse a private IAMD audio-content pilot.

The sampling unit is an Internet Archive identifier. One strict original file
is chosen per identifier. ``plan`` is entirely offline; ``download-smoke`` is
hard-limited to the first 50; ``measure-smoke`` only reads local verified files.
``report`` never guesses human labels.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_PHASE1 = ROOT / "build/iamd_feasibility"
DEFAULT_OUT = DEFAULT_PHASE1 / "phase2_pilot"
FORMATS = {"WAV", "FLAC", "AIFF"}
CONTENT_TYPES = {"music", "speech_dominant", "noise_or_sound_effect", "ambiguous"}
QUALITY_LABELS = {"acceptable", "degraded", "ambiguous"}
SOURCE_NATURES = {"likely_real_recording", "likely_midi_or_synthetic_render", "ambiguous"}
QUALITY_FLAGS = {"silence_or_quasi_silence", "excessive_clipping", "suspect_bandwidth_cutoff",
                 "low_audiobox_pq", "other"}
REVIEW_FIELDS = ("identifier", "content_type", "audio_quality", "source_nature",
                 "quality_flags", "other_quality_issue", "reviewer", "review_date", "notes")

# A genre proxy for sampling only. It is neither a content label nor a filter.
GENRE_PATTERNS = {
    "rock_metal": r"\b(?:rock|metal|punk|grunge|emo|shoegaze|hardcore)\b",
    "jazz_blues": r"\b(?:jazz|blues|bebop|swing|fusion)\b",
    "hiphop_rap": r"\b(?:hip[ -]?hop|rap|trap|breakbeat)\b",
    "folk_acoustic": r"\b(?:folk|acoustic|bluegrass|country|singer[ -]?songwriter)\b",
    "pop": r"\b(?:pop|synthpop|indie[ -]?pop)\b",
    "classical": r"\b(?:classical|orchestral|baroque|opera|chamber music)\b",
    "electronic_dance": r"\b(?:electronic|electronica|techno|house|trance|edm|dubstep|idm)\b",
    "ambient_experimental": r"\b(?:ambient|drone|experimental|noise|soundscape)\b",
}

# Cues are inspectable hints, not labels. In particular, electronic music is
# never a cue for a MIDI render. Stronger terms still need human/audio review.
SYNTHETIC_CUES = r"\b(?:midi|soundfont|sf2|tracker|mod(?:ule)? file|sequence(?:d|r|s)?|gm[ -]?render|test tone|sine[ -]?wave|oscillator demo)\b"
REAL_CUES = r"\b(?:live recording|recorded live|live concert|live performance|field recordings?|recorded at|taped at|microphone|mic'd|studio session)\b"
CONTENT_CUES = {
    "speech": r"\b(?:spoken word|podcast|interview|audiobook|radio talk|speech)\b",
    "sound_effect": r"\b(?:sound effects?|sfx|foley|test tone|field recordings?|white noise)\b",
}
# Context/style cues are review prompts, not claims of poor recording or of
# non-music. In particular, live concerts and electronic OSTs may be excellent.
CAPTURE_CONTEXT_CUES = r"\b(?:internal microphone|built-in microphone|recorded live|live performance|audience recording|stage banter|bootleg|rehearsal)\b"
STYLIZED_CONTENT_CUES = r"\b(?:8[ -]?bit|chiptune|game soundtrack|oscillator patches?|soundfont|tracker)\b"


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in values:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temporary, path)


def metadata_text(item: dict, file: dict) -> str:
    fields = (item.get("title"), item.get("description"), item.get("subject"),
              item.get("collection"), item.get("creator"), file.get("name"))
    tags = item.get("tags") or []
    return " ; ".join(str(value) for value in (*fields, *tags) if value)


def genre_proxy(item: dict) -> tuple[str, str]:
    declared = item.get("genre")
    if declared and declared != "[unknown]":
        text = str(declared)
        source = item.get("genre_source") or "declared genre"
    else:
        text = " ; ".join(str(tag) for tag in item.get("tags") or [])
        source = "IAMD/Archive subject tags" if text else "unknown"
    matches = [genre for genre, pattern in GENRE_PATTERNS.items() if re.search(pattern, text, re.I)]
    if len(matches) == 1:
        return matches[0], source
    return ("multi_genre" if matches else "unknown"), source


def metadata_cues(item: dict, file: dict) -> dict:
    text = metadata_text(item, file)
    return {
        "synthetic_render_cues": sorted(set(match.group(0).lower() for match in re.finditer(SYNTHETIC_CUES, text, re.I))),
        "real_recording_cues": sorted(set(match.group(0).lower() for match in re.finditer(REAL_CUES, text, re.I))),
        "speech_cues": sorted(set(match.group(0).lower() for match in re.finditer(CONTENT_CUES["speech"], text, re.I))),
        "sound_effect_cues": sorted(set(match.group(0).lower() for match in re.finditer(CONTENT_CUES["sound_effect"], text, re.I))),
        "capture_context_cues": sorted(set(match.group(0).lower() for match in re.finditer(CAPTURE_CONTEXT_CUES, text, re.I))),
        "stylized_content_cues": sorted(set(match.group(0).lower() for match in re.finditer(STYLIZED_CONTENT_CUES, text, re.I))),
    }


def safe_basename(name: object) -> bool:
    return isinstance(name, str) and bool(name) and name not in {".", ".."} and Path(name).name == name and "\\" not in name


def population(phase1: Path) -> list[dict]:
    items = {row["identifier"]: row for row in read_jsonl(phase1 / "items.jsonl")
             if row.get("technical_candidate")}
    files_by_id = collections.defaultdict(list)
    for file in read_jsonl(phase1 / "files.jsonl"):
        if (file.get("identifier") in items and file.get("status") == "strict_original"
                and file.get("source") == "original" and not file.get("private")
                and file.get("format") in FORMATS and safe_basename(file.get("name"))
                and file.get("size_bytes", 0) > 0 and (file.get("sha1") or file.get("md5"))):
            files_by_id[file["identifier"]].append(file)
    result = []
    for identifier, candidates in sorted(files_by_id.items()):
        item = items[identifier]
        # Representative medium-length track; no preference for a small file or format.
        with_duration = [row for row in candidates if isinstance(row.get("length_s"), (int, float))
                         and math.isfinite(row["length_s"]) and row["length_s"] > 0]
        pool = with_duration or candidates
        chosen = sorted(pool, key=lambda row: (abs((row.get("length_s") or 180) - 180),
                                                row["name"]))[0]
        genre, source = genre_proxy(item)
        cues = metadata_cues(item, chosen)
        result.append({
            "identifier": identifier, "title": item.get("title"), "collection": item.get("collection") or "[unknown]",
            "creator": item.get("creator") or "[unknown]", "genre": item.get("genre"),
            "genre_proxy": genre, "genre_proxy_source": source, "tags": item.get("tags") or [],
            "subject": item.get("subject"), "description": item.get("description"),
            "description_status": "present" if item.get("description") else "not_in_phase1_projection",
            "archive_license_url": item.get("archive_license_url"),
            "archive_licence_category": item.get("archive_licence_category"),
            "technical_candidate": True, "provenance_candidate": bool(item.get("provenance_candidate")),
            "redistributable_candidate": bool(item.get("redistributable_candidate")),
            "original_file_count": len(candidates), "name": chosen["name"], "format": chosen["format"],
            "length_s_metadata": chosen.get("length_s"), "size_bytes_metadata": chosen["size_bytes"],
            "sha1": chosen.get("sha1"), "md5": chosen.get("md5"),
            "source": chosen["source"], "metadata_cues": cues,
        })
    return result


def collection_groups(rows: list[dict], top_n: int = 12) -> dict[str, str]:
    counts = collections.Counter(row["collection"] for row in rows)
    top = {name for name, _ in counts.most_common(top_n)}
    return {name: name if name in top else "[other collections]" for name in counts}


def creator_key(row: dict) -> str:
    creator = row["creator"].strip()
    # Unknown must not be mistaken for a single prolific creator.
    return creator.casefold() if creator.casefold() not in {"[unknown]", "unknown", "various artists"} else f"[unknown]:{row['identifier']}"


def quotas(strata: dict[str, dict[str, list[dict]]], count: int) -> dict[str, int]:
    capacity = {key: len(creators) for key, creators in strata.items()}
    if count > sum(capacity.values()):
        raise ValueError(f"requested {count} identifiers but only {sum(capacity.values())} creator-stratum slots")
    if count < len(strata):
        raise ValueError("sample smaller than the number of non-empty collection×genre strata")
    allocated = {key: 1 for key in strata}
    sizes = {key: sum(map(len, creators.values())) for key, creators in strata.items()}
    while sum(allocated.values()) < count:
        key = max((key for key in strata if allocated[key] < capacity[key]),
                  key=lambda name: (math.sqrt(sizes[name]) / (allocated[name] + 1), name))
        allocated[key] += 1
    return allocated


def make_plan(phase1: Path, out: Path, count: int = 750, seed: int = 42) -> dict:
    if not 500 <= count <= 1000:
        raise ValueError("pilot must select 500–1000 identifiers")
    if (out / "plan.json").exists() or (out / "selection.jsonl").exists():
        raise FileExistsError(f"pilot plan already exists in {out}")
    pool = population(phase1)
    groups = collection_groups(pool)
    strata = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in pool:
        key = groups[row["collection"]] + " | " + row["genre_proxy"]
        strata[key][creator_key(row)].append(row)
    allocated = quotas(strata, count)
    rng = random.Random(seed)
    selected = []
    for key in sorted(strata):
        creators = strata[key]
        n, C = allocated[key], len(creators)
        for creator in rng.sample(sorted(creators), n):
            candidates = sorted(creators[creator], key=lambda row: row["identifier"])
            row = dict(rng.choice(candidates))
            pi = (n / C) / len(candidates)
            row.update({"stratum": key, "stratum_population_items": sum(map(len, creators.values())),
                        "stratum_creator_groups": C, "stratum_sampled_creators": n,
                        "creator_items_in_stratum": len(candidates), "selection_probability": pi,
                        "inverse_probability_weight": 1 / pi, "metadata_review_status": "pending",
                        "content_type": None, "audio_quality": None, "source_nature": None})
            selected.append(row)
    selected.sort(key=lambda row: (row["stratum"], row["identifier"]))
    assert len(selected) == count and len({row["identifier"] for row in selected}) == count
    cache = phase1 / "archive_metadata.sqlite3"
    if cache.exists():
        with sqlite3.connect(f"file:{urllib.parse.quote(str(cache))}?mode=ro", uri=True) as connection:
            for row in selected:
                response = connection.execute("SELECT payload FROM responses WHERE identifier = ?", (row["identifier"],)).fetchone()
                if response and response[0]:
                    metadata = json.loads(response[0]).get("metadata") or {}
                    row["subject"] = metadata.get("subject")
                    row["metadata_cues"] = metadata_cues(row, {"name": row["name"]})
    for row in selected:
        row["sample_id"] = hashlib.sha256(row["identifier"].encode()).hexdigest()[:16]
        row["archive_file_url"] = "https://archive.org/download/{}/{}".format(
            urllib.parse.quote(row["identifier"], safe=""), urllib.parse.quote(row["name"], safe=""))
        row["local_original_path"] = str(out / "originals" / row["sample_id"] / row["name"])
    # Small smoke set intentionally covers all genre proxies and large
    # collections; it is not itself a probability sample for yield inference.
    staged = []
    used = set()
    for field, values in (("genre_proxy", sorted({row["genre_proxy"] for row in selected})),
                          ("collection", sorted({row["collection"] for row in selected
                                                 if groups[row["collection"]] != "[other collections]"}))):
        for value in values:
            candidates = [row for row in selected if row[field] == value and row["identifier"] not in used]
            if candidates:
                picked = rng.choice(candidates)
                staged.append(picked)
                used.add(picked["identifier"])
    remaining = [row for row in selected if row["identifier"] not in used]
    rng.shuffle(remaining)
    staged.extend(remaining)
    for position, row in enumerate(staged):
        row["pilot_batch"] = "smoke_50" if position < 50 else "expand_200" if position < 200 else "full_pilot"
    phase1_summary = json.loads((phase1 / "summary.json").read_text(encoding="utf-8"))
    plan = {"schema_version": 1, "seed": seed, "sampling_unit": "Internet Archive identifier; one original file",
            "population_identifiers": len(pool), "selected_identifiers": len(selected),
            "selected_creators": len({row["creator"] for row in selected}),
            "selected_collections": len({row["collection"] for row in selected}),
            "selected_genre_proxies": dict(collections.Counter(row["genre_proxy"] for row in selected)),
            "selected_provenance_candidates": sum(row["provenance_candidate"] for row in selected),
            "selected_metadata_bytes": sum(row["size_bytes_metadata"] for row in selected),
            "selected_metadata_hours": sum((row["length_s_metadata"] or 0) for row in selected) / 3600,
            "selected_formats": dict(collections.Counter(row["format"] for row in selected)),
            "selected_archive_licence_status": dict(collections.Counter(row["archive_licence_category"] for row in selected)),
            "planned_batches": {name: sum(row["pilot_batch"] == name for row in selected)
                                for name in ("smoke_50", "expand_200", "full_pilot")},
            "phase1_funnel": phase1_summary.get("funnel"),
            "strata": {key: {"N_items": sum(map(len, creators.values())), "N_creator_groups": len(creators),
                              "n_creators": allocated[key]} for key, creators in sorted(strata.items())},
            "design": "Collection (top 12 + other) × genre proxy; sample creators uniformly without replacement, then one identifier uniformly per creator. Exact item inclusion probability stored per row.",
            "caveats": ["Genre proxy is largely inferred from subject tags, not verified genre.",
                        "Metadata-only format and source=original are not proof of genuine lossless content.",
                        "Electronic music is not a MIDI-render cue.",
                        "Phase 1 redistributable_candidate is not a rights approval.",
                        "Do not extrapolate selected-file hours to every file in an Archive item."]}
    write_json(out / "plan.json", plan)
    write_jsonl(out / "selection.jsonl", selected)
    with (out / "review_template.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows({"identifier": row["identifier"]} for row in selected)
    write_metadata_queue(out, selected)
    return plan


def enrichment_rows(out: Path) -> dict[str, dict]:
    path = out / "metadata_enrichment.jsonl"
    if not path.exists():
        return {}
    latest = {}
    lines = path.read_bytes().splitlines(keepends=True)
    for line_number, raw in enumerate(lines, 1):
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            if line_number == len(lines) and not raw.endswith(b"\n"):
                break
            raise ValueError(f"corrupt metadata enrichment UTF-8 line {line_number}") from None
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # A crash may leave only the final JSONL line incomplete.
            if line_number == len(lines) and not raw.endswith(b"\n"):
                break
            raise ValueError(f"corrupt metadata enrichment line {line_number}") from None
        latest[row["identifier"]] = row
    return latest


def write_metadata_queue(out: Path, selected: list[dict]) -> None:
    enriched = enrichment_rows(out)
    queue = []
    for row in selected:
        info = enriched.get(row["identifier"], {})
        with_metadata = dict(row)
        if info.get("status") == "ok":
            with_metadata.update({"description": info.get("description"),
                                  "subject": info.get("subject") or row.get("subject"),
                                  "description_status": info.get("description_status")})
        cues = metadata_cues(with_metadata, {"name": row["name"]})
        queue.append({"identifier": row["identifier"], "title": row["title"],
                      "collection": row["collection"], "creator": row["creator"],
                      "genre_proxy": row["genre_proxy"], "name": row["name"],
                      "description_status": with_metadata.get("description_status"),
                      "metadata_cues": cues,
                      "source_nature_metadata_hint": (
                          "conflicting_cues" if cues["synthetic_render_cues"] and cues["real_recording_cues"] else
                          "synthetic_render_cue_review" if cues["synthetic_render_cues"] else
                          "real_recording_cue_review" if cues["real_recording_cues"] else "no_decisive_cue"),
                      "content_metadata_hint": (
                          "speech_or_sound_effect_cue_review" if cues["speech_cues"] or cues["sound_effect_cues"]
                          else "no_decisive_cue")})
    write_jsonl(out / "metadata_review_queue.jsonl", queue)


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1 / per_second
        self.next_start = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_start - now)
            self.next_start = max(now, self.next_start) + self.interval
        if delay:
            time.sleep(delay)


def fetch_metadata_one(identifier: str, limiter: RateLimiter) -> dict:
    url = "https://archive.org/metadata/" + urllib.parse.quote(identifier, safe="")
    result = {"identifier": identifier, "status": "error", "url": url}
    for attempt in range(2):
        limiter.wait()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "OpenRestor-IAMD-phase2-metadata-only/0.1"})
            with urllib.request.urlopen(request, timeout=25) as response:
                body = json.load(response)
            metadata = body.get("metadata") or {}
            description = metadata.get("description")
            if isinstance(description, list):
                description = " ; ".join(str(value) for value in description)
            description = str(description or "")
            result.update({"status": "ok", "description": description[:20000],
                           "description_status": "truncated" if len(description) > 20000 else
                           "present" if description else "missing",
                           "subject": metadata.get("subject")})
            return result
        except (OSError, ValueError, TimeoutError) as error:
            result["error"] = f"{type(error).__name__}: {error}"
            if attempt == 0:
                time.sleep(1)
    return result


def enrich_metadata(out: Path, max_items: int | None = None, rate: float = 3.0,
                    workers: int = 8) -> dict:
    """Fetch only selected item metadata, never a file/download URL."""
    if rate <= 0 or rate > 5 or workers < 1 or workers > 12 or max_items is not None and max_items < 1:
        raise ValueError("rate must be in (0, 5], workers in 1..12, and max-items positive")
    selected = list(read_jsonl(out / "selection.jsonl"))
    latest = enrichment_rows(out)
    pending = [row for row in selected if latest.get(row["identifier"], {}).get("status") != "ok"]
    if max_items is not None:
        pending = pending[:max_items]
    path = out / "metadata_enrichment.jsonl"
    if path.exists():
        raw = path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            # Only discard an interrupted final record; previous complete rows remain.
            with path.open("rb+") as stream:
                stream.truncate(raw.rfind(b"\n") + 1)
    limiter = RateLimiter(rate)
    with path.open("a", encoding="utf-8") as stream, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_metadata_one, row["identifier"], limiter): row["identifier"] for row in pending}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            identifier = result["identifier"]
            stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            latest[identifier] = result
            if index % 25 == 0 or result["status"] != "ok" or index == len(pending):
                print(f"[metadata {index}/{len(pending)}] {identifier}: {result['status']}", flush=True)
    write_metadata_queue(out, selected)
    return {"selected": len(selected), "attempted_this_run": len(pending),
            "resolved": sum(row.get("status") == "ok" for row in latest.values()),
            "errors": sum(row.get("status") != "ok" for row in latest.values())}


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_original(row: dict) -> bool:
    path = Path(row["local_original_path"])
    algorithm = "sha1" if row.get("sha1") else "md5"
    expected = row.get(algorithm)
    return bool(path.is_file() and path.stat().st_size == row["size_bytes_metadata"]
                and expected and file_digest(path, algorithm) == expected)


def smoke_rows(out: Path) -> list[dict]:
    selected = list(read_jsonl(out / "selection.jsonl"))
    smoke = [row for row in selected if row.get("pilot_batch") == "smoke_50"]
    if len(smoke) != 50 or len({row["identifier"] for row in smoke}) != 50:
        raise ValueError("smoke selection must contain exactly 50 unique identifiers")
    for row in smoke:
        expected_path = out / "originals" / row["sample_id"] / row["name"]
        expected_url = "https://archive.org/download/{}/{}".format(
            urllib.parse.quote(row["identifier"], safe=""), urllib.parse.quote(row["name"], safe=""))
        if (row.get("source") != "original" or row.get("format") not in FORMATS
                or not safe_basename(row.get("name")) or not row.get("sha1") and not row.get("md5")
                or not 0 < row.get("size_bytes_metadata", 0) <= 200_000_000
                or row.get("archive_file_url") != expected_url
                or Path(row["local_original_path"]) != expected_path):
            raise ValueError(f"unsafe or inconsistent smoke row: {row['identifier']}")
    return smoke


def pilot_200_rows(out: Path) -> list[dict]:
    """Return only the locked 50+150 selection, with the same source safeguards."""
    selected = [row for row in read_jsonl(out / "selection.jsonl")
                if row.get("pilot_batch") in {"smoke_50", "expand_200"}]
    if (len(selected) != 200 or len({row["identifier"] for row in selected}) != 200
            or sum(row["pilot_batch"] == "smoke_50" for row in selected) != 50
            or sum(row["pilot_batch"] == "expand_200" for row in selected) != 150):
        raise ValueError("pilot selection must be exactly 50 smoke plus 150 new identifiers")
    for row in selected:
        expected_path = out / "originals" / row["sample_id"] / row["name"]
        expected_url = "https://archive.org/download/{}/{}".format(
            urllib.parse.quote(row["identifier"], safe=""), urllib.parse.quote(row["name"], safe=""))
        if (row.get("source") != "original" or row.get("format") not in FORMATS
                or not safe_basename(row.get("name")) or not (row.get("sha1") or row.get("md5"))
                or not 0 < row.get("size_bytes_metadata", 0) <= 220_000_000
                or row.get("archive_file_url") != expected_url
                or Path(row["local_original_path"]) != expected_path):
            raise ValueError(f"unsafe or inconsistent pilot row: {row['identifier']}")
    if sum(row["size_bytes_metadata"] for row in selected
           if row["pilot_batch"] == "expand_200") > 6 * 1024 ** 3:
        raise ValueError("150-source expansion exceeds hard 6 GiB metadata budget")
    return selected


def download_one_original(row: dict) -> dict:
    target = Path(row["local_original_path"])
    result = {"identifier": row["identifier"], "name": row["name"],
              "license_url": row["archive_license_url"],
              "archive_licence_category": row["archive_licence_category"],
              "provenance_candidate": row["provenance_candidate"],
              "expected_size_bytes": row["size_bytes_metadata"],
              "local_path": str(target)}
    if verified_original(row):
        return {**result, "status": "verified", "reused": True}
    if target.exists():
        return {**result, "status": "existing_target_invalid", "error": "target exists but size/digest differs"}
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    if partial.exists() and partial.stat().st_size > row["size_bytes_metadata"]:
        return {**result, "status": "partial_oversize", "error": "partial exceeds declared size"}
    if partial.exists() and partial.stat().st_size == row["size_bytes_metadata"]:
        if verified_original({**row, "local_original_path": str(partial)}):
            os.replace(partial, target)
            return {**result, "status": "verified", "reused": True}
        return {**result, "status": "checksum_mismatch", "error": "complete partial has wrong digest"}
    command = ["curl", "--location", "--fail", "--silent", "--show-error",
               "--connect-timeout", "20", "--max-time", "900", "--retry", "2",
               "--retry-delay", "2", "--max-filesize", str(row["size_bytes_metadata"]),
               "--continue-at", "-", "--output", str(partial),
               row["archive_file_url"]]
    try:
        response = subprocess.run(command, capture_output=True, text=True, check=False)
        if response.returncode:
            return {**result, "status": "transfer_error", "error": response.stderr.strip(),
                    "partial_size_bytes": partial.stat().st_size if partial.exists() else 0}
        if not verified_original({**row, "local_original_path": str(partial)}):
            return {**result, "status": "checksum_mismatch", "error": "size or SHA1/MD5 mismatch",
                    "partial_size_bytes": partial.stat().st_size if partial.exists() else 0}
        os.replace(partial, target)
        return {**result, "status": "verified", "reused": False}
    except OSError as error:
        return {**result, "status": "transfer_error", "error": f"{type(error).__name__}: {error}"}


def download_smoke(out: Path, *, max_items: int | None = None, workers: int = 3) -> dict:
    if workers < 1 or workers > 4 or max_items is not None and not 1 <= max_items <= 50:
        raise ValueError("smoke download permits 1–4 workers and at most 50 items")
    smoke = smoke_rows(out)
    if sum(row["size_bytes_metadata"] for row in smoke) > 3 * 1024 ** 3:
        raise ValueError("smoke plan exceeds hard 3 GiB metadata budget")
    if max_items is not None:
        smoke = smoke[:max_items]
    status_path = out / "download_status.jsonl"
    statuses = {row["identifier"]: row for row in read_jsonl(status_path)} if status_path.exists() else {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_one_original, row): row for row in smoke}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = futures[future]
            result = future.result()
            statuses[row["identifier"]] = result
            write_jsonl(status_path, [statuses[key] for key in sorted(statuses)])
            print(f"[download-smoke {index}/{len(smoke)}] {result['status']} {row['identifier']} "
                  f"{row['size_bytes_metadata'] / 1e6:.1f} MB", flush=True)
    return {"attempted": len(smoke), "verified": sum(row["status"] == "verified" for row in statuses.values()),
            "failures": {key: row["status"] for key, row in statuses.items() if row["status"] != "verified"}}


def download_expand_200(out: Path, *, max_items: int | None = None, workers: int = 3) -> dict:
    """Download just the 150 locked expansion originals, never the 750 plan."""
    if workers < 1 or workers > 4 or max_items is not None and not 1 <= max_items <= 150:
        raise ValueError("200-pilot download permits 1–4 workers and at most 150 new items")
    expansion = [row for row in pilot_200_rows(out) if row["pilot_batch"] == "expand_200"]
    if max_items is not None:
        expansion = expansion[:max_items]
    status_path = out / "download_status.jsonl"
    statuses = {row["identifier"]: row for row in read_jsonl(status_path)} if status_path.exists() else {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_one_original, row): row for row in expansion}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = futures[future]
            result = future.result()
            statuses[row["identifier"]] = result
            write_jsonl(status_path, [statuses[key] for key in sorted(statuses)])
            print(f"[download-expand-200 {index}/{len(expansion)}] {result['status']} "
                  f"{row['identifier']} {row['size_bytes_metadata'] / 1e6:.1f} MB", flush=True)
    return {"new_selected": len(expansion),
            "new_verified": sum(statuses.get(row["identifier"], {}).get("status") == "verified"
                                for row in expansion),
            "new_failures": {row["identifier"]: statuses.get(row["identifier"], {}).get("status")
                             for row in expansion if statuses.get(row["identifier"], {}).get("status") != "verified"}}


def windows(duration: float, seconds: float = 24.0) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    if duration < seconds:
        return [(0.0, duration)]
    if duration < 3 * seconds + 2:
        return [(max(0.0, (duration - seconds) / 2), seconds)]
    return [(max(0.0, min(duration - seconds, duration * fraction - seconds / 2)), seconds)
            for fraction in (0.1, 0.5, 0.9)]


def format_matches(declared: str, detected: str | None) -> bool:
    # libsndfile reports WAVE_FORMAT_EXTENSIBLE as WAVEX, still a WAV container.
    return detected == declared or declared == "WAV" and detected == "WAVEX"


def measure_local(out: Path, *, with_pq: bool = False, limit: int | None = None,
                  smoke_only: bool = False, pilot_200_only: bool = False) -> dict:
    """Inspect already present originals only; no network or acquisition code."""
    import numpy as np
    import soundfile as sf
    from openrestor.metrics.blind_real import no_reference_descriptors

    if smoke_only and pilot_200_only:
        raise ValueError("smoke_only and pilot_200_only are mutually exclusive")
    selected = (smoke_rows(out) if smoke_only else pilot_200_rows(out) if pilot_200_only
                else list(read_jsonl(out / "selection.jsonl")))
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        selected = selected[:limit]
    score_path = out / "scores.jsonl"
    scores = {row["identifier"]: row for row in read_jsonl(score_path)} if score_path.exists() else {}
    predictor = None
    if with_pq:
        os.environ.setdefault("HF_HOME", str(ROOT / "build/metric_tools/hf_cache"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from audiobox_aesthetics.infer import initialize_predictor
        predictor = initialize_predictor()
    for row in selected:
        identifier = row["identifier"]
        if scores.get(identifier, {}).get("status") == "measured" and (
                not with_pq or scores[identifier].get("audiobox_pq") is not None):
            scores[identifier]["format_matches"] = format_matches(row["format"],
                                                                   scores[identifier].get("detected_format"))
            continue
        path = Path(row["local_original_path"])
        if not path.exists():
            scores[identifier] = {"identifier": identifier, "status": "original_not_present",
                                  "audiobox_pq": None}
            continue
        if not verified_original(row):
            scores[identifier] = {"identifier": identifier, "status": "size_or_digest_mismatch",
                                  "audiobox_pq": None}
            continue
        try:
            segments = []
            with sf.SoundFile(path) as audio:
                duration = len(audio) / audio.samplerate
                detected_format = audio.format
                for index, (start, seconds) in enumerate(windows(duration), 1):
                    audio.seek(round(start * audio.samplerate))
                    data = audio.read(round(seconds * audio.samplerate), dtype="float32", always_2d=True)
                    if len(data) == 0:
                        continue
                    mono = data.mean(axis=1)
                    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
                    clip_path = out / "clips" / f"{row['sample_id']}-p{index}.flac"
                    clip_path.parent.mkdir(parents=True, exist_ok=True)
                    if not clip_path.exists():
                        sf.write(clip_path, data, audio.samplerate, format="FLAC", subtype="PCM_24")
                    part = {"clip_path": str(clip_path), "start_s": start,
                            "duration_s": len(data) / audio.samplerate,
                            "near_silent_sample_ratio": float(np.mean(np.abs(data) < .001)),
                            "clipped_sample_ratio_channels": float(np.mean(np.abs(data) >= .999)),
                            "peak_dbfs": 20 * math.log10(max(float(np.abs(data).max()), 1e-12)),
                            "rms_dbfs": 20 * math.log10(max(rms, 1e-12)),
                            **no_reference_descriptors(data, audio.samplerate),
                            "audiobox_pq": None}
                    if predictor:
                        prediction = predictor.forward([{"path": str(clip_path)}])[0]
                        part["audiobox_pq"] = float(prediction["PQ"])
                    segments.append(part)
                pq = sorted(part["audiobox_pq"] for part in segments if part["audiobox_pq"] is not None)
                scores[identifier] = {"identifier": identifier, "status": "measured",
                                      "declared_format": row["format"], "detected_format": detected_format,
                                      "format_matches": format_matches(row["format"], detected_format),
                                      "sample_rate": audio.samplerate, "channels": audio.channels,
                                      "duration_s": duration, "excerpts": segments,
                                      "audiobox_pq": pq[len(pq) // 2] if pq else None,
                                      "audiobox_status": "measured" if pq else "not_run"}
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            scores[identifier] = {"identifier": identifier, "status": "measurement_failed",
                                  "error": f"{type(error).__name__}: {error}", "audiobox_pq": None}
        write_jsonl(score_path, [scores[key] for key in sorted(scores)])
        print(f"[measure] {identifier}: {scores[identifier]['status']}", flush=True)
    write_jsonl(score_path, [scores[key] for key in sorted(scores)])
    return {"selected_this_run": len(selected), "measured": sum(r["status"] == "measured" for r in scores.values()),
            "missing": sum(r["status"] == "original_not_present" for r in scores.values()),
            "failed": sum(r["status"] in {"measurement_failed", "size_or_digest_mismatch"} for r in scores.values())}


def score_pq_smoke(out: Path, *, max_items: int | None = None, pilot_200: bool = False) -> dict:
    """Score all four Audiobox axes on one central 10 s window per source."""
    smoke = pilot_200_rows(out) if pilot_200 else smoke_rows(out)
    if max_items is not None:
        if not 1 <= max_items <= (200 if pilot_200 else 50):
            raise ValueError("max-items exceeds selected pilot scope")
        smoke = smoke[:max_items]
    path = out / "scores.jsonl"
    scores = {row["identifier"]: row for row in read_jsonl(path)}
    requests = []
    for row in smoke:
        score = scores.get(row["identifier"])
        if not score or score.get("status") != "measured":
            continue
        if (score.get("audiobox_pq_method") == "central_excerpt_10s"
                and all(isinstance(score.get("audiobox_axes", {}).get(axis), (int, float))
                        and math.isfinite(score["audiobox_axes"][axis]) for axis in ("CE", "CU", "PC", "PQ"))):
            continue
        excerpts = score.get("excerpts") or []
        if not excerpts:
            continue
        part = excerpts[len(excerpts) // 2]
        duration = float(part["duration_s"])
        start = max(0, int((duration - 10) // 2)) if duration >= 10 else 0
        end = min(int(duration), start + 10)
        requests.append((row["identifier"], part["clip_path"], start, end))
    if not requests:
        return {"smoke_selected_this_run": len(smoke),
                "complete_pq": sum(scores.get(row["identifier"], {}).get("audiobox_status") == "measured"
                                   for row in smoke),
                "complete_all_axes": sum(all(axis in scores.get(row["identifier"], {}).get("audiobox_axes", {})
                                             for axis in ("CE", "CU", "PC", "PQ")) for row in smoke),
                "partial_or_failed": [row["identifier"] for row in smoke
                                      if not all(axis in scores.get(row["identifier"], {}).get("audiobox_axes", {})
                                                 for axis in ("CE", "CU", "PC", "PQ"))]}
    os.environ.setdefault("HF_HOME", str(ROOT / "build/metric_tools/hf_cache"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from audiobox_aesthetics.infer import initialize_predictor
    try:
        import torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
    except ImportError:
        pass  # A mocked predictor in lightweight offline unit tests needs no torch.
    predictor = initialize_predictor()
    for offset in range(0, len(requests), 4):
        batch = requests[offset:offset + 4]
        inputs = [{"path": clip, "start_time": start, "end_time": end}
                  for _, clip, start, end in batch]
        try:
            predictions = predictor.forward(inputs)
            if len(predictions) != len(batch):
                raise ValueError("Audiobox returned wrong batch size")
            results = [{axis: float(prediction[axis]) for axis in ("CE", "CU", "PC", "PQ")}
                       for prediction in predictions]
        except (OSError, RuntimeError, ValueError, KeyError, IndexError) as batch_error:
            results = []
            for input_ in inputs:
                try:
                    prediction = predictor.forward([input_])[0]
                    results.append({axis: float(prediction[axis]) for axis in ("CE", "CU", "PC", "PQ")})
                except (OSError, RuntimeError, ValueError, KeyError, IndexError):
                    results.append(None)
            print(f"[pq-smoke] batch fallback after {type(batch_error).__name__}", flush=True)
        for (identifier, clip, start, end), value in zip(batch, results):
            score = scores[identifier]
            try:
                if value is None or any(not math.isfinite(number) for number in value.values()):
                    raise ValueError("non-finite Audiobox score")
                score["audiobox_axes"] = value
                score["audiobox_pq"] = value["PQ"]
                score["audiobox_status"] = "measured"
                score["audiobox_pq_method"] = "central_excerpt_10s"
                score["audiobox_pq_clip_path"] = clip
                score["audiobox_pq_window_in_clip_s"] = [start, end]
                score.pop("audiobox_error", None)
            except ValueError as error:
                score.pop("audiobox_axes", None)
                score["audiobox_pq"] = None
                score["audiobox_status"] = "failed"
                score["audiobox_error"] = str(error)
            print(f"[pq-smoke {offset + 1}/{len(requests)}] {identifier}: {score['audiobox_status']}", flush=True)
        write_jsonl(path, [scores[key] for key in sorted(scores)])
    return {"smoke_selected_this_run": len(smoke),
            "complete_pq": sum(scores.get(row["identifier"], {}).get("audiobox_status") == "measured"
                               for row in smoke),
            "complete_all_axes": sum(all(axis in scores.get(row["identifier"], {}).get("audiobox_axes", {})
                                         for axis in ("CE", "CU", "PC", "PQ")) for row in smoke),
            "partial_or_failed": [row["identifier"] for row in smoke
                                  if not all(axis in scores.get(row["identifier"], {}).get("audiobox_axes", {})
                                             for axis in ("CE", "CU", "PC", "PQ"))]}


def score_aesthetics_excerpts_smoke(out: Path, *, pilot_200: bool = False) -> dict:
    """Score each existing listening excerpt's central 10 s; no source downloads."""
    smoke = pilot_200_rows(out) if pilot_200 else smoke_rows(out)
    path = out / "scores.jsonl"
    scores = {row["identifier"]: row for row in read_jsonl(path)}
    tasks = []
    expected = 0
    reused_middle_scores = 0
    for row in smoke:
        score = scores.get(row["identifier"], {})
        if score.get("status") != "measured":
            continue
        excerpts = score.get("excerpts") or []
        if not 1 <= len(excerpts) <= 3:
            raise ValueError(f"unexpected smoke excerpt count: {row['identifier']}")
        for index, part in enumerate(excerpts):
            expected += 1
            clip = Path(part["clip_path"])
            if (not clip.is_file() or clip.parent.resolve() != (out / "clips").resolve()
                    or not clip.name.startswith(row["sample_id"] + "-p") or clip.suffix.lower() != ".flac"):
                raise ValueError(f"unsafe or missing smoke clip: {row['identifier']}")
            duration = float(part["duration_s"])
            start = max(0, int((duration - 10) // 2)) if duration >= 10 else 0
            end = min(int(duration), start + 10)
            if end <= start:
                raise ValueError(f"empty smoke excerpt window: {row['identifier']}")
            axes = part.get("audiobox_axes") or {}
            if all(isinstance(axes.get(axis), (int, float)) and math.isfinite(axes[axis])
                   for axis in ("CE", "CU", "PC", "PQ")):
                continue
            source_axes = score.get("audiobox_axes") or {}
            if (index == len(excerpts) // 2 and score.get("audiobox_pq_clip_path") == str(clip)
                    and score.get("audiobox_pq_window_in_clip_s") == [start, end]
                    and all(isinstance(source_axes.get(axis), (int, float))
                            and math.isfinite(source_axes[axis]) for axis in ("CE", "CU", "PC", "PQ"))):
                part["audiobox_axes"] = dict(source_axes)
                part["audiobox_pq"] = source_axes["PQ"]
                part["audiobox_method"] = "central_10s_reused"
                part["audiobox_window_in_clip_s"] = [start, end]
                reused_middle_scores += 1
                continue
            tasks.append((row["identifier"], index, str(clip), start, end))
    if reused_middle_scores:
        write_jsonl(path, [scores[key] for key in sorted(scores)])
    if tasks:
        os.environ.setdefault("HF_HOME", str(ROOT / "build/metric_tools/hf_cache"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from audiobox_aesthetics.infer import initialize_predictor
        try:
            import torch
            torch.set_num_threads(min(4, os.cpu_count() or 1))
        except ImportError:
            pass
        predictor = initialize_predictor()
        for offset in range(0, len(tasks), 4):
            batch = tasks[offset:offset + 4]
            inputs = [{"path": clip, "start_time": start, "end_time": end}
                      for _, _, clip, start, end in batch]
            try:
                predictions = predictor.forward(inputs)
                if len(predictions) != len(batch):
                    raise ValueError("Audiobox returned wrong batch size")
                results = [{axis: float(prediction[axis]) for axis in ("CE", "CU", "PC", "PQ")}
                           for prediction in predictions]
            except (OSError, RuntimeError, ValueError, KeyError, IndexError) as error:
                print(f"[aesthetics-excerpts] batch fallback after {type(error).__name__}", flush=True)
                results = []
                for input_ in inputs:
                    try:
                        prediction = predictor.forward([input_])[0]
                        results.append({axis: float(prediction[axis]) for axis in ("CE", "CU", "PC", "PQ")})
                    except (OSError, RuntimeError, ValueError, KeyError, IndexError):
                        results.append(None)
            for (identifier, index, _, start, end), value in zip(batch, results):
                part = scores[identifier]["excerpts"][index]
                if value is not None and all(math.isfinite(number) for number in value.values()):
                    part["audiobox_axes"] = value
                    part["audiobox_pq"] = value["PQ"]
                    part["audiobox_method"] = "central_10s"
                    part["audiobox_window_in_clip_s"] = [start, end]
                    part.pop("audiobox_error", None)
                else:
                    part["audiobox_error"] = "missing or non-finite score"
            write_jsonl(path, [scores[key] for key in sorted(scores)])
            print(f"[aesthetics-excerpts {min(offset + 4, len(tasks))}/{len(tasks)}]", flush=True)
    complete = sum(all(axis in (part.get("audiobox_axes") or {}) for axis in ("CE", "CU", "PC", "PQ"))
                   for row in smoke for part in scores.get(row["identifier"], {}).get("excerpts") or [])
    return {"smoke_sources": len(smoke), "expected_excerpts": expected, "complete_all_axes": complete,
            "reused_middle_scores": reused_middle_scores, "attempted_this_run": len(tasks)}


def parse_reviews(out: Path, path: Path) -> dict[str, dict]:
    known = {row["identifier"] for row in read_jsonl(out / "selection.jsonl")}
    reviews = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(REVIEW_FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("review CSV missing required columns")
        for line_number, row in enumerate(reader, 2):
            identifier = row["identifier"]
            if identifier not in known or identifier in reviews:
                raise ValueError(f"unknown or duplicate identifier on line {line_number}: {identifier}")
            if not any(row[field].strip() for field in ("content_type", "audio_quality", "source_nature")):
                continue
            for field, allowed in (("content_type", CONTENT_TYPES), ("audio_quality", QUALITY_LABELS),
                                   ("source_nature", SOURCE_NATURES)):
                row[field] = row[field].strip()
                if row[field] not in allowed:
                    raise ValueError(f"invalid {field} on line {line_number}: {row[field]}")
            flags = {flag.strip() for flag in (row["quality_flags"] or "").split(";") if flag.strip()}
            if not flags <= QUALITY_FLAGS:
                raise ValueError(f"unknown quality flag on line {line_number}: {sorted(flags - QUALITY_FLAGS)}")
            row["quality_flags"] = sorted(flags)
            reviews[identifier] = row
    return reviews


def weighted_rate(selected: list[dict], predicate, population_count: int) -> dict:
    total = sum(row["inverse_probability_weight"] for row in selected)
    passed = sum(row["inverse_probability_weight"] for row in selected if predicate(row))
    rate = passed / total if total else None
    return {"weighted_population_estimate": rate * population_count if rate is not None else None,
            "rate_of_estimated_population": rate,
            "sample_count": sum(bool(predicate(row)) for row in selected),
            "sum_of_inverse_probability_weights": total,
            "known_population_count": population_count,
            "method": "Hájek ratio using exact two-stage item inclusion probabilities; exploratory"}


def report(out: Path, reviews_csv: Path | None = None) -> dict:
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    selected = list(read_jsonl(out / "selection.jsonl"))
    weights = [row["inverse_probability_weight"] for row in selected]
    effective_n = sum(weights) ** 2 / sum(weight ** 2 for weight in weights) if weights else 0
    reviews = parse_reviews(out, reviews_csv) if reviews_csv else {}
    scores_path = out / "scores.jsonl"
    scores = {row["identifier"]: row for row in read_jsonl(scores_path)} if scores_path.exists() else {}
    for row in selected:
        row["review"] = reviews.get(row["identifier"])
    reviewed = [row for row in selected if row["review"]]
    pq = sorted(float(score["audiobox_pq"]) for score in scores.values()
                if isinstance(score.get("audiobox_pq"), (int, float)) and math.isfinite(score["audiobox_pq"]))
    def quantile(q):
        if not pq:
            return None
        index = q * (len(pq) - 1)
        low, high = math.floor(index), math.ceil(index)
        return pq[low] * (high - index) + pq[high] * (index - low) if low != high else pq[low]
    content = collections.Counter(row["review"]["content_type"] for row in reviewed)
    quality = collections.Counter(row["review"]["audio_quality"] for row in reviewed)
    nature = collections.Counter(row["review"]["source_nature"] for row in reviewed)
    reasons = collections.Counter()
    reasons_by_id = {}
    for row in reviewed:
        label = row["review"]
        item_reasons = set()
        score = scores.get(row["identifier"], {})
        if score.get("status") == "measured" and score.get("format_matches") is False:
            item_reasons.add("source_file:format_mismatch")
        if label["content_type"] in {"speech_dominant", "noise_or_sound_effect"}:
            item_reasons.add("content:" + label["content_type"])
        if label["source_nature"] == "likely_midi_or_synthetic_render":
            item_reasons.add("source_nature:midi_or_synthetic_render")
        if label["audio_quality"] == "degraded":
            item_reasons.add("audio_quality:degraded")
        item_reasons.update("audio_quality:" + flag for flag in label["quality_flags"])
        reasons.update(item_reasons)
        reasons_by_id[row["identifier"]] = item_reasons
    def definite(row):
        label = row["review"]
        return (label and label["content_type"] == "music" and label["audio_quality"] == "acceptable"
                and label["source_nature"] == "likely_real_recording"
                and scores.get(row["identifier"], {}).get("format_matches") is True)
    def possible(row):
        label = row["review"]
        return (label and label["content_type"] in {"music", "ambiguous"}
                and label["audio_quality"] in {"acceptable", "ambiguous"}
                and label["source_nature"] in {"likely_real_recording", "ambiguous"}
                and scores.get(row["identifier"], {}).get("format_matches") is True)
    labels_complete = len(reviewed) == len(selected)
    basic_metrics_complete = all(scores.get(row["identifier"], {}).get("status") == "measured" for row in selected)
    pq_complete = len(pq) == len(selected)
    complete = labels_complete and basic_metrics_complete and pq_complete
    population_count = plan["population_identifiers"]
    lower = weighted_rate(selected, definite, population_count) if complete else None
    upper = weighted_rate(selected, possible, population_count) if complete else None
    provenance_lower = weighted_rate(selected, lambda row: definite(row) and row["provenance_candidate"],
                                     population_count) if complete else None
    weighted_reasons = {reason: weighted_rate(selected,
                        lambda row: reason in reasons_by_id.get(row["identifier"], set()), population_count)
                        for reason in reasons} if complete else None
    ambiguous = [row for row in reviewed if (row["review"]["content_type"] == "ambiguous"
                 or row["review"]["audio_quality"] == "ambiguous"
                 or row["review"]["source_nature"] == "ambiguous")]
    by_collection = collections.defaultdict(lambda: {"reviewed": 0, "definite_pass": 0, "problematic": 0})
    by_creator = collections.defaultdict(lambda: {"reviewed": 0, "definite_pass": 0, "problematic": 0})
    for row in reviewed:
        for counter, key in ((by_collection, row["collection"]), (by_creator, row["creator"])):
            counter[key]["reviewed"] += 1
            counter[key]["definite_pass"] += int(bool(definite(row)))
            counter[key]["problematic"] += int(not possible(row))
    def ranked_groups(groups: dict, min_reviews: int, reverse: bool) -> list[dict]:
        eligible = [{"name": name, **stats, "definite_pass_rate": stats["definite_pass"] / stats["reviewed"]}
                    for name, stats in groups.items() if stats["reviewed"] >= min_reviews]
        return sorted(eligible, key=lambda row: (row["definite_pass_rate"] * (-1 if reverse else 1),
                                                  -row["reviewed"], row["name"]))[:15]
    metadata_queue_path = out / "metadata_review_queue.jsonl"
    metadata_queue = list(read_jsonl(metadata_queue_path)) if metadata_queue_path.exists() else []
    data = {
        "selected_identifiers": len(selected), "reviewed_identifiers": len(reviewed),
        "effective_sample_size_from_weights": effective_n,
        "pending_identifiers": len(selected) - len(reviewed),
        "measured_identifiers": sum(row.get("status") == "measured" for row in scores.values()),
        "basic_metrics_complete": basic_metrics_complete, "audiobox_pq_complete": pq_complete,
        "content_type_distribution": dict(content), "audio_quality_distribution": dict(quality),
        "source_nature_distribution": dict(nature),
        "rejection_reasons_counts_nonexclusive": dict(reasons),
        "rejection_reasons_rate_of_reviewed_nonexclusive": {key: count / len(reviewed) for key, count in reasons.items()} if reviewed else {},
        "weighted_rejection_reasons_after_complete_review": weighted_reasons,
        "audiobox_pq": {"n": len(pq), "min": min(pq) if pq else None, "p10": quantile(.1),
                        "p25": quantile(.25), "median": quantile(.5), "p75": quantile(.75),
                        "p90": quantile(.9), "max": max(pq) if pq else None},
        "collection_review": dict(sorted(by_collection.items(), key=lambda pair: (-pair[1]["reviewed"], pair[0]))),
        "creator_review": dict(sorted(by_creator.items(), key=lambda pair: (-pair[1]["reviewed"], pair[0]))),
        "promising_collections_min_5_reviewed": ranked_groups(by_collection, 5, True),
        "problematic_collections_min_5_reviewed": ranked_groups(by_collection, 5, False),
        "promising_creators_min_3_reviewed": ranked_groups(by_creator, 3, True),
        "problematic_creators_min_3_reviewed": ranked_groups(by_creator, 3, False),
        "ambiguous_manual_list": [{"identifier": row["identifier"], "title": row["title"],
                                   "creator": row["creator"], "collection": row["collection"],
                                   "ambiguous_axes": [field for field in ("content_type", "audio_quality", "source_nature")
                                                      if row["review"][field] == "ambiguous"],
                                   "clip_paths": [part["clip_path"] for part in
                                                  scores.get(row["identifier"], {}).get("excerpts", [])]}
                                  for row in ambiguous],
        "metadata_cue_review_list": [row["identifier"] for row in metadata_queue
                                     if row["source_nature_metadata_hint"] != "no_decisive_cue"
                                     or row["content_metadata_hint"] != "no_decisive_cue"],
        "metadata_description_status": dict(collections.Counter(row["description_status"] for row in metadata_queue)),
        "format_mismatch_count": sum(row.get("status") == "measured" and not row.get("format_matches")
                                     for row in scores.values()),
        "weighted_definite_audio_yield": lower,
        "weighted_possible_audio_yield_upper_bound": upper,
        "weighted_definite_audio_and_phase1_provenance": provenance_lower,
        "redistribution_approved": False,
        "verdict": "pending_complete_review_and_pq" if not complete else "audio_yield_estimated_rights_pending",
        "limitations": ["No estimate until all selected identifiers are reviewed; failed downloads count as nonresponse.",
                        "Weighted estimates cover Phase 1 technical identifiers, not unresolved Archive items; effective sample size can be far below 750.",
                        "One reviewed file cannot certify every file in an Archive identifier.",
                        "Creator/collection rates are descriptive; small groups are unstable. Confirm suspected creators with further tracks.",
                        "No automatic rejection based on metadata cues, one classifier or one audio metric.",
                        "Phase 1 provenance_candidate is not clearance for redistribution."]}
    write_json(out / "report.json", data)
    lines = ["# IAMD Phase 2 — pilot de contenu/qualité/nature", "",
             f"{len(reviewed)}/{len(selected)} identifiants revus ; {data['measured_identifiers']} mesurés ; PQ sur {len(pq)}.",
             f"Verdict : **{data['verdict']}**. Aucune redistribution approuvée par ce pilot.", "",
             "Trois axes indépendants : `content_type`, `audio_quality`, `source_nature`.",
             "Les motifs de rejet peuvent se cumuler. Voir `report.json` pour taux et distributions.",
             "Estimation pondérée de rendement : " + (f"{lower['weighted_population_estimate']:.0f} identifiants stricts "
             f"({100 * lower['rate_of_estimated_population']:.1f} %), jusqu'à {upper['weighted_population_estimate']:.0f} "
             "en incluant les ambigus." if lower and upper else "en attente de revue et métriques complètes, PQ compris."),
             "", "Aucun score PQ ni indice MIDI isolé ne décide du rejet.", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "enrich-metadata", "download-smoke",
                                          "download-expand-200", "measure-local", "measure-smoke",
                                          "measure-200", "pq-smoke", "pq-200",
                                          "aesthetics-excerpts-smoke", "aesthetics-excerpts-200", "report"))
    parser.add_argument("--phase1", type=Path, default=DEFAULT_PHASE1)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--identifiers", type=int, default=750)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reviews-csv", type=Path)
    parser.add_argument("--max-items", type=int, help="Bound a metadata-enrichment or local-measurement run")
    parser.add_argument("--rate", type=float, default=3.0, help="Maximum metadata requests per second")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent metadata requests, max 12")
    parser.add_argument("--with-pq", action="store_true", help="Compute Audiobox PQ if already installed")
    args = parser.parse_args()
    if args.stage == "plan":
        result = make_plan(args.phase1, args.out, args.identifiers, args.seed)
    elif args.stage == "enrich-metadata":
        result = enrich_metadata(args.out, args.max_items, args.rate, args.workers)
    elif args.stage == "download-smoke":
        result = download_smoke(args.out, max_items=args.max_items, workers=min(args.workers, 4))
    elif args.stage == "download-expand-200":
        result = download_expand_200(args.out, max_items=args.max_items, workers=min(args.workers, 4))
    elif args.stage == "measure-local":
        result = measure_local(args.out, with_pq=args.with_pq, limit=args.max_items)
    elif args.stage == "measure-smoke":
        result = measure_local(args.out, with_pq=args.with_pq, limit=args.max_items, smoke_only=True)
    elif args.stage == "measure-200":
        if args.max_items is not None:
            raise ValueError("measure-200 always inspects the exact 200 pilot identifiers")
        result = measure_local(args.out, with_pq=False, pilot_200_only=True)
    elif args.stage == "pq-smoke":
        result = score_pq_smoke(args.out, max_items=args.max_items)
    elif args.stage == "pq-200":
        result = score_pq_smoke(args.out, max_items=args.max_items, pilot_200=True)
    elif args.stage == "aesthetics-excerpts-smoke":
        result = score_aesthetics_excerpts_smoke(args.out)
    elif args.stage == "aesthetics-excerpts-200":
        result = score_aesthetics_excerpts_smoke(args.out, pilot_200=True)
    else:
        result = report(args.out, args.reviews_csv)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
