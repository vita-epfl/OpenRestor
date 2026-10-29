#!/usr/bin/env python3
"""Attach checksum-verified local Zenodo pilot audio to canonical catalogue rows.

This is a private technical overlay. It never promotes a rights decision, and
it keeps the catalogue source key so benchmark overlap and rights review use
one stable identity per asset.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import zlib
from pathlib import Path

import soundfile as sf

from openrestor.validation.core import validate_clean_manifest


HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"expected an object at {path}:{number}")
            yield row


def _asset_key(row: dict, *, pilot: bool) -> tuple[str, str, str]:
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"invalid metadata: {row.get('source_key')}")
    record_id = (metadata.get("archive_record_id") if pilot else
                 metadata.get("zenodo_record_id"))
    archive_key = metadata.get("archive_key") if pilot else (row.get("zenodo") or {}).get("archive_key")
    if not archive_key:
        archive_url = str(metadata.get("archive_url") or "")
        archive_key = archive_url.rstrip("/").split("/")[-2] if "/files/" in archive_url else ""
    member = metadata.get("member_name") if pilot else metadata.get("archive_member")
    if not record_id or not archive_key or not member:
        raise ValueError(f"missing Zenodo asset identity: {row.get('source_key')}")
    return str(record_id), str(archive_key), str(member)


def _checksums(path: Path) -> tuple[str, str]:
    digest = hashlib.sha256()
    crc = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            crc = zlib.crc32(block, crc)
    return digest.hexdigest(), f"{crc & 0xffffffff:08x}"


def _records_by_key(records: list[dict], label: str) -> dict[str, dict]:
    indexed = {}
    for row in records:
        key = row.get("source_key")
        if not key or key in indexed:
            raise ValueError(f"missing/duplicate {label} source_key: {key}")
        indexed[key] = row
    return indexed


def _canonical_segments(alias: str, canonical: str, segments: list[dict]) -> list[dict]:
    mapped = []
    seen = set()
    for segment in segments:
        old_id = str(segment.get("segment_id") or "")
        if not old_id.startswith(alias + "#") or old_id in seen:
            raise ValueError(f"invalid/duplicate pilot segment: {old_id}")
        seen.add(old_id)
        result = copy.deepcopy(segment)
        result["pilot_segment_id"] = old_id
        result["segment_id"] = canonical + old_id[len(alias):]
        mapped.append(result)
    if not mapped:
        raise ValueError(f"pilot source has no segments: {alias}")
    return mapped


def overlay(catalogue: list[dict], pilot_rows: list[dict],
            features: list[dict] | None = None,
            decisions: list[dict] | None = None) -> tuple[list[dict], dict]:
    if not pilot_rows:
        raise ValueError("pilot manifest is empty")
    if (features is None) != (decisions is None):
        raise ValueError("features and decisions must be supplied together")
    feature_index = _records_by_key(features, "feature") if features is not None else {}
    decision_index = _records_by_key(decisions, "decision") if decisions is not None else {}
    pilot_keys = {row.get("source_key") for row in pilot_rows}
    if None in pilot_keys or len(pilot_keys) != len(pilot_rows):
        raise ValueError("missing/duplicate pilot source_key")
    if features is not None and (set(feature_index) != pilot_keys or set(decision_index) != pilot_keys):
        raise ValueError("pilot, feature and decision source keys differ")
    rows = {}
    index = {}
    for row in catalogue:
        source_key = row.get("source_key")
        if not source_key or source_key in rows:
            raise ValueError(f"missing/duplicate catalogue source_key: {source_key}")
        rows[source_key] = row
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if row.get("archive_original_files") and metadata.get("zenodo_record_id"):
            key = _asset_key(row, pilot=False)
            if key in index:
                raise ValueError(f"duplicate catalogue Zenodo asset: {key}")
            index[key] = source_key

    replaced = []
    seen_pilot_assets = set()
    for pilot in pilot_rows:
        pilot_flags = pilot.get("pilot") if isinstance(pilot.get("pilot"), dict) else {}
        if (pilot_flags.get("private") is not True
                or pilot_flags.get("audio_downloaded") is not True
                or pilot.get("technical_candidate") is not True):
            raise ValueError(f"not a verified private pilot: {pilot.get('source_key')}")
        key = _asset_key(pilot, pilot=True)
        if key in seen_pilot_assets:
            raise ValueError(f"duplicate pilot Zenodo asset: {key}")
        seen_pilot_assets.add(key)
        if key not in index:
            raise ValueError(f"pilot asset absent from catalogue: {key}")
        canonical_key = index[key]
        if pilot.get("source_key") in rows and pilot.get("source_key") != canonical_key:
            raise ValueError(f"pilot alias already exists in catalogue: {pilot.get('source_key')}")
        canonical = rows[canonical_key]
        if canonical.get("dataset") != pilot.get("dataset") or canonical.get("audio_path"):
            raise ValueError(f"dataset mismatch or catalogue already has audio: {canonical_key}")
        original_rights = canonical.get("rights") or {}
        pilot_rights = pilot.get("rights") or {}
        if (not isinstance(original_rights, dict) or not isinstance(pilot_rights, dict)
                or any(original_rights.get(field) is True or pilot_rights.get(field) is True
                       for field in ("provenance_approved", "redistribution_approved"))
                or any(original_rights.get(field) is not None or pilot_rights.get(field) is not None
                       for field in ("allow_commercial", "allow_derivatives", "allow_redistribution"))):
            raise ValueError(f"pilot overlay cannot transfer approved rights: {canonical_key}")
        for field in ("license_url", "attribution", "evidence_url"):
            if original_rights.get(field) != pilot_rights.get(field):
                raise ValueError(f"{field} conflict for {canonical_key}")
        archive_file = (canonical.get("archive_original_files") or [None])[0]
        if (not isinstance(archive_file, dict) or archive_file.get("name") != key[2]
                or archive_file.get("archive_url") != (pilot.get("metadata") or {}).get("archive_url")
                or str(archive_file.get("crc32") or "").lower()
                != str((pilot.get("metadata") or {}).get("member_crc32") or "").lower()
                or archive_file.get("uncompressed_size_bytes")
                != (pilot.get("metadata") or {}).get("member_uncompressed_size_bytes")):
            raise ValueError(f"archive member evidence mismatch: {canonical_key}")
        expected_sha = str(pilot.get("source_sha256") or "").lower()
        path = Path(str(pilot.get("audio_path") or ""))
        if not HEX_SHA256.fullmatch(expected_sha) or not path.is_file():
            raise ValueError(f"missing/mismatched local audio checksum: {canonical_key}")
        observed_sha, observed_crc = _checksums(path)
        if observed_sha != expected_sha or observed_crc != str(archive_file["crc32"]).lower():
            raise ValueError(f"missing/mismatched local audio checksum: {canonical_key}")
        if path.stat().st_size != archive_file["uncompressed_size_bytes"]:
            raise ValueError(f"local audio size differs from archive member: {canonical_key}")
        with sf.SoundFile(path) as audio:
            if (audio.format != pilot.get("original_format")
                    or audio.format != canonical.get("original_format")
                    or audio.subtype not in {"PCM_16", "PCM_24", "PCM_32", "FLOAT", "DOUBLE"}
                    or audio.samplerate != pilot.get("sample_rate")
                    or audio.channels != pilot.get("channels")
                    or abs(len(audio) / audio.samplerate - float(pilot.get("duration_seconds") or 0)) > .01):
                raise ValueError(f"local audio codec or measurements mismatch: {canonical_key}")
        updated = dict(canonical)
        updated.update(audio_path=str(path.resolve()), source_sha256=expected_sha,
                       sample_rate=pilot["sample_rate"], channels=pilot["channels"],
                       duration_seconds=pilot["duration_seconds"],
                       lossless_status="lossless_container_unverified",
                       technical_candidate=True,
                       # A checked WAV container does not establish uploader
                       # ownership, original provenance, or redistribution.
                       redistributable_candidate=False,
                       pilot={**pilot_flags, "pilot_source_key": pilot["source_key"]})
        if features is not None:
            alias = pilot["source_key"]
            feature, decision = feature_index[alias], decision_index[alias]
            if (feature.get("source_sha256") != expected_sha
                    or Path(str(feature.get("audio_path") or "")).resolve() != path.resolve()
                    or decision.get("policy_version") != "clean-music-v2.1"
                    or decision.get("decision") not in {"auto_accept", "manual_review", "auto_reject"}):
                raise ValueError(f"curation evidence does not match pilot audio: {alias}")
            segments = _canonical_segments(alias, canonical_key, feature.get("segments") or [])
            scored = _canonical_segments(alias, canonical_key, decision.get("segments") or [])
            if {part["segment_id"] for part in segments} != {part["segment_id"] for part in scored}:
                raise ValueError(f"feature and decision segments differ: {alias}")
            if any(part.get("decision") not in {"auto_accept", "manual_review", "auto_reject"}
                   for part in scored):
                raise ValueError(f"invalid segment decision: {alias}")
            accepted = [part["segment_id"] for part in scored if part.get("decision") == "auto_accept"]
            claimed = []
            for segment_id in decision.get("accepted_segment_ids") or []:
                if not str(segment_id).startswith(alias + "#"):
                    raise ValueError(f"invalid accepted segment ID: {segment_id}")
                claimed.append(canonical_key + str(segment_id)[len(alias):])
            if sorted(accepted) != sorted(claimed):
                raise ValueError(f"accepted segment IDs differ: {alias}")
            for part in segments:
                if not Path(str(part.get("clip_path") or "")).is_file():
                    raise ValueError(f"missing local curation clip: {part.get('segment_id')}")
            updated.update(
                features={"schema": feature.get("schema"), "extractor": feature.get("extractor"),
                          "source": "private_pilot_probe_cache"},
                segments=segments, segment_decisions=scored,
                source_decision=decision["decision"], pipeline_decision=decision["decision"],
                pipeline_reasons=decision.get("reasons") or [], clean_score=decision.get("clean_score"),
                curation={"policy_version": decision["policy_version"],
                          "config_sha256": decision.get("config_sha256"),
                          "accepted_segment_ids": accepted,
                          "decision_scope": "sampled_passages_only",
                          "pilot_source_key": alias})
        rows[canonical_key] = updated
        replaced.append({"source_key": canonical_key, "pilot_source_key": pilot["source_key"],
                         "source_sha256": expected_sha})

    result = [rows[key] for key in sorted(rows)]
    report = {"schema_version": "clean-verified-pilot-overlay-v1",
              "catalogue_sources": len(catalogue), "pilot_sources": len(pilot_rows),
              "output_sources": len(result), "verified_overlays": len(replaced),
              "curation_sources_linked": len(replaced) if features is not None else 0,
              "overlays": replaced, "audio_downloaded": False,
              "rights_inferred": False, "rights_changed": False,
              "note": "Only local technical fields were overlaid; original status and rights remain pending."}
    return result, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--features", type=Path,
                        help="Optional private pilot probed features (requires --decisions)")
    parser.add_argument("--decisions", type=Path,
                        help="Optional private pilot v2.1 decisions (requires --features)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-keys-out", type=Path,
                        help="Optional canonical source-key selection for private rights review")
    args = parser.parse_args()
    rows, report = overlay(list(read_jsonl(args.catalogue)), list(read_jsonl(args.pilot)),
                           list(read_jsonl(args.features)) if args.features else None,
                           list(read_jsonl(args.decisions)) if args.decisions else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # The validator chooses JSONL parsing from the suffix; retain it on the
    # temporary file while validating before the atomic replacement.
    temporary = args.out.with_name(args.out.stem + ".tmp" + args.out.suffix)
    try:
        temporary.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                     for row in rows), encoding="utf-8")
        validate_clean_manifest(temporary)
        os.replace(temporary, args.out)
    finally:
        temporary.unlink(missing_ok=True)
    report["schema_validated"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report_temporary = args.report.with_name(args.report.name + ".tmp")
    report_temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
    os.replace(report_temporary, args.report)
    if args.source_keys_out:
        args.source_keys_out.parent.mkdir(parents=True, exist_ok=True)
        selection_temporary = args.source_keys_out.with_name(args.source_keys_out.name + ".tmp")
        selection_temporary.write_text("".join(json.dumps({"source_key": row["source_key"]},
                                                  ensure_ascii=False) + "\n"
                                               for row in report["overlays"]), encoding="utf-8")
        os.replace(selection_temporary, args.source_keys_out)
    print(f"Overlaid {len(report['overlays'])} verified local assets onto {len(rows)} catalogue rows")


if __name__ == "__main__":
    main()
