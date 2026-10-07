"""Blind-Real excerpt windows: disjoint, deterministic, and inside the usable middle."""

from __future__ import annotations

from unittest import TestCase

from openrestore.data.blind_real_clips import EDGE_MARGIN_SECONDS, clip_start


class ClipWindowTests(TestCase):
    EXCERPT = 20.0
    SEED = 20260714

    def test_two_clips_of_one_item_never_overlap(self) -> None:
        for duration in (90.0, 120.0, 305.0, 627.0, 3600.0):
            starts = sorted(
                clip_start("gig", i, duration, self.EXCERPT, self.SEED, clips_per_identifier=2)
                for i in range(2)
            )
            self.assertGreaterEqual(
                starts[1], starts[0] + self.EXCERPT,
                f"overlap at duration {duration}: {starts}",
            )

    def test_windows_stay_inside_the_recording_and_off_the_edges(self) -> None:
        for duration in (90.0, 305.0, 627.0):
            for index in range(2):
                start = clip_start("gig", index, duration, self.EXCERPT, self.SEED, clips_per_identifier=2)
                self.assertGreaterEqual(start, EDGE_MARGIN_SECONDS)
                self.assertLessEqual(start + self.EXCERPT, duration - EDGE_MARGIN_SECONDS + 1.0)

    def test_deterministic_for_a_seed_and_responsive_to_it(self) -> None:
        a = clip_start("gig", 0, 305.0, self.EXCERPT, self.SEED, clips_per_identifier=2)
        b = clip_start("gig", 0, 305.0, self.EXCERPT, self.SEED, clips_per_identifier=2)
        c = clip_start("gig", 0, 305.0, self.EXCERPT, 7, clips_per_identifier=2)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_retries_move_the_window(self) -> None:
        base = clip_start("gig", 0, 305.0, self.EXCERPT, self.SEED, clips_per_identifier=2)
        moved = clip_start("gig", 0, 305.0, self.EXCERPT, self.SEED, attempt=1, clips_per_identifier=2)
        self.assertNotEqual(base, moved)

    def test_recording_too_short_for_margins_centres_the_excerpt(self) -> None:
        start = clip_start("gig", 0, 25.0, self.EXCERPT, self.SEED, clips_per_identifier=2)
        self.assertAlmostEqual(start, 2.5, places=3)
        self.assertGreaterEqual(start, 0.0)

    def test_different_items_get_different_windows(self) -> None:
        starts = {
            clip_start(f"gig{i}", 0, 305.0, self.EXCERPT, self.SEED, clips_per_identifier=2)
            for i in range(30)
        }
        self.assertGreater(len(starts), 10, "windows should not collapse onto one offset")
