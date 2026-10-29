import tempfile
import unittest
from pathlib import Path

from scripts.prepare_clean_corpus_splits import prepare


class CleanCorpusSplitTests(unittest.TestCase):
    def test_exact_duplicates_and_creator_groups_never_cross_splits(self):
        rows = [
            {"dataset": "a", "source_id": "one", "source_sha256": "abc",
             "metadata": {"creator": "Same Artist", "genre": "rock"}},
            {"dataset": "b", "source_id": "copy", "source_sha256": "abc",
             "metadata": {"creator": "Same Artist", "genre": "rock"}},
            {"dataset": "c", "source_id": "two", "source_sha256": "def",
             "metadata": {"creator": "Same Artist", "genre": "jazz"}},
            {"dataset": "d", "source_id": "three", "source_sha256": "ghi",
             "metadata": {"creator": "Other Artist", "genre": "ambient"}},
        ]
        dedup, mapping, report = prepare(rows, seed=2, validation_ratio=.25, test_ratio=.25)
        self.assertEqual(len(dedup), 3)
        self.assertEqual(report["duplicate_rows_removed"], 1)
        by_source = {row["source_key"]: row for row in mapping}
        self.assertEqual(by_source["a:one"]["split"], by_source["b:copy"]["split"])
        self.assertEqual(by_source["a:one"]["split"], by_source["c:two"]["split"])
        self.assertTrue(report["split_disjoint"])
        self.assertFalse(report["audio_accessed"])

    def test_missing_checksums_are_reported_not_silently_deduplicated(self):
        rows = [{"dataset": "a", "source_id": "one", "metadata": {"creator": "A"}},
                {"dataset": "a", "source_id": "two", "metadata": {"creator": "B"}}]
        dedup, mapping, report = prepare(rows)
        self.assertEqual(len(dedup), 2)
        self.assertEqual(report["sources_without_content_checksum"], 2)
        self.assertEqual(report["sources_without_creator"], 0)

    def test_checksum_bridge_keeps_both_creators_other_recordings_together(self):
        rows = [
            {"dataset": "a", "source_id": "shared", "source_sha256": "same",
             "metadata": {"creator": "Artist A"}},
            {"dataset": "b", "source_id": "shared", "source_sha256": "same",
             "metadata": {"creator": "Artist B"}},
            {"dataset": "a", "source_id": "other", "source_sha256": "a-only",
             "metadata": {"creator": "Artist A"}},
            {"dataset": "b", "source_id": "other", "source_sha256": "b-only",
             "metadata": {"creator": "Artist B"}},
        ]
        chosen, mapping, report = prepare(rows, seed=7)
        self.assertEqual(len(chosen), 3)
        self.assertEqual(report["cross_creator_connected_groups"], 1)
        self.assertEqual(report["connected_split_groups"], 1)
        self.assertEqual(len({row["split_group_key"] for row in mapping}), 1)
        self.assertEqual(len({row["split"] for row in mapping}), 1)

    def test_albumdb_album_stays_in_one_split_without_asset_creator(self):
        rows = [
            {"dataset": "albumdb", "source_id": "song01/stem.wav",
             "metadata": {"zenodo_record_id": "19683001", "creator": None}},
            {"dataset": "albumdb", "source_id": "song02/master.wav",
             "metadata": {"zenodo_record_id": "19683001", "creator": None}},
            {"dataset": "albumdb", "source_id": "other-record.wav",
             "metadata": {"zenodo_record_id": "different", "creator": None}},
        ]
        chosen, mapping, report = prepare(rows)
        self.assertEqual(len(chosen), 3)
        by_source = {row["source_key"]: row for row in mapping}
        first = by_source["albumdb:song01/stem.wav"]
        second = by_source["albumdb:song02/master.wav"]
        self.assertEqual(first["split_group_key"], "album:albumdb:19683001")
        self.assertEqual(first["split_group_key"], second["split_group_key"])
        self.assertEqual(first["split"], second["split"])
        self.assertEqual(first["grouping_basis"], "album_record")
        self.assertFalse(first["has_creator"])
        self.assertEqual(report["sources_grouped_by_album"], 2)
        self.assertEqual(report["sources_without_creator"], 3)
        self.assertEqual(report["sources_without_group_identity"], 1)

    def test_explicit_album_group_connects_assets_without_creator(self):
        rows = [
            {"dataset": "custom", "source_id": "a", "metadata": {"album_group_id": "release-1"}},
            {"dataset": "custom", "source_id": "b", "metadata": {"album_group_id": "release-1"}},
        ]
        _, mapping, report = prepare(rows)
        self.assertEqual(len({row["split_group_key"] for row in mapping}), 1)
        self.assertEqual({row["grouping_basis"] for row in mapping}, {"explicit_album"})
        self.assertEqual(report["sources_grouped_by_album"], 2)

    def test_creator_still_connects_separate_albums(self):
        rows = [
            {"dataset": "custom", "source_id": "a",
             "metadata": {"album_group_id": "release-1", "creator": "Artist A"}},
            {"dataset": "custom", "source_id": "b",
             "metadata": {"album_group_id": "release-2", "creator": "Artist A"}},
        ]
        _, mapping, report = prepare(rows)
        self.assertEqual(len({row["split_group_key"] for row in mapping}), 1)
        self.assertEqual(report["connected_split_groups"], 1)

    def test_invalid_duplicate_source_key_fails(self):
        with self.assertRaises(ValueError):
            prepare([{"dataset": "a", "source_id": "one"},
                     {"dataset": "a", "source_id": "one"}])


if __name__ == "__main__":
    unittest.main()
