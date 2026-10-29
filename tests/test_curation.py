"""Curation safeguards: local audio, grouped passages, sparse labels and rights isolation."""

import tempfile
import unittest
import csv
import json
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import soundfile as sf

from openrestor.curation.evaluation import fixed_split, human_class, import_reviews, wilson
from openrestor.curation.features import acoustic_features, extract_local_source, read_jsonl, write_jsonl_atomic
from openrestor.curation.cli import (command_apply_adjudication, command_export,
                                     command_evaluate_independent, command_export_judgments,
                                     command_extract,
                                     command_freeze_predictions, command_listen,
                                     command_prepare_blind_listen,
                                     command_prepare_independent_validation)
from openrestor.curation.models import PROMPTS as CURATION_PROMPTS
from openrestor.curation.metadata import asset_creator, asset_role, metadata_cues
from openrestor.curation.policy import score_source, score_source_v2, score_source_v21
from scripts.iamd_phase2_clap_probe import PROMPTS as PILOT_PROMPTS


def segment(index, *, music=.85, speech=.01, nonmusic=.10, models=True):
    return {"segment_id": f"test:s#p{index}", "acoustic": {
        "near_silent_sample_ratio": .01, "rms_dbfs": -15,
        "clipped_sample_ratio_channels": 0, "bandwidth_hz": 18000},
        "aesthetics": {"PQ": 8, "PC": 6, "CE": 7, "CU": 8} if models else None,
        "ast": {"interest_labels": {"Music": music, "Speech": speech}} if models else None,
        "clap": {"group_scores": {"produced_music": .45,
                                  "legitimate_electronic_music": .43,
                                  "degraded_music": .2,
                                  "non_music": nonmusic,
                                  "rudimentary_synthetic": .15}} if models else None}


def record(segments):
    return {"dataset": "test", "source_id": "s", "source_key": "test:s",
            "sample_rate": 48000, "metadata": {}, "rights": {"status": "unreviewed"},
            "segments": segments}


class CurationTests(unittest.TestCase):
    def test_asset_creator_does_not_confuse_record_authors_with_performers(self):
        self.assertEqual(asset_creator("guitar_techs", "P2_chords.zip", "P2_chords/audio/a.wav"),
                         "Guitar-TECHS P2")
        self.assertIsNone(asset_creator("guitarset", "audio.zip", "track.wav"))

    def test_archive_asset_role_separates_masters_and_stems(self):
        self.assertEqual(asset_role("albumdb", "masters_stereo.zip", "01.wav"),
                         "full_mix_stereo_master")
        self.assertEqual(asset_role("albumdb", "masters_7.1.4.zip", "01.wav"),
                         "full_mix_immersive_master")
        self.assertEqual(asset_role("albumdb", "stems_raw.zip", "01/bass.wav"),
                         "isolated_stem_raw")

    def test_generic_extractor_reads_local_lossless_three_passages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "source.flac"
            t = np.arange(9 * 8000) / 8000
            sf.write(audio, np.sin(2 * np.pi * 440 * t).astype("float32"), 8000)
            result = extract_local_source({"dataset": "other", "source_id": "a",
                                           "audio_path": str(audio), "rights": {"status": "pending"}},
                                          root / "clips", seconds=2)
            self.assertEqual(result["source_key"], "other:a")
            self.assertEqual(len(result["segments"]), 3)
            self.assertTrue(all(Path(item["clip_path"]).is_file() for item in result["segments"]))
            self.assertEqual(result["rights"]["status"], "pending")
            self.assertEqual(score_source(result)["decision"], "manual_review")

    def test_generic_extractor_preserves_manifest_checksum_and_candidate_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source.wav"
            sf.write(path, np.zeros((44100, 1), dtype="float32"), 44100)
            row = {"dataset": "pilot", "source_id": "one", "audio_path": str(path),
                   "source_sha256": "known", "lossless_status": "lossless_container_unverified",
                   "technical_candidate": True, "provenance_candidate": True,
                   "redistributable_candidate": False, "rights": {"status": "pending"}}
            extracted = extract_local_source(row, root / "clips")
            self.assertEqual(extracted["source_sha256"], "known")
            self.assertEqual(extracted["lossless_status"], "lossless_container_unverified")
            self.assertTrue(extracted["technical_candidate"])
            self.assertFalse(extracted["redistributable_candidate"])

    def test_extractor_preserves_curation_annotations_on_fresh_and_cached_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "source.wav"
            sf.write(audio, np.sin(2 * np.pi * 440 * np.arange(16000) / 8000).astype("float32"), 8000)
            manifest = root / "manifest.jsonl"
            output = root / "features.jsonl"
            row = {"dataset": "pilot", "source_id": "annotated", "audio_path": str(audio),
                   "metadata": {"title": "Example"}, "rights": {"status": "pending"},
                   "source_sha256": "old-checksum", "provenance_candidate": True,
                   "source_decision": "manual_review", "pipeline_decision": "manual_review",
                   "pipeline_reasons": ["annotation_pending"], "clean_score": 0.42,
                   "annotations": [{"content_type": "music"}],
                   "annotation_history": [{"version": 1, "decision": "manual_review"}],
                   "features": {"human": {"capture_quality": "acceptable"}}}
            write_jsonl_atomic(manifest, [row])
            args = SimpleNamespace(manifest=manifest, out=output, clips_dir=root / "clips",
                                   segment_seconds=2)
            command_extract(args)
            first = list(read_jsonl(output))[0]
            self.assertEqual(first["source_decision"], "manual_review")
            self.assertEqual(first["annotation_history"][0]["version"], 1)
            self.assertEqual(first["features"]["human"]["capture_quality"], "acceptable")

            row["source_decision"] = "auto_reject"
            row["annotation_history"].append({"version": 2, "decision": "auto_reject"})
            row["pipeline_reasons"] = ["clipping"]
            write_jsonl_atomic(manifest, [row])
            command_extract(args)
            cached = list(read_jsonl(output))[0]
            self.assertEqual(cached["source_decision"], "auto_reject")
            self.assertEqual(len(cached["annotation_history"]), 2)
            self.assertEqual(cached["pipeline_reasons"], ["clipping"])
            self.assertEqual(len(cached["segments"]), len(first["segments"]))

            del row["source_sha256"]
            del row["provenance_candidate"]
            del row["annotations"]
            del row["source_decision"]
            write_jsonl_atomic(manifest, [row])
            command_extract(args)
            refreshed = list(read_jsonl(output))[0]
            for field in ("source_sha256", "provenance_candidate", "annotations", "source_decision"):
                self.assertNotIn(field, refreshed)
            self.assertEqual(len(refreshed["annotation_history"]), 2)

    def test_generic_extractor_uses_wav_for_more_than_eight_channels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "surround.wav"
            samples = np.zeros((8000, 12), dtype="float32")
            samples[:, 0] = np.sin(2 * np.pi * 440 * np.arange(8000) / 8000)
            sf.write(source, samples, 8000, format="WAV", subtype="PCM_16")
            result = extract_local_source({"dataset": "other", "source_id": "surround",
                                           "audio_path": str(source)},
                                          root / "clips", seconds=2)
            segment = result["segments"][0]
            self.assertEqual(result["channels"], 12)
            self.assertEqual(segment["clip_format"], "WAV")
            self.assertTrue(segment["clip_path"].endswith(".wav"))
            self.assertEqual(sf.info(segment["clip_path"]).channels, 12)

    def test_multichannel_acoustics_do_not_look_silent_after_energy_preserving_downmix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "surround_music.wav"
            t = np.arange(8000) / 8000
            samples = np.zeros((8000, 12), dtype="float32")
            samples[:, :4] = np.sin(2 * np.pi * 440 * t)[:, None]
            sf.write(source, samples, 8000, format="WAV", subtype="PCM_16")
            result = extract_local_source({"dataset": "other", "source_id": "surround-music",
                                           "audio_path": str(source)},
                                          root / "clips", seconds=2)
            self.assertGreater(result["segments"][0]["acoustic"]["rms_dbfs"], -20)

    def test_electronic_friendly_acceptance_needs_all_passages(self):
        result = score_source(record([segment(1), segment(2), segment(3)]))
        self.assertEqual(result["decision"], "auto_accept")
        self.assertEqual(result["rights"]["status"], "unreviewed")
        altered = record([segment(1), segment(2, music=.1, speech=.8, nonmusic=.6), segment(3)])
        altered["metadata"] = {"metadata_cues": {"speech_cues": ["podcast"]}}
        result = score_source(altered)
        self.assertEqual(result["decision"], "manual_review")
        self.assertIn("passage_disagreement", result["reasons"])
        result = score_source(record([segment(1, music=.1, speech=.8, nonmusic=.6),
                                      segment(2, music=.1, speech=.8, nonmusic=.6),
                                      segment(3, music=.1, speech=.8, nonmusic=.6)]))
        self.assertEqual(result["decision"], "auto_reject")

    def test_missing_signal_and_low_pq_do_not_auto_reject(self):
        self.assertEqual(score_source(record([segment(1, models=False), segment(2)]))["decision"],
                         "manual_review")
        mixed = record([segment(1), segment(2), segment(3)])
        mixed["segments"][1]["aesthetics"]["PQ"] = 5.4
        self.assertEqual(score_source(mixed)["decision"], "manual_review")

    def test_v2_accepts_multisignal_clean_and_keeps_production_cue_in_review(self):
        clean = score_source_v2(record([segment(1), segment(2), segment(3)]))
        self.assertEqual(clean["decision"], "auto_accept")
        flagged = record([segment(1), segment(2), segment(3)])
        flagged["metadata"] = {"metadata_cues": {"production_context_cues": ["type beat"]}}
        flagged_result = score_source_v2(flagged)
        self.assertEqual(flagged_result["decision"], "manual_review")
        self.assertIn("metadata_production_context_review", flagged_result["reasons"])

    def test_v2_severe_nonmusic_rejects_and_acoustic_proxies_are_nonvetoes(self):
        bad = record([segment(1, music=.05, speech=.8, nonmusic=.7),
                      segment(2, music=.05, speech=.8, nonmusic=.7),
                      segment(3, music=.05, speech=.8, nonmusic=.7)])
        self.assertEqual(score_source_v2(bad)["decision"], "auto_reject")
        noisy = record([segment(1), segment(2), segment(3)])
        for part in noisy["segments"]:
            part["acoustic"]["noise_floor_db"] = -10
            part["acoustic"]["frame_rms_iqr_db"] = 40
        self.assertEqual(score_source_v2(noisy)["decision"], "auto_accept")

    def test_v21_conservative_guard_keeps_segments_explicit(self):
        clean = score_source_v21(record([segment(1), segment(2), segment(3)]))
        self.assertEqual(clean["decision"], "auto_accept")
        self.assertEqual(len(clean["accepted_segment_ids"]), 3)
        degraded = record([segment(1), segment(2), segment(3)])
        for part in degraded["segments"]:
            part["clap"]["group_scores"]["degraded_music"] = .44
        checked = score_source_v21(degraded)
        self.assertEqual(checked["decision"], "manual_review")
        self.assertEqual(checked["accepted_segment_ids"], [])

    def test_acoustic_bounded_descriptor_preserves_original_nyquist(self):
        rate = 44100
        t = np.arange(rate * 8) / rate
        data = np.sin(2 * np.pi * 12000 * t).astype("float32")[:, None]
        values = acoustic_features(data, rate)
        self.assertGreater(values["bandwidth_hz"], 10000)
        self.assertGreater(values["high_frequency_share"], 0.01)

    def test_blank_human_fields_are_unresolved_and_split_is_locked_by_source(self):
        self.assertEqual(human_class({"content_type": "", "audio_quality": "acceptable"})[0], "unresolved")
        self.assertEqual(human_class({"content_type": "music", "audio_quality": "acceptable"})[0],
                         "positive_clip_evidence")
        self.assertEqual(human_class({"content_type": "music", "audio_quality": "acceptable",
                                      "source_nature": "ambiguous"})[0], "unresolved")
        self.assertEqual(human_class({"audio_quality": "degraded"})[0], "negative_clip_evidence")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "split.jsonl"
            first = fixed_split({"iamd:a", "iamd:b"}, {"iamd:a"}, path)
            second = fixed_split({"iamd:a", "iamd:b"}, {"iamd:a", "iamd:b"}, path)
            self.assertEqual(first, second)
            self.assertEqual(second["iamd:b"], "prospective")
        self.assertLess(wilson(1, 1)[0], .5)

    def test_clap_prompts_match_frozen_pilot(self):
        self.assertEqual(CURATION_PROMPTS, PILOT_PROMPTS)

    def test_generic_metadata_hints_do_not_equate_electronic_with_midi(self):
        self.assertFalse(metadata_cues({"title": "Live electronic ambient composition"})
                         ["synthetic_render_cues"])
        self.assertTrue(metadata_cues({"title": "MIDI soundfont sequence"})
                        ["synthetic_render_cues"])

    def test_generic_review_import_keeps_blanks_unknown_and_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["source_key", "content_type",
                                                            "audio_quality", "notes"])
                writer.writeheader()
                writer.writerow({"source_key": "other:a", "content_type": "music",
                                 "audio_quality": "acceptable"})
                writer.writerow({"source_key": "other:b", "notes": "unclear, listen again"})
                writer.writerow({"source_key": "other:c"})
            reviews = import_reviews(path, {"other:a", "other:b", "other:c"})
            self.assertEqual(set(reviews), {"other:a", "other:b"})
            self.assertEqual(reviews["other:a"]["human_class"], "positive_clip_evidence")
            self.assertEqual(reviews["other:b"]["human_class"], "unresolved")
            self.assertEqual(reviews["other:a"]["scope"], "primary_clip_only")
            with path.open("a", encoding="utf-8") as stream:
                stream.write('"other:d","not_a_label","",""\n')
            with self.assertRaises(ValueError):
                import_reviews(path, {"other:a", "other:b", "other:c", "other:d"})

    def test_structured_annotation_fields_are_validated_and_do_not_invent_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "structured.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["source_key", "content_type",
                                                            "audio_quality", "source_nature",
                                                            "capture_quality", "degradation_reason",
                                                            "provenance"])
                writer.writeheader()
                writer.writerow({"source_key": "other:a", "content_type": "music",
                                 "audio_quality": "acceptable", "source_nature": "likely_real_recording",
                                 "capture_quality": "distant_or_reverberant",
                                 "degradation_reason": "distance_reverb", "provenance": "needs_verification"})
            review = import_reviews(path, {"other:a"})["other:a"]
            self.assertEqual(review["human_class"], "negative_clip_evidence")
            self.assertIn("distance_reverb", review["rejection_reasons"])

    def test_independent_validation_manifest_is_source_disjoint_and_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items, catalog, excluded, output = (root / name for name in
                                                ("items.jsonl", "catalog.jsonl", "excluded.jsonl", "validation.jsonl"))
            write_jsonl_atomic(items, [{"identifier": f"new-{i}", "metadata_status": "ok",
                                        "technical_candidate": True, "redistributable_candidate": True,
                                        "archive_licence_category": "compatible"} for i in range(4)])
            write_jsonl_atomic(catalog, [{"identifier": f"new-{i}", "collections": [f"c{i}"],
                                         "artists": [f"a{i}"], "tags": ["rock"]} for i in range(4)])
            write_jsonl_atomic(excluded, [{"source_id": "new-0"}])
            command_prepare_independent_validation(SimpleNamespace(
                items=items, catalog=catalog, files=None, exclude_features=excluded,
                blind_real_manifest=None, out=output, target=3, max_per_creator=2,
                max_per_collection=2, seed=42))
            rows = list(read_jsonl(output))
            self.assertEqual(len(rows), 3)
            self.assertNotIn("new-0", {row["source_id"] for row in rows})
            self.assertTrue(all(row["audio_required"] and row["audio_url"] is None for row in rows))

    def test_changed_source_uses_distinct_clip_cache_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "source.flac"
            samples = np.sin(2 * np.pi * 440 * np.arange(8 * 8000) / 8000).astype("float32")
            sf.write(audio, samples, 8000)
            row = {"dataset": "other", "source_id": "a", "audio_path": str(audio)}
            original = extract_local_source(row, root / "clips", seconds=2)
            sf.write(audio, samples * .5, 8000)
            changed = extract_local_source(row, root / "clips", seconds=2)
            self.assertNotEqual(original["segments"][0]["clip_path"],
                                changed["segments"][0]["clip_path"])

    def test_candidate_export_never_approves_rights_and_blind_page_hides_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root / "clip.flac"
            sf.write(clip, np.zeros(8000, dtype="float32"), 8000)
            source = record([segment(1), segment(2), segment(3)])
            source["metadata"] = {"title": "Secret title", "creator": "Secret artist"}
            for part in source["segments"]:
                part["clip_path"] = str(clip)
                part["start_s"], part["duration_s"] = 0, 1
            features, decisions, exported, page = (root / name for name in
                                                   ("features.jsonl", "decisions.jsonl", "export.jsonl", "listen.html"))
            write_jsonl_atomic(features, [source])
            write_jsonl_atomic(decisions, [score_source(source)])
            command_export(SimpleNamespace(features=features, decisions=decisions, out=exported))
            candidates = list(read_jsonl(exported))
            self.assertEqual(len(candidates), 3)
            self.assertTrue(all(item["redistribution_approved"] is False for item in candidates))
            command_listen(SimpleNamespace(features=features, decisions=decisions, out=page,
                                           source_keys=None, show_predictions=True, blind=True))
            markup = page.read_text(encoding="utf-8")
            self.assertIn("Source 1", markup)
            self.assertNotIn("Secret title", markup)
            self.assertNotIn("Secret artist", markup)
            self.assertNotIn("<small>auto_accept</small>", markup)

    def test_predictions_and_blind_order_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = record([segment(1), segment(2), segment(3)])
            features, decisions, frozen = (root / name for name in
                                           ("features.jsonl", "decisions.jsonl", "frozen.jsonl"))
            write_jsonl_atomic(features, [source])
            write_jsonl_atomic(decisions, [score_source_v2(source)])
            command_freeze_predictions(SimpleNamespace(features=features, decisions=decisions,
                                                       policy="v2", config=None, label=None, out=frozen))
            lock = Path(str(frozen) + ".lock.json")
            self.assertTrue(lock.is_file())
            command_freeze_predictions(SimpleNamespace(features=features, decisions=decisions,
                                                       policy="v2", config=None, label=None, out=frozen))
            changed = score_source_v2(source)
            changed["clean_score"] = 0.01
            write_jsonl_atomic(decisions, [changed])
            with self.assertRaises(ValueError):
                command_freeze_predictions(SimpleNamespace(features=features, decisions=decisions,
                                                           policy="v2", config=None, label=None, out=frozen))

    def test_blind_order_hides_source_keys_and_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, order, page = (root / name for name in
                                     ("manifest.jsonl", "order.jsonl", "blind.html"))
            rows = [{"validation_id": "v1", "source_key": "iamd:secret-a"},
                    {"validation_id": "v2", "source_key": "iamd:secret-b"}]
            write_jsonl_atomic(manifest, rows)
            command_prepare_blind_listen(SimpleNamespace(manifest=manifest, out=order, seed=7))
            order_rows = list(read_jsonl(order))
            self.assertEqual([row["blind_id"] for row in order_rows], ["blind-0001", "blind-0002"])
            source = record([segment(1), segment(2), segment(3)])
            source["source_key"] = "iamd:secret-a"
            source["source_id"] = "secret-a"
            clip = root / "clip.flac"
            sf.write(clip, np.zeros(8000, dtype="float32"), 8000)
            for part in source["segments"]:
                part["clip_path"] = str(clip)
            features = root / "features.jsonl"
            write_jsonl_atomic(features, [source,
                                          {**source, "source_key": "iamd:secret-b", "source_id": "secret-b"}])
            command_listen(SimpleNamespace(features=features, decisions=None, out=page,
                                           source_keys=None, order_file=order, show_predictions=False,
                                           blind=True))
            markup = page.read_text(encoding="utf-8")
            self.assertIn("blind_id", markup)
            self.assertNotIn("iamd:secret-a", markup)
            self.assertNotIn("iamd:secret-b", markup)

    def test_adjudication_is_versioned_and_judgments_are_explainable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = record([segment(1), segment(2), segment(3)])
            source["source_key"] = "iamd:reviewed"
            source["source_id"] = "reviewed"
            source["metadata"] = {"title": "Reviewed", "creator": "Artist", "genre": "Jazz"}
            source["provenance_candidate"] = True
            source["technical_candidate"] = True
            source["redistributable_candidate"] = False
            source["rights"] = {"status": "pilot_pending_asset_review",
                                  "license_url": "https://example.test/cc-by",
                                  "provenance_approved": False}
            features, decisions, reviews = (root / name for name in
                                            ("features.jsonl", "decisions.jsonl", "reviews.jsonl"))
            adjudication, definitive, history, judgments = (root / name for name in
                                                            ("adjudication.json", "definitive.jsonl",
                                                             "history.jsonl", "judgments.jsonl"))
            write_jsonl_atomic(features, [source])
            write_jsonl_atomic(decisions, [score_source_v2(source)])
            write_jsonl_atomic(reviews, [{"source_key": "iamd:reviewed",
                                          "human_class": "negative_clip_evidence",
                                          "content_type": "music", "audio_quality": "degraded"}])
            adjudication.write_text(json.dumps({"corrections": [{
                "source_key": "iamd:reviewed",
                "fields": {"human_class": "positive_clip_evidence", "audio_quality": "acceptable"},
                "note": "manual correction"}]}) + "\n", encoding="utf-8")
            command_apply_adjudication(SimpleNamespace(reviews=reviews, adjudication=adjudication,
                                                       out=definitive, history_out=history,
                                                       version="test-v1"))
            corrected = list(read_jsonl(definitive))[0]
            self.assertEqual(corrected["human_class"], "positive_clip_evidence")
            self.assertTrue(Path(str(definitive) + ".lock.json").is_file())
            history_row = list(read_jsonl(history))[0]
            self.assertEqual(history_row["old_values"]["human_class"], "negative_clip_evidence")
            command_export_judgments(SimpleNamespace(features=features, decisions=decisions,
                                                     reviews=definitive, out=judgments))
            judgment = list(read_jsonl(judgments))[0]
            self.assertIn("pipeline_decision", judgment)
            self.assertEqual(judgment["human_class"], "positive_clip_evidence")
            self.assertEqual(judgment["rights_status"], "pilot_pending_asset_review")
            self.assertTrue(judgment["rights_provenance_candidate"])
            self.assertFalse(judgment["redistributable_candidate"])
            self.assertEqual(judgment["rights"]["license_url"], "https://example.test/cc-by")

    def test_independent_evaluation_accepts_explainable_pipeline_judgments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = record([segment(1), segment(2), segment(3)])
            source["source_key"] = "iamd:judgment-export"
            source["source_id"] = "judgment-export"
            features = root / "features.jsonl"
            decisions = root / "decisions.jsonl"
            judgments = root / "pipeline_judgments.jsonl"
            reviews = root / "reviews.jsonl"
            out = root / "evaluation"
            write_jsonl_atomic(features, [source])
            write_jsonl_atomic(decisions, [score_source_v2(source)])
            write_jsonl_atomic(reviews, [{"source_key": source["source_key"],
                                          "human_class": "positive_clip_evidence"}])
            command_export_judgments(SimpleNamespace(features=features, decisions=decisions,
                                                     reviews=None, out=judgments))
            command_evaluate_independent(SimpleNamespace(
                features=features, reviews=reviews, v2_decisions=judgments,
                v21_decisions=judgments, out_dir=out))
            report = json.loads((out / "independent_evaluation.json").read_text())
            self.assertEqual(report["approaches"]["v2"]["primary_passage"]["auto_accept_binary_denominator"], 1)


if __name__ == "__main__":
    unittest.main()
