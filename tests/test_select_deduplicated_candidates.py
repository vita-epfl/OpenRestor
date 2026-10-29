import json
import tempfile
import unittest
from pathlib import Path

from scripts.select_deduplicated_candidates import select, write_selection


def candidate(source, role, segment="p1"):
    return {"source_key": source, "segment_id": f"{source}#{segment}",
            "metadata": {"asset_role": role}}


def dedup(source, group, members):
    return {"source_key": source, "acoustic_dedup_group_id": group,
            "acoustic_duplicate_source_keys": members}


class DeduplicatedCandidateTests(unittest.TestCase):
    def test_prefers_stereo_master_and_keeps_other_sources(self):
        candidates = [candidate("albumdb:immersive", "full_mix_immersive_master"),
                      candidate("albumdb:stereo", "full_mix_stereo_master", "p1"),
                      candidate("other:unique", "full_mix_example")]
        dedup_rows = [dedup("albumdb:immersive", "g1", ["albumdb:immersive", "albumdb:stereo"]),
                      dedup("albumdb:stereo", "g1", ["albumdb:immersive", "albumdb:stereo"])]
        output, report = select(candidates, dedup_rows)
        self.assertEqual({row["source_key"] for row in output},
                         {"albumdb:stereo", "other:unique"})
        self.assertEqual(report["excluded_sources"], 1)
        self.assertFalse(report["audio_copied"])

    def test_multiple_segments_from_selected_source_are_kept(self):
        candidates = [candidate("a:stereo", "full_mix_stereo_master", "p1"),
                      candidate("a:stereo", "full_mix_stereo_master", "p2"),
                      candidate("a:immersive", "full_mix_immersive_master")]
        rows = [dedup("a:stereo", "g", ["a:stereo", "a:immersive"]),
                dedup("a:immersive", "g", ["a:stereo", "a:immersive"])]
        output, report = select(candidates, rows)
        self.assertEqual(len(output), 2)
        self.assertEqual(report["output_sources"], 1)

    def test_inconsistent_groups_fail_closed(self):
        candidates = [candidate("a:x", "full_mix_example")]
        rows = [dedup("a:x", "g", ["a:x", "a:y"]),
                dedup("a:y", "h", ["a:y", "a:x"])]
        with self.assertRaises(ValueError):
            select(candidates, rows)

    def test_file_selection_records_reproducibility_hashes(self):
        candidates = [candidate("a:stereo", "full_mix_stereo_master")]
        dedup_rows = [dedup("a:stereo", "g", ["a:stereo"])]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates_path = root / "candidates.jsonl"
            dedup_path = root / "dedup.jsonl"
            out_path = root / "selected.jsonl"
            report_path = root / "report.json"
            candidates_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                                  for row in candidates), encoding="utf-8")
            dedup_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                              for row in dedup_rows), encoding="utf-8")
            report = write_selection(candidates_path, dedup_path, out_path, report_path)
            self.assertRegex(report["input_candidates_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(report["input_dedup_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(report["output_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(json.loads(report_path.read_text())["output_sha256"],
                             report["output_sha256"])


if __name__ == "__main__":
    unittest.main()
