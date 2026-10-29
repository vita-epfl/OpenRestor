import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.resolve_zenodo_metadata import resolve_records, summarize_record


class ResolveZenodoMetadataTests(unittest.TestCase):
    def fixture(self):
        return {
            "id": 42, "conceptrecid": "7", "doi": "10.5281/zenodo.42",
            "status": "published",
            "metadata": {"title": "Example", "version": "1.0", "access_right": "open",
                         "license": {"id": "cc-by-4.0"},
                         "creators": [{"name": "Artist"}]},
            "files": [{"key": "audio.zip", "size": 123, "checksum": "md5:abc",
                       "links": {"content": "https://zenodo.test/audio.zip"}}],
        }

    def test_summary_is_fail_closed_and_metadata_only(self):
        row = summarize_record(self.fixture(), "7", "2026-10-29")
        self.assertEqual(row["record_id"], 42)
        self.assertEqual(row["requested_record"], "7")
        self.assertEqual(row["license_url"], "https://creativecommons.org/licenses/by/4.0/")
        self.assertEqual(row["evidence_date"], "2026-10-29")
        self.assertTrue(row["provenance_candidate"])
        self.assertFalse(row["technical_candidate"])
        self.assertFalse(row["redistributable_candidate"])
        self.assertFalse(row["archive_members_inspected"])
        self.assertFalse(row["audio_downloaded"])

    def test_errors_and_resume_are_written_incrementally(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "resolution.jsonl"
            with patch("scripts.resolve_zenodo_metadata.fetch_record",
                       side_effect=[self.fixture(), TimeoutError("offline")]) as fetch:
                rows = resolve_records(["7", "8"], out, timeout=0.01)
            self.assertEqual(len(rows), 2)
            saved = [json.loads(line) for line in out.read_text().splitlines()]
            self.assertEqual({row["requested_record"] for row in saved}, {"7", "8"})
            self.assertEqual(saved[1]["rights_status"], "resolution_error")
            with patch("scripts.resolve_zenodo_metadata.fetch_record") as fetch:
                resolve_records(["7", "8"], out)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
