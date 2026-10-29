"""Verified private audio can enrich catalogue identities without approving rights."""

import hashlib
import json
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.overlay_clean_verified_pilot import main, overlay


class OverlayCleanVerifiedPilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        audio = Path(self.temporary.name) / "source.wav"
        sf.write(audio, np.zeros(8000, dtype="float32"), 8000, format="WAV", subtype="PCM_16")
        data = audio.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        crc = f"{zlib.crc32(data) & 0xffffffff:08x}"
        url = "https://zenodo.org/api/records/123/files/masters_stereo.zip/content"
        rights = {"license_url": "https://creativecommons.org/licenses/by/4.0/",
                  "attribution": "Composer", "evidence_url": "https://zenodo.org/records/123",
                  "allow_commercial": None, "allow_derivatives": None,
                  "allow_redistribution": None, "provenance_approved": False,
                  "redistribution_approved": False, "review_status": "pending"}
        self.catalogue = {
            "dataset": "albumdb", "source_id": "123:masters_stereo.zip:track.wav",
            "source_key": "albumdb:123:masters_stereo.zip:track.wav",
            "audio_path": None, "source_sha256": None, "original_format": "WAV",
            "technical_candidate": False, "redistributable_candidate": False,
            "metadata": {"zenodo_record_id": "123", "archive_url": url,
                         "archive_member": "track.wav"}, "rights": dict(rights),
            "archive_original_files": [{"name": "track.wav", "archive_url": url,
                                        "crc32": crc, "uncompressed_size_bytes": len(data)}],
            "zenodo": {"archive_key": "masters_stereo.zip"},
        }
        self.pilot = {
            "dataset": "albumdb", "source_id": "zenodo-123-private",
            "source_key": "albumdb:zenodo-123-private", "audio_path": str(audio),
            "source_sha256": checksum, "original_format": "WAV", "sample_rate": 8000,
            "channels": 1, "duration_seconds": 1.0, "technical_candidate": True,
            "metadata": {"archive_record_id": 123, "archive_key": "masters_stereo.zip",
                         "archive_url": url, "member_name": "track.wav",
                         "member_crc32": crc, "member_uncompressed_size_bytes": len(data)},
            "rights": dict(rights), "pilot": {"private": True, "audio_downloaded": True},
        }

    def test_overlay_keeps_canonical_identity_and_pending_rights(self):
        rows, report = overlay([self.catalogue], [self.pilot])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_key"], self.catalogue["source_key"])
        self.assertEqual(rows[0]["source_sha256"], self.pilot["source_sha256"])
        self.assertEqual(rows[0]["lossless_status"], "lossless_container_unverified")
        self.assertTrue(rows[0]["technical_candidate"])
        self.assertFalse(rows[0]["redistributable_candidate"])
        self.assertEqual(rows[0]["rights"], self.catalogue["rights"])
        self.assertFalse(report["rights_inferred"])
        self.assertFalse(report["audio_downloaded"])

    def test_mismatched_crc_and_approvals_fail_closed(self):
        wrong_crc = {**self.catalogue, "archive_original_files": [
            {**self.catalogue["archive_original_files"][0], "crc32": "00000000"}]}
        with self.assertRaisesRegex(ValueError, "evidence mismatch"):
            overlay([wrong_crc], [self.pilot])
        approved = {**self.catalogue, "rights": {
            **self.catalogue["rights"], "redistribution_approved": True}}
        with self.assertRaisesRegex(ValueError, "approved rights"):
            overlay([approved], [self.pilot])

    def test_unknown_or_duplicate_pilot_asset_fails(self):
        absent = {**self.pilot, "metadata": {**self.pilot["metadata"], "member_name": "other.wav"}}
        with self.assertRaisesRegex(ValueError, "absent from catalogue"):
            overlay([self.catalogue], [absent])
        with self.assertRaisesRegex(ValueError, "duplicate pilot"):
            overlay([self.catalogue], [self.pilot, self.pilot])
        alias = {**self.pilot, "metadata": {}, "archive_original_files": None}
        with self.assertRaisesRegex(ValueError, "alias already exists"):
            overlay([self.catalogue, alias], [self.pilot])
        with self.assertRaisesRegex(ValueError, "empty"):
            overlay([self.catalogue], [])

    def test_local_checksum_and_crc_must_match_archive_evidence(self):
        wrong_sha = {**self.pilot, "source_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "checksum"):
            overlay([self.catalogue], [wrong_sha])
        fake_crc = "00000000"
        catalogue = {**self.catalogue, "archive_original_files": [
            {**self.catalogue["archive_original_files"][0], "crc32": fake_crc}]}
        pilot = {**self.pilot, "metadata": {**self.pilot["metadata"], "member_crc32": fake_crc}}
        with self.assertRaisesRegex(ValueError, "checksum"):
            overlay([catalogue], [pilot])

    def test_existing_curation_scores_follow_canonical_identity(self):
        alias = self.pilot["source_key"]
        clip = self.pilot["audio_path"]
        feature = {"source_key": alias, "source_sha256": self.pilot["source_sha256"],
                   "audio_path": clip, "schema": "openrestor-curation-features-v1",
                   "segments": [{"segment_id": alias + "#p1", "clip_path": clip,
                                 "aesthetics": {"PQ": 8.0}}]}
        decision = {"source_key": alias, "policy_version": "clean-music-v2.1",
                    "decision": "auto_accept", "clean_score": .83,
                    "reasons": ["v21_multisignal_agreement"],
                    "segments": [{"segment_id": alias + "#p1", "decision": "auto_accept"}],
                    "accepted_segment_ids": [alias + "#p1"]}
        rows, report = overlay([self.catalogue], [self.pilot], [feature], [decision])
        row = rows[0]
        self.assertEqual(report["curation_sources_linked"], 1)
        self.assertEqual(row["segments"][0]["segment_id"], row["source_key"] + "#p1")
        self.assertEqual(row["segments"][0]["pilot_segment_id"], alias + "#p1")
        self.assertEqual(row["source_decision"], "auto_accept")
        self.assertEqual(row["curation"]["decision_scope"], "sampled_passages_only")
        self.assertFalse(row["rights"]["redistribution_approved"])
        bad = {**decision, "accepted_segment_ids": ["other:source#p1"]}
        with self.assertRaisesRegex(ValueError, "invalid accepted segment"):
            overlay([self.catalogue], [self.pilot], [feature], [bad])

    def test_cli_validates_before_writing_output(self):
        root = Path(self.temporary.name)
        catalogue_path, pilot_path = root / "catalogue.jsonl", root / "pilot.jsonl"
        output, report, selection = root / "joined.jsonl", root / "report.json", root / "keys.jsonl"
        catalogue_path.write_text(json.dumps(self.catalogue) + "\n", encoding="utf-8")
        pilot_path.write_text(json.dumps(self.pilot) + "\n", encoding="utf-8")
        previous = sys.argv
        try:
            sys.argv = ["overlay", "--catalogue", str(catalogue_path), "--pilot", str(pilot_path),
                        "--out", str(output), "--report", str(report),
                        "--source-keys-out", str(selection)]
            main()
        finally:
            sys.argv = previous
        self.assertEqual(json.loads(output.read_text())["source_key"], self.catalogue["source_key"])
        self.assertTrue(json.loads(report.read_text())["schema_validated"])
        self.assertEqual(json.loads(selection.read_text())["source_key"], self.catalogue["source_key"])


if __name__ == "__main__":
    unittest.main()
