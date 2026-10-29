#!/usr/bin/env python3
"""Build the PRIVATE per-media rights register from local audits and RIR records.

No network calls. Everything except the aggregate summary is written below build/.
To approve a source later, supply a private JSONL review override with media_key,
review_status, reviewer, exact licence URL, attribution and dated evidence.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openrestor.degradations.core import load_yaml, sha256_file
from openrestor.rights import cc_terms, media_key, public_summary, validate_record

REPO = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def base_record(dataset: str, source_id: str) -> dict:
    return {"media_key": media_key(dataset, source_id), "dataset": dataset,
            "source_id": source_id, "license_label": None, "license_url": None,
            "attribution": None, "evidence_url": None, "evidence_date": None,
            "review_status": "pending", "reviewer": None,
            "allow_commercial": None, "allow_redistribution": None,
            "allow_derivatives": None, "share_alike": None,
            "provenance_approved": None, "redistribution_approved": None}


def merge_clean_manifest(records: dict[str, dict], manifest: Path) -> None:
    """Import generic clean-manifest rights without granting missing fields."""
    for row in read_jsonl(manifest):
        dataset, source_id = str(row.get("dataset") or ""), str(row.get("source_id") or "")
        if not dataset or not source_id:
            raise ValueError("clean-corpus manifest row needs dataset and source_id")
        key = media_key(dataset, source_id)
        rights = row.get("rights") or {}
        if not isinstance(rights, dict):
            raise ValueError(f"rights must be an object for {key}")
        record = records.get(key, base_record(dataset, source_id))
        for field in ("license_label", "license_url", "attribution", "evidence_url",
                      "evidence_date", "reviewer", "allow_commercial",
                      "allow_redistribution", "allow_derivatives", "share_alike"):
            if field in rights:
                record[field] = rights[field]
        incoming_status = rights.get("review_status") or rights.get("status")
        if incoming_status in {"pending", "approved", "rejected"}:
            record["review_status"] = incoming_status
        elif incoming_status:
            record["review_status"] = "pending"
            record["provenance_note"] = f"Imported source status: {incoming_status}"
        # These fields are provenance evidence, never permission grants.
        for field in ("source_status", "rights_status", "provenance_approved",
                      "redistribution_approved", "source_sha256", "identity",
                      "rights_review_history"):
            if field in rights:
                record[field] = rights[field]
        if not record.get("evidence_url"):
            record["evidence_url"] = rights.get("evidence_source")
        records[key] = record


def build(args: argparse.Namespace) -> dict[str, dict]:
    records: dict[str, dict] = {}
    audit = {str(row["source_id"]): row for row in read_jsonl(args.jamendo_audit)}
    for row in read_jsonl(args.sonicmaster_manifest):
        source_id = str(row["source_id"])
        key = media_key("sonicmaster_clean", source_id)
        if key in records:
            continue
        record = base_record("sonicmaster_clean", source_id)
        evidence = audit.get(source_id)
        if evidence:
            url = evidence.get("licence_url") or None
            record.update(cc_terms(url))
            record.update(license_url=url, attribution=evidence.get("artist_name"),
                          evidence_url=evidence.get("share_url"),
                          evidence_date=evidence.get("fetched_at"),
                          evidence_source=evidence.get("evidence_source"),
                          provenance_note="Current API claim only; underlying and historical rights unapproved")
        records[key] = record

    sdd = json.loads(args.sdd_licences.read_text(encoding="utf-8"))
    for item in sdd.values():
        source_id = str(item["source_id"])
        record = base_record("sdd", source_id)
        label = str(item["licence"])
        record["license_label"] = label + " (SDD table; exact URL unrecorded)"
        match = re.fullmatch(r"BY(?:-NC)?(?:-ND|-SA)? (\d+\.\d)", label)
        if match:
            code = label.split()[0].lower()
            record.update(allow_commercial="nc" not in code,
                          allow_redistribution=True, allow_derivatives="nd" not in code,
                          share_alike="sa" in code)
        record.update(evidence_url="https://zenodo.org/records/10072001",
                      provenance_note="Per-track table lacks verified creator, licence URL and redistribution review")
        records[record["media_key"]] = record

    for row in read_jsonl(args.blind_synthetic_manifest):
        if row.get("dataset") != "musdb18_hq":
            continue
        source_id = str(row["source_id"])
        key = media_key("musdb18_hq", source_id)
        if key not in records:
            record = base_record("musdb18_hq", source_id)
            record.update(evidence_url="https://sigsep.github.io/datasets/musdb.html",
                          provenance_note="Academic access is not redistribution permission")
            records[key] = record

    for path in (args.blind_real_manifest, args.clean_control_manifest):
        for row in read_jsonl(path):
            source_id = str(row["id"])
            record = base_record("blind_real", source_id)
            url = row.get("license_url")
            record.update(cc_terms(url))
            record.update(license_url=url, attribution=row.get("attribution"),
                          evidence_url=row.get("internet_archive_metadata"),
                          provenance_note="Uploader CC tag; independent rights/provenance sign-off pending")
            records[record["media_key"]] = record

    rooms = load_yaml(args.rir_rights)
    checksums = {}
    for line in args.rir_checksums.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split(None, 1)
        checksums[relative.strip()] = digest
    if len(checksums) != 14:
        raise ValueError(f"Expected exactly 14 RIRs, found {len(checksums)}")
    for relative, expected in checksums.items():
        source = REPO / relative
        if sha256_file(source) != expected:
            raise ValueError(f"RIR checksum mismatch: {relative}")
        matches = [room for room in rooms["rooms"] if fnmatch.fnmatch(relative, room["pattern"])]
        if len(matches) != 1:
            raise ValueError(f"RIR needs exactly one rights record: {relative}")
        room = matches[0]
        record = base_record("openair_rir", relative)
        record.update(license_label=room["license_label"], license_url=room["license_url"],
                      attribution=room["attribution"], evidence_url=room["evidence_url"],
                      evidence_date=rooms["reviewed_at"], reviewer=rooms["reviewer"],
                      review_status="approved", allow_commercial=True,
                      allow_redistribution=True, allow_derivatives=True, share_alike=False,
                      provenance_approved=True, redistribution_approved=True,
                      provenance_note="Checksum and rights record verified locally",
                      sha256=expected)
        records[record["media_key"]] = record

    if args.clean_corpus_manifest:
        merge_clean_manifest(records, args.clean_corpus_manifest)
    if args.review_overrides:
        for override in read_jsonl(args.review_overrides):
            key = str(override.pop("media_key"))
            if key not in records:
                raise ValueError(f"Review override for unknown media: {key}")
            if "dataset" in override or "source_id" in override:
                raise ValueError("Review override may not change media identity")
            records[key].update(override)
    for record in records.values():
        validate_record(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sonicmaster-manifest", type=Path,
                        default=REPO / "configs/datasets/sonicmaster_original_split.jsonl")
    parser.add_argument("--jamendo-audit", type=Path,
                        default=REPO / "build/licence-audits/sonicmaster_jamendo/tracks.jsonl")
    parser.add_argument("--sdd-licences", type=Path, default=REPO / "build/sdd_track_licences.json")
    parser.add_argument("--blind-synthetic-manifest", type=Path,
                        default=REPO / "build/blind-synthetic/manifest.jsonl")
    parser.add_argument("--blind-real-manifest", type=Path,
                        default=REPO / "build/blind_real/blind_real_test_manifest.jsonl")
    parser.add_argument("--clean-control-manifest", type=Path,
                        default=REPO / "build/blind_real/clean_control_manifest.jsonl")
    parser.add_argument("--rir-rights", type=Path,
                        default=REPO / "configs/releases/rir_rights_v0_1.yaml")
    parser.add_argument("--rir-checksums", type=Path,
                        default=REPO / "docs/degradation_assets_v0_1.sha256")
    parser.add_argument("--review-overrides", type=Path,
                        help="Private JSONL of human approvals; never commit or publish it")
    parser.add_argument("--clean-corpus-manifest", type=Path,
                        help="Optional generic clean manifest; imported as asset-level pending rights")
    parser.add_argument("--out", type=Path, default=REPO / "build/rights/media_registry.jsonl")
    parser.add_argument("--summary", type=Path, default=REPO / "build/rights/public_summary.json")
    args = parser.parse_args()
    records = build(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for key in sorted(records):
            handle.write(json.dumps(records[key], sort_keys=True, ensure_ascii=False) + "\n")
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(public_summary(records.values()), indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(f"private rights registry: {args.out} ({len(records)} media)")
    print(f"aggregate-only summary: {args.summary}")


if __name__ == "__main__":
    main()
