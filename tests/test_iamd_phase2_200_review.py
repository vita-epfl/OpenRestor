"""Offline guards for contrastive 200-source triage and review rules."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.iamd_phase2_200_review import (AST_MODEL_REVISION, classify, evaluate, parse_validation,
                                             selected_excerpt)
from scripts.iamd_phase2_clap_probe import MODEL_REVISION, PROMPT_VERSION, PROMPTS, group_scores


def measured_score(*, pq=7.5, ce=6.5, cu=7.0, pc=5.0, bandwidth=18000, clipping=0):
    return {"status": "measured", "format_matches": True, "sample_rate": 44100,
            "duration_s": 180, "audiobox_axes": {"CE": ce, "CU": cu, "PC": pc, "PQ": pq},
            "excerpts": [{"clip_path": f"clip-{i}.flac",
                          "audiobox_axes": {"CE": ce, "CU": cu, "PC": pc, "PQ": pq},
                          "bandwidth_hz": bandwidth, "clipped_sample_ratio_channels": clipping,
                          "rms_dbfs": -16, "near_silent_sample_ratio": .01} for i in range(3)]}


def classify_fixture(score=None, *, top="produced_music", music=.85, speech=.01, margin=.1,
                     cues=None, license_category="unknown"):
    groups = {name: .1 for name in PROMPTS}
    groups[top] = .4
    row = {"identifier": "test", "pilot_batch": "expand_200", "sample_id": "abcdefgh",
           "archive_licence_category": license_category, "provenance_candidate": False,
           "archive_license_url": None}
    score = score or measured_score()
    middle = score["excerpts"][len(score["excerpts"]) // 2]["clip_path"]
    ast = {"status": "scored", "clip_path": middle, "model_revision": AST_MODEL_REVISION,
           "interest_labels": {"Music": music, "Speech": speech}}
    clap = {"status": "scored", "clip_path": middle, "model_revision": MODEL_REVISION,
            "prompt_version": PROMPT_VERSION,
            "group_scores": groups, "top_group": top, "top_margin": margin}
    return classify(row, score, ast, clap, {"metadata_cues": cues or {}})


class Phase2200ReviewTests(unittest.TestCase):
    def test_prompt_groups_equal_and_relative_not_probabilities(self):
        self.assertEqual({len(group) for group in PROMPTS.values()}, {4})
        scores = group_scores(list(range(20)))
        self.assertEqual(list(scores), list(PROMPTS))
        self.assertEqual(scores["produced_music"], 1.5)
        with self.assertRaises(ValueError):
            group_scores([.1])

    def test_electronic_music_can_be_accepted_but_rights_stay_separate(self):
        result = classify_fixture(top="legitimate_electronic_music")
        self.assertEqual(result["classification"], "accept_candidate")
        self.assertEqual(result["rights_status"], "archive_licence_unknown")

    def test_high_pq_capture_context_stays_in_review(self):
        result = classify_fixture(score=measured_score(pq=8.2),
                                  cues={"capture_context_cues": ["live performance"]})
        self.assertEqual(result["classification"], "review")
        self.assertIn("metadata_content_or_capture_review", result["reasons"])

    def test_low_pq_alone_never_rejects_good_music(self):
        result = classify_fixture(score=measured_score(pq=5.4))
        self.assertEqual(result["classification"], "review")

    def test_low_ast_music_alone_never_rejects_song(self):
        result = classify_fixture(music=.04, top="degraded_music")
        self.assertEqual(result["classification"], "review")

    def test_nonmusic_rejection_needs_cross_signal(self):
        signal = {"sound_effect_cues": ["field recordings"]}
        strong = classify_fixture(top="non_music", music=.2, speech=.7, cues=signal)
        self.assertEqual(strong["classification"], "reject_candidate")
        weak = classify_fixture(top="non_music", music=.8, speech=.01, cues=signal)
        self.assertEqual(weak["classification"], "review")

    def test_missing_model_score_is_review_not_rejection(self):
        result = classify_fixture(music=None)
        self.assertEqual(result["classification"], "review")
        self.assertIn("incomplete_measurements_or_model_scores", result["reasons"])

    def test_primary_excerpt_is_temporal_middle_matching_model_window(self):
        score = measured_score()
        for part, pq in zip(score["excerpts"], (4, 7, 9)):
            part["audiobox_axes"]["PQ"] = pq
        self.assertEqual(selected_excerpt(score)["clip_path"], "clip-1.flac")
        score["excerpts"][0]["audiobox_axes"]["PQ"] = 7
        score["excerpts"][1]["audiobox_axes"]["PQ"] = 4
        self.assertEqual(selected_excerpt(score)["clip_path"], "clip-1.flac")

    def test_blind_review_cannot_call_one_good_clip_a_good_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            fields = ("identifier", "content_type", "audio_quality", "source_nature",
                      "pool_suitability",
                      "scope", "source_level_label", "notes")
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"identifier": "new", "content_type": "music",
                                 "audio_quality": "acceptable", "source_nature": "likely_real_recording",
                                 "pool_suitability": "suitable",
                                 "scope": "primary_clip_only", "source_level_label": "promising",
                                 "notes": "nice excerpt"})
            with patch("scripts.iamd_phase2_200_review.pilot_200_rows",
                       return_value=[{"identifier": "new", "pilot_batch": "expand_200"}]):
                with self.assertRaisesRegex(ValueError, "one clip"):
                    parse_validation(Path(tmp), path)

    def test_validation_metrics_use_only_new_sources_and_keep_clip_scope(self):
        predictions = [
            {"identifier": "old", "pilot_batch": "smoke_50", "classification": "reject_candidate"},
            {"identifier": "good", "pilot_batch": "expand_200", "classification": "reject_candidate",
             "genre_proxy": "pop", "collection": "A", "rights_status": "archive_licence_unknown"},
            {"identifier": "bad", "pilot_batch": "expand_200", "classification": "accept_candidate",
             "genre_proxy": "rock_metal", "collection": "B", "rights_status": "provenance_unvalidated"},
        ]
        reviews = [
            {"identifier": "good", "content_type": "music", "audio_quality": "acceptable",
             "source_nature": "likely_real_recording", "pool_suitability": "suitable",
             "scope": "primary_clip_only", "source_level_label": ""},
            {"identifier": "bad", "content_type": "music", "audio_quality": "degraded",
             "source_nature": "likely_real_recording", "pool_suitability": "suitable",
             "scope": "primary_clip_only", "source_level_label": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp, patch(
                "scripts.iamd_phase2_200_review.parse_validation", return_value=reviews):
            result = evaluate(Path(tmp), predictions, Path(tmp) / "review.csv")
        self.assertEqual(result["validation_reviewed"], 2)
        self.assertFalse(result["validation_complete"])
        self.assertEqual(result["potential_false_rejects_good_clip"], ["good"])
        self.assertEqual(result["degraded_clips_auto_accepted"], ["bad"])
        self.assertEqual(result["source_level_promising_checked_multiple"], 0)


if __name__ == "__main__":
    unittest.main()
