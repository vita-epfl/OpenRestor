#!/usr/bin/env python3
"""Build a common curation manifest from the bounded private Zenodo pilot.

This adapter is deliberately local-only.  It does not fetch an archive or
grant redistribution rights: every pilot row remains provenance-ambiguous and
rights-pending until the individual member has been reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from openrestor.curation.metadata import asset_creator, asset_role


DEFAULT_DATASET_MAP = {
    "20849469": "choralebricks",
    "3371780": "guitarset",
    "14963133": "guitar_techs",
}


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _creator_text(record: dict) -> str | None:
    names = [item.get("name") for item in record.get("creators", [])
             if isinstance(item, dict) and item.get("name")]
    return "; ".join(names) or None


def _dataset_map(values: list[str]) -> dict[str, str]:
    result = dict(DEFAULT_DATASET_MAP)
    for value in values:
        if "=" not in value:
            raise ValueError(f"--dataset-map expects RECORD_ID=DATASET, got {value!r}")
        record_id, dataset = value.split("=", 1)
        if not record_id or not dataset or ":" in dataset:
            raise ValueError(f"invalid dataset mapping: {value!r}")
        result[record_id] = dataset
    return result


def prepare(ledger_path: Path, metadata_path: Path, audio_root: Path,
            dataset_overrides: list[str] | None = None) -> list[dict]:
    metadata = {}
    for row in read_jsonl(metadata_path):
        record_id = str(row.get("record_id") or "")
        if not record_id:
            raise ValueError(f"Zenodo metadata row has no record_id: {metadata_path}")
        if record_id in metadata:
            raise ValueError(f"duplicate Zenodo record_id: {record_id}")
        metadata[record_id] = row

    dataset_map = _dataset_map(dataset_overrides or [])
    rows = {}
    for ledger in read_jsonl(ledger_path):
        if ledger.get("status") != "verified" or not ledger.get("private_pilot"):
            raise ValueError("pilot ledger contains a row that is not verified/private")
        record_id = str(ledger.get("dataset_record_id") or "")
        if record_id not in metadata:
            raise ValueError(f"no Zenodo metadata for record {record_id}")
        expected_sha = str(ledger.get("audio_sha256") or "").lower()
        if len(expected_sha) != 64:
            raise ValueError(f"invalid audio_sha256 for {ledger.get('identity')}")
        path = audio_root / f"{expected_sha}.wav"
        if not path.is_file():
            # The ledger intentionally records the temporary extraction path;
            # the build artifact is authoritative after it is copied back.
            raise FileNotFoundError(f"private pilot audio is missing: {path}")
        observed_sha = sha256(path)
        if observed_sha != expected_sha:
            raise ValueError(f"checksum mismatch for {path}: {observed_sha} != {expected_sha}")

        record = metadata[record_id]
        dataset = dataset_map.get(record_id, f"zenodo_{record_id}")
        member_name = str(ledger.get("member_name") or "")
        if not member_name:
            raise ValueError(f"pilot row has no member_name: {ledger.get('identity')}")
        member_token = hashlib.sha256(member_name.encode("utf-8")).hexdigest()[:16]
        source_id = f"zenodo-{record_id}-{member_token}"
        source_key = f"{dataset}:{source_id}"
        if source_key in rows:
            raise ValueError(f"duplicate pilot source: {source_key}")

        license_id = record.get("license_id")
        license_url = record.get("license_url")
        performer = asset_creator(dataset, str(ledger.get("archive_key") or ""), member_name)
        role = asset_role(dataset, str(ledger.get("archive_key") or ""), member_name)
        rights = {
            "license_id": license_id,
            "license_label": license_id,
            "license_url": license_url,
            "evidence_url": record.get("record_url"),
            "evidence_date": record.get("evidence_date"),
            "attribution": _creator_text(record),
            "review_status": "metadata_confirmed_pending_asset_review",
            "rights_status": "metadata_confirmed_pending_asset_review",
            "allow_commercial": None,
            "allow_redistribution": None,
            "allow_derivatives": None,
            "provenance_approved": False,
            "redistribution_approved": False,
            "source_status": "ambiguous_original_status",
        }
        metadata_row = {
            "title": record.get("title"),
            "creator": performer,
            "dataset_creators": _creator_text(record),
            "collection": dataset,
            "asset_role": role,
            # Keep the record-level description for provenance, but do not feed
            # its dataset-wide MIDI/annotation vocabulary to source-level cues.
            "dataset_description": record.get("description"),
            "archive_record_id": int(record_id),
            "archive_record_url": record.get("record_url"),
            "license_evidence_date": record.get("evidence_date"),
            "archive_url": ledger.get("archive_url"),
            "member_name": member_name,
            "member_url": ((str(ledger.get("archive_url")) + "#member=" +
                            quote(member_name, safe="/"))
                           if ledger.get("archive_url") else None),
            "member_crc32": ledger.get("crc32"),
            "member_uncompressed_size_bytes": ledger.get("uncompressed_bytes"),
            "archive_key": ledger.get("archive_key"),
            "identity": ledger.get("identity"),
        }
        row = {
            "schema": "openrestor-clean-pilot-manifest-v1",
            "dataset": dataset,
            "source_id": source_id,
            "source_key": source_key,
            "audio_path": str(path.resolve()),
            "source_sha256": expected_sha,
            "original_format": ledger.get("local_format"),
            "sample_rate": ledger.get("local_sample_rate_hz"),
            "channels": ledger.get("local_channels"),
            "duration_seconds": ledger.get("local_duration_seconds"),
            "lossless_status": "lossless_container_unverified",
            "technical_candidate": True,
            "provenance_candidate": bool(record.get("provenance_candidate")),
            "redistributable_candidate": False,
            "metadata": metadata_row,
            "rights": rights,
            "pilot": {
                "private": True,
                "audio_downloaded": True,
                "source_status": "ambiguous_original_status",
                "ledger_identity": ledger.get("identity"),
            },
        }
        rows[source_key] = row
    return [rows[key] for key in sorted(rows)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--dataset-map", action="append", default=[],
                        help="Override RECORD_ID=DATASET (repeatable)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = prepare(args.ledger, args.metadata, args.audio_root, args.dataset_map)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    args.out.write_text(payload, encoding="utf-8")
    print(f"Prepared {len(rows)} private pilot manifest rows: {args.out}")


if __name__ == "__main__":
    main()
