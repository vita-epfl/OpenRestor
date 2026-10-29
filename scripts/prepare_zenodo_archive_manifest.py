#!/usr/bin/env python3
"""Build a metadata-only manifest from the bounded Zenodo archive probe.

The input contains only Zenodo record metadata and ZIP central-directory
entries.  This command never downloads or extracts audio.  A WAV/FLAC/AIFF
extension is therefore recorded as a *candidate format* only: the emitted
rows remain ``technical_candidate=false`` and
``source_status=ambiguous_original_status`` until an exact member is fetched,
decoded and checksum/provenance reviewed.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from openrestor.curation.metadata import asset_creator, asset_role


LOSSLESS_FORMATS = {"WAV", "FLAC", "AIFF", "AIF"}
KNOWN_DATASETS = {
    "14963133": "guitar_techs",
    "20849469": "choralebricks",
    "3371780": "guitarset",
    "5120004": "musicnet",
}


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


def _record_id(row: dict) -> str:
    value = row.get("record_id") or row.get("requested_record")
    if value in (None, ""):
        raise ValueError("Zenodo row has no record_id/requested_record")
    return str(value)


def _dataset_name(meta: dict, mapping: dict[str, str]) -> str:
    record_id = _record_id(meta)
    if record_id in mapping:
        return mapping[record_id]
    if record_id in KNOWN_DATASETS:
        return KNOWN_DATASETS[record_id]
    title = str(meta.get("title") or "").lower()
    for token, name in (("guitar-techs", "guitar_techs"),
                        ("guitarset", "guitarset"),
                        ("musicnet", "musicnet"),
                        ("choralebricks", "choralebricks")):
        if token in title:
            return name
    return f"zenodo_{record_id}"


def _format(member: dict) -> str | None:
    value = str(member.get("format") or "").upper().lstrip(".")
    if value in LOSSLESS_FORMATS:
        return "AIFF" if value == "AIF" else value
    name = str(member.get("name") or "")
    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix in {"wav", "flac", "aiff", "aif"}:
        return "AIFF" if suffix == "aif" else suffix.upper()
    return None


def _safe_member_name(value: object) -> str:
    name = str(value or "").strip()
    if not name or name.endswith("/"):
        return ""
    # Keep the archive-relative name readable while preventing an accidental
    # path interpretation in downstream tools.
    return re.sub(r"^/+", "", name)


def _archive_url(record_id: str, archive_key: str) -> str:
    return ("https://zenodo.org/api/records/" + quote(record_id, safe="")
            + "/files/" + quote(archive_key, safe="") + "/content")


def prepare(metadata_path: Path, members_path: Path,
            dataset_map: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    mapping = dataset_map or {}
    metadata: dict[str, dict] = {}
    for row in read_jsonl(metadata_path):
        record_id = _record_id(row)
        if record_id in metadata:
            raise ValueError(f"duplicate Zenodo metadata record: {record_id}")
        metadata[record_id] = row

    output: list[dict] = []
    seen: set[str] = set()
    skipped: Counter[str] = Counter()
    by_dataset: Counter[str] = Counter()
    by_format: Counter[str] = Counter()
    archive_rows = 0
    for archive in read_jsonl(members_path):
        archive_rows += 1
        record_id = _record_id(archive)
        meta = metadata.get(record_id)
        if meta is None:
            skipped["missing_record_metadata"] += 1
            continue
        if archive.get("resolution_status") != "resolved":
            skipped["archive_probe_unresolved"] += 1
            continue
        if archive.get("archive_members_inspected") is not True:
            skipped["archive_members_not_inspected"] += 1
            continue
        dataset = _dataset_name(meta, mapping)
        creators = [str(item.get("name")) for item in (meta.get("creators") or [])
                    if isinstance(item, dict) and item.get("name")]
        attribution = "; ".join(creators) or None
        license_url = meta.get("license_url") or None
        archive_key = str(archive.get("archive_key") or "")
        archive_url = str(archive.get("archive_url") or
                          _archive_url(record_id, archive_key))
        for member in archive.get("members") or []:
            if not isinstance(member, dict):
                skipped["non_object_member"] += 1
                continue
            if member.get("is_directory") or member.get("is_macos_sidecar"):
                skipped["directory_or_macos_sidecar"] += 1
                continue
            name = _safe_member_name(member.get("name"))
            fmt = _format(member)
            if not name or fmt is None:
                skipped["non_lossless_member"] += 1
                continue
            source_id = f"{record_id}:{archive_key}:{name}"
            source_key = f"{dataset}:{source_id}"
            if source_key in seen:
                raise ValueError(f"duplicate generated source key: {source_key}")
            seen.add(source_key)
            by_dataset[dataset] += 1
            by_format[fmt] += 1
            member_url = archive_url + "#member=" + quote(name, safe="/")
            performer = asset_creator(dataset, archive_key, name)
            role = asset_role(dataset, archive_key, name)
            rights = {
                "license_label": meta.get("license_id") or license_url,
                "license_url": license_url,
                "attribution": attribution,
                "evidence_url": meta.get("record_url"),
                "evidence_date": meta.get("evidence_date"),
                "review_status": "metadata_candidate_pending_asset_review",
                "rights_status": "metadata_candidate_pending_asset_review",
                "allow_commercial": None,
                "allow_redistribution": None,
                "allow_derivatives": None,
                "provenance_approved": False,
                "redistribution_approved": False,
                "source_status": "ambiguous_original_status",
                "provenance_note": (
                    "Zenodo ZIP member metadata only; source/original status, "
                    "codec and exact asset scope require a bounded file review."
                ),
            }
            output.append({
                "schema": "openrestor-clean-manifest-v1",
                "dataset": dataset,
                "source_id": source_id,
                "source_key": source_key,
                "audio_path": None,
                "source_sha256": None,
                "original_format": fmt,
                "sample_rate": None,
                "channels": None,
                "duration_seconds": None,
                "lossless_status": "archive_member_format_unverified",
                "technical_candidate": False,
                "provenance_candidate": bool(meta.get("provenance_candidate")),
                "redistributable_candidate": False,
                "metadata": {
                    "title": f"{meta.get('title') or dataset} — {name}",
                    # Record authors are kept separately for attribution; do
                    # not treat them as the performer of every member.
                    "creator": performer,
                    "asset_role": role,
                    "dataset_creators": attribution,
                    "genre": "[unknown]",
                    "collection": f"zenodo:{record_id}/{archive_key}",
                    "zenodo_record_id": record_id,
                    "zenodo_record_url": meta.get("record_url"),
                    "license_evidence_date": meta.get("evidence_date"),
                    "archive_url": archive_url,
                    "archive_member": name,
                    "member_url": member_url,
                    "member_crc32": member.get("crc32"),
                    "member_compressed_size_bytes": member.get("compressed_size_bytes"),
                    "member_uncompressed_size_bytes": member.get("uncompressed_size_bytes"),
                },
                "rights": rights,
                "archive_original_files": [{
                    "name": name,
                    "format": fmt,
                    "archive_url": archive_url,
                    "member_url": member_url,
                    "source_status": "ambiguous_original_status",
                    "crc32": member.get("crc32"),
                    "compressed_size_bytes": member.get("compressed_size_bytes"),
                    "uncompressed_size_bytes": member.get("uncompressed_size_bytes"),
                }],
                "zenodo": {
                    "metadata_only": True,
                    "record_id": record_id,
                    "archive_key": archive_key,
                    "record_license_url": license_url,
                    "record_redistributable_candidate": bool(meta.get("redistributable_candidate")),
                },
            })

    output.sort(key=lambda row: row["source_key"])
    report = {
        "schema_version": "zenodo-archive-manifest-audit-v1",
        "metadata_records": len(metadata),
        "archive_rows": archive_rows,
        "output_sources": len(output),
        "metadata_only": True,
        "audio_downloaded": False,
        "technical_candidate_count": 0,
        "provenance_candidate_count": sum(bool(row["provenance_candidate"]) for row in output),
        "redistributable_candidate_count": 0,
        "ambiguous_original_status_count": len(output),
        "by_dataset": dict(sorted(by_dataset.items())),
        "by_format": dict(sorted(by_format.items())),
        "skipped": dict(sorted(skipped.items())),
        "note": "ZIP member names/formats do not prove original codec or rights; no audio was downloaded.",
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True,
                        help="JSONL from resolve_zenodo_metadata.py")
    parser.add_argument("--members", type=Path, required=True,
                        help="JSONL from inspect_zenodo_zip_ranges.py")
    parser.add_argument("--dataset-map", action="append", default=[], metavar="RECORD=DATASET",
                        help="Override a record-to-dataset name mapping; repeatable")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    mapping = {}
    for value in args.dataset_map:
        if "=" not in value or not all(value.split("=", 1)):
            parser.error(f"--dataset-map must be RECORD=DATASET, got {value!r}")
        key, dataset = value.split("=", 1)
        mapping[key] = dataset
    rows, report = prepare(args.metadata, args.members, mapping)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                        for row in rows), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Prepared {len(rows)} metadata-only Zenodo archive rows: {args.out}")


if __name__ == "__main__":
    main()
