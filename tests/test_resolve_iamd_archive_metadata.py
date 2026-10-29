"""Portable Archive resolver and offline handoff tests (no live requests)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import audit_iamd_lossless_feasibility as audit
from scripts import resolve_iamd_archive_metadata as resolver


class PortableResolverTests(unittest.TestCase):
    @staticmethod
    def candidate(identifier, licence="BY"):
        url = ("https://creativecommons.org/publicdomain/zero/1.0/" if licence == "CC0" else
               "https://creativecommons.org/licenses/by/4.0/")
        return {"identifier": identifier, "segments": 1, "license_types": [licence],
                "license_urls": [url], "genres": ["Jazz"], "collections": ["opensource_audio"],
                "creators": ["Artist"], "artists": ["Artist"], "tags": ["jazz"]}

    @staticmethod
    def prepare_offline_fixture(out, candidates):
        text = "".join(json.dumps(candidate) + "\n" for candidate in candidates)
        (out / "iamd_clean_candidate_identifiers.jsonl").write_text(text)
        (out / "candidates.jsonl").write_text(text)
        (out / "scan_summary.json").write_text(json.dumps({"blind_real_identifiers_excluded_set": 0}))

    def test_metadata_api_only_keeps_original_and_ambiguous_lossless(self):
        body = {
            "metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                         "rights": "Credit Artist", "creator": "Artist"},
            "files": [
                {"name": "dir/song.flac", "source": "original", "format": "Flac", "size": "1000",
                 "length": "40", "sha1": "sha1", "md5": "md5"},
                {"name": "unknown.wav", "format": "WAVE", "size": "500"},
                {"name": "derivative.aiff", "source": "derivative", "format": "AIFF"},
                {"name": "source.mp3", "source": "original", "format": "VBR MP3"},
            ],
        }
        with patch.object(resolver, "get_bytes", return_value=json.dumps(body).encode()) as get:
            result = resolver.resolve("example", 1, 0, False)
        self.assertEqual(get.call_args.args[0], "https://archive.org/metadata/example")
        self.assertEqual(result["status"], "ok")
        self.assertEqual([file["original_status"] for file in result["files"]],
                         ["strict_original", "source_ambiguous"])
        self.assertEqual(result["lossless_file_counts"]["derivative_or_other"], 1)
        self.assertEqual(result["files"][0]["md5"], "md5")
        self.assertEqual(result["files"][0]["download_url"],
                         "https://archive.org/download/example/dir/song.flac")

    def test_xml_fallback_uses_files_and_meta_xml_only(self):
        urls = []

        def fake_get(url, timeout, retries):
            urls.append(url)
            if "/metadata/" in url:
                raise RuntimeError("metadata API unavailable")
            if url.endswith("_files.xml"):
                return (b'<files><file name="tune.aiff" source="original">'
                        b'<format>AIFF</format><size>4000</size><md5>digest</md5>'
                        b'</file></files>')
            return (b'<metadata><licenseurl>https://creativecommons.org/publicdomain/zero/1.0/'
                    b'</licenseurl><rights>Public domain dedication</rights></metadata>')

        with patch.object(resolver, "get_bytes", side_effect=fake_get):
            result = resolver.resolve("example", 1, 0, True)
        self.assertEqual(result["method"], "files_xml")
        self.assertEqual(result["metadata"]["rights"], "Public domain dedication")
        self.assertEqual(result["files"][0]["original_status"], "strict_original")
        self.assertEqual(urls, ["https://archive.org/metadata/example",
                                "https://archive.org/download/example/example_files.xml",
                                "https://archive.org/download/example/example_meta.xml"])

    def test_files_xml_without_meta_xml_keeps_rights_unknown(self):
        def fake_get(url, timeout, retries):
            if "/metadata/" in url or url.endswith("_meta.xml"):
                raise RuntimeError("unavailable")
            return b'<files><file name="tune.wav" source="original"><format>WAVE</format></file></files>'

        with patch.object(resolver, "get_bytes", side_effect=fake_get):
            result = resolver.resolve("example", 1, 0, True)
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["metadata"]["licenseurl"])
        self.assertIn("licence/rights unknown", result["warning"])

    def test_resume_recovers_incomplete_final_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resolution.jsonl"
            path.write_bytes(b'{"identifier":"done","status":"ok"}\n{"identifier":"broken"')
            progress = resolver.read_progress(path)
            self.assertEqual(progress, {"done": "ok"})
            self.assertEqual(path.read_text(), '{"identifier":"done","status":"ok"}\n')

    def test_final_candidates_exclude_all_known_collection_flags(self):
        licence = {"license_types": ["BY"],
                   "license_urls": ["https://creativecommons.org/licenses/by/4.0/"]}
        rows = [{**licence, "identifier": "a", "collections": ["opensource_audio"]},
                {**licence, "identifier": "b", "collections": ["radio-aporee-maps"]},
                {**licence, "identifier": "c", "collections": ["hifidelity_potpourri"]},
                {**licence, "identifier": "d", "collections": ["opensource_audio", "podcasts_miscellaneous"]},
                {"identifier": "e", "collections": ["opensource_audio"], "license_types": ["BY"],
                 "license_urls": ["https://creativecommons.org/licenses/by-nc/4.0/"]}]
        final, reasons = audit.select_final_candidates(rows)
        self.assertEqual([row["identifier"] for row in final], ["a"])
        self.assertEqual(reasons["known_non_music_collection"], 2)
        self.assertEqual(reasons["known_doubtful_licence_collection"], 1)
        self.assertEqual(reasons["missing_or_conflicting_iamd_licence_url"], 1)

    def test_external_jsonl_import_generates_offline_report(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.prepare_offline_fixture(out, [self.candidate("example")])
            resolved = {"schema_version": 1, "identifier": "example", "status": "ok",
                        "method": "metadata_api", "metadata": {
                            "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                            "rights": "Credit Artist", "creator": "Artist", "collection": "opensource_audio"},
                        "files": [{"name": "song.flac", "source": "original", "format": "Flac",
                                   "size": "1000", "length": "100", "sha1": "digest",
                                   "download_url": "https://archive.org/download/example/song.flac"}]}
            path = out / "external_resolution.jsonl"
            path.write_text(json.dumps(resolved) + "\n")
            with patch.object(audit, "OUT", out), patch.object(
                    audit, "FINAL_CANDIDATES", out / "iamd_clean_candidate_identifiers.jsonl"):
                audit.import_resolution(path)
                audit.report()
            summary = json.loads((out / "summary.json").read_text())
            self.assertTrue(summary["audit_complete"])
            self.assertEqual(summary["files"]["strict_original"], 1)
            self.assertEqual(summary["identifiers"]["potentially_redistributable"], 1)
            self.assertEqual(summary["strict_hours"]["known_hours"], 100 / 3600)
            self.assertEqual(summary["funnel"]["technical_candidate"], 1)
            self.assertEqual(summary["funnel"]["provenance_candidate"], 1)
            self.assertEqual(summary["funnel"]["redistributable_candidate"], 1)

    def test_partial_final_line_timeouts_missing_license_and_ambiguous_original(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.prepare_offline_fixture(out, [self.candidate(key) for key in ("a", "b", "c", "d")])
            resolved_a = {"schema_version": 1, "identifier": "a", "status": "ok",
                          "metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                                       "creator": "Artist", "collection": "opensource_audio"},
                          "files": [{"name": "good.flac", "source": "original", "format": "Flac",
                                     "size": "1000", "length": "100", "md5": "digest"},
                                    {"name": "maybe.wav", "format": "WAVE", "size": "500"}]}
            resolved_b = {"schema_version": 1, "identifier": "b", "status": "ok",
                          "metadata": {"creator": "Artist", "collection": "opensource_audio"},
                          "files": [{"name": "maybe.wav", "format": "WAVE", "size": "500"},
                                    {"name": "hf_reencode.mp3", "source": "original",
                                     "format": "VBR MP3", "size": "1000"}]}
            timeout = {"schema_version": 1, "identifier": "c", "status": "error",
                       "error": "TimeoutError: metadata API unavailable"}
            path = out / "external_resolution.jsonl"
            path.write_bytes(("".join(json.dumps(row) + "\n" for row in
                                     (resolved_a, resolved_b, timeout)) +
                              '{"schema_version":1,"identifier":"d"').encode())
            with patch.object(audit, "OUT", out), patch.object(
                    audit, "FINAL_CANDIDATES", out / "iamd_clean_candidate_identifiers.jsonl"):
                audit.import_resolution(path)
                audit.report()
            summary = json.loads((out / "summary.json").read_text())
            funnel = summary["funnel"]
            self.assertEqual((funnel["metadata_resolved"], funnel["metadata_failed"],
                              funnel["metadata_not_attempted"]), (2, 1, 1))
            self.assertEqual((funnel["archive_licence_compatible"], funnel["archive_licence_unknown"],
                              funnel["archive_licence_contradictory"]), (1, 1, 0))
            self.assertEqual((funnel["has_wav_flac_aiff"], funnel["has_explicit_source_original"],
                              funnel["ambiguous_original_status"]), (2, 1, 2))
            self.assertEqual((funnel["technical_candidate"], funnel["provenance_candidate"],
                              funnel["redistributable_candidate"]), (1, 1, 1))
            self.assertEqual(summary["files"]["strict_original"], 1)
            self.assertTrue(summary["import"]["partial_tail_ignored"])
            self.assertEqual(summary["decision"]["verdict"], "NO-GO")
            self.assertTrue(summary["decision"]["provisional"])
            self.assertNotIn("hf_reencode.mp3", (out / "files.jsonl").read_text())

    def test_malformed_middle_line_keeps_previous_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.prepare_offline_fixture(out, [self.candidate("a"), self.candidate("b")])
            old = out / "old.jsonl"
            old.write_text(json.dumps({"schema_version": 1, "identifier": "a", "status": "error",
                                       "error": "timeout"}) + "\n")
            corrupt = out / "corrupt.jsonl"
            corrupt.write_text(json.dumps({"schema_version": 1, "identifier": "b", "status": "error"}) +
                               "\n{broken}\n")
            with patch.object(audit, "OUT", out), patch.object(
                    audit, "FINAL_CANDIDATES", out / "iamd_clean_candidate_identifiers.jsonl"):
                audit.import_resolution(old)
                with self.assertRaisesRegex(ValueError, "line 2"):
                    audit.import_resolution(corrupt)
                audit.report()
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["funnel"]["metadata_failed"], 1)
            self.assertEqual(summary["funnel"]["metadata_not_attempted"], 1)

    def test_retry_latest_record_wins_and_reimport_clears_stale_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.prepare_offline_fixture(out, [self.candidate("a"), self.candidate("b")])
            old = out / "old.jsonl"
            old.write_text(json.dumps({"schema_version": 1, "identifier": "b", "status": "error"}) + "\n")
            latest = out / "latest.jsonl"
            rows = [{"schema_version": 1, "identifier": "a", "status": "error"},
                    {"schema_version": 1, "identifier": "a", "status": "ok",
                     "metadata": {}, "files": []}]
            latest.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with patch.object(audit, "OUT", out), patch.object(
                    audit, "FINAL_CANDIDATES", out / "iamd_clean_candidate_identifiers.jsonl"):
                audit.import_resolution(old)
                audit.import_resolution(latest)
                audit.report()
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual((summary["funnel"]["metadata_resolved"],
                              summary["funnel"]["metadata_failed"],
                              summary["funnel"]["metadata_not_attempted"]), (1, 0, 1))

    def test_licence_contradiction_and_format_mismatch_do_not_become_technical(self):
        candidate = self.candidate("example")
        response = {"metadata": {"licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"},
                    "files": [{"name": "mislabelled.wav", "source": "original",
                               "format": "VBR MP3", "size": "1000"},
                              {"name": "lossy.mp3", "source": "original", "format": "VBR MP3"}]}
        item, files = audit.analyse_item(candidate, response, "ok")
        self.assertEqual(item["archive_licence_category"], "contradictory")
        self.assertTrue(item["has_explicit_original_file"])
        self.assertFalse(item["technical_candidate"])
        self.assertEqual([file["status"] for file in files], ["format_ambiguous"])

    def test_go_heuristic_does_not_apply_genre_quota(self):
        summary = {"funnel": {"metadata_not_attempted": 0, "technical_candidate": 3000,
                              "redistributable_candidate": 2500},
                   "metadata_coverage_fraction": 0.95,
                   "potential_hours": {"estimated_hours_including_imputation": 800},
                   "redistributable_collection_concentration": {"top_1_share": 0.4},
                   "redistributable_creator_concentration": {"top_1_share": 0.02,
                                                              "effective_groups": 300}}
        self.assertEqual(audit.assess_feasibility(summary)["verdict"], "GO")
        summary["redistributable_collection_concentration"]["top_1_share"] = 0.9
        self.assertEqual(audit.assess_feasibility(summary)["verdict"], "NO-GO")

    def test_cc0_by_formats_hours_and_concentration_are_reported_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            candidates = [self.candidate("a", "CC0"), self.candidate("b", "BY")]
            candidates[0]["creators"] = candidates[0]["artists"] = ["Alpha"]
            candidates[1]["creators"] = candidates[1]["artists"] = ["Beta"]
            self.prepare_offline_fixture(out, candidates)
            records = [
                {"schema_version": 1, "identifier": "a", "status": "ok",
                 "metadata": {"licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
                              "creator": "Alpha", "collection": "collection_a"},
                 "files": [{"name": "one.wav", "source": "original", "format": "WAVE",
                            "size": "1000", "length": "100", "sha1": "digest"}]},
                {"schema_version": 1, "identifier": "b", "status": "ok",
                 "metadata": {"licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                              "creator": "Beta", "collection": "collection_b"},
                 "files": [{"name": "two.flac", "source": "original", "format": "Flac",
                            "size": "2000", "length": "200", "md5": "digest"},
                           {"name": "three.aiff", "source": "original", "format": "AIFF",
                            "size": "3000", "sha1": "digest"}]},
            ]
            path = out / "resolution.jsonl"
            path.write_text("".join(json.dumps(record) + "\n" for record in records))
            with patch.object(audit, "OUT", out), patch.object(
                    audit, "FINAL_CANDIDATES", out / "iamd_clean_candidate_identifiers.jsonl"):
                audit.import_resolution(path)
                audit.report()
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["potential_formats"], {"WAV": 1, "FLAC": 1, "AIFF": 1})
            self.assertEqual(summary["redistributable_license_types"], {"CC0": 1, "CC BY": 1})
            self.assertEqual(summary["potential_size_bytes"], 6000)
            self.assertEqual(summary["potential_hours"]["files_missing_length"], 1)
            self.assertEqual(summary["potential_hours"]["files_unestimated"], 1)
            self.assertEqual(summary["redistributable_creator_concentration"]["top_1_share"], 0.5)
            self.assertEqual(summary["redistributable_collection_concentration"]["effective_groups"], 2)
            self.assertEqual(summary["decision"]["verdict"], "NO-GO")


if __name__ == "__main__":
    unittest.main()
