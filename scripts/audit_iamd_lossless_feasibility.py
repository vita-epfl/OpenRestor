#!/usr/bin/env python3
"""Metadata-only feasibility audit: IAMD catalogue -> Internet Archive originals.

No audio URL is requested. All intermediate data remains under ignored build/.
Run stages in order: scan, fetch, report. Fetch is resumable via SQLite.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime as dt
import json
import math
import re
import sqlite3
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openrestor.data.blind_real import (  # noqa: E402
    has_doubtful_licence_collection,
    is_non_music_collection,
    primary_collection,
    stream_jsonl,
)
from openrestor.rights import cc_terms  # noqa: E402

BUILD = ROOT / "build/blind_real"
OUT = ROOT / "build/iamd_feasibility"
CATALOGUE = BUILD / "iamd_catalogue.jsonl"
FINAL_CANDIDATES = OUT / "iamd_clean_candidate_identifiers.jsonl"
LOSSLESS_SUFFIXES = {".wav": "WAV", ".wave": "WAV", ".flac": "FLAC",
                     ".aiff": "AIFF", ".aif": "AIFF"}
AUDIO_SUFFIXES = set(LOSSLESS_SUFFIXES) | {".mp3", ".m4a", ".ogg", ".shn", ".ape", ".wma"}
EXTRA_NON_MUSIC = ("podcasts", "audio_religion", "audio_sermons", "social-media-video",
                   "folksoundomy_podfic", "spinal_implant_screws_collection")
BLIND_REAL_LISTS = (
    "blind_real_test_manifest.jsonl", "clean_control_manifest.jsonl",
    "public_test_candidates.jsonl", "round2_candidates.jsonl", "round2_frozen.jsonl",
    "blind_real_test_manifest.jsonl.pre_artist_cap",
    "blind_real_test_manifest.jsonl.pre_segmented_fix",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def blind_real_identifiers() -> set[str]:
    used: set[str] = set()
    for name in BLIND_REAL_LISTS:
        path = BUILD / name
        if path.is_file():
            for row in stream_jsonl(path):
                identifier = row.get("internet_archive_identifier") or row.get("identifier")
                if identifier:
                    used.add(str(identifier))
    rejections = BUILD / "rejected_identifiers.tsv"
    if rejections.is_file():
        for line in rejections.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            key = line.split("\t", 1)[0]
            if key.startswith("blind_real--"):
                key = key.split("--", 2)[1]
            used.add(key)
    return used


def _value(value: Any) -> str:
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value if item)
    return str(value or "").strip()


def scan() -> None:
    used = blind_real_identifiers()
    counts: collections.Counter[str] = collections.Counter()
    items: dict[str, dict[str, Any]] = {}
    for row in stream_jsonl(CATALOGUE):
        counts["catalogue_rows"] += 1
        licence = _value(row.get("license_type"))
        if licence not in {"CC0", "BY"}:
            counts["rows_other_licence"] += 1
            continue
        counts["rows_cc0_by"] += 1
        identifier = _value(row.get("identifier"))
        if not identifier:
            counts["rows_missing_identifier"] += 1
            continue
        if identifier in used:
            counts["rows_blind_real_excluded"] += 1
            continue
        item = items.setdefault(identifier, {
            "identifier": identifier, "segments": 0, "license_types": set(),
            "license_urls": set(), "genres": set(), "collections": set(),
            "creators": set(), "artists": set(), "tags": set(),
        })
        item["segments"] += 1
        item["license_types"].add(licence)
        for field, target in (("license_url", "license_urls"), ("genre", "genres"),
                              ("collection", "collections"), ("creator", "creators"),
                              ("artist", "artists"), ("tags", "tags")):
            value = _value(row.get(field))
            if value:
                item[target].add(value)
        if counts["catalogue_rows"] % 500_000 == 0:
            print(f"[scan] {counts['catalogue_rows']:,} rows, {len(items):,} identifiers", flush=True)
    ordered = []
    for item in items.values():
        ordered.append({key: sorted(value) if isinstance(value, set) else value
                        for key, value in item.items()})
    ordered.sort(key=lambda row: row["identifier"])
    final, exclusion = select_final_candidates(ordered)
    counts["blind_real_identifiers_excluded_set"] = len(used)
    counts["candidate_identifiers"] = len(ordered)
    counts["candidate_segments"] = sum(item["segments"] for item in ordered)
    counts["final_candidate_identifiers"] = len(final)
    counts["collection_filter_exclusions"] = dict(exclusion)
    write_jsonl(OUT / "candidates.jsonl", ordered)
    write_jsonl(FINAL_CANDIDATES, final)
    write_json(OUT / "scan_summary.json", dict(counts))
    print(f"[scan] {len(final):,} final candidate identifiers; {len(used)} Blind-Real IDs excluded", flush=True)


def select_final_candidates(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], collections.Counter[str]]:
    final = []
    exclusion: collections.Counter[str] = collections.Counter()
    for item in items:
        collections_ = item.get("collections") or []
        non_music = any(is_non_music_collection(value) or
                        any(word in value.lower() for word in EXTRA_NON_MUSIC)
                        for value in collections_)
        doubtful = any(has_doubtful_licence_collection(value) for value in collections_)
        if non_music:
            exclusion["known_non_music_collection"] += 1
        if doubtful:
            exclusion["known_doubtful_licence_collection"] += 1
        types = item.get("license_types") or []
        urls = item.get("license_urls") or []
        label = cc_terms(urls[0])["license_label"] if len(urls) == 1 else None
        licence_valid = ((types == ["CC0"] and label == "CC0 1.0") or
                         (types == ["BY"] and bool(label) and label.startswith("CC BY ")))
        if not licence_valid:
            exclusion["missing_or_conflicting_iamd_licence_url"] += 1
        if not non_music and not doubtful and licence_valid:
            final.append(item)
    return final, exclusion


def cache_connection() -> sqlite3.Connection:
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(OUT / "archive_metadata.sqlite3")
    con.execute("CREATE TABLE IF NOT EXISTS responses (identifier TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT, error TEXT, fetched_at TEXT NOT NULL)")
    con.commit()
    return con


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.next_start = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_start - now)
            self.next_start = max(now, self.next_start) + self.interval
        if delay:
            time.sleep(delay)


def project_metadata(body: dict[str, Any]) -> dict[str, Any]:
    metadata = body.get("metadata") or {}
    files = []
    for file in body.get("files") or []:
        name = _value(file.get("name"))
        if Path(name).suffix.lower() not in AUDIO_SUFFIXES:
            continue
        files.append({key: file.get(key) for key in
                      ("name", "source", "format", "size", "length", "sha1", "md5", "private")})
    return {
        "metadata": {key: metadata.get(key) for key in
                     ("identifier", "licenseurl", "rights", "creator", "uploader", "title",
                      "collection", "subject", "genre", "mediatype", "access-restricted-item")},
        "files": files,
        "files_count": body.get("files_count"),
    }


def fetch_one(identifier: str, limiter: RateLimiter) -> tuple[str, str, dict[str, Any] | None, str | None]:
    import urllib.parse

    url = "https://archive.org/metadata/" + urllib.parse.quote(identifier, safe="")
    last_error = None
    for attempt in range(4):
        limiter.wait()
        request = urllib.request.Request(url, headers={"User-Agent": "OpenRestor-IAMD-feasibility/0.1 (metadata only)"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.load(response)
            if not isinstance(body, dict) or not isinstance(body.get("files"), list):
                return identifier, "invalid_metadata", None, "missing files list"
            return identifier, "ok", project_metadata(body), None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
            last_error = f"{type(error).__name__}: {error}"
            if isinstance(error, urllib.error.HTTPError) and error.code in (400, 403, 404):
                break
            time.sleep(min(2 ** attempt, 8))
    return identifier, "error", None, last_error


def fetch(workers: int, rate: float, retry_errors: bool) -> None:
    candidates = [row["identifier"] for row in stream_jsonl(FINAL_CANDIDATES)]
    con = cache_connection()
    cached = {row[0]: row[1] for row in con.execute("SELECT identifier, status FROM responses")}
    todo = [identifier for identifier in candidates if identifier not in cached or (retry_errors and cached[identifier] != "ok")]
    print(f"[fetch] {len(todo):,} to query, {len(candidates) - len(todo):,} cached; {rate:g} requests/s max", flush=True)
    if not todo:
        con.close()
        return
    # A short preflight prevents an Archive outage from turning into 18k timed-out jobs.
    try:
        with urllib.request.urlopen("https://archive.org/metadata/APP13003", timeout=10) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        con.close()
        raise SystemExit(f"Archive metadata preflight failed; no candidate requests sent: {error}") from error
    limiter = RateLimiter(rate)
    statuses: collections.Counter[str] = collections.Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(todo), 100):
            batch = todo[start:start + 100]
            futures = {pool.submit(fetch_one, identifier, limiter): identifier for identifier in batch}
            for future in concurrent.futures.as_completed(futures):
                identifier, status, payload, error = future.result()
                con.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)",
                            (identifier, status, json.dumps(payload, ensure_ascii=False) if payload else None,
                             error, dt.datetime.now(dt.timezone.utc).isoformat()))
                statuses[status] += 1
            con.commit()
            done = start + len(batch)
            print(f"[fetch] {done:,}/{len(todo):,}; ok={statuses['ok']:,} errors={done-statuses['ok']:,}", flush=True)
            if done <= 300 and statuses["ok"] < done / 2:
                raise SystemExit("Archive metadata failure rate >50% in early batches; stopped and cached results for inspection")
    con.commit()
    con.close()


def import_resolution(path: Path) -> None:
    """Replace the private cache from portable JSONL, entirely offline.

    The last complete record for an identifier wins (external retries append).
    An incomplete, unterminated final line is ignored; malformed earlier lines
    fail before the existing cache is changed.
    """
    candidates = {row["identifier"] for row in stream_jsonl(FINAL_CANDIDATES)}
    latest: dict[str, tuple[str, str | None, str | None, str]] = {}
    total_rows = 0
    partial_tail_ignored = False
    with path.open("rb") as handle:
        file_size = path.stat().st_size
        line_number = 0
        while raw_line := handle.readline():
            line_number += 1
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                if handle.tell() == file_size and not raw_line.endswith(b"\n"):
                    partial_tail_ignored = True
                    break
                raise ValueError(f"Invalid resolver JSONL at line {line_number}: {error}") from error
            if not isinstance(row, dict):
                raise ValueError(f"Resolver line {line_number} must be a JSON object")
            identifier = row.get("identifier")
            if identifier not in candidates:
                raise ValueError(f"Unexpected identifier on line {line_number}: {identifier!r}")
            if row.get("schema_version") != 1:
                raise ValueError(f"Unsupported resolver schema on line {line_number}")
            status = row.get("status")
            if status == "ok":
                metadata = row.get("metadata")
                files = row.get("files")
                file_counts = row.get("lossless_file_counts")
                if not isinstance(metadata, dict) or not isinstance(files, list):
                    raise ValueError(f"Missing metadata/files on line {line_number}")
                if any(not isinstance(file, dict) for file in files):
                    raise ValueError(f"Non-object file metadata on line {line_number}")
                if file_counts is not None and (not isinstance(file_counts, dict) or
                                                any(not isinstance(value, int) or value < 0
                                                    for value in file_counts.values())):
                    raise ValueError(f"Invalid lossless_file_counts on line {line_number}")
                payload = {"metadata": metadata, "files": files,
                           "retrieval_method": row.get("method"), "warning": row.get("warning"),
                           "lossless_file_counts": file_counts}
            elif status in {"not_found", "error", "invalid_metadata"}:
                payload = None
            else:
                raise ValueError(f"Unknown resolver status on line {line_number}: {status!r}")
            latest[identifier] = (status, json.dumps(payload, ensure_ascii=False) if payload else None,
                                  str(row.get("error") or "") or None,
                                  row.get("fetched_at_utc") or dt.datetime.now(dt.timezone.utc).isoformat())
            total_rows += 1
    con = cache_connection()
    try:
        with con:
            con.execute("DELETE FROM responses")
            con.executemany("INSERT INTO responses VALUES (?, ?, ?, ?, ?)",
                            ((identifier, *record) for identifier, record in latest.items()))
    finally:
        con.close()
    stats = {"source": str(path), "input_records": total_rows,
             "unique_identifiers": len(latest), "candidate_identifiers": len(candidates),
             "partial_tail_ignored": partial_tail_ignored,
             "latest_statuses": dict(collections.Counter(record[0] for record in latest.values()))}
    write_json(OUT / "import_summary.json", stats)
    print(f"[import] {total_rows:,} records, {len(latest):,} identifiers; "
          f"partial tail ignored={partial_tail_ignored}", flush=True)


def _cc_label(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    return cc_terms(url)["license_label"]


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def _genre(item: dict[str, Any], archive: dict[str, Any]) -> str:
    raw = item.get("genres") or []
    if raw:
        return " | ".join(raw)
    archive_genre = _value(archive.get("genre"))
    return archive_genre or "[unknown]"


def _collection(item: dict[str, Any], archive: dict[str, Any]) -> str:
    value = archive.get("collection") or (item.get("collections") or [None])[0]
    return primary_collection({"collection": _value(value)})


def _creator(item: dict[str, Any], archive: dict[str, Any]) -> str:
    return (_value(archive.get("creator")) or
            ((item.get("artists") or item.get("creators") or ["[unknown]"])[0]))


def _format(name: str) -> str | None:
    return LOSSLESS_SUFFIXES.get(Path(name).suffix.lower())


def _format_consistent(fmt: str, declared: Any) -> bool:
    text = _value(declared).lower()
    if not text:
        return False
    terms = {"WAV": ("wave", "wav"), "FLAC": ("flac",), "AIFF": ("aiff", "aifc", "aif")}
    return any(term in text for term in terms[fmt])


def _licence_status(item: dict[str, Any], archive_url: Any) -> tuple[str, str | None]:
    urls = item.get("license_urls") or []
    labels = {_cc_label(url) for url in urls}
    labels.discard(None)
    archive_label = _cc_label(archive_url)
    if len(urls) != 1 or len(labels) != 1:
        return "iamd_missing_or_conflicting", archive_label
    expected = next(iter(labels))
    if expected not in {"CC0 1.0"} and not expected.startswith("CC BY "):
        return "iamd_url_not_cc0_by", archive_label
    expected_type = "CC0" if expected == "CC0 1.0" else "BY"
    if set(item.get("license_types") or []) != {expected_type}:
        return "iamd_type_url_conflict", archive_label
    if not archive_label:
        return "archive_missing_or_other", None
    return ("match" if archive_label == expected else "conflict"), archive_label


def analyse_item(item: dict[str, Any], response: dict[str, Any] | None, status: str,
                 error: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    identifier = item["identifier"]
    if status != "ok" or response is None:
        return {"identifier": identifier, "status": "metadata_unavailable",
                "metadata_status": status, "metadata_error": error}, []
    archive = response["metadata"]
    licence_status, archive_label = _licence_status(item, archive.get("licenseurl"))
    collection = _collection(item, archive)
    collection_text = _value(archive.get("collection") or item.get("collections")).lower()
    creator = _creator(item, archive)
    genre = _genre(item, archive)
    suspect = has_doubtful_licence_collection(collection_text)
    non_music = is_non_music_collection(collection_text) or any(word in collection_text for word in EXTRA_NON_MUSIC)
    files = []
    for raw in response["files"]:
        name = _value(raw.get("name"))
        fmt = _format(name)
        if not fmt:
            continue
        source = _value(raw.get("source")).lower()
        private = _value(raw.get("private")).lower() in {"true", "1", "yes"}
        if private:
            file_status = "private_file"
        elif source == "original":
            file_status = "strict_original" if _format_consistent(fmt, raw.get("format")) else "format_ambiguous"
        elif not source:
            file_status = "source_ambiguous"
        else:
            file_status = "derivative_or_other"
        file = {
            "identifier": identifier, "name": name, "format": fmt, "archive_format": raw.get("format"),
            "source": source or None, "private": private, "status": file_status,
            "length_s": _number(raw.get("length")),
            "size_bytes": int(_number(raw.get("size")) or 0), "sha1": raw.get("sha1"),
            "md5": raw.get("md5"), "download_url": raw.get("download_url"),
        }
        file["redistributable_file_candidate"] = (file_status == "strict_original" and
                                                     file["size_bytes"] > 0 and
                                                     bool(file["sha1"] or file["md5"]))
        files.append(file)
    strict = [file for file in files if file["status"] == "strict_original"]
    source_counts = response.get("lossless_file_counts") or {}
    if not isinstance(source_counts, dict):
        source_counts = {}
    lossless_count = max(len(files), sum(int(value or 0) for value in source_counts.values()))
    technical = bool(strict)
    provenance = (technical and licence_status == "match" and not suspect and
                  not non_music and bool(creator and creator != "[unknown]"))
    redistributable = provenance and any(file["redistributable_file_candidate"] for file in strict)
    licence_category = ("compatible" if licence_status == "match" else
                        "unknown" if licence_status in {"archive_missing_or_other", "iamd_missing_or_conflicting"}
                        else "contradictory")
    out = {
        "identifier": identifier, "status": "resolved", "metadata_status": "ok",
        "segments": item["segments"],
        "iamd_license_types": item["license_types"], "iamd_license_urls": item["license_urls"],
        "archive_license_url": archive.get("licenseurl"), "archive_license_label": archive_label,
        "archive_rights": archive.get("rights"),
        "retrieval_method": response.get("retrieval_method"), "retrieval_warning": response.get("warning"),
        "licence_status": licence_status, "archive_licence_category": licence_category,
        "genre": genre, "genre_source": "IAMD genre" if item.get("genres") else ("Archive genre" if archive.get("genre") else "unknown"),
        "tags": item.get("tags") or [], "collection": collection, "creator": creator,
        "uploader": _value(archive.get("uploader")), "title": _value(archive.get("title")),
        "suspect_collection": suspect, "non_music_collection": non_music,
        "has_lossless_file": lossless_count > 0,
        "lossless_file_count": lossless_count,
        "has_explicit_original_file": any(file["source"] == "original" for file in files),
        "ambiguous_original_status": any(file["status"] == "source_ambiguous" for file in files),
        "strict_original_files": len(strict),
        "source_ambiguous_files": sum(file["status"] == "source_ambiguous" for file in files),
        "format_ambiguous_files": sum(file["status"] == "format_ambiguous" for file in files),
        "derivative_files": max(sum(file["status"] == "derivative_or_other" for file in files),
                                int(source_counts.get("derivative_or_other") or 0)),
        "private_files": max(sum(file["status"] == "private_file" for file in files),
                             int(source_counts.get("private_file") or 0)),
        "technical_candidate": technical, "provenance_candidate": provenance,
        "redistributable_candidate": redistributable,
        "plausible": provenance, "potentially_redistributable": redistributable,
    }
    return out, files


def _hours(files: list[dict[str, Any]]) -> dict[str, Any]:
    known = [file for file in files if file["length_s"] is not None]
    missing = [file for file in files if file["length_s"] is None]
    rate_by_format: dict[str, list[float]] = collections.defaultdict(list)
    for file in known:
        if file["size_bytes"]:
            rate_by_format[file["format"]].append(file["size_bytes"] / file["length_s"])
    imputed_s = 0.0
    unestimated = 0
    for file in missing:
        rates = rate_by_format.get(file["format"], [])
        if rates and file["size_bytes"]:
            imputed_s += file["size_bytes"] / statistics.median(rates)
        else:
            unestimated += 1
    return {"known_hours": sum(file["length_s"] for file in known) / 3600,
            "estimated_hours_including_imputation": (sum(file["length_s"] for file in known) + imputed_s) / 3600,
            "files_with_length": len(known), "files_missing_length": len(missing),
            "files_unestimated": unestimated,
            "imputation": "Missing lengths estimated from file size / median observed bytes per second within format; not verified audio duration."}


def _distribution(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(collections.Counter(str(item.get(key) or "[unknown]") for item in items).items(),
                       key=lambda pair: (-pair[1], pair[0])))


def _concentration(distribution: dict[str, int]) -> dict[str, Any]:
    """Item-level concentration, including unknown labels as an explicit bucket."""
    counts = list(distribution.values())
    total = sum(counts)
    if not total:
        return {"items": 0, "groups": 0, "top_1_share": None, "top_5_share": None,
                "top_10_share": None, "effective_groups": None,
                "unknown_items": 0, "top_groups": {}}
    ordered = sorted(distribution.items(), key=lambda pair: (-pair[1], pair[0]))
    return {"items": total, "groups": len(ordered),
            "top_1_share": counts[0] / total,
            "top_5_share": sum(counts[:5]) / total,
            "top_10_share": sum(counts[:10]) / total,
            "effective_groups": 1 / sum((count / total) ** 2 for count in counts),
            "unknown_items": distribution.get("[unknown]", 0),
            "top_groups": dict(ordered[:25])}


def _tags(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for item in items:
        labels = {tag.strip().lower() for value in item.get("tags") or []
                  for tag in re.split(r"[;,]", value) if tag.strip()}
        counts.update(labels)
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _candidate_field(candidate: dict[str, Any], field: str) -> str:
    values = candidate.get(field) or []
    if field == "collections":
        return primary_collection({"collection": values[0] if values else None})
    if field == "creators":
        values = candidate.get("artists") or values
    return " | ".join(values) if values else "[unknown]"


def assess_feasibility(summary: dict[str, Any]) -> dict[str, Any]:
    """Conservative, transparent Phase-1 heuristic; never a rights approval.

    'Several thousand' is operationalized as >=2,000 distinct IA items. Genre
    metadata is reported, but no genre share or quota is imposed. Collection
    and creator concentration stand in for broad diversity evidence.
    """
    limits = {"min_redistributable_identifiers": 2000,
              "min_estimated_hours": 500.0,
              "min_metadata_coverage": 0.80,
              "min_redistributable_share_of_technical": 0.50,
              "max_top_collection_share": 0.70,
              "max_top_creator_share": 0.10,
              "min_effective_creators": 100.0}
    reasons = []
    funnel = summary["funnel"]
    if funnel["metadata_not_attempted"]:
        return {"verdict": "NO-GO", "provisional": True,
                "reasons": ["résolution Archive incomplète : certains identifiants n'ont pas été interrogés ; "
                            "les zéros observés ne prouvent pas l'absence de sources lossless"],
                "heuristic_thresholds": limits,
                "scope": "Faisabilité Phase 1 uniquement ; ni preuve de titularité, ni approbation de redistribution."}
    if summary["metadata_coverage_fraction"] < limits["min_metadata_coverage"]:
        reasons.append("trop de métadonnées Archive manquantes ou en échec")
    if funnel["redistributable_candidate"] < limits["min_redistributable_identifiers"]:
        reasons.append("moins de 2 000 sources avec originaux et licence/provenance plausibles")
    if summary["potential_hours"]["estimated_hours_including_imputation"] < limits["min_estimated_hours"]:
        reasons.append("moins de 500 heures estimées dans le sous-ensemble plausible")
    technical = funnel["technical_candidate"]
    if technical and funnel["redistributable_candidate"] / technical < limits["min_redistributable_share_of_technical"]:
        reasons.append("plus de la moitié des sources techniques perdent la licence/provenance ou les métadonnées de fichier requises")
    collection = summary["redistributable_collection_concentration"]
    creator = summary["redistributable_creator_concentration"]
    if collection["top_1_share"] is not None and collection["top_1_share"] > limits["max_top_collection_share"]:
        reasons.append("une collection concentre plus de 70 % du sous-ensemble plausible")
    if creator["top_1_share"] is not None and creator["top_1_share"] > limits["max_top_creator_share"]:
        reasons.append("un créateur concentre plus de 10 % du sous-ensemble plausible")
    if creator["effective_groups"] is not None and creator["effective_groups"] < limits["min_effective_creators"]:
        reasons.append("moins de 100 créateurs effectifs après prise en compte de la concentration")
    return {"verdict": "NO-GO" if reasons else "GO", "provisional": False,
            "reasons": reasons, "heuristic_thresholds": limits,
            "scope": "Faisabilité Phase 1 uniquement ; ni preuve de titularité, ni approbation de redistribution."}


def report() -> None:
    candidates = list(stream_jsonl(FINAL_CANDIDATES))
    all_candidates = list(stream_jsonl(OUT / "candidates.jsonl"))
    non_music_ids = {item["identifier"] for item in all_candidates
                     if any(is_non_music_collection(value) or
                            any(word in value.lower() for word in EXTRA_NON_MUSIC)
                            for value in item.get("collections") or [])}
    doubtful_ids = {item["identifier"] for item in all_candidates
                    if any(has_doubtful_licence_collection(value)
                           for value in item.get("collections") or [])}
    unflagged_candidates = candidates
    con = cache_connection()
    cached = {identifier: (status, json.loads(payload) if payload else None, error)
              for identifier, status, payload, error in
              con.execute("SELECT identifier, status, payload, error FROM responses")}
    con.close()
    items, files = [], []
    for candidate in candidates:
        status, response, error = cached.get(candidate["identifier"], ("not_fetched", None, None))
        item, file_rows = analyse_item(candidate, response, status, error)
        items.append(item)
        files.extend(file_rows)
    strict = [file for file in files if file["status"] == "strict_original"]
    technical_items = [item for item in items if item.get("technical_candidate")]
    plausible_items = [item for item in items if item.get("provenance_candidate")]
    potential_items = [item for item in items if item.get("redistributable_candidate")]
    potential_ids = {item["identifier"] for item in potential_items}
    potential_files = [file for file in strict if file["identifier"] in potential_ids and
                       file["redistributable_file_candidate"]]
    scan_summary = json.loads((OUT / "scan_summary.json").read_text(encoding="utf-8"))
    metadata_ok = sum(item.get("status") == "resolved" for item in items)
    metadata_not_attempted = sum(item.get("metadata_status") == "not_fetched" for item in items)
    metadata_failed = len(candidates) - metadata_ok - metadata_not_attempted
    archive_licence_categories = _distribution(
        [item for item in items if item.get("status") == "resolved"], "archive_licence_category")
    potential_collections = _distribution(potential_items, "collection")
    potential_creators = _distribution(potential_items, "creator")
    technical_collections = _distribution(technical_items, "collection")
    technical_creators = _distribution(technical_items, "creator")
    funnel = {
        "initial_candidates": len(candidates),
        "metadata_attempted": len(candidates) - metadata_not_attempted,
        "metadata_resolved": metadata_ok,
        "metadata_failed": metadata_failed,
        "metadata_not_attempted": metadata_not_attempted,
        "archive_licence_compatible": archive_licence_categories.get("compatible", 0),
        "archive_licence_unknown": archive_licence_categories.get("unknown", 0),
        "archive_licence_contradictory": archive_licence_categories.get("contradictory", 0),
        "has_wav_flac_aiff": sum(bool(item.get("has_lossless_file")) for item in items),
        "has_explicit_source_original": sum(bool(item.get("has_explicit_original_file")) for item in items),
        "ambiguous_original_status": sum(bool(item.get("ambiguous_original_status")) for item in items),
        "technical_candidate": len(technical_items),
        "provenance_candidate": len(plausible_items),
        "redistributable_candidate": len(potential_items),
    }
    summary = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "audit_complete": metadata_ok == len(candidates),
        "resolution_attempt_complete": metadata_not_attempted == 0,
        "metadata_coverage_fraction": metadata_ok / len(candidates) if candidates else 0.0,
        "funnel": funnel,
        "scan": scan_summary,
        "pre_collection_filter_identifiers": len(all_candidates),
        "catalogue_collection_flags": {
            "known_non_music_identifiers": len(non_music_ids),
            "known_doubtful_licence_identifiers": len(doubtful_ids),
            "unflagged_identifiers": len(unflagged_candidates),
            "note": "Metadata-only flags, not a final rights or music-quality review; categories may overlap.",
        },
        "identifiers": {"catalogue_candidates": len(candidates), "metadata_ok": metadata_ok,
                        "technical": len(technical_items), "plausible": len(plausible_items), "potentially_redistributable": len(potential_items)},
        "files": {"strict_original": len(strict), "source_ambiguous": sum(file["status"] == "source_ambiguous" for file in files),
                  "format_ambiguous": sum(file["status"] == "format_ambiguous" for file in files),
                  "derivative_or_other": sum(item.get("derivative_files", 0) for item in items),
                  "private": sum(item.get("private_files", 0) for item in items),
                  "potentially_redistributable": len(potential_files)},
        "strict_formats": _distribution(strict, "format"),
        "potential_formats": _distribution(potential_files, "format"),
        "strict_size_bytes": sum(file["size_bytes"] for file in strict),
        "strict_files_missing_size": sum(file["size_bytes"] <= 0 for file in strict),
        "potential_size_bytes": sum(file["size_bytes"] for file in potential_files),
        "potential_files_missing_size": sum(file["size_bytes"] <= 0 for file in potential_files),
        "strict_hours": _hours(strict), "potential_hours": _hours(potential_files),
        "iamd_licences": _distribution([{"label": " | ".join(item["license_urls"]) or "[unknown]"} for item in candidates], "label"),
        "iamd_license_types": _distribution([{"label": " | ".join(item["license_types"])} for item in candidates], "label"),
        "catalogue_genres": _distribution([{"label": _candidate_field(item, "genres")} for item in candidates], "label"),
        "catalogue_collections": _distribution([{"label": _candidate_field(item, "collections")} for item in candidates], "label"),
        "catalogue_creators": _distribution([{"label": _candidate_field(item, "creators")} for item in candidates], "label"),
        "catalogue_tags_metadata_hints": _tags(candidates),
        "unflagged_catalogue_genres": _distribution([{"label": _candidate_field(item, "genres")} for item in unflagged_candidates], "label"),
        "unflagged_catalogue_collections": _distribution([{"label": _candidate_field(item, "collections")} for item in unflagged_candidates], "label"),
        "unflagged_catalogue_creators": _distribution([{"label": _candidate_field(item, "creators")} for item in unflagged_candidates], "label"),
        "unflagged_catalogue_tags_metadata_hints": _tags(unflagged_candidates),
        "archive_licence_status": _distribution(items, "licence_status"),
        "archive_licence_categories": archive_licence_categories,
        "metadata_failure_statuses": _distribution(
            [item for item in items if item.get("status") == "metadata_unavailable" and
             item.get("metadata_status") != "not_fetched"], "metadata_status"),
        "archive_licence_urls": _distribution(
            [item for item in items if item.get("status") == "resolved"], "archive_license_url"),
        "archive_rights_present_identifiers": sum(bool(item.get("archive_rights")) for item in items),
        "retrieval_methods": _distribution(
            [item for item in items if item.get("status") == "resolved"], "retrieval_method"),
        "potential_archive_licences": _distribution([{"label": item["archive_license_label"]} for item in potential_items], "label"),
        "potential_archive_licence_urls": _distribution([{"label": item["archive_license_url"]} for item in potential_items], "label"),
        "technical_genres": _distribution(technical_items, "genre"),
        "technical_collections": technical_collections,
        "technical_creators": technical_creators,
        "technical_collection_concentration": _concentration(technical_collections),
        "technical_creator_concentration": _concentration(technical_creators),
        "provenance_genres": _distribution(plausible_items, "genre"),
        "provenance_collections": _distribution(plausible_items, "collection"),
        "provenance_creators": _distribution(plausible_items, "creator"),
        "potential_genres": _distribution(potential_items, "genre"),
        "potential_genre_sources": _distribution(potential_items, "genre_source"),
        "potential_collections": potential_collections,
        "potential_creators": potential_creators,
        "redistributable_collection_concentration": _concentration(potential_collections),
        "redistributable_creator_concentration": _concentration(potential_creators),
        "redistributable_license_types": _distribution(
            [{"label": "CC0" if item["archive_license_label"] == "CC0 1.0" else "CC BY"}
             for item in potential_items], "label"),
        "potential_tags_metadata_hints": _tags(potential_items),
        "exclusion_reasons_nonexclusive": {
            "blind_real_identifiers_in_exclusion_set": scan_summary["blind_real_identifiers_excluded_set"],
            "metadata_failed": metadata_failed,
            "metadata_not_attempted": metadata_not_attempted,
            "no_wav_flac_aiff_declared": sum(item.get("status") == "resolved" and
                                             not item.get("has_lossless_file") for item in items),
            "no_explicit_source_original": sum(item.get("status") == "resolved" and
                                               not item.get("has_explicit_original_file") for item in items),
            "no_strict_original_file": sum(item.get("status") == "resolved" and not item.get("strict_original_files") for item in items),
            "licence_unknown": funnel["archive_licence_unknown"],
            "licence_contradictory": funnel["archive_licence_contradictory"],
            "known_suspect_collection": sum(item.get("suspect_collection") is True for item in items),
            "known_non_music_collection": sum(item.get("non_music_collection") is True for item in items),
            "incomplete_credit_or_checksum": len(plausible_items) - len(potential_items),
        },
    }
    summary["decision"] = assess_feasibility(summary)
    import_stats_path = OUT / "import_summary.json"
    if import_stats_path.is_file():
        summary["import"] = json.loads(import_stats_path.read_text(encoding="utf-8"))
    write_jsonl(OUT / "items.jsonl", items)
    write_jsonl(OUT / "files.jsonl", files)
    write_json(OUT / "summary.json", summary)
    lines = ["# Audit de faisabilité IAMD → originaux Internet Archive", "",
             "Métadonnées uniquement ; aucun audio IAMD ni Archive téléchargé. "
             "`source=original` et l'extension/format sont déclaratifs : le caractère réellement lossless "
             "reste à vérifier sur les fichiers avant toute redistribution.", "",
             f"**Couverture : {metadata_ok:,}/{len(candidates):,} métadonnées résolues ; "
             f"{metadata_failed:,} échecs ; {metadata_not_attempted:,} non tentées.** "
             "Les comptes de fichiers, heures et octets sont observés uniquement sur les réponses résolues ; "
             "ils ne sont pas des zéros pour les items manquants.", "",
             "## Funnel (identifiants uniques)", "",
             "| Étape / catégorie | Nombre |", "| --- | ---: |",
             f"| Candidats initiaux CC0/CC BY, hors Blind-Real et collections connues | {funnel['initial_candidates']:,} |",
             f"| Métadonnées Archive résolues | {funnel['metadata_resolved']:,} |",
             f"| Métadonnées échouées / timeout / introuvables | {funnel['metadata_failed']:,} |",
             f"| Non encore tentées | {funnel['metadata_not_attempted']:,} |",
             f"| Licence Archive compatible avec IAMD | {funnel['archive_licence_compatible']:,} |",
             f"| Licence Archive inconnue | {funnel['archive_licence_unknown']:,} |",
             f"| Licence Archive contradictoire | {funnel['archive_licence_contradictory']:,} |",
             f"| Au moins un WAV / FLAC / AIFF déclaré | {funnel['has_wav_flac_aiff']:,} |",
             f"| Au moins un fichier non privé explicitement `source=original` | {funnel['has_explicit_source_original']:,} |",
             f"| `ambiguous_original_status` : au moins un fichier sans statut `source` | {funnel['ambiguous_original_status']:,} |",
             f"| `technical_candidate` : au moins un original lossless strict, non privé | {funnel['technical_candidate']:,} |",
             f"| `provenance_candidate` : technique + licence concordante + créateur + collection non signalée | {funnel['provenance_candidate']:,} |",
             f"| `redistributable_candidate` : provenance + taille et SHA1/MD5 d'au moins un original | {funnel['redistributable_candidate']:,} |",
             "",
             "Les lignes licence et présence de fichiers sont des catégories parmi les items résolus, "
             "non des filtres successifs. `ambiguous_original_status` peut chevaucher les candidats techniques "
             "si un autre fichier du même item est explicitement original. Un candidat redistribuable "
             "**n'est pas une autorisation de redistribution** : les droits de l'uploader restent à vérifier.", "",
             f"Avant ces {len(candidates):,} candidats : {len(all_candidates):,} items CC0/BY hors Blind-Real ; "
             f"{len(non_music_ids):,} collections non musicales connues et {len(doubtful_ids):,} "
             "collections à licence douteuse exclues (motifs non exclusifs).", ""]
    if metadata_ok:
        lines += ["## Heures et volume à télécharger (estimations métadonnées)", "",
                  f"- Niveau technique : **{len(strict):,} fichiers**, "
                  f"**{summary['strict_hours']['estimated_hours_including_imputation']:,.1f} h** estimées "
                  f"({summary['strict_hours']['known_hours']:,.1f} h de durées déclarées), "
                  f"**{summary['strict_size_bytes']/1024**3:,.1f} Gio** déclarés.",
                  f"- `redistributable_candidate` : **{len(potential_files):,} fichiers**, "
                  f"**{summary['potential_hours']['estimated_hours_including_imputation']:,.1f} h** estimées "
                  f"({summary['potential_hours']['known_hours']:,.1f} h déclarées), "
                  f"**{summary['potential_size_bytes']/1024**3:,.1f} Gio** déclarés.",
                  f"- Durées manquantes : {summary['potential_hours']['files_missing_length']:,} fichiers candidats "
                  f"dont {summary['potential_hours']['files_unestimated']:,} sans estimation possible. "
                  f"Tailles manquantes : {summary['strict_files_missing_size']:,} fichiers techniques. "
                  "Les sommes de tailles sont des bornes inférieures si des tailles manquent.", ""]
    else:
        lines += ["## Heures et volume à télécharger", "",
                  "**Indéterminables sans réponse Archive ; aucune valeur zéro n'est inférée.**", ""]
    lines += ["## Ambiguïtés et exclusions", ""]
    if metadata_ok:
        lines += [f"- Fichiers lossless à `source` absent : **{summary['files']['source_ambiguous']:,}** ; "
                  f"format Archive discordant ou absent : **{summary['files']['format_ambiguous']:,}** ; "
                  f"dérivés/autres : **{summary['files']['derivative_or_other']:,}** ; "
                  f"fichiers privés : **{summary['files']['private']:,}**."]
        lines += [f"- Champ `rights` Archive présent : {summary['archive_rights_present_identifiers']:,} "
                  "items résolus ; texte conservé dans `items.jsonl` pour revue humaine."]
    else:
        lines += ["- Statut `source=original` et cas ambigus : **indéterminables**, pas zéro."]
    if metadata_ok:
        lines += ["- Motifs ci-dessous non exclusifs (un item peut en cumuler plusieurs) :"]
        lines += [f"  - {name}: {count:,}" for name, count in summary["exclusion_reasons_nonexclusive"].items()]
    else:
        lines += [f"- Métadonnées Archive indisponibles pour les **{len(candidates):,}** candidats ; "
                  "aucun autre motif lié aux fichiers ou à la licence Archive n'est déductible."]
    sections = (("Licences IAMD (types)", "iamd_license_types"),
                       ("Licences IAMD (URL exactes)", "iamd_licences"),
                       ("Statuts des échecs de métadonnées Archive", "metadata_failure_statuses"),
                       ("Genres déclarés dans IAMD", "catalogue_genres"),
                       ("Collections déclarées dans IAMD", "catalogue_collections"),
                       ("Artistes/créateurs déclarés dans IAMD", "catalogue_creators"),
                       ("Tags IAMD, indices non vérifiés", "catalogue_tags_metadata_hints"),
                       ("Genres IAMD sans collections déjà signalées", "unflagged_catalogue_genres"),
                       ("Collections IAMD sans collections déjà signalées", "unflagged_catalogue_collections"),
                       ("Artistes IAMD sans collections déjà signalées", "unflagged_catalogue_creators"),
                       ("Tags IAMD sans collections déjà signalées", "unflagged_catalogue_tags_metadata_hints"))
    archive_sections = (("Formats WAV / FLAC / AIFF, niveau technique (fichiers)", "strict_formats"),
                       ("Formats WAV / FLAC / AIFF, candidats redistribuables (fichiers)", "potential_formats"),
                       ("Concordance licences Archive", "archive_licence_status"),
                       ("Licences Archive : compatibles / inconnues / contradictoires (items)", "archive_licence_categories"),
                       ("URL exactes des licences Archive, tous items résolus", "archive_licence_urls"),
                       ("Méthodes de récupération", "retrieval_methods"),
                       ("CC BY / CC0 des candidats redistribuables (items)", "redistributable_license_types"),
                       ("Versions de licence des candidats redistribuables", "potential_archive_licences"),
                       ("URL exactes des licences des candidats redistribuables", "potential_archive_licence_urls"),
                       ("Genres des candidats techniques", "technical_genres"),
                       ("Genres des candidats à provenance plausible", "provenance_genres"),
                       ("Genres des candidats redistribuables", "potential_genres"),
                       ("Sources des étiquettes de genre", "potential_genre_sources"),
                       ("Tags IAMD des candidats redistribuables, indices non vérifiés", "potential_tags_metadata_hints"),
                       ("Collections des candidats techniques : items par collection", "technical_collections"),
                       ("Créateurs des candidats techniques : items par créateur", "technical_creators"),
                       ("Collections des candidats redistribuables : items par collection", "potential_collections"),
                       ("Créateurs des candidats redistribuables : items par créateur", "potential_creators"))
    for title, key in sections + (archive_sections if metadata_ok else ()):
        lines += ["", f"## {title}", ""]
        values = summary[key]
        lines += [f"- {label}: {count:,}" for label, count in list(values.items())[:25]]
        if len(values) > 25:
            lines.append(f"- … {len(values)-25:,} catégories supplémentaires dans `summary.json`.")
    if metadata_ok:
        lines += ["", "## Concentration des sources", "",
                  "Comptages par `identifier` unique ; les libellés inconnus restent un groupe explicite.", "",
                  "| Sous-ensemble / champ | Groupes | Top 1 | Top 5 | Top 10 | Groupes effectifs | Inconnus |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for title, key in (("Technique / collection", "technical_collection_concentration"),
                           ("Technique / créateur", "technical_creator_concentration"),
                           ("Redistribuable / collection", "redistributable_collection_concentration"),
                           ("Redistribuable / créateur", "redistributable_creator_concentration")):
            concentration = summary[key]
            pct = lambda value: f"{100 * value:.1f} %" if value is not None else "indéterminé"
            effective = concentration["effective_groups"]
            lines.append(f"| {title} | {concentration['groups']:,} | "
                         f"{pct(concentration['top_1_share'])} | {pct(concentration['top_5_share'])} | "
                         f"{pct(concentration['top_10_share'])} | "
                         f"{effective:.1f} | {concentration['unknown_items']:,} |"
                         if effective is not None else
                         f"| {title} | 0 | indéterminé | indéterminé | indéterminé | indéterminé | 0 |")
    lines += ["", "## Lecture juridique", "",
              "`CC0`/`CC BY` dans IAMD et une licence concordante sur Archive restent des assertions "
              "de métadonnées. Le champ `rights` est conservé pour revue des contradictions éventuelles. "
              "Ni la titularité de l'uploader, ni le codec effectif, ni l'absence "
              "de transcodage avec perte ne sont établis en Phase 1.", ""]
    decision = summary["decision"]
    lines += ["## Verdict de faisabilité Phase 1", "",
              f"**{decision['verdict']}{' provisoire' if decision['provisional'] else ''}.** "
              "Ce verdict ne valide ni les droits des uploaders ni la fidélité lossless réelle des fichiers.", ""]
    lines += [f"- {reason}." for reason in decision["reasons"]]
    if not decision["reasons"]:
        lines.append("- Volume, heures et dispersion des sources dépassent les garde-fous de faisabilité.")
    lines += ["", "Garde-fous opérationnels explicites : au moins 2 000 `identifier` candidats, "
              "500 h estimées, 80 % de métadonnées résolues, 50 % des candidats techniques "
              "conservés après contrôles de provenance/fichier ; aucune collection > 70 %, "
              "aucun créateur > 10 %, au moins 100 créateurs effectifs. "
              "Aucun quota de genre n'est appliqué ; la répartition des genres et ses inconnus "
              "doivent être examinés avant une décision scientifique définitive.", ""]
    if summary.get("import", {}).get("partial_tail_ignored"):
        lines += ["Une dernière ligne JSONL incomplète a été ignorée à l'import ; "
                  "l'`identifier` correspondant reste non tenté tant qu'un résultat complet n'est pas rapatrié.", ""]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] {OUT / 'report.md'}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("scan", "fetch", "import", "report"))
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--rate", type=float, default=10.0, help="Maximum metadata requests per second")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--resolution-jsonl", type=Path,
                        help="Resolver output to import locally, without network")
    args = parser.parse_args()
    if args.stage == "scan":
        scan()
    elif args.stage == "fetch":
        fetch(args.workers, args.rate, args.retry_errors)
    elif args.stage == "import":
        if args.resolution_jsonl is None:
            parser.error("import requires --resolution-jsonl")
        import_resolution(args.resolution_jsonl)
    else:
        report()


if __name__ == "__main__":
    main()
