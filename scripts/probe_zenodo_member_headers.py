#!/usr/bin/env python3
"""Probe a bounded sample of ZIP audio-member headers via HTTP Range.

The probe downloads only the local ZIP header and a bounded prefix of each
selected member's compressed stream. It never reconstructs a complete audio
file and never marks ``source=original`` or redistribution rights as approved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.inspect_zenodo_zip_ranges import fetch_range


def _find_chunk(data: bytes, chunk_id: bytes) -> tuple[int, int] | None:
    little = data[:4] in {b"RIFF", b"RF64"}
    cursor = 12 if data[:4] in {b"RIFF", b"RF64", b"FORM"} else 0
    while cursor + 8 <= len(data):
        ident = data[cursor:cursor + 4]
        size = struct.unpack_from("<I" if little else ">I", data, cursor + 4)[0]
        if ident == chunk_id:
            return cursor + 8, size
        cursor += 8 + size + (size & 1)
    return None


def _parse_extended_rate(value: bytes) -> float | None:
    if len(value) != 10:
        return None
    exponent = int.from_bytes(value[:2], "big")
    fraction = int.from_bytes(value[2:], "big")
    if exponent == 0 or exponent == 0x7FFF:
        return None
    return (1.0 + fraction / 2**63) * 2**(exponent - 16383)


def parse_audio_header(data: bytes, extension: str) -> dict:
    """Parse container metadata from a prefix; missing fields remain unknown."""
    result = {"container_signature": data[:12].decode("latin1", errors="replace"),
              "header_complete": False, "codec": None, "sample_rate_hz": None,
              "channels": None, "bits_per_sample": None, "duration_seconds": None}
    suffix = extension.lower()
    if suffix == ".wav" and len(data) >= 12 and data[:4] in {b"RIFF", b"RF64"} and data[8:12] == b"WAVE":
        result["container"] = "WAV"
        fmt = _find_chunk(data, b"fmt ")
        if fmt and fmt[1] >= 16 and len(data) >= fmt[0] + 16:
            payload = data[fmt[0]:fmt[0] + fmt[1]]
            audio_format, channels, rate, byte_rate, _align, bits = struct.unpack_from("<HHIIHH", payload)
            result.update(sample_rate_hz=rate, channels=channels, bits_per_sample=bits,
                          codec={1: "PCM", 3: "IEEE_FLOAT", 0xFFFE: "WAVE_FORMAT_EXTENSIBLE"}.get(
                              audio_format, f"WAV_FORMAT_{audio_format}"), header_complete=True)
            data_chunk = _find_chunk(data, b"data")
            if data_chunk and byte_rate:
                result["duration_seconds"] = data_chunk[1] / byte_rate
        return result
    if suffix in {".aif", ".aiff"} and len(data) >= 12 and data[:4] == b"FORM" and data[8:12] in {b"AIFF", b"AIFC"}:
        result["container"] = data[8:12].decode("ascii")
        comm = _find_chunk(data, b"COMM")
        if comm and comm[1] >= 18 and len(data) >= comm[0] + 18:
            channels, frames, bits = struct.unpack_from(">HIH", data, comm[0])
            rate = _parse_extended_rate(data[comm[0] + 8:comm[0] + 18])
            result.update(sample_rate_hz=rate, channels=channels, bits_per_sample=bits,
                          codec="AIFF_PCM", duration_seconds=frames / rate if rate else None,
                          header_complete=True)
        return result
    if suffix == ".flac" and data[:4] == b"fLaC" and len(data) >= 42:
        result["container"] = "FLAC"
        block_type = data[4] & 0x7F
        block_size = int.from_bytes(data[5:8], "big")
        if block_type == 0 and block_size >= 34:
            packed = int.from_bytes(data[18:26], "big")
            rate = packed >> 44
            channels = ((packed >> 41) & 0x7) + 1
            bits = ((packed >> 36) & 0x1F) + 1
            samples = packed & ((1 << 36) - 1)
            result.update(sample_rate_hz=rate, channels=channels, bits_per_sample=bits,
                          codec="FLAC", duration_seconds=samples / rate if rate else None,
                          header_complete=True)
        return result
    result["container"] = "unknown"
    return result


def _member_data_start(url: str, member: dict, timeout: float) -> tuple[int, int]:
    offset = int(member["local_header_offset"])
    header = fetch_range(url, offset, offset + 29, timeout)
    if header[:4] != b"PK\x03\x04":
        raise ValueError("local ZIP header signature missing")
    name_length, extra_length = struct.unpack_from("<HH", header, 26)
    return offset + 30 + name_length + extra_length, int(member["compressed_size_bytes"])


def probe_member(url: str, member: dict, max_probe_bytes: int = 262144,
                 timeout: float = 30.0) -> dict:
    if member.get("is_directory") or not member.get("format"):
        raise ValueError("member is not an eligible audio extension")
    data_start, compressed_size = _member_data_start(url, member, timeout)
    amount = min(compressed_size, max_probe_bytes)
    compressed = fetch_range(url, data_start, data_start + amount - 1, timeout)
    method = int(member.get("compression_method", -1))
    if method == 0:
        prefix = compressed
    elif method == 8:
        prefix = zlib.decompressobj(-15).decompress(compressed, max_probe_bytes)
    else:
        raise ValueError(f"unsupported ZIP compression method: {method}")
    parsed = parse_audio_header(prefix, "." + str(member["format"]).lower())
    return {"member_name": member["name"], "format_from_name": member["format"],
            "compression_method": method, "compressed_size_bytes": compressed_size,
            "probe_bytes_downloaded": 30 + amount, "uncompressed_prefix_bytes": len(prefix),
            "source_status": "ambiguous_original_status", "audio_downloaded": False,
            "metadata_only": True, **parsed}


def _stable_sample(members: list[dict], archive_identity: str, count: int, seed: int) -> list[dict]:
    eligible = [m for m in members if m.get("format") and not m.get("is_macos_sidecar")]
    ordered = sorted(eligible, key=lambda m: hashlib.sha256(
        f"{seed}|{archive_identity}|{m['name']}".encode()).hexdigest())
    return ordered[:min(count, len(ordered))]


def read_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def write_jsonl(path: Path, rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(rows[key], ensure_ascii=False, sort_keys=True) + "\n"
                                      for key in sorted(rows)), encoding="utf-8")
    os.replace(temporary, path)


def run(input_path: Path, output: Path, sample_per_archive: int, seed: int,
        max_probe_bytes: int, timeout: float) -> list[dict]:
    existing = {str(row["identity"]): row for row in read_jsonl(output)} if output.exists() else {}
    for archive in read_jsonl(input_path):
        identity_base = str(archive.get("identity"))
        for member in _stable_sample(archive.get("members") or [], identity_base, sample_per_archive, seed):
            identity = f"{identity_base}:{member['name']}"
            if identity in existing:
                continue
            row = {"identity": identity, "archive_identity": identity_base,
                   "record_id": archive.get("record_id"), "archive_key": archive.get("archive_key"),
                   "archive_url": archive.get("archive_url"), "member_name": member["name"],
                   "status": "pending"}
            try:
                row.update(probe_member(str(archive["archive_url"]), member, max_probe_bytes, timeout), status="resolved")
            except Exception as error:
                row.update({"status": "error", "source_status": "unresolved",
                            "audio_downloaded": False, "metadata_only": True,
                            "error_type": type(error).__name__, "error": str(error)})
            existing[identity] = row
            write_jsonl(output, existing)
    return [existing[key] for key in sorted(existing)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample-per-archive", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--max-probe-bytes", type=int, default=262144)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if not 1 <= args.sample_per_archive <= 10 or not 4096 <= args.max_probe_bytes <= 4 * 1024 * 1024:
        raise SystemExit("sample-per-archive must be 1..10 and max-probe-bytes 4096..4194304")
    rows = run(args.input, args.out, args.sample_per_archive, args.seed,
               args.max_probe_bytes, args.timeout)
    print(f"Probed {len(rows)} bounded audio headers: {args.out}")


if __name__ == "__main__":
    main()
