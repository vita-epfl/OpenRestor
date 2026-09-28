from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

import numpy as np
import soundfile as sf

from openrestor.degradations.core import write_jsonl
from openrestor.metrics.core import pairwise_metrics
from openrestor.metrics.pipeline import no_restoration, score, validate_restored_manifest

SAMPLE_RATE = 44_100
CONFIG = Path("configs/evaluation/metrics.yaml")


def _audio(seconds: float = 1.0) -> np.ndarray:
    t = np.arange(round(seconds * SAMPLE_RATE), dtype=np.float32) / SAMPLE_RATE
    return np.column_stack(
        [
            0.25 * np.sin(2 * math.pi * 220 * t) + 0.06 * np.sin(2 * math.pi * 6_000 * t),
            0.23 * np.sin(2 * math.pi * 330 * t + 0.2) + 0.05 * np.sin(2 * math.pi * 8_000 * t),
        ]
    ).astype(np.float32)


def _write(path: Path, audio: np.ndarray, rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, rate, subtype="PCM_16")


def _row(item_id: str, effect: str, severity: str = "test") -> dict[str, object]:
    return {
        "id": item_id,
        "dataset": "fixture",
        "split": "validation",
        "clean_id": "clean-1",
        "clean_path": "clean/clean.wav",
        "degraded_path": f"degraded/{item_id}.wav",
        "degradation_recipe_id": f"single_{effect}",
        "severity": severity,
        "duration_seconds": 1.0,
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "degradation_params": [{"parameters": {"effect": effect}, "variant": effect}],
    }


class MetricTests(TestCase):
    def test_metric_directions_and_determinism(self) -> None:
        from openrestor.degradations.core import load_yaml

        config = load_yaml(CONFIG)
        clean = _audio()
        exact = pairwise_metrics(clean, clean.copy(), config)
        quiet = pairwise_metrics(clean, clean * 0.25, config)
        lowpass = np.column_stack(
            [np.convolve(clean[:, channel], np.ones(15) / 15, mode="same") for channel in range(2)]
        )
        filtered = pairwise_metrics(clean, lowpass.astype(np.float32), config)
        noisy = pairwise_metrics(
            clean, clean + np.random.default_rng(1).normal(0, 0.04, clean.shape), config
        )
        clipped = pairwise_metrics(clean, np.clip(clean * 4, -0.4, 0.4), config)
        reverb = pairwise_metrics(clean, clean + np.roll(clean, 600, axis=0) * 0.3, config)
        mono = pairwise_metrics(
            clean, np.repeat(clean.mean(axis=1, keepdims=True), 2, axis=1), config
        )
        self.assertLess(exact["l1"], 1e-10)
        self.assertGreater(exact["snr_db"], quiet["snr_db"])
        self.assertLess(exact["lsd_db"], filtered["lsd_db"])
        self.assertLess(exact["rmse"], noisy["rmse"])
        self.assertLess(exact["log_mel_ssim"], 1.000001)
        self.assertGreater(exact["log_mel_ssim"], clipped["log_mel_ssim"])
        self.assertGreater(exact["log_mel_ssim"], reverb["log_mel_ssim"])
        self.assertGreater(exact["log_mel_ssim"], mono["log_mel_ssim"])
        # Room metrics operate on the paired clean-to-evaluated transfer: an
        # identity transfer has no residual tail, whereas a delayed reflection
        # lowers DRR and increases residual tail energy.
        self.assertEqual(exact["rt60_s"], 0.0)
        self.assertEqual(exact["drr_db"], 80.0)
        self.assertEqual(exact["late_tail_db"], -80.0)
        self.assertLess(reverb["drr_db"], exact["drr_db"])
        self.assertGreater(reverb["late_tail_db"], exact["late_tail_db"])
        self.assertGreaterEqual(reverb["rt60_s"], 0.0)
        self.assertEqual(exact, pairwise_metrics(clean, clean.copy(), config))

    def test_scoring_manifest_validation_and_no_restoration(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            clean_root, degraded_root = root / "audio", root / "audio"
            clean = _audio()
            noisy = clean + np.random.default_rng(3).normal(0, 0.02, clean.shape).astype(np.float32)
            _write(clean_root / "clean/clean.wav", clean)
            _write(degraded_root / "degraded/item-noise.wav", noisy)
            _write(degraded_root / "degraded/item-bright.wav", clean * 0.9)
            rows = [_row("item-noise", "noise"), _row("item-bright", "bright")]
            manifest = root / "degraded.jsonl"
            write_jsonl(manifest, rows)
            restored_root, restored_manifest = root / "restored", root / "restored.jsonl"
            no_restoration(manifest, degraded_root, restored_root, restored_manifest)
            valid, failures = validate_restored_manifest(manifest, restored_manifest)
            self.assertEqual(len(valid), 2)
            self.assertFalse(failures)
            report = score(
                manifest, degraded_root, clean_root, restored_manifest, CONFIG, root / "scores"
            )
            self.assertEqual(report["ranking"], "diagnostic_only_no_aggregate")
            self.assertEqual(report["items"]["scored"], 2)
            self.assertIn("noise_interference", report["by_category"])
            self.assertIn("eq_coloration", report["by_category"])
            self.assertAlmostEqual(report["overall"]["l1"]["improvement"], 0.0, places=6)
            self.assertTrue((root / "scores/per_item_scores.jsonl").is_file())
            self.assertTrue((root / "scores/report.md").is_file())
            self.assertTrue((root / "scores/failures.json").is_file())

    def test_invalid_manifest_and_audio_failures_are_written(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "degraded.jsonl"
            write_jsonl(manifest, [_row("item", "codec")])
            restored = root / "restored.jsonl"
            write_jsonl(
                restored,
                [
                    {"id": "unknown", "restored_audio_path": "missing.wav"},
                    {"id": "unknown", "restored_audio_path": "other.wav"},
                ],
            )
            invalid_audio = root / "wrong-rate.wav"
            _write(invalid_audio, _audio(), 48_000)
            write_jsonl(restored, [{"id": "item", "restored_audio_path": invalid_audio.name}])
            valid_audio, audio_failures = validate_restored_manifest(manifest, restored)
            self.assertFalse(valid_audio)
            self.assertEqual(audio_failures[0]["code"], "invalid_restored_audio")
            write_jsonl(
                restored,
                [
                    {"id": "unknown", "restored_audio_path": "missing.wav"},
                    {"id": "unknown", "restored_audio_path": "other.wav"},
                ],
            )
            valid, failures = validate_restored_manifest(manifest, restored)
            self.assertFalse(valid)
            self.assertGreaterEqual(len(failures), 3)
            with self.assertRaisesRegex(ValueError, "failures"):
                score(manifest, root, root, restored, CONFIG, root / "scores")
            failure_doc = json.loads((root / "scores/failures.json").read_text())
            self.assertTrue(failure_doc["failures"])

    def test_cli_validate_and_no_restoration(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            clean = _audio()
            _write(root / "audio/clean/clean.wav", clean)
            _write(root / "audio/degraded/item.wav", clean * 0.5)
            manifest = root / "degraded.jsonl"
            write_jsonl(manifest, [_row("item", "volume")])
            restored_manifest = root / "out/restored.jsonl"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openrestor.metrics.cli",
                    "no-restoration",
                    "--degraded-manifest",
                    str(manifest),
                    "--degraded-root",
                    str(root / "audio"),
                    "--output-root",
                    str(root / "out/audio"),
                    "--output-manifest",
                    str(restored_manifest),
                ],
                check=True,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openrestor.metrics.cli",
                    "validate-restored",
                    "--degraded-manifest",
                    str(manifest),
                    "--restored-manifest",
                    str(restored_manifest),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn('"valid_items": 1', result.stdout)


class _FakePerceptualBackend:
    identifier = "fake-perceptual-v1"

    @staticmethod
    def _vector(audio: np.ndarray) -> np.ndarray:
        mono = audio.mean(axis=1)
        return np.array(
            [[mono.mean(), mono.std(), np.mean(np.abs(mono)), mono.max()]], dtype=np.float64
        )

    def clap(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        return self._vector(audio)

    def fadtk(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        vector = self._vector(audio)[0]
        return np.vstack([vector, vector * 1.001])

    def fadtk_distance(self, reference: np.ndarray, estimate: np.ndarray) -> float:
        return float(np.sum((reference.mean(axis=0) - estimate.mean(axis=0)) ** 2))

    def fadtk_fma_pop_distance(self, estimate: np.ndarray) -> float:
        return float(np.sum(estimate.mean(axis=0) ** 2))

    def verify_fma_pop(self) -> dict[str, object]:
        return {"backend": "fake-fadtk", "reference": "fma_pop"}

    def aesthetics(self, audio: np.ndarray, sample_rate: int) -> dict[str, float]:
        value = float(np.mean(np.abs(audio)))
        return {"CE": value, "CU": value + 0.1, "PC": value + 0.2, "PQ": value + 0.3}


class PerceptualMetricTests(TestCase):
    def test_mock_perceptual_scoring_and_metadata_join(self) -> None:
        from openrestor.metrics.perceptual import perceptual_score

        with TemporaryDirectory() as directory:
            root = Path(directory)
            clean = _audio()
            _write(root / "audio/clean/clean.wav", clean)
            _write(root / "audio/degraded/a.wav", clean * 0.75)
            _write(root / "audio/degraded/b.wav", clean * 0.55)
            manifest = root / "degraded.jsonl"
            write_jsonl(manifest, [_row("a", "noise"), _row("b", "codec")])
            restored = root / "restoration.jsonl"
            write_jsonl(
                restored,
                [
                    {
                        "id": "a",
                        "restored_audio_path": "audio/degraded/a.wav",
                        "inference_steps": 25,
                    },
                    {
                        "id": "b",
                        "restored_audio_path": "audio/degraded/b.wav",
                        "timestamp": "2026-08-14T00:00:00Z",
                    },
                ],
            )
            config = root / "perceptual.yaml"
            config.write_text(
                "benchmark_version: v0.1\nsubmission_id: test\nmetric_pack: perceptual_gpu_v0_1\n"
                "validation: {duration_tolerance_samples: 0}\ncache: {directory: "
                + str(root / "cache")
                + "}\n",
                encoding="utf-8",
            )
            report = perceptual_score(
                manifest,
                root / "audio",
                root / "audio",
                restored,
                config,
                root / "scores",
                backend=_FakePerceptualBackend(),
            )
            self.assertEqual(report["items"]["scored"], 2)
            self.assertIn("fadtk_fma_pop", report["overall"])
            metadata = [
                json.loads(line)
                for line in (root / "scores/restoration_metadata.jsonl").read_text().splitlines()
            ]
            self.assertEqual(metadata[0]["degradation_type"], "noise")
            self.assertEqual(metadata[0]["inference_steps"], 25)
            cache_files = list((root / "cache/embeddings").rglob("*.npz"))
            self.assertTrue(cache_files)
            repeated = perceptual_score(
                manifest,
                root / "audio",
                root / "audio",
                restored,
                config,
                root / "scores-repeat",
                backend=_FakePerceptualBackend(),
            )
            self.assertEqual(report["overall"]["clap_cosine"], repeated["overall"]["clap_cosine"])


@skipUnless(
    os.environ.get("OPENRESTORE_PERCEPTUAL_INTEGRATION") == "1",
    "set OPENRESTORE_PERCEPTUAL_INTEGRATION=1 after running setup-perceptual",
)
class RealPerceptualIntegrationTests(TestCase):
    def test_real_backends_encode_audio(self) -> None:
        import torch

        if not torch.cuda.is_available():
            self.skipTest("CUDA is required")
        from openrestor.metrics.perceptual import LearnedBackends

        cache = Path(
            os.environ.get("OPENRESTORE_PERCEPTUAL_CACHE", "~/.cache/openrestor/perceptual-v0_1")
        ).expanduser()
        backend = LearnedBackends(cache, "cuda")
        audio = _audio()
        self.assertEqual(backend.clap(audio, SAMPLE_RATE).shape[0], 1)
        self.assertGreaterEqual(backend.fadtk(audio, SAMPLE_RATE).shape[0], 1)
        self.assertEqual(set(backend.aesthetics(audio, SAMPLE_RATE)), {"CE", "CU", "PC", "PQ"})
