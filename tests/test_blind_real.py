"""Blind-Real curation: licence gate, live evidence, deduplication, cap and ranking."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from openrestore.data.blind_real import (
    acoustid_artist_agreement,
    artist_groups,
    artist_names,
    best_original_file,
    cap_items_per_artist,
    looks_ambient_or_noise,
    primary_collection,
    require_fpcalc,
    select_diverse_candidates,
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


class BlindRealSplitTests(TestCase):
    def test_confidence_tiers_grade_evidence(self) -> None:
        from openrestore.data.blind_real import confidence_tier, select_high_confidence

        structured = _row(venue="Olympia", tags="live")
        strong = _row(tags="recorded live; soundboard")
        weak = _row(tags="live")
        none = _row(title="Studio Album")
        self.assertEqual(confidence_tier(structured), "structured")
        self.assertEqual(confidence_tier(strong), "strong_phrase")
        self.assertEqual(confidence_tier(weak), "weak_keyword")
        self.assertEqual(confidence_tier(none), "none")

        # A bare keyword is not evidence, so the weak tier is excluded by default.
        kept = select_high_confidence([structured, strong, weak, none])
        self.assertEqual(len(kept), 2)

    def test_splits_are_disjoint_by_identifier(self) -> None:
        from openrestore.data.blind_real import assign_source_disjoint_splits, validate_source_disjoint

        # Several clips per concert: they must all land in the same split.
        rows = [
            {"identifier": f"concert{i}", "key": f"c{i}-{j}"}
            for i in range(40) for j in range(3)
        ]
        assigned = assign_source_disjoint_splits(rows, validation_identifiers=6, test_identifiers=6)
        validate_source_disjoint(assigned)

        per_identifier: dict[str, set[str]] = {}
        for row in assigned:
            per_identifier.setdefault(row["identifier"], set()).add(row["split"])
        for identifier, splits in per_identifier.items():
            self.assertEqual(len(splits), 1, f"{identifier} crossed splits: {splits}")

        counts: dict[str, int] = {}
        for identifier, splits in per_identifier.items():
            split = next(iter(splits))
            counts[split] = counts.get(split, 0) + 1
        self.assertEqual(counts["blind_real_validation"], 6)
        self.assertEqual(counts["blind_real_test"], 6)
        self.assertEqual(counts["blind_real_train"], 28)

        # Deterministic for a fixed seed.
        again = assign_source_disjoint_splits(rows, validation_identifiers=6, test_identifiers=6)
        self.assertEqual([r["split"] for r in assigned], [r["split"] for r in again])

    def test_leakage_is_detected_and_overconsumption_rejected(self) -> None:
        from openrestore.data.blind_real import assign_source_disjoint_splits, validate_source_disjoint

        leaking = [
            {"identifier": "gig", "split": "blind_real_train"},
            {"identifier": "gig", "split": "blind_real_test"},
        ]
        with self.assertRaisesRegex(ValueError, "leaks across"):
            validate_source_disjoint(leaking)

        rows = [{"identifier": f"i{i}"} for i in range(4)]
        with self.assertRaisesRegex(ValueError, "no train split"):
            assign_source_disjoint_splits(rows, validation_identifiers=2, test_identifiers=2)

    def test_scan_report_sizes_from_identifiers_not_clips(self) -> None:
        from openrestore.data.blind_real import scan_report

        rows = [_row(identifier=f"gig{i}", key=f"k{i}", license_type="BY",
                     tags="recorded live", venue="Hall" if i % 2 else None) for i in range(60)]
        rows += [_row(identifier=f"weak{i}", key=f"w{i}", license_type="BY", tags="live") for i in range(20)]
        rows += [_row(identifier=f"nc{i}", key=f"n{i}", license_type="BY-NC-SA", tags="recorded live") for i in range(30)]
        report = scan_report(rows, cap_per_identifier=2)

        self.assertEqual(report["segments_scanned"], 110)
        self.assertEqual(report["permissive_segments"], 80)
        self.assertEqual(report["high_confidence_identifiers"], 60)
        self.assertEqual(report["distinct_identifiers_by_confidence"]["weak_keyword"], 20)
        self.assertEqual(report["clips_after_cap"], 120)
        sizes = report["achievable_sizes"]
        self.assertEqual(
            sizes["train_identifiers"] + sizes["validation_identifiers"] + sizes["test_identifiers"], 60
        )


class RejectionTests(TestCase):
    def test_rejections_apply_per_item_and_per_clip(self) -> None:
        from openrestore.data.blind_real import is_rejected, load_rejections
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = Path(directory) / "rejected.tsv"
            path.write_text(
                "# a comment\n\n"
                "noisyGig\tharsh noise\n"
                "blind_real--mixedGig--00\tfirst excerpt is speech\n",
                encoding="utf-8",
            )
            rejections = load_rejections(path)
            self.assertEqual(len(rejections), 2)
            # Whole item.
            self.assertEqual(is_rejected(rejections, "noisyGig"), "harsh noise")
            self.assertEqual(is_rejected(rejections, "noisyGig", "blind_real--noisyGig--01"), "harsh noise")
            # One clip of an item whose other clip is fine.
            self.assertEqual(is_rejected(rejections, "mixedGig", "blind_real--mixedGig--00"), "first excerpt is speech")
            self.assertIsNone(is_rejected(rejections, "mixedGig", "blind_real--mixedGig--01"))
            self.assertIsNone(is_rejected(rejections, "goodGig", "blind_real--goodGig--00"))

    def test_a_sheet_collapses_to_item_level_when_every_clip_is_rejected(self) -> None:
        import csv
        from tempfile import TemporaryDirectory

        from openrestore.data.blind_real import verdicts_to_rejections

        rows = [
            # Both clips rejected: collapses to the identifier.
            {"identifier": "allBad", "clip_id": "blind_real--allBad--00", "verdict": "non", "note": "engine noise"},
            {"identifier": "allBad", "clip_id": "blind_real--allBad--01", "verdict": "non", "note": "engine noise"},
            # One clip rejected: stays clip-level.
            {"identifier": "halfBad", "clip_id": "blind_real--halfBad--00", "verdict": "non", "note": "speech"},
            {"identifier": "halfBad", "clip_id": "blind_real--halfBad--01", "verdict": "", "note": ""},
            # Approved spellings are not rejections.
            {"identifier": "fine", "clip_id": "blind_real--fine--00", "verdict": "ok", "note": ""},
            {"identifier": "fine", "clip_id": "blind_real--fine--01", "verdict": "", "note": ""},
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "verdicts.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            out = verdicts_to_rejections(path)

        self.assertIn("allBad", out)
        self.assertNotIn("blind_real--allBad--00", out)
        self.assertIn("blind_real--halfBad--00", out)
        self.assertNotIn("halfBad", out)
        self.assertNotIn("blind_real--halfBad--01", out)
        self.assertFalse(any("fine" in k for k in out))

    def test_field_recording_collections_are_excluded(self) -> None:
        from openrestore.data.blind_real import filter_candidates, is_non_music_collection

        self.assertTrue(is_non_music_collection("radio-aporee-maps"))
        self.assertFalse(is_non_music_collection("etree"))
        # A field recording titled "Audience before a show" trips the live keywords.
        aporee = _row(license_type="BY", title="Cergy, France - Audience before a show",
                      collection="radio-aporee-maps")
        self.assertEqual(filter_candidates([aporee]), [])


class ArtistDiversityTests(TestCase):
    """Source-disjointness by identifier does not stop one act dominating the set."""

    def test_items_sharing_any_credited_name_form_one_act(self):
        rows = [
            {"internet_archive_identifier": "a", "attribution": "Daniel Romano's Outfit; Carson McHone"},
            {"internet_archive_identifier": "b", "attribution": "Carson McHone"},
            {"internet_archive_identifier": "c", "attribution": "Daniel Romano's Outfit; Daniel Romano"},
            {"internet_archive_identifier": "d", "attribution": "Capsule Corp."},
            {"internet_archive_identifier": "e", "attribution": "Daniel Romano's Outfit"},
        ]
        groups = artist_groups(rows)
        self.assertEqual(groups["a"], groups["b"])
        self.assertEqual(groups["a"], groups["c"])
        self.assertEqual(groups["a"], groups["e"])
        self.assertNotEqual(groups["a"], groups["d"])
        # Named after the act credited most often, not whichever name sorts first.
        self.assertEqual(groups["a"], "daniel romano's outfit")

    def test_cap_keeps_the_clip_richest_items_of_an_act(self):
        rows = (
            [{"internet_archive_identifier": "many", "attribution": "The Old Silver Band", "id": f"many-{i}"}
             for i in range(2)]
            + [{"internet_archive_identifier": f"solo{i}", "attribution": "The Old Silver Band", "id": f"solo{i}-0"}
               for i in range(3)]
            + [{"internet_archive_identifier": "other", "attribution": "Capsule Corp.", "id": "other-0"}]
        )
        kept, report = cap_items_per_artist(rows, cap=2)
        kept_ids = {row["internet_archive_identifier"] for row in kept}
        self.assertIn("many", kept_ids)
        self.assertIn("other", kept_ids)
        self.assertEqual(report["identifiers_after"], 3)
        self.assertEqual(len(report["dropped"]), 2)

    def test_cap_does_not_depend_on_row_order(self):
        rows = [{"internet_archive_identifier": f"i{i}", "attribution": "The Same Band", "id": f"i{i}-0"}
                for i in range(6)]
        first, _ = cap_items_per_artist(rows, cap=3)
        second, _ = cap_items_per_artist(list(reversed(rows)), cap=3)
        self.assertEqual(
            {row["internet_archive_identifier"] for row in first},
            {row["internet_archive_identifier"] for row in second},
        )

    def test_an_unattributed_item_is_never_merged_with_another(self):
        rows = [{"internet_archive_identifier": "x", "attribution": ""},
                {"internet_archive_identifier": "y", "attribution": None}]
        groups = artist_groups(rows)
        self.assertNotEqual(groups["x"], groups["y"])


class RoundTwoSelectionTests(TestCase):
    """Selecting without the live proxy: exclude the predictable, spread the rest."""

    def test_ambient_and_noise_tags_are_recognised(self):
        self.assertTrue(looks_ambient_or_noise({"tags": "ambient; chillout; electronic"}))
        self.assertTrue(looks_ambient_or_noise({"tags": "holzkopf noise kaunas"}))
        self.assertTrue(looks_ambient_or_noise({"genre": "Dark Ambient"}))
        self.assertTrue(looks_ambient_or_noise({"tags": "ambeint; electricguitar"}), "a real typo in the data")
        self.assertFalse(looks_ambient_or_noise({"tags": "blues; live; guitar"}))
        # Word boundaries: these words contain the patterns but are not about noise.
        self.assertFalse(looks_ambient_or_noise({"title": "Noisettes at the Forum"}))
        self.assertFalse(looks_ambient_or_noise({"tags": "ambiental"}))

    def test_primary_collection_skips_the_generic_buckets(self):
        self.assertEqual(primary_collection({"collection": "community; netlabels"}), "netlabels")
        self.assertEqual(primary_collection({"collection": "opensource_audio; community"}), "opensource_audio")
        self.assertEqual(primary_collection({"collection": ""}), "unknown")

    def test_selection_spreads_across_collections(self):
        rows = ([{"identifier": f"big{i}", "collection": "netlabels", "artist": f"Band {i}"} for i in range(50)]
                + [{"identifier": f"small{i}", "collection": "cratediggers", "artist": f"Act {i}"} for i in range(5)])
        picked = select_diverse_candidates(rows, target=10, cap_per_identifier=1)
        collections = {row["primary_collection"] for row in picked}
        self.assertEqual(collections, {"netlabels", "cratediggers"},
                         "a large bucket must not fill the list on its own")

    def test_selection_respects_the_artist_cap_and_excludes_known_items(self):
        rows = [{"identifier": f"i{i}", "collection": "netlabels", "artist": "One Band"} for i in range(10)]
        rows += [{"identifier": "already", "collection": "netlabels", "artist": "Other Band"}]
        picked = select_diverse_candidates(rows, target=10, cap_per_identifier=1, cap_per_artist=3,
                                           exclude_identifiers=["already"])
        self.assertEqual(len(picked), 3, "one artist cannot exceed the cap")
        self.assertNotIn("already", {row["identifier"] for row in picked})

    def test_selection_is_reproducible(self):
        rows = [{"identifier": f"i{i}", "collection": "netlabels", "artist": f"Band {i}"} for i in range(40)]
        first = [row["identifier"] for row in select_diverse_candidates(rows, target=8, cap_per_identifier=1)]
        second = [row["identifier"] for row in select_diverse_candidates(list(reversed(rows)), target=8,
                                                                        cap_per_identifier=1)]
        self.assertEqual(first, second)

    def test_artist_names_reads_a_raw_catalogue_row(self):
        self.assertEqual(artist_names({"artist": "The Old Silver Band"}), ["the old silver band"])
        self.assertEqual(artist_names({"creator": "Capsule Corp."}), ["capsule corp."])


class ScreenPreconditionTests(TestCase):
    def test_a_missing_fingerprinter_raises_instead_of_reporting_a_clean_screen(self):
        """A missing fpcalc once produced 195 per-item failures and a printed
        "0 commercial matches", which reads as a screened set. It must fail loudly."""
        with self.assertRaises(FileNotFoundError):
            require_fpcalc("definitely-not-installed-fpcalc")


class AcoustidMeaningTests(TestCase):
    """A fingerprint match means different things in different pools."""

    def test_the_artists_own_catalogued_release_is_recognised(self):
        row = {"matches": [{"artists": ["Photophob"], "title": "Space Anthem Nr. 42"}]}
        self.assertEqual(acoustid_artist_agreement("Photophob", row), "same_artist")

    def test_a_label_uploading_its_own_artist_is_flagged_as_different(self):
        row = {"matches": [{"artists": ["Delta Is"]}]}
        self.assertEqual(acoustid_artist_agreement("Parenthetical Records", row), "different_artist")

    def test_no_match_is_not_evidence_of_anything(self):
        self.assertEqual(acoustid_artist_agreement("Anyone", {"matches": []}), "no_match")
        self.assertEqual(acoustid_artist_agreement("Anyone", {}), "no_match")

    def test_punctuation_and_case_do_not_break_agreement(self):
        row = {"matches": [{"artists": ["yukiga futte uresii"]}]}
        self.assertEqual(acoustid_artist_agreement("Yukiga Futte Uresii", row), "same_artist")
