import json
import tempfile
import unittest
from pathlib import Path

from scripts.normalize_clean_manifest import main, normalize


class CleanManifestAdapterTests(unittest.TestCase):
    def test_normalizes_common_dataset_aliases_and_preserves_rights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text(json.dumps({
                "dataset_name": "albumdb", "identifier": "album-1",
                "path": "/data/album-1.flac", "artist": "Artist", "genres": ["rock"],
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "review_status": "pending", "sample_rate": 48000,
            }) + "\n", encoding="utf-8")
            out = root / "manifest.jsonl"
            import sys
            old = sys.argv
            try:
                sys.argv = ["normalize", "--input", str(source), "--out", str(out)]
                main()
            finally:
                sys.argv = old
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["source_key"], "albumdb:album-1")
            self.assertEqual(row["metadata"]["creator"], "Artist")
            self.assertEqual(row["metadata"]["genre"], ["rock"])
            self.assertEqual(row["rights"]["review_status"], "pending")
            self.assertIsNone(row["rights"].get("allow_commercial"))

    def test_preserves_curation_features_segments_and_annotation_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            curation = {
                "features": {"PQ": 7.2, "bandwidth_hz": 19000},
                "segments": [{"segment_id": "pilot:one#p1", "start_s": 10.0}],
                "segment_decisions": [{"segment_id": "pilot:one#p1", "decision": "auto_accept"}],
                "source_decision": "manual_review",
                "annotations": [{"reviewer": "R", "content_type": "music"}],
                "annotation_history": [{"version": 1, "decision": "manual_review"}],
            }
            source.write_text(json.dumps({
                "dataset": "pilot", "source_id": "one", "audio_path": "/data/one.wav",
                **curation,
            }) + "\n", encoding="utf-8")
            out = root / "manifest.jsonl"
            import sys
            old = sys.argv
            try:
                sys.argv = ["normalize", "--input", str(source), "--out", str(out)]
                main()
            finally:
                sys.argv = old
            row = json.loads(out.read_text().splitlines()[0])
            for field, value in curation.items():
                self.assertEqual(row[field], value)

    def test_canonicalizes_numeric_metadata_and_rejects_invalid_values(self):
        row = normalize({
            "dataset": "pilot", "source_id": "numeric", "audio_path": None,
            "sample_rate": "44100", "channels": "2", "duration": "3.5",
        })
        self.assertEqual(row["sample_rate"], 44100)
        self.assertEqual(row["channels"], 2)
        self.assertEqual(row["duration_seconds"], 3.5)
        with self.assertRaisesRegex(ValueError, "sample_rate"):
            normalize({"dataset": "pilot", "source_id": "bad", "sample_rate": "unknown"})


if __name__ == "__main__":
    unittest.main()
