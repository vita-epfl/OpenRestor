"""Release gates: CC terms, approval, physical shard filtering and public redaction."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

import h5py

from openrestor.degradations.core import sha256_file
from openrestor.publication import classify_index, repack_hdf5, validate_pack
from openrestor.publication_cli import check_nc_access, media_notice
from openrestor.rights import cc_terms, media_key, pack_family, public_summary


def record(source_id: str, url: str | None, *, approved: bool = True) -> dict:
    row = {"media_key": media_key("sonicmaster_clean", source_id),
           "dataset": "sonicmaster_clean", "source_id": source_id,
           "license_url": url, "attribution": "Artist / track / source",
           "evidence_url": "https://example.org/track", "evidence_date": "2026-10-19",
           "review_status": "approved" if approved else "pending", "reviewer": "test reviewer",
           "provenance_approved": approved, "redistribution_approved": approved}
    row.update(cc_terms(url))
    return row


class RightsReleaseTests(TestCase):
    def test_by_sa_nc_nd_missing_and_unapproved(self):
        by = record("by", "https://creativecommons.org/licenses/by/4.0/")
        sa = record("sa", "https://creativecommons.org/licenses/by-sa/3.0/")
        nc = record("nc", "https://creativecommons.org/licenses/by-nc/4.0/")
        nc_sa = record("nc-sa", "https://creativecommons.org/licenses/by-nc-sa/4.0/")
        nd = record("nd", "https://creativecommons.org/licenses/by-nd/4.0/")
        unknown = record("missing", None, approved=False)
        pending = record("pending", "https://creativecommons.org/licenses/by/4.0/",
                         approved=False)
        self.assertEqual(pack_family(by, "commercial_compatible"), "base")
        self.assertEqual(pack_family(sa, "commercial_compatible"),
                         "sa:https://creativecommons.org/licenses/by-sa/3.0/")
        self.assertIsNone(pack_family(nc, "commercial_compatible"))
        self.assertEqual(pack_family(nc, "academic_noncommercial"), "nc_extension")
        self.assertEqual(pack_family(nc_sa, "academic_noncommercial"),
                         "sa:https://creativecommons.org/licenses/by-nc-sa/4.0/")
        for row in (nd, unknown, pending):
            for profile in ("commercial_compatible", "academic_noncommercial"):
                self.assertIsNone(pack_family(row, profile))

    def test_missing_provenance_approval_is_not_publishable(self):
        row = record("missing-provenance", "https://creativecommons.org/licenses/by/4.0/")
        row.pop("provenance_approved")
        self.assertIsNone(pack_family(row, "commercial_compatible"))

    def test_missing_redistribution_approval_is_not_publishable(self):
        row = record("missing-redistribution", "https://creativecommons.org/licenses/by/4.0/")
        row.pop("redistribution_approved")
        self.assertIsNone(pack_family(row, "commercial_compatible"))

    def test_no_false_permission_for_unknown_url(self):
        self.assertEqual(cc_terms("https://example.org/license")["allow_commercial"], None)
        self.assertEqual(cc_terms(None)["allow_derivatives"], None)

    def test_approved_cc_flags_cannot_contradict_nc_or_nd(self):
        nc = record("nc", "https://creativecommons.org/licenses/by-nc/4.0/")
        nc["allow_commercial"] = True
        with self.assertRaisesRegex(ValueError, "contradicts"):
            pack_family(nc, "commercial_compatible")
        nd = record("nd", "https://creativecommons.org/licenses/by-nd/4.0/")
        nd["allow_derivatives"] = True
        with self.assertRaisesRegex(ValueError, "contradicts"):
            pack_family(nd, "academic_noncommercial")

    def test_public_summary_contains_counts_not_blocked_ids(self):
        rows = [record("secret-private-id", None, approved=False),
                record("approved-id", "https://creativecommons.org/licenses/by/4.0/"),
                record("nc-id", "https://creativecommons.org/licenses/by-nc/4.0/")]
        summary = json.dumps(public_summary(rows))
        self.assertNotIn("secret-private-id", summary)
        self.assertNotIn("approved-id", summary)
        self.assertNotIn("nc-id", summary)
        self.assertNotIn("source_id", summary)
        self.assertEqual(json.loads(summary)["profiles"]["commercial_compatible"],
                         {"sonicmaster_clean": 1})
        self.assertEqual(json.loads(summary)["profiles"]["academic_noncommercial"],
                         {"sonicmaster_clean": 2})
        self.assertEqual(json.loads(summary)["profile_families"]["academic_noncommercial"],
                         {"base": 1, "nc_extension": 1})

    def test_nc_requires_documented_controlled_access(self):
        with self.assertRaisesRegex(ValueError, "requires"):
            check_nc_access(None)
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / "approval.json"
            approval = {"approved_by": "test reviewer", "approved_at": "2026-10-19",
                        "approval_reference": "internal approval record", "access_mode": "public_download",
                        "uses_effectively_noncommercial": True}
            path.write_text(json.dumps(approval), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "controlled"):
                check_nc_access(path)
            approval["access_mode"] = "controlled_research_access"
            path.write_text(json.dumps(approval), encoding="utf-8")
            check_nc_access(path)

    def test_attribution_only_names_released_media(self):
        approved = record("approved-id", "https://creativecommons.org/licenses/by/4.0/")
        blocked = record("private-id", None, approved=False)
        registry = {row["media_key"]: row for row in (approved, blocked)}
        notice = media_notice([{"dataset": "sonicmaster_clean", "source_id": "approved-id"}],
                              registry, "diagnostic")
        self.assertEqual(len(notice), 1)
        self.assertEqual(notice[0]["source_id"], "approved-id")
        self.assertNotIn("private-id", json.dumps(notice))

    def test_mixed_hdf5_shard_is_rebuilt_without_excluded_item(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            frozen, clean, target = root / "frozen", root / "clean", root / "candidate"
            source = frozen / "shards" / "mixed.h5"
            source.parent.mkdir(parents=True)
            text = h5py.string_dtype("utf-8")
            with h5py.File(source, "w") as shard:
                shard.attrs["format"] = "openrestore.degraded.v0.1"
                shard.create_dataset("audio", data=[[[1.0]], [[2.0]]], compression="gzip")
                for name in ("item_id", "clean_id", "degraded_path", "manifest_json"):
                    shard.create_dataset(name, data=["allowed", "blocked"], dtype=text)
            clean.mkdir()
            rows = []
            for offset, source_id in enumerate(("allowed", "blocked")):
                clip = clean / f"{source_id}.wav"
                clip.write_bytes(source_id.encode())
                rows.append({"id": source_id, "dataset": "sonicmaster_clean",
                             "source_id": source_id, "clean_path": clip.name,
                             "audio_sha256": sha256_file(clip),
                             "degraded_audio_shard": "shards/mixed.h5",
                             "degraded_audio_shard_index": offset,
                             "degraded_audio_shard_sha256": sha256_file(source)})
            index = root / "index.jsonl"
            index.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            registry = {media_key("sonicmaster_clean", "allowed"):
                        record("allowed", "https://creativecommons.org/licenses/by/4.0/"),
                        media_key("sonicmaster_clean", "blocked"):
                        record("blocked", "https://creativecommons.org/licenses/by-nd/4.0/")}
            selected, withheld = classify_index(index, registry, "commercial_compatible")
            self.assertEqual(withheld["sonicmaster_clean"], 1)
            output = repack_hdf5(selected["base"], frozen, clean, target)
            validate_pack(output, registry, "commercial_compatible", "base", target, "diagnostic")
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0]["degraded_audio_shard_index"], 0)
            self.assertNotEqual(output[0]["degraded_audio_shard_sha256"], sha256_file(source))
            with h5py.File(target / "shards/mixed.h5", "r") as shard:
                self.assertEqual(len(shard["item_id"]), 1)
                self.assertEqual(shard["item_id"][0].decode(), "allowed")
            self.assertFalse((target / "clean/blocked.wav").exists())
            self.assertEqual(sha256_file(source), rows[0]["degraded_audio_shard_sha256"])
