import csv
import json
import tempfile
import unittest
from pathlib import Path

from openrestor.curation.evaluation import import_blind_reviews


class BlindReviewImportTests(unittest.TestCase):
    def test_maps_filled_blind_row_and_ignores_blank_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            order = root / "order.jsonl"
            order.write_text(json.dumps({"blind_id": "blind-0001", "blind_rank": 1,
                                         "source_key": "demo:one"}) + "\n" +
                             json.dumps({"blind_id": "blind-0002", "blind_rank": 2,
                                         "source_key": "demo:two"}) + "\n", encoding="utf-8")
            reviews = root / "reviews.csv"
            with reviews.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["blind_id", "content_type", "audio_quality"])
                writer.writeheader()
                writer.writerow({"blind_id": "blind-0001", "content_type": "music", "audio_quality": "acceptable"})
                writer.writerow({"blind_id": "blind-0002", "content_type": "", "audio_quality": ""})
            result = import_blind_reviews(reviews, order, {"demo:one", "demo:two"})
            self.assertEqual(set(result), {"demo:one"})
            self.assertEqual(result["demo:one"]["blind_id"], "blind-0001")
            self.assertEqual(result["demo:one"]["human_class"], "positive_clip_evidence")

    def test_unknown_blind_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            order = root / "order.jsonl"
            order.write_text(json.dumps({"blind_id": "blind-0001", "source_key": "demo:one"}) + "\n",
                             encoding="utf-8")
            reviews = root / "reviews.csv"
            reviews.write_text("blind_id,content_type\nblind-9999,music\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                import_blind_reviews(reviews, order, {"demo:one"})


if __name__ == "__main__":
    unittest.main()
