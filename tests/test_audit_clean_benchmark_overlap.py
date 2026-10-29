import unittest

from scripts.audit_clean_benchmark_overlap import audit


class BenchmarkOverlapTests(unittest.TestCase):
    def test_archive_identifier_blocks_iamd_against_blind_real(self):
        candidates = [{"dataset": "iamd_archive", "source_id": "record-one"},
                      {"dataset": "albumdb", "source_id": "song-two"}]
        references = {"blind_real_test": [{"dataset": "blind_real",
                                            "internet_archive_identifier": "record-one"}]}
        safe, overlap, report = audit(candidates, references)
        self.assertEqual([row["source_id"] for row in safe], ["song-two"])
        self.assertEqual(overlap[0]["reference_labels"], ["blind_real_test"])
        self.assertEqual(report["overlap_sources"], 1)

    def test_alias_and_source_hash_match_but_clip_hash_does_not(self):
        digest = "a" * 64
        candidates = [{"dataset": "iamd_archive", "source_id": "same"},
                      {"dataset": "other", "source_id": "hash", "source_sha256": digest},
                      {"dataset": "other", "source_id": "clip-hash", "source_sha256": "b" * 64}]
        references = {"evaluation": [{"dataset": "iamd", "source_id": "same"},
                                     {"dataset": "unrelated", "source_id": "x",
                                      "source_sha256": digest, "audio_sha256": "b" * 64}]}
        safe, overlap, _ = audit(candidates, references)
        self.assertEqual([row["source_id"] for row in safe], ["clip-hash"])
        self.assertEqual(len(overlap), 2)

    def test_missing_identity_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "lacks stable identity"):
            audit([{"source_key": "a:x"}], {"test": [{"dataset": "a", "source_id": "y"}]})


if __name__ == "__main__":
    unittest.main()
