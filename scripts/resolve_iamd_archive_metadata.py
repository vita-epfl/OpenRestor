#!/usr/bin/env python3
"""Portable, metadata-only Internet Archive resolver (Python standard library).

Input: JSONL with one ``identifier`` per row plus optional IAMD metadata.
Output: append-only JSONL, one result per attempted identifier. Re-running skips
completed identifiers; --retry-errors appends a newer result for failed ones.
Only /metadata/<id> and, optionally, <id>_files.xml / <id>_meta.xml are GETs.
It never requests an audio download URL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SUFFIXES = {".wav": "WAV", ".wave": "WAV", ".flac": "FLAC",
            ".aiff": "AIFF", ".aif": "AIFF"}
META_FIELDS = ("identifier", "licenseurl", "rights", "creator", "uploader", "title",
               "collection", "subject", "genre", "mediatype", "access-restricted-item")
FILE_FIELDS = ("name", "source", "format", "size", "length", "sha1", "md5", "private")
MAX_METADATA_BYTES = 32 * 1024 * 1024
USER_AGENT = "OpenRestor-IAMD-feasibility/0.2 (metadata only)"


def metadata_url(identifier: str) -> str:
    return "https://archive.org/metadata/" + urllib.parse.quote(identifier, safe="")


def xml_url(identifier: str, kind: str) -> str:
    encoded_id = urllib.parse.quote(identifier, safe="")
    filename = urllib.parse.quote(identifier + "_" + kind + ".xml", safe="")
    return f"https://archive.org/download/{encoded_id}/{filename}"


def download_url(identifier: str, name: str) -> str:
    return ("https://archive.org/download/" + urllib.parse.quote(identifier, safe="") +
            "/" + urllib.parse.quote(name, safe="/"))


def get_bytes(url: str, timeout: float, retries: int) -> bytes:
    """Read bounded metadata responses only; callers supply fixed metadata URLs."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read(MAX_METADATA_BYTES + 1)
            if len(payload) > MAX_METADATA_BYTES:
                raise ValueError("metadata response exceeds 32 MiB safety limit")
            return payload
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            last_error = error
            if isinstance(error, urllib.error.HTTPError) and error.code in {400, 403, 404}:
                break
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"{url}: {type(last_error).__name__}: {last_error}") from last_error


def _format(name: str) -> str | None:
    return SUFFIXES.get(Path(name).suffix.lower())


def _format_matches(fmt: str, declared: Any) -> bool:
    text = str(declared or "").lower()
    terms = {"WAV": ("wave", "wav"), "FLAC": ("flac",), "AIFF": ("aiff", "aifc", "aif")}
    return any(term in text for term in terms[fmt])


def _private(value: Any) -> bool:
    return str(value or "").lower() in {"true", "1", "yes"}


def filter_files(identifier: str, raw_files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep only lossless-extension metadata; separate strict and ambiguous cases."""
    files: list[dict[str, Any]] = []
    counts = {"strict_original": 0, "source_ambiguous": 0,
              "format_ambiguous": 0, "derivative_or_other": 0, "private_file": 0}
    for raw in raw_files:
        name = raw.get("name")
        if not isinstance(name, str) or not name or not _format(name):
            continue
        fmt = _format(name)
        source = str(raw.get("source") or "").lower().strip()
        if _private(raw.get("private")):
            status = "private_file"
        elif source == "original":
            status = "strict_original" if _format_matches(fmt, raw.get("format")) else "format_ambiguous"
        elif not source:
            status = "source_ambiguous"
        else:
            status = "derivative_or_other"
        counts[status] += 1
        if status in {"derivative_or_other", "private_file"}:
            continue
        file = {key: raw.get(key) for key in FILE_FIELDS}
        file.update(format_family=fmt, original_status=status,
                    download_url=download_url(identifier, name))
        files.append(file)
    return files, counts


def metadata_api(identifier: str, timeout: float, retries: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    body = json.loads(get_bytes(metadata_url(identifier), timeout, retries))
    if body == [] or body == {}:
        raise LookupError("item not found (empty metadata response)")
    if not isinstance(body, dict):
        raise ValueError("metadata response is not an object")
    if body.get("is_dark") or body.get("is_dark_item"):
        raise ValueError("item is dark/restricted")
    if body.get("error"):
        raise ValueError(f"metadata API error: {body['error']}")
    if not isinstance(body.get("files"), list) or not isinstance(body.get("metadata"), dict):
        raise ValueError("metadata response lacks files or item metadata")
    return ({key: body["metadata"].get(key) for key in META_FIELDS}, body["files"])


def _parse_files_xml(payload: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    if root.tag != "files":
        raise ValueError(f"unexpected files XML root: {root.tag}")
    files = []
    for node in root.findall("file"):
        file = {key: node.get(key) or node.findtext(key) for key in FILE_FIELDS}
        files.append(file)
    return files


def _parse_meta_xml(payload: bytes) -> dict[str, Any]:
    root = ET.fromstring(payload)
    if root.tag != "metadata":
        raise ValueError(f"unexpected metadata XML root: {root.tag}")
    metadata: dict[str, Any] = {}
    for key in META_FIELDS:
        values = [(node.text or "").strip() for node in root.findall(key)]
        values = [value for value in values if value]
        metadata[key] = values[0] if len(values) == 1 else values or None
    return metadata


def xml_fallback(identifier: str, timeout: float, retries: int) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    raw_files = _parse_files_xml(get_bytes(xml_url(identifier, "files"), timeout, retries))
    warning = None
    try:
        metadata = _parse_meta_xml(get_bytes(xml_url(identifier, "meta"), timeout, retries))
    except (RuntimeError, ET.ParseError, ValueError) as error:
        metadata = {key: None for key in META_FIELDS}
        warning = f"item _meta.xml unavailable; licence/rights unknown: {error}"
    return metadata, raw_files, warning


def resolve(identifier: str, timeout: float, retries: int, use_xml_fallback: bool) -> dict[str, Any]:
    row: dict[str, Any] = {"schema_version": 1, "identifier": identifier,
                           "fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    api_error = None
    try:
        metadata, raw_files = metadata_api(identifier, timeout, retries)
        method, warning = "metadata_api", None
    except (RuntimeError, LookupError, ValueError, json.JSONDecodeError) as error:
        api_error = f"{type(error).__name__}: {error}"
        if not use_xml_fallback:
            row.update(status="not_found" if isinstance(error, LookupError) else "error",
                       method="metadata_api", error=api_error)
            return row
        try:
            metadata, raw_files, warning = xml_fallback(identifier, timeout, retries)
            method = "files_xml"
        except (RuntimeError, ET.ParseError, ValueError) as xml_error:
            row.update(status="not_found" if isinstance(error, LookupError) else "error",
                       method="metadata_api+files_xml", error=f"{api_error}; XML: {xml_error}")
            return row
    files, counts = filter_files(identifier, raw_files)
    row.update(status="ok", method=method, metadata=metadata, files=files,
               lossless_file_counts=counts)
    if api_error:
        row["metadata_api_error"] = api_error
    if warning:
        row["warning"] = warning
    return row


def read_candidates(path: Path) -> list[str]:
    identifiers: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            identifier = row.get("identifier")
            if not isinstance(identifier, str) or not identifier or not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
                raise ValueError(f"Unsafe/missing identifier on input line {line_number}: {identifier!r}")
            if identifier in seen:
                raise ValueError(f"Duplicate identifier on input line {line_number}: {identifier}")
            identifiers.append(identifier)
            seen.add(identifier)
    return identifiers


def read_progress(path: Path) -> dict[str, str]:
    """Recover only a truncated final line from this script's append-only output."""
    latest: dict[str, str] = {}
    if not path.exists():
        return latest
    with path.open("rb+") as handle:
        while True:
            start = handle.tell()
            line = handle.readline()
            if not line:
                break
            try:
                row = json.loads(line)
                latest[row["identifier"]] = row["status"]
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
                if handle.read(1):
                    raise ValueError(f"Invalid non-final JSONL line at byte {start}: {error}") from error
                handle.truncate(start)
                break
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Filtered IAMD candidates JSONL")
    parser.add_argument("--output", type=Path, required=True, help="Incremental resolution JSONL")
    parser.add_argument("--xml-fallback", action="store_true", help="Try _files.xml and _meta.xml when MDAPI fails")
    parser.add_argument("--retry-errors", action="store_true", help="Retry prior errors, appending a newer result")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=0.25, help="Delay between identifiers in seconds")
    parser.add_argument("--max-items", type=int, help="Limit this run for a small connectivity test")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output must be different files")
    if args.timeout <= 0 or args.retries < 0 or args.sleep < 0 or (args.max_items is not None and args.max_items < 1):
        parser.error("timeout must be positive; retries/sleep nonnegative; max-items positive")
    candidates = read_candidates(args.input)
    progress = read_progress(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    remaining = [identifier for identifier in candidates
                 if identifier not in progress or (args.retry_errors and progress[identifier] == "error")]
    if args.max_items is not None:
        remaining = remaining[:args.max_items]
    print(f"{len(candidates):,} candidates; {len(remaining):,} to resolve; {len(progress):,} prior results", flush=True)
    with args.output.open("a", encoding="utf-8") as handle:
        for number, identifier in enumerate(remaining, 1):
            result = resolve(identifier, args.timeout, args.retries, args.xml_fallback)
            handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            if number % 100 == 0 or result["status"] != "ok":
                print(f"{number:,}/{len(remaining):,} {identifier}: {result['status']}", flush=True)
            if number < len(remaining):
                time.sleep(args.sleep)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted; completed JSONL lines are safely resumable.", file=sys.stderr)
        sys.exit(130)
