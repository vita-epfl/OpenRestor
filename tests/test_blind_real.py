"""Blind-Real curation: licence gate, live evidence, deduplication, cap and ranking."""

from __future__ import annotations

from unittest import TestCase

from openrestore.data.blind_real import (
    best_original_file,
    filter_candidates,
    freeze_candidate_list,
    live_evidence,
    looks_live,
    rank_candidates,
    select_candidates,
    selection_statistics,
)


def _row(**kwargs):
    base = {"key": "k", "identifier": "item", "license_type": "BY", "tags": None, "title": None}
    return {**base, **kwargs}


class BlindRealCurationTests(TestCase):
    def test_live_keywords_match_on_word_boundaries(self) -> None:
        # The bare substring "aud" appears in "opensource_audio", which must not count.
        self.assertFalse(looks_live(_row(collection="opensource_audio; community")))
        self.assertFalse(looks_live(_row(title="Delivery")))
        self.assertTrue(looks_live(_row(title="Live at The Moody Theater")))
        self.assertTrue(looks_live(_row(tags="concert; audience")))
        self.assertTrue(looks_live(_row(is_live=1.0)))

    def test_licence_gate_excludes_non_commercial_and_no_derivatives(self) -> None:
        rows = [
            _row(license_type="CC0", title="Live in Paris"),
            _row(license_type="BY", title="Live in Paris"),
            _row(license_type="BY-SA", title="Live in Paris"),
            _row(license_type="BY-NC", title="Live in Paris"),
            _row(license_type="BY-NC-SA", title="Live in Paris"),
            _row(license_type="BY-ND", title="Live in Paris"),
        ]
        kept = {r["license_type"] for r in filter_candidates(rows)}
        self.assertEqual(kept, {"CC0", "BY"})
        with_sa = {r["license_type"] for r in filter_candidates(rows, allow_share_alike=True)}
        self.assertEqual(with_sa, {"CC0", "BY", "BY-SA"})
        # A permissive licence is not enough on its own.
        self.assertEqual(filter_candidates([_row(license_type="CC0", title="Studio Album")]), [])

    def test_evidence_grades_structured_above_bare_keywords(self) -> None:
        weak = live_evidence(_row(tags="live"))
        strong = live_evidence(_row(tags="recorded live; audience", venue="Olympia", city="Paris"))
        self.assertEqual(weak["structured_fields"], [])
        self.assertEqual(weak["strong_phrases"], [])
        self.assertIn("venue", strong["structured_fields"])
        self.assertTrue(strong["strong_phrases"])
        self.assertGreater(strong["evidence_score"], weak["evidence_score"])

    def test_ranking_prefers_better_licence_evidence_and_fidelity(self) -> None:
        rows = [
            _row(identifier="weak", license_type="BY", tags="live"),
            _row(identifier="best", license_type="CC0", tags="recorded live; soundboard",
                 venue="Olympia", sample_rate="96000", bit_depth=24, channels=2.0, artist="X", date="1998"),
        ]
        self.assertEqual(rank_candidates(rows)[0]["identifier"], "best")

    def test_cap_and_deduplication_spread_the_selection(self) -> None:
        rows = [_row(identifier="loud", key=f"loud-{i}", tags="live") for i in range(30)]
        rows += [_row(identifier=f"other{i}", key=f"o{i}", tags="live") for i in range(10)]
        selected = select_candidates(rows, target=400, cap_per_identifier=2)
        per_id: dict[str, int] = {}
        for row in selected:
            per_id[row["identifier"]] = per_id.get(row["identifier"], 0) + 1
        self.assertEqual(max(per_id.values()), 2, per_id)
        self.assertEqual(per_id["loud"], 2, "one noisy item must not dominate")
        # 2 from the noisy identifier, plus one each from the ten that only have one row.
        self.assertEqual(len(selected), 12)
        with self.assertRaises(ValueError):
            select_candidates(rows, cap_per_identifier=0)

    def test_target_bounds_the_selection(self) -> None:
        rows = [_row(identifier=f"i{i}", key=f"k{i}", tags="live") for i in range(50)]
        self.assertEqual(len(select_candidates(rows, target=7, cap_per_identifier=1)), 7)

    def test_frozen_rows_carry_provenance_and_no_clean_reference(self) -> None:
        rows = [_row(identifier="gig", key="k1", tags="recorded live", venue="Olympia",
                     artist="Band", license_url="https://creativecommons.org/licenses/by/4.0/")]
        frozen = freeze_candidate_list(select_candidates(rows, target=5, cap_per_identifier=1), excerpt_seconds=15.0)
        self.assertEqual(len(frozen), 1)
        row = frozen[0]
        self.assertEqual(row["split"], "blind_real_test")
        self.assertEqual(row["internet_archive_identifier"], "gig")
        self.assertIn("archive.org/metadata/gig", row["internet_archive_metadata"])
        self.assertEqual(row["attribution"], "Band")
        self.assertEqual(row["excerpt_seconds"], 15.0)
        self.assertFalse(row["selection"]["qa_listened"])
        # This track has no clean reference and no degradation label, by design.
        for forbidden in ("clean_path", "clean_id", "degradation_chain", "degradation_tracking"):
            self.assertNotIn(forbidden, row)

        stats = selection_statistics(frozen)
        self.assertEqual(stats["items"], 1)
        self.assertEqual(stats["max_per_identifier"], 1)

    def test_best_original_prefers_lossless_and_skips_derivatives(self) -> None:
        metadata = {"files": [
            {"name": "show.mp3", "source": "derivative", "size": "100"},
            {"name": "show.mp3", "source": "original", "size": "100"},
            {"name": "show.flac", "source": "original", "size": "900"},
            {"name": "notes.txt", "source": "original", "size": "10"},
        ]}
        self.assertEqual(best_original_file(metadata)["name"], "show.flac")
        self.assertIsNone(best_original_file({"files": [{"name": "a.txt", "source": "original"}]}))
