import io
import struct
import unittest
import zipfile
from unittest.mock import patch

from scripts.probe_zenodo_member_headers import parse_audio_header, probe_member


class ProbeZenodoMemberHeaderTests(unittest.TestCase):
    def test_parse_wav_pcm_header(self):
        data = bytearray(b"RIFF" + struct.pack("<I", 36) + b"WAVE")
        data += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 2, 48000, 192000, 4, 16)
        data += b"data" + struct.pack("<I", 192000)
        row = parse_audio_header(bytes(data), ".wav")
        self.assertEqual(row["container"], "WAV")
        self.assertEqual(row["codec"], "PCM")
        self.assertEqual(row["sample_rate_hz"], 48000)
        self.assertEqual(row["channels"], 2)

    def test_probe_member_uses_local_header_and_bounded_member_prefix(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("song.wav", b"RIFF" + b"\x00" * 200)
        payload = stream.getvalue()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            info = archive.infolist()[0]
            member = {"name": info.filename, "format": "WAV", "compression_method": 8,
                      "compressed_size_bytes": info.compress_size,
                      "local_header_offset": info.header_offset, "is_directory": False}

        def ranges(_url, start, end, _timeout):
            return payload[start:end + 1]

        with patch("scripts.probe_zenodo_member_headers.fetch_range", side_effect=ranges):
            row = probe_member("https://example.test/a.zip", member, 4096, 1)
        self.assertFalse(row["audio_downloaded"])
        self.assertEqual(row["source_status"], "ambiguous_original_status")
        self.assertLessEqual(row["probe_bytes_downloaded"], 4096 + 30)


if __name__ == "__main__":
    unittest.main()
