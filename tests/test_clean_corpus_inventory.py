import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.audit_clean_corpus_sources import main


class CleanCorpusInventoryTests(unittest.TestCase):
    def test_decoded_mp3_transfer_is_not_lossless(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp3"
            transfer = root / "audio" / "sdd--track--00.wav"
            transfer.parent.mkdir()
            sf.write(transfer, np.zeros(8000, dtype="float32"), 8000)
            index = root / "index.jsonl"
            index.write_text(json.dumps({"dataset": "sdd", "source_id": "track",
                                         "audio_path": str(source), "duration_seconds": 1}) + "\n")
            out, summary = root / "audit.jsonl", root / "summary.json"
            import sys
            old = sys.argv
            try:
                sys.argv = ["audit", "--index", str(index), "--audio-root", str(root),
                            "--out", str(out), "--summary", str(summary)]
                main()
            finally:
                sys.argv = old
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["lossless_status"], "clean_lossy_hq")
            self.assertEqual(row["audio_path"], str(transfer))
            self.assertTrue(row["technical_candidate"])
            self.assertFalse(row["redistributable_candidate"])

    def test_original_pcm_with_matching_checksum_is_clean_lossless(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "original.wav"
            sf.write(audio, np.zeros(8000, dtype="float32"), 8000, subtype="PCM_16")
            import hashlib
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            index = root / "index.jsonl"
            index.write_text(json.dumps({
                "dataset": "iamd_archive", "source_id": "original",
                "audio_path": str(audio), "source_sha256": digest,
                "provenance_candidate": True,
                "rights": {"source_status": "archive_original_download_verified_codec_unverified",
                            "license_label": "CC BY 4.0"},
            }) + "\n", encoding="utf-8")
            out, summary = root / "audit.jsonl", root / "summary.json"
            import sys
            old = sys.argv
            try:
                sys.argv = ["audit", "--index", str(index), "--out", str(out),
                            "--summary", str(summary)]
                main()
            finally:
                sys.argv = old
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["lossless_status"], "clean_lossless")
            self.assertTrue(row["source_original_verified"])
            self.assertTrue(row["codec_lossless_verified"])
            self.assertTrue(row["source_hash_match"])
            self.assertTrue(row["provenance_candidate"])
            self.assertEqual(row["rights"]["license_label"], "CC BY 4.0")

    def test_original_pcm_with_wrong_checksum_stays_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "original.wav"
            sf.write(audio, np.zeros(8000, dtype="float32"), 8000, subtype="PCM_16")
            index = root / "index.jsonl"
            index.write_text(json.dumps({
                "dataset": "iamd_archive", "source_id": "wrong",
                "audio_path": str(audio), "source_sha256": "0" * 64,
                "rights": {"source_status": "archive_original_download_verified"},
            }) + "\n", encoding="utf-8")
            out, summary = root / "audit.jsonl", root / "summary.json"
            import sys
            old = sys.argv
            try:
                sys.argv = ["audit", "--index", str(index), "--out", str(out),
                            "--summary", str(summary)]
                main()
            finally:
                sys.argv = old
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["lossless_status"], "lossless_container_unverified")
            self.assertFalse(row["source_hash_match"])


if __name__ == "__main__":
    unittest.main()
