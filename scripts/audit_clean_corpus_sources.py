#!/usr/bin/env python3
"""Audit locally indexed audio for the OpenRestore Clean multi-dataset pool.

This is an inventory gate, not a rights approval and not an audio downloader. It
uses existing indexes, optionally resolves transferred files below ``--audio-root``,
and records the original container separately from the local transfer container.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import soundfile as sf


LOSSLESS = {".wav", ".flac", ".aif", ".aiff"}
LOSSY = {".mp3", ".aac", ".m4a", ".ogg", ".opus"}
VERIFIED_ORIGINAL_PREFIXES = ("archive_original_download_verified", "strict_original_verified")


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSONL at {path}:{number}") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def transfer_candidate(root: Path | None, dataset: str, source_id: str) -> Path | None:
    if root is None:
        return None
    prefix = f"{dataset}--{source_id}--"
    matches = sorted(path for path in root.rglob("*")
                     if path.is_file() and path.name.startswith(prefix))
    return matches[0] if len(matches) == 1 else None


def _source_status(row: dict) -> str:
    rights = row.get("rights") or {}
    archive_original = row.get("archive_original") or {}
    return str(row.get("source_status") or rights.get("source_status") or
               archive_original.get("source_status") or archive_original.get("source") or "")


def _lossless_codec(actual_format: str, subtype: str) -> bool:
    """Return true only for decoded PCM/IEEE-float in a lossless container."""
    return actual_format in {"WAV", "FLAC", "AIFF"} and (
        subtype.startswith("PCM_") or subtype == "IEEE_FLOAT"
    )


def inspect(row: dict, audio_root: Path | None, hash_missing: bool,
            registry: dict[str, dict]) -> dict:
    dataset = str(row.get("dataset") or "unknown")
    source_id = str(row.get("source_id") or "")
    source_key = f"{dataset}:{source_id}"
    indexed_path = Path(str(row.get("audio_path") or ""))
    local_path = indexed_path if indexed_path.is_file() else transfer_candidate(audio_root, dataset, source_id)
    source_ext = indexed_path.suffix.lower()
    # Prefer the external asset registry when supplied, but keep inline rights
    # from a common manifest when auditing a pilot directly.  The audit must
    # never erase provenance metadata merely because no separate registry path
    # was passed.
    rights = registry.get(source_key) or row.get("rights") or {"status": "not_in_asset_registry"}
    result = {"dataset": dataset, "source_id": source_id, "source_key": source_key,
              "indexed_audio_path": str(indexed_path), "local_audio_path": str(local_path) if local_path else None,
              "audio_path": str(local_path) if local_path else None,
              "original_extension": source_ext or None,
              "source_sha256": row.get("source_sha256"), "role": row.get("role"),
              "split": row.get("split"), "availability": "missing" if local_path is None else "available",
              "rights": rights}
    if local_path is None:
        result.update(lossless_status="unavailable", technical_candidate=False,
                      provenance_candidate=False, redistributable_candidate=False,
                      format=None, subtype=None,
                      sample_rate=None, channels=None, duration_seconds=None, size_bytes=None)
        return result
    try:
        info = sf.info(local_path)
        actual_format = str(info.format or "").upper()
        subtype = str(info.subtype or "")
        actual_ext = local_path.suffix.lower()
        result.update(format=actual_format, subtype=subtype, actual_extension=actual_ext,
                      sample_rate=info.samplerate, channels=info.channels,
                      duration_seconds=float(info.duration), size_bytes=local_path.stat().st_size)
        if hash_missing or not result.get("source_sha256"):
            result["local_sha256"] = sha256(local_path)
        original_status = _source_status(row)
        original_verified = any(original_status.startswith(prefix)
                                for prefix in VERIFIED_ORIGINAL_PREFIXES)
        expected_sha = str(result.get("source_sha256") or "").lower()
        if original_verified and expected_sha:
            observed_sha = result.get("local_sha256") or sha256(local_path)
            result["local_sha256"] = observed_sha
            result["source_hash_match"] = observed_sha.lower() == expected_sha
        else:
            result["source_hash_match"] = False
        codec_verified = _lossless_codec(actual_format, subtype)
        result["source_original_verified"] = original_verified
        result["codec_lossless_verified"] = codec_verified
        # A decoded MP3 remains lossy even when the transfer is a WAV.
        if source_ext in LOSSY or dataset == "sdd":
            status = "clean_lossy_hq"
        elif (source_ext in LOSSLESS and actual_ext in LOSSLESS and
              codec_verified and original_verified and result["source_hash_match"]):
            status = "clean_lossless"
        elif source_ext in LOSSLESS and actual_ext in LOSSLESS and actual_format in {"WAV", "FLAC", "AIFF"}:
            status = "lossless_container_unverified"
        else:
            status = "format_or_provenance_ambiguous"
        result["lossless_status"] = status
        result["technical_candidate"] = status in {"clean_lossless", "lossless_container_unverified", "clean_lossy_hq"}
        result["provenance_candidate"] = bool(
            row.get("provenance_candidate") is True or
            rights.get("provenance_candidate") is True or
            rights.get("review_status") == "approved"
        )
        result["redistributable_candidate"] = bool(
            row.get("redistributable_candidate") is True or
            (rights.get("review_status") == "approved" and
             rights.get("allow_redistribution") is True and
             rights.get("allow_derivatives") is True)
        )
    except (OSError, RuntimeError, ValueError) as error:
        result.update(lossless_status="unreadable", technical_candidate=False,
                      provenance_candidate=False, redistributable_candidate=False,
                      format=None, subtype=None,
                      sample_rate=None, channels=None, duration_seconds=None,
                      size_bytes=local_path.stat().st_size,
                      read_error=f"{type(error).__name__}: {error}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="append", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path,
                        help="Optional existing transfer root; no audio is downloaded")
    parser.add_argument("--rights-registry", type=Path,
                        help="Optional per-asset rights JSONL; absent records stay unknown")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--hash-missing", action="store_true",
                        help="Hash local files absent from the source index; can be expensive")
    args = parser.parse_args()
    registry = {}
    if args.rights_registry:
        for row in read_jsonl(args.rights_registry):
            registry[str(row.get("media_key"))] = row
    rows = []
    seen = set()
    for index in args.index:
        for row in read_jsonl(index):
            key = f"{row.get('dataset')}:{row.get('source_id')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(inspect(row, args.audio_root, args.hash_missing, registry))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
                        encoding="utf-8")
    by_dataset = collections.defaultdict(lambda: collections.Counter())
    hours = collections.Counter()
    bytes_by_dataset = collections.Counter()
    rights_by_dataset = collections.defaultdict(collections.Counter)
    formats_by_dataset = collections.defaultdict(collections.Counter)
    candidate_counts = collections.Counter()
    for row in rows:
        by_dataset[row["dataset"]][row["lossless_status"]] += 1
        hours[row["dataset"]] += float(row.get("duration_seconds") or 0) / 3600
        bytes_by_dataset[row["dataset"]] += int(row.get("size_bytes") or 0)
        rights_by_dataset[row["dataset"]][str((row.get("rights") or {}).get("review_status") or "unknown")] += 1
        formats_by_dataset[row["dataset"]][str(row.get("format") or "unknown")] += 1
        for field in ("technical_candidate", "provenance_candidate", "redistributable_candidate"):
            if row.get(field):
                candidate_counts[field] += 1
    summary = {"source_count": len(rows), "unique_source_keys": len(seen),
               "by_dataset_status": {key: dict(value) for key, value in sorted(by_dataset.items())},
               "hours_by_dataset": {key: round(value, 3) for key, value in sorted(hours.items())},
               "bytes_by_dataset": dict(sorted(bytes_by_dataset.items())),
               "rights_review_status_by_dataset": {key: dict(value) for key, value in sorted(rights_by_dataset.items())},
               "formats_by_dataset": {key: dict(value) for key, value in sorted(formats_by_dataset.items())},
               "candidate_counts": dict(candidate_counts),
               "lossless_definition": "MP3/AAC-origin material is clean_lossy_hq even if decoded to WAV; clean_lossless requires a verified-original status, a PCM/IEEE_FLOAT codec and a matching source SHA-256; other WAV/FLAC/AIFF remains lossless_container_unverified.",
               "rights_are_not_inferred": True}
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(f"Audited {len(rows)} unique indexed sources; wrote {args.out} and {args.summary}")


if __name__ == "__main__":
    main()
