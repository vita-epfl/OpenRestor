import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.audit_clean_audio_duplicates import audit, local_sources


class CleanAudioDuplicateTests(unittest.TestCase):
    def test_local_selection_skips_only_unavailable_catalogue_rows(self):
        rows = [{"source_key": "a:one", "audio_path": None},
                {"source_key": "a:two", "audio_path": "/private/missing.wav"}]
        selected, skipped = local_sources(rows)
        self.assertEqual(skipped, 1)
        self.assertEqual(selected[0]["source_key"], "a:two")

    def test_gain_changed_copy_is_candidate_but_noise_is_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rate = 8000
            t = np.arange(rate * 3) / rate
            original = (0.4 * np.sin(2 * np.pi * 440 * t) +
                        0.15 * np.sin(2 * np.pi * 880 * t)).astype("float32")
            sf.write(root / "a.wav", original, rate)
            sf.write(root / "b.flac", original * .5, rate)
            rng = np.random.default_rng(7)
            sf.write(root / "c.wav", rng.normal(size=len(original)).astype("float32") * .1, rate)
            rows = [{"dataset": "a", "source_id": "one", "audio_path": str(root / "a.wav")},
                    {"dataset": "b", "source_id": "copy", "audio_path": str(root / "b.flac")},
                    {"dataset": "c", "source_id": "noise", "audio_path": str(root / "c.wav")}]
            output, report = audit(rows, window_seconds=2, similarity_threshold=.985)
            self.assertEqual(report["failed_sources"], 0)
            self.assertEqual(report["acoustic_duplicate_groups"], 1)
            by_key = {row["source_key"]: row for row in output}
            self.assertEqual(by_key["a:one"]["acoustic_duplicate_source_keys"],
                             ["a:one", "b:copy"])
            self.assertTrue(by_key["a:one"]["acoustic_dedup_representative"])
            self.assertFalse(by_key["b:copy"]["acoustic_dedup_representative"])
            self.assertEqual(by_key["c:noise"]["acoustic_duplicate_source_keys"], ["c:noise"])
            self.assertTrue(report["human_verification_required"])
            self.assertFalse(report["deletion_performed"])


if __name__ == "__main__":
    unittest.main()
