import json
import tempfile
import unittest
from pathlib import Path

from scripts.export_clean_rights_review_queue import build, queue_row


class RightsReviewQueueTests(unittest.TestCase):
    def test_canonical_zenodo_asset_fields_are_visible_without_audio_path(self):
        row = {"dataset": "albumdb", "source_id": "123:masters.zip:track.wav",
               "audio_path": "/private/track.wav",
               "metadata": {"zenodo_record_id": "123",
                            "zenodo_record_url": "https://zenodo.org/records/123",
                            "archive_member": "track.wav"},
               "zenodo": {"archive_key": "masters.zip"}, "rights": {}}
        result = queue_row(row)
        self.assertEqual(result["archive_record_id"], "123")
        self.assertEqual(result["archive_key"], "masters.zip")
        self.assertEqual(result["member_name"], "track.wav")
        self.assertNotIn("audio_path", result)

    def test_queue_is_metadata_only_and_deduplicates_identical_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {
                "dataset": "pilot", "source_id": "one", "audio_path": "/private/audio.wav",
                "metadata": {"title": "Song", "creator": "Artist",
                             "dataset_creators": "Dataset Author",
                             "archive_record_id": 42,
                             "archive_record_url": "https://example.test/records/42",
                             "archive_key": "audio.zip",
                             "member_name": "tracks/song.wav",
                             "member_url": "https://example.test/audio.zip#member=tracks/song.wav",
                             "member_crc32": "deadbeef",
                             "identity": "42:audio.zip:tracks/song.wav"},
                "rights": {"license_label": "CC BY 4.0", "license_url": "https://example.test/by",
                           "license_id": "cc-by-4.0",
                           "review_status": "pending", "provenance_approved": False,
                           "redistribution_approved": False},
                "technical_candidate": True, "provenance_candidate": True,
                "redistributable_candidate": False,
            }
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            first.write_text(json.dumps(row) + "\n", encoding="utf-8")
            second.write_text(json.dumps(row) + "\n", encoding="utf-8")
            out, report = root / "queue.jsonl", root / "report.json"
            result = build([first, second], out, report)
            saved = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(result["sources"], 1)
            self.assertTrue(saved["audio_path_omitted"])
            self.assertNotIn("audio_path", saved)
            self.assertFalse(saved["redistribution_approved"])
            self.assertEqual(saved["creator"], "Artist")
            self.assertEqual(saved["dataset_creators"], "Dataset Author")
            self.assertEqual(saved["member_name"], "tracks/song.wav")
            self.assertEqual(saved["member_crc32"], "deadbeef")
            self.assertEqual(saved["license_id"], "cc-by-4.0")
            self.assertTrue(result["rights_are_not_inferred"])

    def test_conflicting_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"dataset": "pilot", "source_id": "one", "rights": {"review_status": "pending"}},
                    {"dataset": "pilot", "source_id": "one", "rights": {"review_status": "approved"}}]
            path = root / "rows.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
                build([path], root / "queue.jsonl", root / "report.json")

    def test_source_key_subset_is_reproducible_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for source_id in ("one", "two"):
                rows.append({"dataset": "pilot", "source_id": source_id,
                             "rights": {"review_status": "pending"}})
            manifest = root / "manifest.jsonl"
            manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            selection = root / "selection.jsonl"
            selection.write_text(json.dumps({"source_key": "pilot:two"}) + "\n", encoding="utf-8")
            out, report = root / "queue.jsonl", root / "report.json"
            result = build([manifest], out, report, selection)
            self.assertEqual(result["input_sources"], 2)
            self.assertEqual(result["sources"], 1)
            self.assertEqual(json.loads(out.read_text())["source_key"], "pilot:two")
            unknown = root / "unknown.jsonl"
            unknown.write_text(json.dumps({"source_key": "pilot:nope"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown key"):
                build([manifest], root / "bad.jsonl", root / "bad.json", unknown)


if __name__ == "__main__":
    unittest.main()
