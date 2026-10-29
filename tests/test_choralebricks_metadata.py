import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_choralebricks_metadata import build_rows, main


class ChoraleBricksMetadataTests(unittest.TestCase):
    def test_official_table_has_ten_metadata_only_works(self):
        rows = build_rows()
        self.assertEqual(len(rows), 10)
        self.assertEqual(sum(row["duration_seconds"] for row in rows), 402)
        self.assertTrue(all(row["audio_path"] is None for row in rows))
        self.assertTrue(all(row["provenance_candidate"] for row in rows))
        self.assertTrue(all(not row["redistributable_candidate"] for row in rows))
        self.assertEqual(len({row["source_key"] for row in rows}), 10)

    def test_cli_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "choralebricks.jsonl"
            import sys
            old = sys.argv
            try:
                sys.argv = ["prepare", "--out", str(out)]
                main()
            finally:
                sys.argv = old
            self.assertEqual(len(out.read_text().splitlines()), 10)
            self.assertEqual(json.loads(out.read_text().splitlines()[0])["dataset"], "choralebricks")


if __name__ == "__main__":
    unittest.main()
