import json
import tempfile
import unittest
from pathlib import Path

from scripts.export_clean_clip_candidates import export_candidates


def _feature(key="demo:one"):
    return {
        "source_key": key,
        "dataset": "demo",
        "source_id": key.split(":", 1)[1],
        "audio_path": "/private/source.wav",
        "source_sha256": "abc",
        "sample_rate": 44100,
        "format": "WAV",
        "lossless_status": "clean_lossless",
        "technical_candidate": True,
        "provenance_candidate": True,
        "redistributable_candidate": False,
        "metadata": {"title": "One", "creator": "Artist", "genre": "jazz", "collection": "set"},
        "rights": {
            "review_status": "pending",
            "rights_status": "pending",
            "provenance_approved": False,
            "redistribution_approved": False,
            "allow_redistribution": None,
            "allow_derivatives": None,
        },
        "segments": [
            {"segment_id": f"{key}#p1", "clip_path": "/private/clip.flac",
             "start_s": 1.0, "duration_s": 24.0},
            {"segment_id": f"{key}#p2", "clip_path": "/private/clip2.flac",
             "start_s": 25.0, "duration_s": 24.0},
        ],
    }


class CleanClipCandidateTests(unittest.TestCase):
    def test_exports_accepted_sampled_segment_without_granting_rights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = _feature()
            decision = {
                "source_key": "demo:one",
                "decision": "manual_review",
                "clean_score": 0.8,
                "reasons": ["passage_disagreement"],
                "accepted_segment_ids": ["demo:one#p1"],
                "segments": [
                    {"segment_id": "demo:one#p1", "decision": "auto_accept",
                     "clean_score": 0.9, "reasons": ["agreement"]},
                    {"segment_id": "demo:one#p2", "decision": "manual_review",
                     "clean_score": 0.6, "reasons": ["bandwidth_review"]},
                ],
            }
            features_path = root / "features.jsonl"
            decisions_path = root / "decisions.jsonl"
            features_path.write_text(json.dumps(feature) + "\n", encoding="utf-8")
            decisions_path.write_text(json.dumps(decision) + "\n", encoding="utf-8")
            rows, summary = export_candidates(features_path, decisions_path)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["segment_id"], "demo:one#p1")
            self.assertTrue(rows[0]["source_validation_required"])
            self.assertFalse(rows[0]["rights_gate_passed"])
            self.assertFalse(rows[0]["public_research_eligible"])
            self.assertFalse(rows[0]["public_commercial_eligible"])
            self.assertEqual(rows[0]["rights_gate_reason"], "provenance_not_approved")
            self.assertEqual(summary["selected_sources"], 1)
            self.assertEqual(summary["selected_segments"], 1)
            self.assertFalse(summary["rights_inferred"])
            self.assertFalse(summary["audio_copied"])

    def test_auto_rejected_source_is_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = _feature()
            decision = {
                "source_key": "demo:one",
                "decision": "auto_reject",
                "accepted_segment_ids": [],
                "segments": [
                    {"segment_id": "demo:one#p1", "decision": "auto_reject",
                     "clean_score": 0.0, "reasons": ["nonmusic"]},
                    {"segment_id": "demo:one#p2", "decision": "auto_reject",
                     "clean_score": 0.0, "reasons": ["nonmusic"]},
                ],
            }
            features_path = root / "features.jsonl"
            decisions_path = root / "decisions.jsonl"
            features_path.write_text(json.dumps(feature) + "\n", encoding="utf-8")
            decisions_path.write_text(json.dumps(decision) + "\n", encoding="utf-8")
            rows, summary = export_candidates(features_path, decisions_path)
            self.assertEqual(rows, [])
            self.assertEqual(summary["selected_sources"], 0)
            self.assertEqual(summary["rights_gate_by_selected_segment"],
                             {"public_commercial": 0, "public_research": 0})

    def test_isolated_stems_can_be_excluded_without_affecting_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = _feature()
            feature["metadata"]["asset_role"] = "isolated_stem_raw"
            decision = {
                "source_key": "demo:one", "decision": "auto_accept",
                "clean_score": 0.9, "accepted_segment_ids": ["demo:one#p1"],
                "segments": [
                    {"segment_id": "demo:one#p1", "decision": "auto_accept",
                     "clean_score": 0.9, "reasons": []},
                    {"segment_id": "demo:one#p2", "decision": "manual_review",
                     "clean_score": 0.6, "reasons": []},
                ],
            }
            features_path = root / "features.jsonl"
            decisions_path = root / "decisions.jsonl"
            features_path.write_text(json.dumps(feature) + "\n", encoding="utf-8")
            decisions_path.write_text(json.dumps(decision) + "\n", encoding="utf-8")
            rows, summary = export_candidates(
                features_path, decisions_path,
                exclude_asset_roles={"isolated_stem_raw"})
        self.assertEqual(rows, [])
        self.assertEqual(summary["excluded_asset_role_segments"], {"isolated_stem_raw": 1})

    def test_inconsistent_accepted_segment_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = _feature()
            decision = {
                "source_key": "demo:one",
                "decision": "auto_accept",
                "accepted_segment_ids": ["demo:one#p1"],
                "segments": [
                    {"segment_id": "demo:one#p1", "decision": "manual_review"},
                    {"segment_id": "demo:one#p2", "decision": "auto_accept"},
                ],
            }
            features_path = root / "features.jsonl"
            decisions_path = root / "decisions.jsonl"
            features_path.write_text(json.dumps(feature) + "\n", encoding="utf-8")
            decisions_path.write_text(json.dumps(decision) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                export_candidates(features_path, decisions_path)


if __name__ == "__main__":
    unittest.main()
