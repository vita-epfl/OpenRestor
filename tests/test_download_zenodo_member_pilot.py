import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from scripts.download_zenodo_member_pilot import run


def jsonl(path, rows):
    path.write_text("".join(__import__("json").dumps(row) + "\n" for row in rows), encoding="utf-8")


class DownloadZenodoMemberPilotTests(unittest.TestCase):
    def test_download_verifies_crc_and_marks_private(self):
        stream = io.BytesIO()
        audio = io.BytesIO()
        sf.write(audio, np.zeros(8000, dtype="float32"), 8000, format="WAV", subtype="PCM_16")
        wav = audio.getvalue()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("song.wav", wav)
        payload = stream.getvalue()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            info = archive.infolist()[0]
            member = {"name": info.filename, "format": "WAV", "compression_method": 8,
                      "compressed_size_bytes": info.compress_size, "uncompressed_size_bytes": info.file_size,
                      "local_header_offset": info.header_offset, "crc32": f"{info.CRC:08x}",
                      "is_directory": False, "is_macos_sidecar": False}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archives = root / "archives.jsonl"; probes = root / "probes.jsonl"; out = root / "pilot"
            jsonl(archives, [{"identity": "1:a.zip", "record_id": 1, "archive_key": "a.zip",
                              "archive_url": "https://example.test/a.zip", "members": [member]}])
            jsonl(probes, [{"identity": "1:a.zip:song.wav", "archive_identity": "1:a.zip",
                            "member_name": "song.wav", "status": "resolved",
                            "compressed_size_bytes": info.compress_size}])
            def ranges(_url, start, end, _timeout): return payload[start:end + 1]
            with patch("scripts.download_zenodo_member_pilot.fetch_range", side_effect=ranges), \
                 patch("scripts.probe_zenodo_member_headers.fetch_range", side_effect=ranges):
                rows = run(archives, probes, out, 1, 1024 * 1024, 1)
            self.assertEqual(rows[0]["status"], "verified")
            self.assertTrue(rows[0]["private_pilot"])
            self.assertFalse(rows[0]["redistribution_approved"])
            self.assertTrue(Path(rows[0]["local_audio_path"]).is_file())
            self.assertTrue((out / "PRIVATE_PILOT_NOTICE.md").is_file())


if __name__ == "__main__":
    unittest.main()
