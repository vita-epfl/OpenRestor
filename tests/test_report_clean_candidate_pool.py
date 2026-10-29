import unittest

from scripts.report_clean_candidate_pool import summarize


class CandidatePoolReportTests(unittest.TestCase):
    def test_unknowns_and_candidate_axes_are_separate(self):
        rows = [
            {"source_key": "a:1", "dataset": "a", "duration_seconds": 3600,
             "metadata": {"genre": "rock", "creator": "one",
                          "member_uncompressed_size_bytes": 48000},
             "technical_candidate": True, "provenance_candidate": False,
             "redistributable_candidate": False, "lossless_status": "clean_lossless",
             "rights": {"license_label": "CC BY", "review_status": "pending"}},
            {"source_key": "b:2", "dataset": "b", "duration_seconds": None,
             "technical_candidate": False, "provenance_candidate": True,
             "redistributable_candidate": False, "metadata": {"genre": ["rock", "live"]},
             "rights": {"license_label": "CC0", "review_status": "unknown"}},
        ]
        report = summarize(rows)
        self.assertEqual(report["source_count"], 2)
        self.assertAlmostEqual(report["estimated_hours"], 1.0)
        self.assertEqual(report["duration_unknown_sources"], 1)
        self.assertEqual(report["estimated_uncompressed_bytes"], 48000)
        self.assertEqual(report["size_known_sources"], 1)
        self.assertEqual(report["size_unknown_sources"], 1)
        self.assertEqual(report["candidate_counts"]["technical_candidate"], 1)
        self.assertEqual(report["candidate_counts"]["provenance_candidate"], 1)
        self.assertEqual(report["distributions"]["genre"]["rock"], 2)
        self.assertEqual(report["distributions"]["license"]["CC BY"], 1)
        self.assertEqual(report["concentration"]["creator"]["unknown_items"], 1)
        self.assertLessEqual(report["concentration"]["genre"]["top_5_share"], 1.0)
        self.assertFalse(report["rights_inferred"])

    def test_duplicate_source_keys_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate source_key"):
            summarize([{"source_key": "a:1"}, {"source_key": "a:1"}])


if __name__ == "__main__":
    unittest.main()
