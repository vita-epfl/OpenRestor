"""Metadata-only feasibility audit invariants."""

import io
import json
import unittest
from unittest.mock import patch

from scripts.audit_iamd_lossless_feasibility import RateLimiter, analyse_item, fetch_one, project_metadata


class IamdFeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.item = {
            "identifier": "example", "segments": 3,
            "license_types": ["BY"],
            "license_urls": ["https://creativecommons.org/licenses/by/4.0/"],
            "genres": ["jazz"], "collections": ["netlabels"],
            "artists": ["Artist"], "creators": [], "tags": [],
        }

    def test_only_explicit_original_lossless_is_strict(self):
        source = {
            "metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                         "creator": "Artist", "collection": "netlabels"},
            "files": [
                {"name": "one.flac", "source": "original", "format": "Flac", "size": "1000", "length": "40", "sha1": "abc"},
                {"name": "two.wav", "format": "WAVE", "size": "1000", "length": "40", "sha1": "def"},
                {"name": "three.aiff", "source": "derivative", "format": "AIFF", "size": "1000", "length": "40", "sha1": "ghi"},
                {"name": "four.mp3", "source": "original", "format": "VBR MP3", "size": "1000", "length": "40"},
            ],
        }
        row, files = analyse_item(self.item, project_metadata(source), "ok")
        self.assertEqual(row["strict_original_files"], 1)
        self.assertEqual(row["source_ambiguous_files"], 1)
        self.assertEqual(row["derivative_files"], 1)
        self.assertEqual(len(files), 3)
        self.assertTrue(row["potentially_redistributable"])

    def test_public_domain_mark_is_not_cc0(self):
        self.item["license_types"] = ["CC0"]
        self.item["license_urls"] = ["https://creativecommons.org/publicdomain/zero/1.0/"]
        source = {"metadata": {"licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
                               "creator": "Artist", "collection": "netlabels"},
                  "files": [{"name": "one.flac", "source": "original", "format": "Flac",
                             "size": "1000", "length": "40", "sha1": "abc"}]}
        row, _ = analyse_item(self.item, project_metadata(source), "ok")
        self.assertEqual(row["licence_status"], "archive_missing_or_other")
        self.assertFalse(row["plausible"])

    def test_missing_or_conflicting_archive_format_is_not_strict(self):
        source = {"metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/"},
                  "files": [{"name": "one.wav", "source": "original", "format": "VBR MP3",
                             "size": "1000", "length": "40", "sha1": "abc"}]}
        row, files = analyse_item(self.item, project_metadata(source), "ok")
        self.assertEqual(row["strict_original_files"], 0)
        self.assertEqual(files[0]["status"], "format_ambiguous")

    def test_private_original_is_not_strict(self):
        source = {"metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/"},
                  "files": [{"name": "one.flac", "source": "original", "format": "Flac",
                             "private": "true", "size": "1000", "length": "40", "sha1": "abc"}]}
        row, files = analyse_item(self.item, project_metadata(source), "ok")
        self.assertEqual(row["strict_original_files"], 0)
        self.assertEqual(files[0]["status"], "private_file")

    def test_md5_can_substitute_for_missing_sha1(self):
        source = {"metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                               "creator": "Artist", "collection": "netlabels"},
                  "files": [{"name": "one.flac", "source": "original", "format": "Flac",
                             "size": "1000", "length": "40", "md5": "digest"}]}
        row, files = analyse_item(self.item, project_metadata(source), "ok")
        self.assertTrue(row["potentially_redistributable"])
        self.assertEqual(files[0]["md5"], "digest")

    def test_iamd_type_must_match_iamd_url(self):
        self.item["license_types"] = ["CC0"]
        source = {"metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/"},
                  "files": [{"name": "one.flac", "source": "original", "format": "Flac",
                             "size": "1000", "length": "40", "sha1": "abc"}]}
        row, _ = analyse_item(self.item, project_metadata(source), "ok")
        self.assertEqual(row["licence_status"], "iamd_type_url_conflict")
        self.assertFalse(row["plausible"])

    def test_fetch_requests_only_metadata_not_audio(self):
        payload = {"metadata": {"identifier": "example"}, "files": []}

        def fake_open(request, timeout):
            self.assertEqual(request.full_url, "https://archive.org/metadata/example")
            return io.BytesIO(json.dumps(payload).encode())

        with patch("urllib.request.urlopen", side_effect=fake_open):
            identifier, status, result, error = fetch_one("example", RateLimiter(1000))
        self.assertEqual((identifier, status, error), ("example", "ok", None))
        self.assertEqual(result["files"], [])


if __name__ == "__main__":
    unittest.main()
