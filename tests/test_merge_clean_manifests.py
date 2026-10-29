import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_clean_manifests import merge


class MergeCleanManifestTests(unittest.TestCase):
    def test_identical_duplicates_collapse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {"dataset": "x", "source_id": "1", "value": "same"}
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            first.write_text(json.dumps(row) + "\n", encoding="utf-8")
            second.write_text(json.dumps(row) + "\n", encoding="utf-8")
            rows, report = merge([first, second])
            self.assertEqual(len(rows), 1)
            self.assertEqual(report["duplicate_identical_count"], 1)
            self.assertEqual(report["override_count"], 0)

    def test_conflict_requires_explicit_override_and_later_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "catalogue.jsonl"
            second = root / "pilot.jsonl"
            first.write_text(json.dumps({"dataset": "x", "source_id": "1",
                                         "technical_candidate": False}) + "\n", encoding="utf-8")
            second.write_text(json.dumps({"dataset": "x", "source_id": "1",
                                          "technical_candidate": True}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
                merge([first, second])
            rows, report = merge([first, second], allow_overrides=True)
            self.assertTrue(rows[0]["technical_candidate"])
            self.assertEqual(report["override_count"], 1)

    def test_missing_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text(json.dumps({"dataset": "x"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no source key"):
                merge([path])

    def test_cli_output_is_schema_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text(json.dumps({
                "dataset": "x", "source_id": "1", "source_key": "x:1",
                "audio_path": None, "metadata": {}, "rights": {},
            }) + "\n", encoding="utf-8")
            output, report = root / "merged.jsonl", root / "report.json"
            import sys
            from scripts.merge_clean_manifests import main
            old = sys.argv
            try:
                sys.argv = ["merge", "--input", str(source), "--out", str(output),
                            "--report", str(report)]
                main()
            finally:
                sys.argv = old
            self.assertTrue(json.loads(report.read_text())["schema_validated"])


if __name__ == "__main__":
    unittest.main()
