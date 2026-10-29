"""Sparse human labels must not become implicit clean or bad labels."""

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.iamd_phase2_sparse_review import analyze, parse_reviews


class SparseReviewTests(unittest.TestCase):
    def test_sparse_fields_stay_unassessed_and_flag_accepted_problem(self):
        predictions = {
            "a": {"identifier": "a", "classification": "accept_candidate", "acoustic": {},
                  "collection": "A", "genre_proxy": "rock", "creator": "One"},
            "b": {"identifier": "b", "classification": "review", "acoustic": {},
                  "collection": "B", "genre_proxy": "pop", "creator": "Two"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["identifier", "audio_quality"])
                writer.writeheader()
                writer.writerows([{"identifier": "a", "audio_quality": "degraded"},
                                  {"identifier": "b", "audio_quality": ""}])
            csv_rows, reviewed = parse_reviews(path, set(predictions))
        result = analyze(predictions, reviewed, csv_rows)
        self.assertEqual(result["reviewed_any_explicit_label_or_note"], 1)
        self.assertEqual(result["field_counts_among_reviewed"]["content_type"], {"unassessed": 1})
        self.assertEqual(result["explicit_problem_count"], 1)
        self.assertEqual([case["identifier"] for case in result["explicit_problems_auto_accepted"]], ["a"])
        self.assertEqual(result["fully_positive_clip_labels"], 0)

    def test_unknown_or_invalid_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.csv"
            path.write_text("identifier,audio_quality\nother,acceptable\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown or duplicate"):
                parse_reviews(path, {"a"})
            path.write_text("identifier,audio_quality\na,great\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid audio_quality"):
                parse_reviews(path, {"a"})

    def test_source_label_needs_more_than_primary_clip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.csv"
            path.write_text("identifier,source_level_label\na,promising\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires multiple excerpts"):
                parse_reviews(path, {"a"})


if __name__ == "__main__":
    unittest.main()
