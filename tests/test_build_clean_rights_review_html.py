import csv
import tempfile
import unittest
from pathlib import Path

from scripts.build_clean_rights_review_html import build


class CleanRightsReviewHtmlTests(unittest.TestCase):
    def test_builds_local_filtered_form_without_audio_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "review.csv"
            fields = ["source_key", "dataset", "title", "collection", "creator",
                      "original_format", "source_status", "license_label", "evidence_url",
                      "archive_url", "member_url", "decision"]
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"source_key": "a:1", "dataset": "a", "title": "A <song>",
                                 "creator": "Artist", "decision": ""})
                writer.writerow({"source_key": "b:2", "dataset": "b", "title": "B",
                                 "decision": ""})
            out = root / "review.html"
            result = build(source, out)
            text = out.read_text(encoding="utf-8")
            self.assertEqual(result["rows"], 2)
            self.assertFalse(result["audio_loaded"])
            self.assertFalse(result["network_requests"])
            self.assertIn("A &lt;song&gt;", text)
            self.assertIn('data-field="decision"', text)
            self.assertIn("Télécharger le CSV", text)
            self.assertNotIn("audio_path", text)
            self.assertIn("localStorage", text)

    def test_rejects_audio_path_column(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.csv"
            source.write_text("source_key,decision,audio_path\na:1,,/private/a.wav\n",
                              encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "audio_path"):
                build(source, root / "out.html")


if __name__ == "__main__":
    unittest.main()

