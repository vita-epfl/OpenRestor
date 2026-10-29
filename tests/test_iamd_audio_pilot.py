"""Safety and inference invariants of the bounded Phase 1b pilot."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.iamd_audio_pilot import (allocation, import_annotations, make_plan,
                                      passage_windows, population, transfer, weighted_yield)


def jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.phase1 = self.root / "phase1"
        self.phase1.mkdir()
        self.out = self.root / "pilot"
        jsonl(self.phase1 / "items.jsonl", [
            {"identifier": "a", "redistributable_candidate": True, "provenance_candidate": True,
             "collection": "rock", "creator": "Artist A", "genre": "rock", "title": "A",
             "tags": [], "archive_license_url": "CC BY", "licence_status": "match"},
            {"identifier": "b", "redistributable_candidate": True, "provenance_candidate": True,
             "collection": "jazz", "creator": "Artist B", "genre": "jazz", "title": "B",
             "tags": [], "archive_license_url": "CC0", "licence_status": "match"},
            {"identifier": "c", "redistributable_candidate": False, "provenance_candidate": False,
             "collection": "rock", "creator": "Artist C", "genre": "rock", "title": "C"},
        ])
        files = []
        for identifier, name in [("a", "one.flac"), ("a", "two.wav"), ("b", "three.aiff")]:
            files.append({"identifier": identifier, "name": name, "format": name.split(".")[-1].upper(),
                          "source": "original", "status": "strict_original", "archive_format": name,
                          "private": False, "redistributable_file_candidate": True, "size_bytes": 100,
                          "length_s": 100, "sha1": "x", "md5": None})
        files += [
            {**files[0], "name": "bad.mp3", "format": "MP3"},
            {**files[0], "name": "derived.flac", "source": "derivative"},
            {**files[0], "name": "../escape.flac"},
            {**files[0], "name": "ambiguous.flac", "status": "source_ambiguous", "source": None},
        ]
        jsonl(self.phase1 / "files.jsonl", files)
        (self.phase1 / "summary.json").write_text(json.dumps({"funnel": {"initial_candidates": 3,
            "metadata_resolved": 3, "metadata_failed": 0}}), encoding="utf-8")

    def test_population_never_uses_mp3_derivatives_ambiguous_or_path_traversal(self):
        self.assertEqual({r["name"] for r in population(self.phase1)},
                         {"one.flac", "two.wav", "three.aiff"})

    def test_plan_is_deterministic_and_tracks_probabilities(self):
        first = make_plan(self.phase1, self.out, 2, 42, 0.1, 3, 18)
        self.assertEqual(first["selected_tracks"], 2)
        tracks = list(map(json.loads, (self.out / "tracks.jsonl").read_text().splitlines()))
        self.assertEqual(len({r["collection"] for r in tracks}), 2)
        self.assertEqual(sorted(r["selection_probability"] for r in tracks), [0.5, 1.0])
        self.assertTrue(all(r["audio_review_status"] == "audio_review_pending" for r in tracks))
        with self.assertRaises(FileExistsError):
            make_plan(self.phase1, self.out, 2, 42, 0.1, 3, 18)

    def test_budget_and_safety_constraints(self):
        for count, gib, passages, seconds in [(201, 10, 3, 18), (1, 11, 3, 18),
                                               (1, 10, 1, 18), (1, 10, 3, 30)]:
            with self.assertRaises(ValueError):
                make_plan(self.phase1, self.out, count, 42, gib, passages, seconds)
        ledger = {"new_bytes": 90}
        row = {"track_id": "test", "identifier": "a", "name": "one.flac", "size_bytes": 100,
               "sha1": "x", "download_url": "https://archive.org/download/a/one.flac"}
        with patch("scripts.iamd_audio_pilot.verified", return_value=False):
            result = transfer(self.out, row, ledger, 100,
                              runner=lambda *a, **k: self.fail("network should not be called"))
        self.assertEqual(result["status"], "budget_deferred")
        self.assertEqual(ledger["new_bytes"], 90)

    def test_passages_do_not_overlap(self):
        starts = passage_windows(100, 18, 3)
        self.assertEqual(len(starts), 3)
        self.assertTrue(all(b >= a + 18 for a, b in zip(starts, starts[1:])))
        self.assertEqual(passage_windows(55, 18, 3), [])

    def test_human_annotation_required_before_yield(self):
        tracks = [{"track_id": "x", "stratum": "a", "stratum_population_tracks": 2,
                   "stratum_sample_tracks": 1}]
        segments = [{"track_id": "x", "segment_id": "x-p1", "duration_s": 18}]
        self.assertIsNone(weighted_yield(tracks, segments, {}))
        self.assertIsNotNone(weighted_yield(tracks, segments, {"x-p1": {"clean_quality": "acceptable"}}))

    def test_annotation_import_rejects_unknown_ids_and_partial_rows(self):
        self.out.mkdir()
        jsonl(self.out / "segments.jsonl", [{"segment_id": "known", "track_id": "x"}])
        csv_path = self.root / "review.csv"
        fields = ["segment_id", "clean_quality", "content", "instruments", "use_global_eq",
                  "use_denoising", "use_brass", "use_drums", "defects", "rejection_reasons", "notes"]
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerow({"segment_id": "unknown", "clean_quality": "acceptable"})
        with self.assertRaises(ValueError):
            import_annotations(self.out, csv_path)
        self.assertFalse((self.out / "annotations.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
