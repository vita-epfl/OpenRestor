import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.prepare_iamd_pilot_manifest import prepare


class IamdPilotManifestTests(unittest.TestCase):
    def test_only_checksum_verified_audio_enters_pending_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_dir = root / "originals" / "track-a"
            audio_dir.mkdir(parents=True)
            path = audio_dir / "song.wav"
            sf.write(path, np.zeros(8000, dtype="float32"), 8000)
            payload = path.read_bytes()
            track = {
                "track_id": "track-a", "identifier": "archive-a", "name": "song.wav",
                "format": "WAV", "source": "original", "size_bytes": len(payload),
                "sha1": hashlib.sha1(payload).hexdigest(), "md5": None,
                "creator": "Artist", "collection": "collection", "genre": "Jazz",
                "title": "Song", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "licence_status": "match",
            }
            (root / "tracks.jsonl").write_text(json.dumps(track) + "\n", encoding="utf-8")
            (root / "download_status.jsonl").write_text(json.dumps({
                "track_id": "track-a", "status": "verified"}) + "\n", encoding="utf-8")
            rows, report = prepare(root, root)
            self.assertEqual(report["verified_sources"], 1)
            row = rows[0]
            self.assertEqual(row["original_format"], "WAV")
            self.assertEqual(row["sample_rate"], 8000)
            self.assertTrue(row["source_sha256"])
            self.assertFalse(row["redistributable_candidate"])
            self.assertFalse(row["rights"]["provenance_approved"])
            self.assertIsNone(row["rights"]["allow_redistribution"])

    def test_partial_or_checksum_mismatch_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_dir = root / "originals" / "track-a"
            audio_dir.mkdir(parents=True)
            path = audio_dir / "song.wav"
            path.write_bytes(b"not-a-valid-audio")
            track = {"track_id": "track-a", "identifier": "archive-a", "name": "song.wav",
                     "format": "WAV", "source": "original", "size_bytes": path.stat().st_size,
                     "sha1": "0" * 40, "md5": None}
            (root / "tracks.jsonl").write_text(json.dumps(track) + "\n", encoding="utf-8")
            rows, report = prepare(root, root)
            self.assertEqual(rows, [])
            self.assertEqual(report["skipped"], {"sha1_mismatch": 1})


if __name__ == "__main__":
    unittest.main()
