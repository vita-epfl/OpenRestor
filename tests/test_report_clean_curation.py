import json
import tempfile
import unittest
from pathlib import Path

from scripts.report_clean_curation import build


class CleanCurationReportTests(unittest.TestCase):
    def test_joins_source_and_decision_without_inventing_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = {
                "source_key": "demo:one", "dataset": "demo", "source_id": "one",
                "audio_path": "/private/one.wav", "source_sha256": "abc",
                "duration_s": 12.0, "technical_candidate": True,
                "provenance_candidate": True, "redistributable_candidate": False,
                "metadata": {"creator": "Artist", "collection": "set", "title": "One"},
                "rights": {"review_status": "pending", "provenance_approved": False},
                "segments": [{"segment_id": "demo:one#p1", "acoustic": {"bandwidth_hz": 12000},
                              "aesthetics": {"PQ": 8.0}, "ast": {"interest_labels": {"Music": .9}},
                              "clap": {"group_scores": {"produced_music": .8, "non_music": .1,
                                                            "rudimentary_synthetic": .2}}},
                             {"segment_id": "demo:one#p2", "acoustic": {"bandwidth_hz": 8000},
                              "aesthetics": {"PQ": 6.0}, "ast": {"interest_labels": {"Music": .8}},
                              "clap": {"group_scores": {"produced_music": .7, "non_music": .2,
                                                            "rudimentary_synthetic": .3}}}],
            }
            decision = {"source_key": "demo:one", "decision": "auto_accept",
                        "clean_score": .9, "reasons": ["agreement"], "accepted_segment_ids": ["demo:one#p1"]}
            f, d = root / "features.jsonl", root / "decisions.jsonl"
            f.write_text(json.dumps(feature) + "\n", encoding="utf-8")
            d.write_text(json.dumps(decision) + "\n", encoding="utf-8")
            rows, summary = build(f, d)
            self.assertEqual(rows[0]["decision_scope"], "source_decision_from_sampled_passages")
            self.assertEqual(rows[0]["primary_metrics"]["PQ"], 6.0)
            self.assertAlmostEqual(rows[0]["primary_metrics"]["clap_music_minus_nonmusic"], .5)
            self.assertEqual(rows[0]["passage_metrics"]["PQ"], {"n": 2, "median": 7.0,
                                                                  "min": 6.0, "max": 8.0})
            self.assertEqual(summary["decisions"], {"auto_accept": 1})
            self.assertFalse(summary["human_labels_inferred"])

    def test_mismatched_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            f, d = root / "features.jsonl", root / "decisions.jsonl"
            f.write_text(json.dumps({"source_key": "demo:one", "segments": [{}]}) + "\n", encoding="utf-8")
            d.write_text(json.dumps({"source_key": "demo:two"}) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build(f, d)


if __name__ == "__main__":
    unittest.main()
