import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_iamd_pilot_listen import build


class IamdPilotListenTests(unittest.TestCase):
    def test_template_and_page_cover_all_segments_without_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "segments.jsonl").write_text("".join(json.dumps({
                "segment_id": f"s-p{i}", "track_id": "track", "clip_path": f"clips/s-p{i}.flac",
                "identifier": "s", "name": "song.wav", "creator": "Artist",
                "collection": "music", "start_s": i, "duration_s": 18,
                "license_url": "https://example.test/license"}) + "\n" for i in range(1, 4)), encoding="utf-8")
            (root / "scores.jsonl").write_text("".join(json.dumps({
                "segment_id": f"s-p{i}", "audiobox_pq": i + 5, "bandwidth_hz": 12000}) + "\n" for i in range(1, 4)), encoding="utf-8")
            judgments = root / "judgments.jsonl"
            judgments.write_text(json.dumps({
                "source_id": "s--track",
                "pipeline_decision": "manual_review",
                "pipeline_clean_score": 0.61,
                "pipeline_reasons": ["passage_disagreement"],
                "segments": [{"segment_id": f"dataset:s--track#p{i}",
                              "decision": "auto_accept" if i == 3 else "manual_review",
                              "clean_score": 0.7, "reasons": ["v21_multisignal_agreement"]}
                             for i in range(1, 4)]
            }) + "\n", encoding="utf-8")
            html = root / "listen.html"
            csv = root / "annotations.csv"
            result = build(root, html, csv, judgments)
            self.assertEqual(result["segments"], 3)
            self.assertIn("s-p3", html.read_text())
            self.assertIn("<dt>PQ</dt>", html.read_text())
            self.assertIn("passage_disagreement", html.read_text())
            self.assertIn("v21_multisignal_agreement", html.read_text())
            lines = csv.read_text().splitlines()
            self.assertEqual(len(lines), 4)
            self.assertIn("clean_quality", lines[0])
            self.assertNotIn("acceptable", csv.read_text())


if __name__ == "__main__":
    unittest.main()
