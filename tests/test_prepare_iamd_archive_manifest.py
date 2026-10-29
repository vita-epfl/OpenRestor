import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_iamd_archive_manifest import prepare


class IamdArchiveManifestTests(unittest.TestCase):
    def test_metadata_only_manifest_is_fail_closed_for_rights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.jsonl"
            items = root / "items.jsonl"
            files = root / "files.jsonl"
            candidates.write_text(json.dumps({
                "identifier": "item-a", "creators": ["Artist A"],
                "genres": ["Jazz"], "collections": ["music"], "tags": ["live"],
                "license_urls": ["https://creativecommons.org/licenses/by/4.0"],
            }) + "\n", encoding="utf-8")
            items.write_text(json.dumps({
                "identifier": "item-a", "status": "resolved",
                "technical_candidate": True, "provenance_candidate": True,
                "redistributable_candidate": True,
                "archive_license_label": "CC BY 4.0",
                "archive_license_url": "https://creativecommons.org/licenses/by/4.0/",
                "archive_licence_category": "compatible", "creator": "Artist A",
                "collection": "music", "genre": "Jazz", "tags": ["live"],
                "title": "A Live Track", "retrieval_method": "metadata_api",
            }) + "\n", encoding="utf-8")
            files.write_text(json.dumps({
                "identifier": "item-a", "name": "track.flac", "format": "FLAC",
                "archive_format": "24bit Flac", "source": "original",
                "status": "strict_original", "private": False,
                "size_bytes": 1234, "length_s": 12.5,
                "sha1": "abc", "md5": None, "download_url": None,
            }) + "\n", encoding="utf-8")
            rows, report = prepare(candidates, items, files, "provenance")
            self.assertEqual(report["output_sources"], 1)
            row = rows[0]
            self.assertIsNone(row["audio_path"])
            self.assertTrue(row["technical_candidate"])
            self.assertTrue(row["provenance_candidate"])
            self.assertFalse(row["redistributable_candidate"])
            self.assertFalse(row["rights"]["provenance_approved"])
            self.assertIsNone(row["rights"]["allow_redistribution"])
            self.assertEqual(row["duration_seconds"], 12.5)
            self.assertEqual(row["archive_original_files"][0]["download_url"],
                             "https://archive.org/download/item-a/track.flac")

    def test_alternate_originals_do_not_double_count_duration_and_bad_rows_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write(path, rows):
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            write(root / "candidates.jsonl", [
                {"identifier": "item-a", "creators": ["A"], "collections": ["c"]},
                {"identifier": "item-b", "creators": ["B"], "collections": ["c"]},
            ])
            write(root / "items.jsonl", [
                {"identifier": "item-a", "status": "resolved", "technical_candidate": True,
                 "provenance_candidate": True, "redistributable_candidate": False,
                 "archive_license_label": "CC0 1.0", "archive_license_url": "https://creativecommons.org/publicdomain/zero/1.0/"},
                {"identifier": "item-b", "status": "resolved", "technical_candidate": False,
                 "provenance_candidate": False, "redistributable_candidate": False},
            ])
            write(root / "files.jsonl", [
                {"identifier": "item-a", "name": "a.flac", "format": "FLAC", "source": "original",
                 "status": "strict_original", "private": False, "size_bytes": 1, "length_s": 10},
                {"identifier": "item-a", "name": "a.wav", "format": "WAV", "source": "original",
                 "status": "strict_original", "private": False, "size_bytes": 1, "length_s": 20},
                {"identifier": "item-b", "name": "b.mp3", "format": "MP3", "source": "original",
                 "status": "derivative_or_other", "private": False, "size_bytes": 1, "length_s": 4},
            ])
            rows, report = prepare(root / "candidates.jsonl", root / "items.jsonl",
                                   root / "files.jsonl", "technical")
            self.assertEqual([r["source_id"] for r in rows], ["item-a"])
            self.assertEqual(rows[0]["duration_seconds"], 20.0)
            self.assertEqual(report["counts_skipped"]["no_strict_original"], 1)


if __name__ == "__main__":
    unittest.main()
