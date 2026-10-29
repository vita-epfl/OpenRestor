#!/usr/bin/env python3
"""Inspect Zenodo ZIP central directories with bounded HTTP Range requests.

Only ZIP metadata bytes are fetched: the end-of-central-directory record and
the central directory.  No audio member is downloaded or opened.  The result
is deliberately ambiguous about ``source=original`` because ZIP metadata does
not establish that property.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


RANGE_USER_AGENT = "OpenRestore-archive-metadata-audit/1"
ZIP_EOCD = b"PK\x05\x06"
ZIP64_EOCD = b"PK\x06\x06"
ZIP_CENTRAL = b"PK\x01\x02"
ZIP64_EXTRA = 0x0001
AUDIO_EXTENSIONS = {".wav": "WAV", ".flac": "FLAC", ".aiff": "AIFF", ".aif": "AIFF"}


def _curl_range(url: str, start: int, end: int, timeout: float) -> bytes:
    """Fallback for Zenodo/proxy combinations where urllib receives a 406."""
    with tempfile.TemporaryDirectory(prefix="openrestore-range-") as directory:
        headers = Path(directory) / "headers"
        body = Path(directory) / "body"
        command = [
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--retry", "2", "--retry-delay", "5", "--connect-timeout", "20",
            "--max-time", str(max(1, int(timeout))), "--range", f"{start}-{end}",
            "--header", "Accept-Encoding: identity", "--user-agent", RANGE_USER_AGENT,
            "--dump-header", str(headers), "--output", str(body), url,
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        header_blocks = headers.read_bytes().replace(b"\r\n", b"\n").split(b"\n\n")
        block = next((candidate for candidate in reversed(header_blocks)
                      if candidate.startswith(b"HTTP/")), b"")
        lines = block.splitlines()
        if not lines:
            raise ValueError("curl returned no HTTP status")
        status = int(lines[0].split()[1])
        response_headers = {}
        for line in lines[1:]:
            if b":" in line:
                key, value = line.split(b":", 1)
                response_headers[key.decode("ascii", "ignore").lower()] = value.strip().decode(
                    "ascii", "ignore")
        data = body.read_bytes()
    expected = end - start + 1
    content_range = response_headers.get("content-range", "")
    if status != 206 or not content_range.startswith(f"bytes {start}-{end}/"):
        raise ValueError(f"curl did not honor bounded range ({status}, {content_range!r})")
    if len(data) != expected:
        raise ValueError(f"curl range length mismatch: expected {expected}, got {len(data)}")
    return data


def fetch_range(url: str, start: int, end: int, timeout: float = 30.0,
                retry_after_limit: float = 60.0) -> bytes:
    if start < 0 or end < start:
        raise ValueError("invalid byte range")
    request = Request(url, headers={
        "Range": f"bytes={start}-{end}",
        "Accept": "application/octet-stream",
        "Accept-Encoding": "identity",
        "User-Agent": RANGE_USER_AGENT,
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            data = response.read()
            content_range = response.headers.get("Content-Range", "")
    except Exception as error:
        code = getattr(error, "code", None)
        if code in {403, 406, 429}:
            return _curl_range(url, start, end, timeout)
        # Zenodo can return 406 with Retry-After while throttling range probes.
        # Do one bounded retry only; callers retain the error if the window is
        # longer than the configured limit or the second request fails.
        retry_after = float(getattr(error, "headers", {}).get("Retry-After", "0") or 0)
        if retry_after <= 0 or retry_after > retry_after_limit:
            raise
        time.sleep(retry_after)
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            data = response.read()
            content_range = response.headers.get("Content-Range", "")
    expected = end - start + 1
    if status != 206 or not content_range.startswith(f"bytes {start}-{end}/"):
        raise ValueError(f"server did not honor bounded range ({status}, {content_range!r})")
    if len(data) != expected:
        raise ValueError(f"range length mismatch: expected {expected}, got {len(data)}")
    return data


def _zip64_values(extra: bytes, values: list[int]) -> list[int]:
    offset = 0
    for length, kind in _extra_fields(extra):
        if kind == ZIP64_EXTRA:
            payload = extra[offset + 4:offset + 4 + length]
            cursor = 0
            output = []
            for value in values:
                if value == 0xFFFFFFFF:
                    if cursor + 8 > len(payload):
                        raise ValueError("truncated ZIP64 extra field")
                    output.append(struct.unpack_from("<Q", payload, cursor)[0])
                    cursor += 8
                else:
                    output.append(value)
            return output
        offset += 4 + length
    return values


def _extra_fields(extra: bytes):
    offset = 0
    while offset + 4 <= len(extra):
        kind, length = struct.unpack_from("<HH", extra, offset)
        if offset + 4 + length > len(extra):
            raise ValueError("truncated ZIP extra field")
        yield length, kind
        offset += 4 + length


def parse_zip_central_directory(central: bytes, expected_entries: int | None = None) -> list[dict]:
    """Parse central-directory entries without reading local file data."""
    entries = []
    offset = 0
    while offset < len(central):
        if central[offset:offset + 4] != ZIP_CENTRAL:
            # A trailing padding/comment is not a member; tolerate only zero bytes.
            if not all(byte == 0 for byte in central[offset:]):
                raise ValueError(f"invalid central-directory signature at offset {offset}")
            break
        if offset + 46 > len(central):
            raise ValueError("truncated central-directory header")
        fields = struct.unpack_from("<4s6H3L5H2L", central, offset)
        (_, _made, _needed, flags, method, _mtime, _mdate, crc, compressed,
         uncompressed, name_len, extra_len, comment_len, _disk, _internal, _external,
         local_offset) = fields
        begin = offset + 46
        end_name = begin + name_len
        end_extra = end_name + extra_len
        end_entry = end_extra + comment_len
        if end_entry > len(central):
            raise ValueError("truncated central-directory member")
        name_bytes = central[begin:end_name]
        encoding = "utf-8" if flags & 0x800 else "cp437"
        name = name_bytes.decode(encoding, errors="replace")
        extra = central[end_name:end_extra]
        compressed, uncompressed, local_offset = _zip64_values(
            extra, [compressed, uncompressed, local_offset])
        suffix = Path(name).suffix.lower()
        is_macos_sidecar = name.startswith("__MACOSX/") or Path(name).name.startswith("._")
        entries.append({
            "name": name,
            "is_directory": name.endswith("/"),
            "is_macos_sidecar": is_macos_sidecar,
            "compression_method": method,
            "flags": flags,
            "crc32": f"{crc:08x}",
            "compressed_size_bytes": compressed,
            "uncompressed_size_bytes": uncompressed,
            "local_header_offset": local_offset,
            "format": AUDIO_EXTENSIONS.get(suffix) if not is_macos_sidecar else None,
            "source_status": ("ambiguous_original_status"
                              if suffix in AUDIO_EXTENSIONS and not is_macos_sidecar else None),
        })
        offset = end_entry
    if expected_entries is not None and len(entries) != expected_entries:
        raise ValueError(f"central-directory count mismatch: expected {expected_entries}, got {len(entries)}")
    return entries


def parse_zip_metadata(archive_size: int, tail: bytes, central: bytes) -> list[dict]:
    """Decode EOCD from a bounded tail and parse the supplied central directory."""
    position = tail.rfind(ZIP_EOCD)
    if position < 0 or position + 22 > len(tail):
        raise ValueError("ZIP end-of-central-directory record not found")
    (_signature, _disk, _cd_disk, disk_entries, total_entries, cd_size, cd_offset,
     comment_length) = struct.unpack_from("<4s4H2LH", tail, position)
    if position + 22 + comment_length > len(tail):
        raise ValueError("truncated ZIP comment")
    if disk_entries == 0xFFFF or total_entries == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise ValueError("ZIP64 central-directory offsets require ZIP64 locator support")
    if cd_offset + cd_size > archive_size:
        raise ValueError("central directory lies outside archive")
    if len(central) != cd_size:
        raise ValueError(f"central-directory byte count mismatch: expected {cd_size}, got {len(central)}")
    return parse_zip_central_directory(central, total_entries)


def inspect_archive(url: str, archive_size: int, archive_key: str,
                    timeout: float = 30.0, max_central_directory_bytes: int = 128 * 1024 * 1024) -> dict:
    if archive_size <= 0:
        raise ValueError("archive size must be positive")
    tail_size = min(archive_size, 65557)
    tail_start = archive_size - tail_size
    tail = fetch_range(url, tail_start, archive_size - 1, timeout)
    eocd = tail.rfind(ZIP_EOCD)
    if eocd < 0 or eocd + 22 > len(tail):
        raise ValueError("ZIP end-of-central-directory record not found")
    (_sig, _disk, _cd_disk, _disk_entries, total_entries, cd_size, cd_offset,
     _comment_length) = struct.unpack_from("<4s4H2LH", tail, eocd)
    if cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF or total_entries == 0xFFFF:
        raise ValueError("ZIP64 archive is not supported by the bounded inspector")
    if cd_size > max_central_directory_bytes:
        raise ValueError(f"central directory exceeds safety limit: {cd_size} bytes")
    central = fetch_range(url, cd_offset, cd_offset + cd_size - 1, timeout) if cd_size else b""
    members = parse_zip_metadata(archive_size, tail, central)
    audio = [member for member in members if member.get("format")]
    sidecars = [member for member in members if member.get("is_macos_sidecar")]
    formats = collections.Counter(member["format"] for member in audio)
    return {
        "schema_version": "zenodo-zip-range-inspection-v1",
        "archive_key": archive_key,
        "archive_url": url,
        "archive_size_bytes": archive_size,
        "metadata_only": True,
        "audio_downloaded": False,
        "archive_members_inspected": True,
        "source_status": "ambiguous_original_status",
        "member_count": len(members),
        "audio_member_count": len(audio),
        "macos_sidecar_count": len(sidecars),
        "audio_member_formats": dict(sorted(formats.items())),
        "audio_uncompressed_bytes": sum(member["uncompressed_size_bytes"] for member in audio),
        "members": members,
        "notes": "ZIP central directory only; source=original and per-file licence remain unresolved.",
    }


def read_jsonl(path: Path):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at {path}:{number}") from error


def write_jsonl(path: Path, rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(rows[key], ensure_ascii=False, sort_keys=True) + "\n"
                                      for key in sorted(rows)), encoding="utf-8")
    os.replace(temporary, path)


def inspect_resolution_file(input_path: Path, out: Path, timeout: float = 30.0,
                           refresh: bool = False) -> list[dict]:
    existing = {}
    if out.exists():
        for row in read_jsonl(out):
            existing[str(row.get("identity"))] = row
    resolutions = list(read_jsonl(input_path))
    for resolution in resolutions:
        for file in resolution.get("files") or []:
            key = str(file.get("key") or "")
            if not key.lower().endswith(".zip"):
                continue
            identity = f"{resolution.get('record_id')}:{key}"
            if identity in existing and not refresh:
                continue
            row = {"identity": identity, "record_id": resolution.get("record_id"),
                   "requested_record": resolution.get("requested_record"), **{
                       "archive_key": key,
                       "archive_url": file.get("download_url"),
                       "archive_size_bytes": file.get("size_bytes"),
                       "resolution_status": "pending",
                   }}
            try:
                result = inspect_archive(str(file["download_url"]), int(file["size_bytes"]), key, timeout)
                row.update(result, resolution_status="resolved")
            except Exception as error:
                row.update({"resolution_status": "error", "metadata_only": True,
                            "audio_downloaded": False, "source_status": "unresolved",
                            "error_type": type(error).__name__, "error": str(error)})
            existing[identity] = row
            write_jsonl(out, existing)
    return [existing[key] for key in sorted(existing)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="JSONL produced by resolve_zenodo_metadata.py")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    rows = inspect_resolution_file(args.input, args.out, args.timeout, args.refresh)
    print(f"Inspected {len(rows)} Zenodo ZIP metadata records: {args.out}")


if __name__ == "__main__":
    main()
