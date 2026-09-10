from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

import numpy as np
import soundfile as sf
from scipy import signal

from openrestore.degradations.core import load_yaml, read_jsonl, run_ffmpeg_codec, sha256_file, write_jsonl
from openrestore.degradations.effects import apply_operation
from openrestore.degradations.pipeline import CANONICAL_DEGRADATION_IDS, apply_recipe, render_degradations, validate_config, write_hdf5_shards

SAMPLE_RATE = 44_100


def _fixture_audio(seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * seconds), dtype=np.float32) / SAMPLE_RATE
    left = 0.24 * np.sin(2 * math.pi * 220 * t) + 0.08 * np.sin(2 * math.pi * 3_000 * t)
    right = 0.22 * np.sin(2 * math.pi * 330 * t + 0.3) + 0.06 * np.sin(2 * math.pi * 5_500 * t)
    return np.column_stack([left, right]).astype(np.float32)


def _write_audio(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")


def _band_energy(audio: np.ndarray, low: float, high: float) -> float:
    freqs, spectrum = signal.welch(np.mean(audio, axis=1), SAMPLE_RATE, nperseg=2048)
    mask = (freqs >= low) & (freqs <= high)
    return float(np.mean(spectrum[mask]))


class DegradationPrimitiveTests(TestCase):
    def test_canonical_registry_has_exactly_24_ids(self) -> None:
        config = load_yaml(Path("configs/degradations/single/v0_1.yaml"))
        validate_config(config)
        self.assertEqual(tuple(recipe["id"] for recipe in config["recipes"]), CANONICAL_DEGRADATION_IDS)
        self.assertNotIn("volume", CANONICAL_DEGRADATION_IDS)
        self.assertEqual(len(CANONICAL_DEGRADATION_IDS), 24)

    def test_new_canonical_effects_are_audible_and_deterministic(self) -> None:
        audio = _fixture_audio(0.25)
        cases = [
            ("spectral_eq", None, {"mode": "low_mid_emphasis", "gain_db": 12}),
            ("compression", None, {"mode": "strong_compression"}),
            ("saturation_overdrive", "soft", {"drive": 4.0}),
            ("dropouts_glitches", "dropout", {"rate_hz": 8.0, "min_duration_ms": 25, "max_duration_ms": 45}),
            ("neural_codec", None, {"intermediate_sample_rate": 8_000, "quantization_bits": 5}),
            ("channel_damage", "attenuation", {"target_channel": 1, "gain_db": -18}),
            ("pitch_speed_instability", None, {"wow_rate_hz": 0.5, "wow_depth_percent": 2.0, "flutter_rate_hz": 6.0, "flutter_depth_percent": 0.6}),
        ]
        for primitive, variant, params in cases:
            first, first_params = apply_operation(audio, SAMPLE_RATE, primitive, variant, params.copy(), np.random.default_rng(42))
            second, second_params = apply_operation(audio, SAMPLE_RATE, primitive, variant, params.copy(), np.random.default_rng(42))
            self.assertEqual(first.shape, audio.shape, primitive)
            self.assertTrue(np.isfinite(first).all(), primitive)
            self.assertTrue(np.allclose(first, second), primitive)
            self.assertEqual(first_params, second_params, primitive)
            self.assertGreater(float(np.mean(np.abs(first - audio))), 1e-4, primitive)

    def test_all_primitives_are_deterministic_and_seeded(self) -> None:
        audio = _fixture_audio()
        recipes = [
            ("eq_coloration", "boom", {"gain_db": {"min": 3, "max": 5}, "frequency_hz": 220}),
            ("dynamics", "compression", {"threshold_db": -18, "ratio": {"min": 2, "max": 4}}),
            ("reverb_room", "small", {"wet": {"min": 0.1, "max": 0.2}, "decay_seconds": 0.25}),
            ("gain_level", "low_volume", {"gain_db": {"min": -8, "max": -4}}),
            ("clipping_distortion", "soft", {"drive": {"min": 1.2, "max": 1.8}}),
            ("stereo_spatial", "width", {"width": {"min": 0.3, "max": 0.8}}),
            ("bandwidth_filtering", "lowpass", {"cutoff_hz": {"min": 4_000, "max": 8_000}}),
            ("noise_interference", "broadband", {"snr_db": {"min": 18, "max": 24}}),
            ("noise_interference", "clicks_crackle", {"click_rate_hz": {"min": 1, "max": 3}, "crackle_rate_hz": {"min": 8, "max": 20}, "click_level_db": -8, "crackle_level_db": -26}),
            ("device_mic_response", "consumer_mic", {"high_hz": 6_000, "self_noise_snr_db": 28}),
            ("codec_resampling", "resampling", {"intermediate_sample_rate": {"min": 12_000, "max": 18_000}}),
        ]
        for primitive, variant, params in recipes:
            recipe = {
                "id": f"test_{primitive}",
                "severity": "medium",
                "operations": [{"primitive": primitive, "variant": variant, "parameters": params}],
            }
            first, first_params = apply_recipe(audio, SAMPLE_RATE, "item", recipe, 123)
            second, second_params = apply_recipe(audio, SAMPLE_RATE, "item", recipe, 123)
            third, third_params = apply_recipe(audio, SAMPLE_RATE, "item", recipe, 456)
            self.assertEqual(first.shape, audio.shape, primitive)
            self.assertTrue(np.isfinite(first).all(), primitive)
            self.assertLessEqual(float(np.max(np.abs(first))), 1.0, primitive)
            self.assertTrue(np.allclose(first, second), primitive)
            self.assertEqual(first_params, second_params, primitive)
            self.assertNotEqual(first_params, third_params, primitive)

    def test_behavior_proxies_move_in_expected_direction(self) -> None:
        audio = _fixture_audio()
        rng = np.random.default_rng(1)
        eq, _ = apply_operation(audio, SAMPLE_RATE, "eq_coloration", "boom", {"gain_db": 6, "frequency_hz": 220}, rng)
        self.assertGreater(_band_energy(eq, 80, 300), _band_energy(audio, 80, 300))

        gain, params = apply_operation(audio, SAMPLE_RATE, "gain_level", "low_volume", {"gain_db": -8}, rng)
        self.assertLess(np.max(np.abs(gain)), np.max(np.abs(audio)))
        self.assertFalse(params["hidden_clipping"])

        clipped, params = apply_operation(audio * 2.0, SAMPLE_RATE, "clipping_distortion", "hard", {"drive": 2.5, "threshold": 0.55}, rng)
        self.assertGreater(params["clipped_sample_ratio"], 0)
        self.assertLessEqual(float(np.max(np.abs(clipped))), 1.0)

        mono, params = apply_operation(audio, SAMPLE_RATE, "stereo_spatial", "mono", {}, rng)
        self.assertTrue(np.allclose(mono[:, 0], mono[:, 1]))

        lowpass, _ = apply_operation(audio, SAMPLE_RATE, "bandwidth_filtering", "lowpass", {"cutoff_hz": 1_000}, rng)
        self.assertLess(_band_energy(lowpass, 3_000, 7_000), _band_energy(audio, 3_000, 7_000))

        noisy, _ = apply_operation(audio, SAMPLE_RATE, "noise_interference", "broadband", {"snr_db": 12}, rng)
        self.assertGreater(np.mean(np.square(noisy - audio)), 0)


        clicks, params = apply_operation(audio, SAMPLE_RATE, "noise_interference", "clicks_crackle", {"click_rate_hz": 2, "crackle_rate_hz": 12, "click_level_db": -2, "crackle_level_db": -18, "click_duration_ms": 3, "crackle_duration_ms": 0.5}, np.random.default_rng(7))
        self.assertGreater(params["click_count"] + params["crackle_count"], 0)
        self.assertEqual(params["click_duration_ms"], 3)
        self.assertEqual(params["crackle_duration_ms"], 0.5)
        self.assertGreater(np.mean(np.square(clicks - audio)), 0)

        reverb, _ = apply_operation(audio, SAMPLE_RATE, "reverb_room", "small", {"wet": 0.25, "decay_seconds": 0.35}, rng)
        self.assertGreater(np.mean(np.abs(reverb[-4_000:])), np.mean(np.abs(audio[-4_000:])) * 0.8)

        damaged, params = apply_operation(audio, SAMPLE_RATE, "device_mic_response", "bluetooth_small_speaker_recapture", {}, rng)
        self.assertEqual(params["variant"], "bluetooth_small_speaker_recapture")
        self.assertTrue(params["child_operations"])
        self.assertEqual(damaged.shape, audio.shape)

        distant, distant_params = apply_operation(audio, SAMPLE_RATE, "distant_mic_capture", "room_capture", {"distance_m": 1.5, "absorption": 0.45, "air_absorption_cutoff_hz": 12_000}, np.random.default_rng(2))
        self.assertEqual(distant.shape, audio.shape)
        self.assertGreaterEqual(distant_params["room_noise_snr_db"], 100)

    def test_ariel_effect_registry_is_deterministic_and_tracks_effects(self) -> None:
        audio = _fixture_audio(0.25)
        effects = (
            "comp", "punch", "xband", "bright", "dark", "airy", "boom", "clarity",
            "mud", "warm", "vocal", "small", "big", "mix", "stereo", "clip", "volume",
        )
        for effect in effects:
            first, first_params = apply_operation(audio, SAMPLE_RATE, "ariel", effect, {}, np.random.default_rng(42))
            second, second_params = apply_operation(audio, SAMPLE_RATE, "ariel", effect, {}, np.random.default_rng(42))
            self.assertEqual(first.shape, audio.shape, effect)
            self.assertTrue(np.isfinite(first).all(), effect)
            self.assertTrue(np.allclose(first, second), effect)
            self.assertEqual(first_params, second_params, effect)
            self.assertEqual(first_params["effect"], effect)

    def test_mud_matches_sonicmaster_ariel_filter(self) -> None:
        audio = _fixture_audio(0.25)
        output, params = apply_operation(audio, SAMPLE_RATE, "ariel", "mud", {}, np.random.default_rng(42))
        attenuation = params["gain"]
        expected_sos = signal.cheby2(2, attenuation, [200, 500], "bandpass", fs=SAMPLE_RATE, output="sos")
        expected = signal.sosfilt(expected_sos, audio, axis=0)
        self.assertTrue(np.array_equal(output, expected))

    def test_vocal_matches_sonicmaster_ariel_filter(self) -> None:
        audio = _fixture_audio(0.25)
        output, params = apply_operation(audio, SAMPLE_RATE, "ariel", "vocal", {}, np.random.default_rng(42))
        attenuation = params["gain"]
        expected_sos = signal.cheby2(2, attenuation, [350, 3_500], "bandstop", fs=SAMPLE_RATE, output="sos")
        expected = signal.sosfilt(expected_sos, audio, axis=0)
        self.assertTrue(np.array_equal(output, expected))

    def test_asset_and_external_tool_failures_are_actionable(self) -> None:
        audio = _fixture_audio(0.1)
        with self.assertRaisesRegex(FileNotFoundError, "mic_ir_dir"):
            apply_operation(audio, SAMPLE_RATE, "ariel", "mic", {}, np.random.default_rng(1))
        with self.assertRaisesRegex(FileNotFoundError, "real_rir_dir"):
            apply_operation(audio, SAMPLE_RATE, "ariel", "real", {}, np.random.default_rng(1))
        with TemporaryDirectory() as directory:
            rir_dir = Path(directory) / "nested"
            impulse = np.zeros(128, dtype=np.float32)
            impulse[0] = 1.0
            _write_audio(rir_dir / "test_rir.wav", np.column_stack([impulse, impulse]))
            rendered, rendered_params = apply_operation(audio, SAMPLE_RATE, "ariel", "real", {"real_rir_dir": directory}, np.random.default_rng(1))
            self.assertEqual(rendered.shape, audio.shape)
            self.assertEqual(rendered_params["rir_name"], "test_rir")
        with patch("openrestore.degradations.core.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "FFmpeg on PATH"):
                run_ffmpeg_codec(audio, SAMPLE_RATE, "mp3", "64k")
        with self.assertRaisesRegex(ValueError, "max_order"):
            apply_operation(audio, SAMPLE_RATE, "distant_mic_capture", "room_capture", {"max_order": 11}, np.random.default_rng(1))

    @skipUnless(shutil.which("ffmpeg") is not None, "ffmpeg is required for codec roundtrip")
    def test_codec_roundtrip_produces_valid_audio(self) -> None:
        audio = _fixture_audio(0.5)
        result, params = apply_operation(audio, SAMPLE_RATE, "codec_resampling", "mp3", {"bitrate": "96k"}, np.random.default_rng(1))
        self.assertEqual(result.shape, audio.shape)
        self.assertEqual(params["variant"], "mp3")
        self.assertTrue(np.isfinite(result).all())


class DegradationPipelineTests(TestCase):
    def test_config_validation_and_render_manifest(self) -> None:
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            clean_root = tmp / "clean"
            clean_path = clean_root / "train" / "sonicmaster_clean" / "clip.wav"
            _write_audio(clean_path, _fixture_audio())
            manifest = tmp / "index.jsonl"
            write_jsonl(
                manifest,
                [
                    {
                        "id": "clip",
                        "dataset": "sonicmaster_clean",
                        "split": "train",
                        "source_id": "source",
                        "clean_path": "train/sonicmaster_clean/clip.wav",
                        "duration_seconds": 1.0,
                        "sample_rate": SAMPLE_RATE,
                        "channels": 2,
                    }
                ],
            )
            config = tmp / "config.yaml"
            config.write_text(
                """
version: test
recipes:
  - id: single_eq_test
    severity: mild
    operations:
      - primitive: eq_coloration
        variant: comb_filter_phase_coloration
        parameters:
          delay_ms:
            min: 2
            max: 5
          mix:
            min: 0.2
            max: 0.4
""".strip(),
                encoding="utf-8",
            )
            validate_config(__import__("yaml").safe_load(config.read_text()))
            with self.assertRaisesRegex(ValueError, "exactly one operation"):
                validate_config({"recipes": [{"id": "invalid", "severity": "test", "operations": [{"primitive": "eq_coloration"}, {"primitive": "dynamics"}]}]})
            output_root = tmp / "degraded"
            output_manifest = tmp / "degraded.jsonl"
            checksums = tmp / "checksums.jsonl"
            rows = render_degradations(manifest, clean_root, output_root, config, output_manifest, checksums, 99)
            self.assertEqual(len(rows), 1)
            for row in rows:
                path = output_root / row["degraded_path"]
                self.assertTrue(path.is_file())
                self.assertEqual(row["degraded_audio_sha256"], sha256_file(path))
                self.assertIn("degradation_tracking", row)
                self.assertIn("degradation_params", row)
                self.assertEqual(row["degradation_tracking"]["item_seed"], row["degradation_seed"])
            self.assertEqual(len(read_jsonl(checksums)), 1)
            shards_dir = tmp / "release" / "shards"
            output_index = tmp / "release" / "index.jsonl"
            shard_rows = write_hdf5_shards(output_root, output_manifest, shards_dir, output_index, shard_size=1)
            self.assertEqual(len(shard_rows), 1)
            self.assertEqual(shard_rows[0]["degraded_audio_shard"], "shards/degraded-00000.h5")
            import h5py
            with h5py.File(shards_dir / "degraded-00000.h5", "r") as shard:
                self.assertEqual(shard.attrs["sample_rate"], SAMPLE_RATE)
                self.assertEqual(shard["audio"].shape, (1, SAMPLE_RATE, 2))
                self.assertEqual(shard["item_id"][0].decode(), "clip--single_eq_test")
            self.assertEqual(read_jsonl(output_index), shard_rows)

    def test_boundary_parameters_are_seed_independent(self) -> None:
        recipe = {
            "id": "review_min_noise",
            "severity": "minimum_preview",
            "operations": [{"primitive": "noise_interference", "variant": "broadband", "parameters": {"snr_db": 25, "review_boundary": "minimum"}}],
        }
        first, first_params = apply_recipe(_fixture_audio(), SAMPLE_RATE, "item", recipe, 1)
        second, second_params = apply_recipe(_fixture_audio(), SAMPLE_RATE, "item", recipe, 2)
        self.assertNotEqual(first_params[0]["seed"], second_params[0]["seed"])
        self.assertFalse(np.allclose(first, second))
        self.assertEqual(first_params[0]["parameters"], second_params[0]["parameters"])
        self.assertEqual(first_params[0]["parameters"]["snr_db"], 25)
        self.assertEqual(first_params[0]["parameters"]["review_boundary"], "minimum")

    def test_cli_list_recipes_and_render(self) -> None:
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            clean_root = tmp / "clean"
            clean_path = clean_root / "train" / "sonicmaster_clean" / "clip.wav"
            _write_audio(clean_path, _fixture_audio(0.5))
            manifest = tmp / "index.jsonl"
            write_jsonl(
                manifest,
                [{"id": "clip", "dataset": "sonicmaster_clean", "split": "train", "source_id": "source", "clean_path": "train/sonicmaster_clean/clip.wav", "duration_seconds": 0.5, "sample_rate": SAMPLE_RATE, "channels": 2}],
            )
            config = tmp / "config.yaml"
            config.write_text(
                """
version: test
recipes:
  - id: single_gain_test
    severity: mild
    operations:
      - primitive: gain_level
        variant: low_volume
        parameters:
          gain_db:
            min: -6
            max: -3
""".strip(),
                encoding="utf-8",
            )
            listed = subprocess.run(
                [sys.executable, "-m", "openrestore.degradations.cli", "list-recipes", "--config", str(config)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("single_gain_test", listed.stdout)
            output_root = tmp / "degraded"
            output_manifest = tmp / "degraded.jsonl"
            checksums = tmp / "checksums.jsonl"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openrestore.degradations.cli",
                    "render",
                    "--manifest",
                    str(manifest),
                    "--clean-root",
                    str(clean_root),
                    "--output-root",
                    str(output_root),
                    "--config",
                    str(config),
                    "--output-manifest",
                    str(output_manifest),
                    "--checksums",
                    str(checksums),
                    "--seed",
                    "7",
                    "--quiet",
                ],
                check=True,
            )
            rows = read_jsonl(output_manifest)
            self.assertEqual(len(rows), 1)
            self.assertTrue((output_root / rows[0]["degraded_path"]).exists())
            release_root = tmp / "release"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "openrestore.degradations.cli",
                    "shard",
                    "--output-root", str(output_root),
                    "--manifest", str(output_manifest),
                    "--shards-dir", str(release_root / "shards"),
                    "--output-index", str(release_root / "index.jsonl"),
                    "--shard-size", "1",
                    "--quiet",
                ],
                check=True,
            )
            index_rows = read_jsonl(release_root / "index.jsonl")
            self.assertEqual(index_rows[0]["degraded_audio_shard"], "shards/degraded-00000.h5")
            self.assertTrue((release_root / index_rows[0]["degraded_audio_shard"]).is_file())
