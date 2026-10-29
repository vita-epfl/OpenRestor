import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_zenodo_archive_manifest import prepare


class ZenodoArchiveManifestTests(unittest.TestCase):
    def test_emits_only_lossless_named_members_and_stays_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata.jsonl"
            metadata.write_text(json.dumps({
                "record_id": "42", "title": "Example", "record_url": "https://zenodo.org/records/42",
                "evidence_date": "2026-10-29",
                "license_id": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "creators": [{"name": "Creator"}], "provenance_candidate": True,
                "redistributable_candidate": True,
            }) + "\n", encoding="utf-8")
            members = root / "members.jsonl"
            members.write_text(json.dumps({
                "record_id": "42", "archive_key": "audio.zip", "archive_url": "https://example/audio.zip",
                "resolution_status": "resolved", "archive_members_inspected": True,
                "source_status": "ambiguous_original_status",
                "members": [
                    {"name": "track.wav", "format": "WAV", "is_directory": False,
                     "is_macos_sidecar": False, "crc32": "abc"},
                    {"name": "track.mp3", "format": "MP3", "is_directory": False,
                     "is_macos_sidecar": False},
                    {"name": "folder/", "is_directory": True},
                ],
            }) + "\n", encoding="utf-8")
            rows, report = prepare(metadata, members, {"42": "example"})
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["dataset"], "example")
            self.assertEqual(rows[0]["original_format"], "WAV")
            self.assertFalse(rows[0]["technical_candidate"])
            self.assertFalse(rows[0]["redistributable_candidate"])
            self.assertEqual(rows[0]["rights"]["source_status"], "ambiguous_original_status")
            self.assertEqual(rows[0]["rights"]["evidence_date"], "2026-10-29")
            self.assertEqual(report["by_format"], {"WAV": 1})
            self.assertEqual(report["ambiguous_original_status_count"], 1)
            self.assertFalse(report["audio_downloaded"])

    def test_unresolved_archive_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "metadata.jsonl"
            metadata.write_text(json.dumps({"record_id": "1", "title": "x"}) + "\n", encoding="utf-8")
            members = root / "members.jsonl"
            members.write_text(json.dumps({"record_id": "1", "resolution_status": "timeout"}) + "\n",
                                encoding="utf-8")
            rows, report = prepare(metadata, members)
            self.assertEqual(rows, [])
            self.assertEqual(report["skipped"], {"archive_probe_unresolved": 1})


if __name__ == "__main__":
    unittest.main()
