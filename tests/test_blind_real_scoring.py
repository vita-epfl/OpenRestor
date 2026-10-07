"""Blind-Real scoring: no-reference descriptors and item-level aggregation."""

from __future__ import annotations

import math
from unittest import TestCase

import numpy as np

from openrestore.metrics.blind_real import aggregate, no_reference_descriptors, score_clip

SAMPLE_RATE = 44100


def _tone(seconds: float = 1.0, freq: float = 440.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    mono = amp * np.sin(2 * math.pi * freq * t)
    return np.column_stack([mono, mono]).astype(np.float32)


class AggregationTests(TestCase):
    def test_an_item_with_two_clips_does_not_weigh_twice(self) -> None:
        # One item contributes two clips scoring 0, another contributes one scoring 3.
        rows = [
            {"id": "a0", "internet_archive_identifier": "loud", "score": 0.0},
            {"id": "a1", "internet_archive_identifier": "loud", "score": 0.0},
            {"id": "b0", "internet_archive_identifier": "quiet", "score": 3.0},
        ]
        report = aggregate(rows)
        self.assertEqual(report["clips"], 3)
        self.assertEqual(report["identifiers"], 2)
        # Naive clip averaging would give 1.0; per-identifier averaging gives 1.5.
        self.assertAlmostEqual(np.mean([r["score"] for r in rows]), 1.0)
        self.assertAlmostEqual(report["dataset"]["score"]["mean"], 1.5)

    def test_per_identifier_breakdown_is_reported(self) -> None:
        rows = [
            {"id": "a0", "internet_archive_identifier": "gig", "score": 1.0},
            {"id": "a1", "internet_archive_identifier": "gig", "score": 3.0},
        ]
        report = aggregate(rows)
        self.assertEqual(len(report["per_identifier"]), 1)
        item = report["per_identifier"][0]
        self.assertEqual(item["identifier"], "gig")
        self.assertEqual(item["clips"], 2)
        self.assertAlmostEqual(item["metrics"]["score"], 2.0)

    def test_empty_input_is_handled(self) -> None:
        report = aggregate([])
        self.assertEqual(report["clips"], 0)
        self.assertEqual(report["identifiers"], 0)


class DescriptorTests(TestCase):
    def test_descriptors_respond_in_the_expected_direction(self) -> None:
        clean = _tone()
        rng = np.random.default_rng(0)
        noisy = np.clip(clean + rng.normal(0, 0.05, clean.shape).astype(np.float32), -1, 1)

        c, n = no_reference_descriptors(clean, SAMPLE_RATE), no_reference_descriptors(noisy, SAMPLE_RATE)
        # Added broadband noise raises the floor and makes the spectrum flatter.
        self.assertGreater(n["noise_floor_db"], c["noise_floor_db"])
        self.assertGreater(n["spectral_flatness"], c["spectral_flatness"])

        # Band-limiting the tone's partials reduces the measured bandwidth.
        narrow = np.copy(clean)
        spectrum = np.fft.rfft(narrow[:, 0])
        freqs = np.fft.rfftfreq(narrow.shape[0], 1 / SAMPLE_RATE)
        spectrum[freqs > 2000] = 0
        band = np.fft.irfft(spectrum, n=narrow.shape[0]).astype(np.float32)
        narrow = np.column_stack([band, band])
        self.assertLessEqual(
            no_reference_descriptors(narrow, SAMPLE_RATE)["bandwidth_hz"],
            c["bandwidth_hz"] + 1.0,
        )

    def test_clipping_is_detected(self) -> None:
        loud = np.clip(_tone(amp=2.0), -1.0, 1.0)
        d = no_reference_descriptors(loud, SAMPLE_RATE)
        self.assertGreater(d["clipped_sample_ratio"], 0.1)
        self.assertLess(d["crest_factor_db"], 6.0)

    def test_no_restoration_gives_zero_deltas(self) -> None:
        audio = _tone()
        row = score_clip(audio, audio, SAMPLE_RATE)
        deltas = [v for k, v in row.items() if k.startswith("delta_")]
        self.assertTrue(deltas)
        for value in deltas:
            self.assertAlmostEqual(value, 0.0, places=10)

    def test_empty_audio_does_not_raise(self) -> None:
        self.assertEqual(no_reference_descriptors(np.zeros((0, 2), dtype=np.float32), SAMPLE_RATE), {})
