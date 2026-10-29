import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.inspect_zenodo_zip_ranges import inspect_archive, parse_zip_central_directory


class InspectZenodoZipRangeTests(unittest.TestCase):
    def archive_bytes(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("audio/song.wav", b"wav")
            archive.writestr("audio/song.flac", b"flac")
            archive.writestr("README.txt", b"readme")
        return stream.getvalue()

    def test_central_directory_parser_only_exposes_member_metadata(self):
        data = self.archive_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            # Locate the central directory from the first local header offset and
            # the central record lengths; this is only a fixture construction aid.
            start = data.find(b"PK\x01\x02")
            end = data.find(b"PK\x05\x06")
            members = parse_zip_central_directory(data[start:end], len(infos))
        self.assertEqual([m["format"] for m in members], ["WAV", "FLAC", None])
        self.assertEqual(members[0]["source_status"], "ambiguous_original_status")

    def test_macos_sidecar_is_not_counted_as_audio(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("__MACOSX/._song.wav", b"sidecar")
            archive.writestr("song.wav", b"wav")
        data = stream.getvalue()
        start = data.find(b"PK\x01\x02")
        end = data.find(b"PK\x05\x06")
        members = parse_zip_central_directory(data[start:end], 2)
        self.assertIsNone(members[0]["format"])
        self.assertTrue(members[0]["is_macos_sidecar"])
        self.assertEqual(members[1]["format"], "WAV")

    def test_inspect_archive_uses_only_range_fetches(self):
        data = self.archive_bytes()
        calls = []

        def bounded(_url, start, end, _timeout=30.0):
            calls.append((start, end))
            return data[start:end + 1]

        result = None
        with patch("scripts.inspect_zenodo_zip_ranges.fetch_range", side_effect=bounded):
            result = inspect_archive("https://example.test/a.zip", len(data), "a.zip")
        self.assertEqual(result["audio_member_count"], 2)
        self.assertEqual(result["macos_sidecar_count"], 0)
        self.assertEqual(result["audio_member_formats"], {"FLAC": 1, "WAV": 1})
        self.assertFalse(result["audio_downloaded"])
        self.assertEqual(result["source_status"], "ambiguous_original_status")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
