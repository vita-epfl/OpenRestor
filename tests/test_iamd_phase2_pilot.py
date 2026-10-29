"""Offline sampling, three-axis review and safety tests for IAMD Phase 2."""

import csv
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.iamd_phase2_pilot import (download_one_original, enrich_metadata, enrichment_rows,
                                       format_matches, genre_proxy, make_plan, measure_local,
                                       metadata_cues, parse_reviews, pilot_200_rows, population, report,
                                       score_aesthetics_excerpts_smoke,
                                       score_pq_smoke, smoke_rows, windows, write_jsonl)
from scripts.iamd_phase2_smoke_review import build as build_smoke_review, metrics, suggestions
from scripts.iamd_phase2_content_probe import planned_windows


def jsonl(path, values):
    path.write_text("".join(json.dumps(row) + "\n" for row in values), encoding="utf-8")


class Phase2PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.phase1 = self.root / "phase1"
        self.phase1.mkdir()
        self.out = self.root / "phase2"

    def fixtures(self, n=600):
        items, files = [], []
        for index in range(n):
            identifier = f"item-{index:04d}"
            collection = ("rock-label", "jazz-label", "electronic-label")[index % 3]
            creator = f"Artist-{index // 2}"
            items.append({"identifier": identifier, "technical_candidate": True,
                          "provenance_candidate": index % 7 != 0,
                          "redistributable_candidate": index % 7 != 0,
                          "collection": collection, "creator": creator, "title": identifier,
                          "genre": "[unknown]", "genre_source": "unknown",
                          "tags": [collection.split("-")[0]], "archive_license_url": "CC BY",
                          "archive_licence_category": "compatible"})
            files.append({"identifier": identifier, "name": f"song-{index}.flac", "format": "FLAC",
                          "status": "strict_original", "source": "original", "private": False,
                          "size_bytes": 1000 + index, "length_s": 180, "sha1": "abc", "md5": None})
        jsonl(self.phase1 / "items.jsonl", items)
        jsonl(self.phase1 / "files.jsonl", files)
        (self.phase1 / "summary.json").write_text(json.dumps({"funnel": {"technical_candidate": n}}))

    def test_population_only_strict_originals_with_integrity(self):
        self.fixtures(1)
        with (self.phase1 / "files.jsonl").open("a") as stream:
            for name, fmt, source, status in [("bad.mp3", "MP3", "original", "strict_original"),
                                              ("derived.flac", "FLAC", "derivative", "derivative_or_other"),
                                              ("unknown.flac", "FLAC", None, "source_ambiguous"),
                                              ("../escape.wav", "WAV", "original", "strict_original")]:
                stream.write(json.dumps({"identifier": "item-0000", "name": name, "format": fmt,
                                         "source": source, "status": status, "private": False,
                                         "size_bytes": 1000, "sha1": "abc"}) + "\n")
        rows = population(self.phase1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "song-0.flac")

    def test_electronic_not_midi_and_metadata_cues_are_only_hints(self):
        item = {"genre": "[unknown]", "tags": ["electronic; dance"], "title": "Electronic live session",
                "collection": "netlabel", "creator": "Someone"}
        self.assertEqual(genre_proxy(item)[0], "electronic_dance")
        self.assertFalse(metadata_cues(item, {"name": "song.flac"})["synthetic_render_cues"])
        item["description"] = "Made with a MIDI soundfont"
        self.assertIn("midi", metadata_cues(item, {"name": "song.flac"})["synthetic_render_cues"])
        item["description"] = "One hour of field recordings made with an internal microphone"
        cues = metadata_cues(item, {"name": "song.flac"})
        self.assertIn("field recordings", cues["sound_effect_cues"])
        self.assertIn("internal microphone", cues["capture_context_cues"])
        item["description"] = "Live set with stage banter"
        self.assertIn("stage banter", metadata_cues(item, {"name": "song.flac"})["capture_context_cues"])
        item["description"] = "Official original game soundtrack; polished electronic music"
        cues = metadata_cues(item, {"name": "song.flac"})
        self.assertIn("game soundtrack", cues["stylized_content_cues"])
        self.assertFalse(cues["synthetic_render_cues"])

    def test_plan_is_identifier_level_stratified_and_no_audio(self):
        self.fixtures()
        plan = make_plan(self.phase1, self.out, count=500, seed=9)
        rows = list(map(json.loads, (self.out / "selection.jsonl").read_text().splitlines()))
        self.assertEqual(plan["selected_identifiers"], 500)
        self.assertEqual(len({row["identifier"] for row in rows}), 500)
        self.assertEqual(plan["planned_batches"], {"smoke_50": 50, "expand_200": 150, "full_pilot": 300})
        self.assertEqual({row["format"] for row in rows}, {"FLAC"})
        self.assertEqual({row["genre_proxy"] for row in rows if row["pilot_batch"] == "smoke_50"},
                         {row["genre_proxy"] for row in rows})
        self.assertTrue(all(0 < row["selection_probability"] <= 1 for row in rows))
        self.assertEqual({row["source_nature"] for row in rows}, {None})
        self.assertFalse((self.out / "originals").exists())
        with self.assertRaises(FileExistsError):
            make_plan(self.phase1, self.out, count=500, seed=9)

    def test_pilot_200_filters_batches_not_first_200_sorted_lines(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500, seed=9)
        rows = pilot_200_rows(self.out)
        self.assertEqual(len(rows), 200)
        self.assertEqual(sum(row["pilot_batch"] == "smoke_50" for row in rows), 50)
        self.assertEqual(sum(row["pilot_batch"] == "expand_200" for row in rows), 150)
        self.assertFalse(any(row["pilot_batch"] == "full_pilot" for row in rows))

    def test_review_import_keeps_axes_independent_and_report_waits_for_pq(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        rows = list(map(json.loads, (self.out / "selection.jsonl").read_text().splitlines()))
        review_path = self.root / "reviews.csv"
        with review_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("identifier", "content_type", "audio_quality",
                                                        "source_nature", "quality_flags", "proposed_reasons",
                                                        "other_quality_issue",
                                                        "reviewer", "review_date", "notes"))
            writer.writeheader()
            for index, row in enumerate(rows):
                writer.writerow({"identifier": row["identifier"],
                                 "content_type": "noise_or_sound_effect" if index == 0 else "music",
                                 "audio_quality": "degraded" if index == 1 else "acceptable",
                                 "source_nature": "likely_midi_or_synthetic_render" if index == 2 else "likely_real_recording",
                                 "quality_flags": "excessive_clipping" if index == 1 else ""})
        self.assertEqual(len(parse_reviews(self.out, review_path)), 500)
        pending = report(self.out, review_path)
        self.assertEqual(pending["verdict"], "pending_complete_review_and_pq")
        self.assertIsNone(pending["weighted_definite_audio_yield"])
        self.assertEqual(pending["rejection_reasons_counts_nonexclusive"]["content:noise_or_sound_effect"], 1)
        self.assertEqual(pending["rejection_reasons_counts_nonexclusive"]["audio_quality:excessive_clipping"], 1)
        jsonl(self.out / "scores.jsonl", [{"identifier": row["identifier"], "status": "measured",
                                             "format_matches": index != 3, "audiobox_pq": 6.0}
                                            for index, row in enumerate(rows)])
        complete = report(self.out, review_path)
        self.assertEqual(complete["verdict"], "audio_yield_estimated_rights_pending")
        self.assertEqual(complete["audiobox_pq"]["median"], 6.0)
        self.assertEqual(complete["rejection_reasons_counts_nonexclusive"]["source_file:format_mismatch"], 1)
        self.assertLess(complete["weighted_definite_audio_yield"]["sample_count"], 500)
        self.assertFalse(complete["redistribution_approved"])

    def test_invalid_review_and_partial_metadata_tail(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        path = self.out / "metadata_enrichment.jsonl"
        path.write_bytes(b'{"identifier":"item-0001","status":"ok"}\n{"identifier":')
        self.assertEqual(enrichment_rows(self.out)["item-0001"]["status"], "ok")
        review_path = self.root / "reviews.csv"
        review_path.write_text("identifier,content_type,audio_quality,source_nature,quality_flags,other_quality_issue,reviewer,review_date,notes\n"
                               "item-0001,music,acceptable,electronic,,,test,,\n")
        with self.assertRaises(ValueError):
            parse_reviews(self.out, review_path)

    def test_metadata_enrichment_is_bounded_and_resumable(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        requests = []
        def fake_open(request, timeout):
            requests.append(request.full_url)
            return io.BytesIO(json.dumps({"metadata": {"description": "Recorded live with microphones",
                                                        "subject": ["rock", "concert"]}}).encode())
        with patch("scripts.iamd_phase2_pilot.urllib.request.urlopen", side_effect=fake_open):
            first = enrich_metadata(self.out, max_items=1)
            second = enrich_metadata(self.out, max_items=1)
        self.assertEqual(first["attempted_this_run"], 1)
        self.assertEqual(second["resolved"], 2)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all("/metadata/" in url and "/download/" not in url for url in requests))
        self.assertEqual(len(enrichment_rows(self.out)), 2)

    def test_metadata_timeout_is_recorded_then_retried(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        with patch("scripts.iamd_phase2_pilot.urllib.request.urlopen", side_effect=TimeoutError("slow")):
            failed = enrich_metadata(self.out, max_items=1)
        self.assertEqual(failed["errors"], 1)
        with patch("scripts.iamd_phase2_pilot.urllib.request.urlopen",
                   return_value=io.BytesIO(b'{"metadata":{"description":"session"}}')):
            retried = enrich_metadata(self.out, max_items=1)
        self.assertEqual(retried["resolved"], 1)
        self.assertEqual(retried["errors"], 0)

    def test_concurrent_metadata_results_are_complete_jsonl(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        with patch("scripts.iamd_phase2_pilot.urllib.request.urlopen",
                   side_effect=lambda request, timeout: io.BytesIO(b'{"metadata":{"description":"music"}}')):
            result = enrich_metadata(self.out, max_items=4, rate=5, workers=3)
        self.assertEqual(result["resolved"], 4)
        self.assertEqual(len(enrichment_rows(self.out)), 4)

    def test_windows_bounded(self):
        self.assertEqual(len(windows(180)), 3)
        self.assertEqual(len(windows(30)), 1)
        self.assertEqual(len(windows(7)), 1)

    def test_incremental_jsonl_write_preserves_prior_file_on_error(self):
        destination = self.root / "progress.jsonl"
        write_jsonl(destination, [{"ok": 1}])
        with self.assertRaises(TypeError):
            write_jsonl(destination, [{"bad": object()}])
        self.assertEqual(list(map(json.loads, destination.read_text().splitlines())), [{"ok": 1}])

    def test_smoke_download_is_limited_and_verified_file_is_reused(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        selected = smoke_rows(self.out)
        self.assertEqual(len(selected), 50)
        self.assertEqual({row["pilot_batch"] for row in selected}, {"smoke_50"})
        row = selected[0]
        original = Path(row["local_original_path"])
        original.parent.mkdir(parents=True)
        original.write_bytes(b"test original")
        row["size_bytes_metadata"] = original.stat().st_size
        row["sha1"] = hashlib.sha1(original.read_bytes()).hexdigest()
        with patch("scripts.iamd_phase2_pilot.subprocess.run", side_effect=AssertionError("network called")):
            result = download_one_original(row)
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["reused"])
        selected[1]["source"] = "derivative"
        jsonl(self.out / "selection.jsonl", selected)
        with self.assertRaises(ValueError):
            smoke_rows(self.out)

    def test_wavex_is_wav_and_smoke_report_keeps_unreviewed_sources(self):
        self.assertTrue(format_matches("WAV", "WAVEX"))
        self.assertFalse(format_matches("FLAC", "WAVEX"))
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        identifier = smoke_rows(self.out)[0]["identifier"]
        jsonl(self.out / "ast_content_probe.jsonl", [{"identifier": identifier, "status": "scored",
                                                       "interest_labels": {"Music": .8, "Speech": .1},
                                                       "top_labels": [{"label": "Music", "score": .8}]}])
        summary = build_smoke_review(self.out)
        self.assertEqual(summary["selected"], 50)
        self.assertEqual(summary["sources_with_ast_content_probe"], 1)
        self.assertIsNone(summary["observed_audio_clean_yield"])
        self.assertEqual(len((self.out / "listening.csv").read_text().splitlines()), 51)
        self.assertIn('data-field="proposed_reasons"', (self.out / "listening.html").read_text())
        self.assertIn("AST Music 0.80", (self.out / "listening.html").read_text())
        self.assertFalse((self.out / "originals").exists())

    def test_quality_and_metadata_suggestions_are_not_automatic_rejections(self):
        row = {"archive_licence_category": "compatible", "provenance_candidate": True}
        queue = {"metadata_cues": {"synthetic_render_cues": ["midi"], "speech_cues": [],
                                   "sound_effect_cues": []}}
        score = {"status": "measured", "sample_rate": 44100, "format_matches": True,
                 "audiobox_pq": 4.0, "excerpts": [{"bandwidth_hz": 9000,
                 "near_silent_sample_ratio": .9, "rms_dbfs": -45,
                 "clipped_sample_ratio_channels": 0.0}]}
        reasons = suggestions(row, queue, score, None)
        self.assertIn("metadata_midi_sequence_cue_review", reasons)
        self.assertIn("bandwidth_cutoff_review", reasons)
        self.assertIn("quasi_silence_review", reasons)
        self.assertNotIn("pq_bottom_quintile_review", reasons)

    def test_audiobox_excerpt_range_preserves_worst_passage(self):
        measured = metrics({"excerpts": [{"audiobox_axes": {"PQ": 7.9}},
                                         {"audiobox_axes": {"PQ": 7.1}},
                                         {"audiobox_axes": {"PQ": 5.2}}]})
        self.assertEqual(measured["audiobox_pq_excerpt_min"], 5.2)
        self.assertEqual(measured["audiobox_pq_excerpt_median"], 7.1)
        self.assertEqual(measured["audiobox_pq_excerpt_max"], 7.9)

    def test_smoke_yield_waits_for_all_fifty_human_reviews(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        selected = smoke_rows(self.out)
        jsonl(self.out / "scores.jsonl", [{"identifier": row["identifier"], "status": "measured",
                                            "format_matches": True, "excerpts": []}
                                           for row in selected])
        reviews_csv = self.root / "smoke_reviews.csv"
        with reviews_csv.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("identifier", "content_type", "audio_quality",
                                                        "source_nature", "quality_flags", "proposed_reasons",
                                                        "other_quality_issue", "reviewer", "review_date", "notes"))
            writer.writeheader()
            for index, row in enumerate(selected):
                writer.writerow({"identifier": row["identifier"],
                                 "content_type": "speech_dominant" if index == 0 else "music",
                                 "audio_quality": "acceptable", "source_nature": "likely_real_recording",
                                 "proposed_reasons": "spoken_content" if index == 0 else ""})
        pending = build_smoke_review(self.out, reviews_csv)
        self.assertEqual(pending["human_reviews_complete"], 50)
        self.assertIsNone(pending["observed_audio_clean_yield"])
        jsonl(self.out / "download_status.jsonl", [{"identifier": row["identifier"], "status": "verified"}
                                                  for row in selected])
        jsonl(self.out / "scores.jsonl", [{"identifier": row["identifier"], "status": "measured",
                                            "format_matches": True, "audiobox_status": "measured",
                                            "audiobox_pq": 5 + index / 100, "excerpts": []}
                                           for index, row in enumerate(selected)])
        summary = build_smoke_review(self.out, reviews_csv)
        self.assertEqual(summary["observed_audio_clean_yield"], 49 / 50)
        self.assertEqual(summary["human_rejection_or_ambiguity_reasons_nonexclusive"],
                         {"content_type:speech_dominant": 1})
        self.assertEqual(summary["human_edited_review_reasons_nonexclusive"], {"spoken_content": 1})
        self.assertEqual(len(list(map(json.loads, (self.out / "smoke_measurements.jsonl").read_text().splitlines()))),
                         50)

    def test_audiobox_saves_all_four_axes_and_resumes_without_reloading_model(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        selected = smoke_rows(self.out)
        (self.out / "clips").mkdir()
        score_rows = []
        for index, row in enumerate(selected):
            excerpts = []
            for part_index in range(1, 4 if index == 0 else 2):
                clip = self.out / "clips" / f'{row["sample_id"]}-p{part_index}.flac'
                clip.touch()
                excerpts.append({"clip_path": str(clip), "duration_s": 24.0})
            score_rows.append({"identifier": row["identifier"], "status": "measured", "excerpts": excerpts})
        jsonl(self.out / "scores.jsonl", score_rows)
        calls = []
        module = types.ModuleType("audiobox_aesthetics.infer")
        def initialize_predictor():
            calls.append("initialize")
            class Predictor:
                def forward(self, batch):
                    calls.append(batch)
                    return [{"CE": 5.0, "CU": 6.0, "PC": 4.0, "PQ": 7.0} for _ in batch]
            return Predictor()
        module.initialize_predictor = initialize_predictor
        package = types.ModuleType("audiobox_aesthetics")
        package.__path__ = []
        with patch.dict(sys.modules, {"audiobox_aesthetics": package, "audiobox_aesthetics.infer": module}):
            first = score_pq_smoke(self.out)
            second = score_pq_smoke(self.out)
            excerpts = score_aesthetics_excerpts_smoke(self.out)
            resumed_excerpts = score_aesthetics_excerpts_smoke(self.out)
        self.assertEqual(first["complete_all_axes"], 50)
        self.assertEqual(second["complete_all_axes"], 50)
        self.assertEqual(excerpts["complete_all_axes"], 52)
        self.assertEqual(excerpts["reused_middle_scores"], 50)
        self.assertEqual(resumed_excerpts["attempted_this_run"], 0)
        self.assertEqual(calls.count("initialize"), 2)
        self.assertEqual(len([call for call in calls if isinstance(call, list)]), 14)
        row = next(map(json.loads, (self.out / "scores.jsonl").read_text().splitlines()))
        self.assertEqual(row["audiobox_axes"], {"CE": 5.0, "CU": 6.0, "PC": 4.0, "PQ": 7.0})
        self.assertEqual(row["audiobox_pq_window_in_clip_s"], [7, 17])

    def test_content_probe_is_restricted_to_existing_smoke_clips(self):
        self.fixtures()
        make_plan(self.phase1, self.out, count=500)
        selected = smoke_rows(self.out)
        (self.out / "clips").mkdir()
        scores = []
        for row in selected:
            clip = self.out / "clips" / f'{row["sample_id"]}-p1.flac'
            clip.touch()
            scores.append({"identifier": row["identifier"], "status": "measured",
                           "excerpts": [{"clip_path": str(clip), "duration_s": 24.0}],
                           "audiobox_pq_window_in_clip_s": [7, 17]})
        jsonl(self.out / "scores.jsonl", scores)
        self.assertEqual(len(planned_windows(self.out)), 50)
        scores[0]["excerpts"][0]["clip_path"] = str(self.root / "not-in-smoke.flac")
        (self.root / "not-in-smoke.flac").touch()
        jsonl(self.out / "scores.jsonl", scores)
        with self.assertRaises(ValueError):
            planned_windows(self.out)

    def test_measure_local_only_reads_present_verified_original(self):
        try:
            import numpy as np
            import soundfile as sf
        except ImportError:
            self.skipTest("local audio dependencies unavailable")
        self.out.mkdir()
        original = self.out / "originals" / "sample" / "test.wav"
        original.parent.mkdir(parents=True)
        wave = 0.1 * np.sin(2 * np.pi * 440 * np.arange(8000) / 8000)
        sf.write(original, wave, 8000)
        row = {"identifier": "item-0001", "sample_id": "sample", "name": "test.wav",
               "local_original_path": str(original), "format": "WAV",
               "size_bytes_metadata": original.stat().st_size,
               "sha1": hashlib.sha1(original.read_bytes()).hexdigest(), "md5": None}
        jsonl(self.out / "selection.jsonl", [row])
        result = measure_local(self.out)
        self.assertEqual(result["measured"], 1)
        score = next(map(json.loads, (self.out / "scores.jsonl").read_text().splitlines()))
        self.assertEqual(score["detected_format"], "WAV")
        self.assertIsNone(score["audiobox_pq"])
        self.assertEqual(len(score["excerpts"]), 1)
        self.assertTrue(Path(score["excerpts"][0]["clip_path"]).exists())


if __name__ == "__main__":
    unittest.main()
