#!/usr/bin/env python3
"""Convert verified IAMD Phase 1b originals into the common clean manifest.

This adapter is local-only and fail-closed.  It consumes files already verified
against the Archive SHA-1/MD5 metadata, computes a local SHA-256, and probes the
container.  It never downloads or copies audio.  Rights remain pending even
when the Archive metadata advertises CC0/CC BY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import soundfile as sf


FORMATS = {"WAV", "FLAC", "AIFF"}


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            yield row


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verified(path: Path, row: dict) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing_local_file"
    expected_size = int(row.get("size_bytes") or 0)
    if expected_size <= 0 or path.stat().st_size != expected_size:
        return False, "size_mismatch"
    if row.get("sha1") and digest(path, "sha1") != str(row["sha1"]).lower():
        return False, "sha1_mismatch"
    if not row.get("sha1") and row.get("md5") and digest(path, "md5") != str(row["md5"]).lower():
        return False, "md5_mismatch"
    if not row.get("sha1") and not row.get("md5"):
        return False, "archive_checksum_missing"
    return True, "verified_archive_checksum"


def _archive_url(identifier: str) -> str:
    return "https://archive.org/details/" + quote(identifier, safe="")


def prepare(plan_path: Path, out_dir: Path) -> tuple[list[dict], dict]:
    tracks = list(read_jsonl(plan_path / "tracks.jsonl"))
    statuses = {}
    status_path = plan_path / "download_status.jsonl"
    if status_path.exists():
        for row in read_jsonl(status_path):
            track_id = str(row.get("track_id") or "")
            if track_id:
                statuses[track_id] = row

    output, skipped = [], {}
    seen = set()
    for track in tracks:
        track_id = str(track.get("track_id") or "")
        if not track_id or track_id in seen:
            raise ValueError(f"missing or duplicate track_id: {track_id!r}")
        seen.add(track_id)
        identifier = str(track.get("identifier") or "")
        name = str(track.get("name") or "")
        if not identifier or not name or Path(name).name != name:
            skipped["unsafe_or_missing_archive_name"] = skipped.get("unsafe_or_missing_archive_name", 0) + 1
            continue
        path = out_dir / "originals" / track_id / name
        ok, reason = verified(path, track)
        if not ok:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        try:
            with sf.SoundFile(path) as audio:
                container = str(audio.format or "").upper()
                if container not in FORMATS:
                    skipped["local_container_not_lossless"] = skipped.get("local_container_not_lossless", 0) + 1
                    continue
                sample_rate, channels = int(audio.samplerate), int(audio.channels)
                duration = len(audio) / sample_rate
        except (OSError, RuntimeError, ValueError) as error:
            skipped["local_audio_probe_failed"] = skipped.get("local_audio_probe_failed", 0) + 1
            continue
        source_id = f"{identifier}--{track_id}"
        archive_license = track.get("license_url")
        creator = track.get("creator") or None
        output.append({
            "schema": "openrestor-clean-manifest-v1",
            "dataset": "iamd_archive",
            "source_id": source_id,
            "source_key": f"iamd_archive:{source_id}",
            "audio_path": str(path.resolve()),
            "source_sha256": digest(path, "sha256"),
            "original_format": container,
            "sample_rate": sample_rate,
            "channels": channels,
            "duration_seconds": duration,
            "lossless_status": "lossless_container_unverified",
            "technical_candidate": True,
            "provenance_candidate": bool(track.get("licence_status") == "match" and creator),
            "redistributable_candidate": False,
            "metadata": {
                "title": track.get("title") or name,
                "creator": creator,
                "genre": track.get("genre") or "[unknown]",
                "collection": track.get("collection") or "[unknown]",
                "tags": track.get("tags") or [],
                "archive_identifier": identifier,
                "archive_item_url": _archive_url(identifier),
                "archive_original_name": name,
            },
            "rights": {
                "license_label": archive_license,
                "license_url": archive_license,
                "attribution": creator,
                "evidence_url": _archive_url(identifier),
                "review_status": "pilot_pending_asset_review",
                "rights_status": "pilot_pending_asset_review",
                "allow_commercial": None,
                "allow_redistribution": None,
                "allow_derivatives": None,
                "provenance_approved": False,
                "redistribution_approved": False,
                "source_status": "archive_original_download_verified_codec_unverified",
                "provenance_note": "Private pilot only; uploader rights and lossless source chain require review.",
            },
            "archive_original": {
                "identifier": identifier,
                "name": name,
                "format": track.get("format"),
                "source": track.get("source"),
                "archive_sha1": track.get("sha1"),
                "archive_md5": track.get("md5"),
                "download_status": statuses.get(track_id, {}).get("status"),
            },
        })
    report = {
        "schema_version": "iamd-pilot-manifest-v1",
        "plan_sources": len(tracks),
        "verified_sources": len(output),
        "skipped": dict(sorted(skipped.items())),
        "audio_downloaded_by_adapter": False,
        "audio_copied_by_adapter": False,
        "redistribution_approved": False,
        "rights_are_asset_level": True,
    }
    return sorted(output, key=lambda row: row["source_key"]), report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    rows, report = prepare(args.pilot_dir, args.pilot_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                        for row in rows), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Prepared {len(rows)} verified private IAMD pilot rows: {args.out}")


if __name__ == "__main__":
    main()
