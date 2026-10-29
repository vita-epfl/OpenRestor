#!/usr/bin/env python3
"""Download a tiny private pilot of selected Zenodo ZIP members.

This is the first stage that retrieves complete audio bytes.  It is bounded by
member count and compressed-byte budget, verifies the ZIP CRC and uncompressed
size, writes only below a caller-provided private directory, and records that
rights/provenance remain unresolved.  It never downloads a complete archive.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
import struct
import zlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.inspect_zenodo_zip_ranges import fetch_range
from scripts.probe_zenodo_member_headers import _member_data_start


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


def decompress_member(compressed: bytes, method: int) -> bytes:
    if method == 0:
        return compressed
    if method == 8:
        return zlib.decompress(compressed, -15)
    raise ValueError(f"unsupported ZIP compression method: {method}")


def choose_members(archives_path: Path, probes_path: Path, max_members: int) -> list[dict]:
    archives = {str(row["identity"]): row for row in read_jsonl(archives_path)}
    probes = [row for row in read_jsonl(probes_path) if row.get("status") == "resolved"]
    selected = []
    for probe in sorted(probes, key=lambda row: (int(row.get("compressed_size_bytes") or 0), row["identity"])):
        archive = archives.get(str(probe.get("archive_identity")))
        if not archive:
            continue
        member = next((item for item in archive.get("members") or []
                       if item.get("name") == probe.get("member_name")), None)
        if member:
            selected.append({"probe": probe, "archive": archive, "member": member})
        if len(selected) >= max_members:
            break
    return selected


def download_one(item: dict, out_dir: Path, timeout: float) -> dict:
    probe, archive, member = item["probe"], item["archive"], item["member"]
    identity = str(probe["identity"])
    url = str(archive["archive_url"])
    data_start, compressed_size = _member_data_start(url, member, timeout)
    compressed = fetch_range(url, data_start, data_start + compressed_size - 1, timeout)
    if len(compressed) != compressed_size:
        raise ValueError(f"compressed byte count mismatch: expected {compressed_size}, got {len(compressed)}")
    audio = decompress_member(compressed, int(member["compression_method"]))
    expected_size = int(member["uncompressed_size_bytes"])
    if len(audio) != expected_size:
        raise ValueError(f"uncompressed size mismatch: expected {expected_size}, got {len(audio)}")
    crc = f"{binascii.crc32(audio) & 0xFFFFFFFF:08x}"
    if crc != str(member["crc32"]).lower():
        raise ValueError(f"CRC mismatch: expected {member['crc32']}, got {crc}")
    digest = hashlib.sha256(audio).hexdigest()
    suffix = Path(str(member["name"])).suffix.lower() or ".audio"
    target = out_dir / "audio" / f"{digest}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != audio:
        raise ValueError(f"SHA-256 path collision with different bytes: {target}")
    if not target.exists():
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(audio)
        os.replace(temporary, target)
    local = {}
    try:
        import soundfile as sf
        info = sf.info(target)
        local = {"local_format": info.format, "local_subtype": info.subtype,
                 "local_sample_rate_hz": info.samplerate, "local_channels": info.channels,
                 "local_duration_seconds": float(info.duration)}
    except Exception as error:
        local = {"local_probe_error": f"{type(error).__name__}: {error}"}
    return {"identity": identity, "status": "verified", "dataset_record_id": archive.get("record_id"),
            "archive_key": archive.get("archive_key"), "member_name": member["name"],
            "archive_url": url, "local_audio_path": str(target),
            "compressed_bytes_downloaded": len(compressed), "uncompressed_bytes": len(audio),
            "crc32": crc, "audio_sha256": digest, "source_status": "ambiguous_original_status",
            "rights_status": "metadata_confirmed_pending_asset_review",
            "redistribution_approved": False, "private_pilot": True,
            "audio_downloaded": True, **local}


def run(archives_path: Path, probes_path: Path, out_dir: Path, max_members: int,
        max_total_compressed_bytes: int, timeout: float) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    notice = out_dir / "PRIVATE_PILOT_NOTICE.md"
    if not notice.exists():
        notice.write_text("# Private pilot\n\nAudio is local audit material; do not redistribute.\n"
                          "Rights and provenance remain unresolved.\n", encoding="utf-8")
    ledger_path = out_dir / "download_ledger.jsonl"
    existing = {str(row["identity"]): row for row in read_jsonl(ledger_path)} if ledger_path.exists() else {}
    selected = choose_members(archives_path, probes_path, max_members)
    used = sum(int(row.get("compressed_bytes_downloaded") or 0) for row in existing.values()
               if row.get("status") == "verified")
    for item in selected:
        identity = str(item["probe"]["identity"])
        if identity in existing:
            continue
        needed = int(item["member"]["compressed_size_bytes"])
        if used + needed > max_total_compressed_bytes:
            existing[identity] = {"identity": identity, "status": "budget_deferred",
                                  "compressed_bytes_needed": needed, "private_pilot": True,
                                  "audio_downloaded": False}
            write_jsonl(ledger_path, existing)
            continue
        try:
            result = download_one(item, out_dir, timeout)
            used += int(result["compressed_bytes_downloaded"])
        except Exception as error:
            result = {"identity": identity, "status": "error", "private_pilot": True,
                      "audio_downloaded": False, "error_type": type(error).__name__, "error": str(error)}
        existing[identity] = result
        write_jsonl(ledger_path, existing)
    return [existing[key] for key in sorted(existing)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-members", type=int, default=3)
    parser.add_argument("--max-total-compressed-bytes", type=int, default=50 * 1024 * 1024)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    if not 1 <= args.max_members <= 20 or args.max_total_compressed_bytes <= 0:
        raise SystemExit("max-members must be 1..20 and byte budget positive")
    rows = run(args.archives, args.probes, args.out_dir, args.max_members,
               args.max_total_compressed_bytes, args.timeout)
    print(f"Private pilot ledger: {len(rows)} rows in {args.out_dir}")


if __name__ == "__main__":
    main()
