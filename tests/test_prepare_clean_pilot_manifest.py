import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_clean_pilot_manifest import _dataset_map, prepare


class CleanPilotManifestTests(unittest.TestCase):
    def test_maps_records_verifies_checksum_and_keeps_rights_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_root = root / "audio"
            audio_root.mkdir()
            data = b"bounded-pilot-audio"
            digest = hashlib.sha256(data).hexdigest()
            (audio_root / f"{digest}.wav").write_bytes(data)
            ledger = root / "ledger.jsonl"
            ledger.write_text(json.dumps({
                "status": "verified", "private_pilot": True,
                "dataset_record_id": 20849469, "audio_sha256": digest,
                "archive_url": "https://zenodo.org/api/records/20849469/files/a.zip/content",
                "crc32": "deadbeef", "uncompressed_bytes": len(data),
                "member_name": "audio/a.wav", "archive_key": "a.zip",
                "identity": "20849469:a.zip:audio/a.wav", "local_format": "WAV",
                "local_sample_rate_hz": 44100, "local_channels": 1,
                "local_duration_seconds": 1.0,
            }) + "\n", encoding="utf-8")
            metadata = root / "metadata.jsonl"
            metadata.write_text(json.dumps({
                "record_id": 20849469, "title": "ChoraleBricks",
                "record_url": "https://zenodo.org/records/20849469",
                "evidence_date": "2026-10-29",
                "license_id": "cc-by-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "creators": [{"name": "A Creator"}], "provenance_candidate": True,
            }) + "\n", encoding="utf-8")
            rows = prepare(ledger, metadata, audio_root)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["dataset"], "choralebricks")
            self.assertEqual(row["source_sha256"], digest)
            self.assertFalse(row["redistributable_candidate"])
            self.assertEqual(row["rights"]["source_status"], "ambiguous_original_status")
            self.assertIsNone(row["rights"]["allow_redistribution"])
            self.assertEqual(row["rights"]["evidence_date"], "2026-10-29")
            self.assertEqual(row["metadata"]["member_name"], "audio/a.wav")
            self.assertEqual(row["metadata"]["member_crc32"], "deadbeef")
            self.assertIn("#member=audio/a.wav", row["metadata"]["member_url"])

    def test_guitar_techs_record_has_stable_default_dataset_name(self):
        self.assertEqual(_dataset_map([])["14963133"], "guitar_techs")


if __name__ == "__main__":
    unittest.main()
