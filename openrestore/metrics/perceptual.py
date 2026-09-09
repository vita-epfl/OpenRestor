"""Optional GPU perceptual metrics matching ARIEL's CLAP and FADTK workflow."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

import librosa
import numpy as np
import soundfile as sf

from openrestore.degradations.core import load_yaml, sha256_file, write_jsonl

from .core import category_for_row, effect_name
from .pipeline import _audio, _resolve, restoration_metadata, validate_restored_manifest


class PerceptualBackend(Protocol):
    """Injectable learned-metric backend, allowing CPU-only deterministic tests."""

    identifier: str

    def clap(self, audio: np.ndarray, sample_rate: int) -> np.ndarray: ...

    def fadtk(self, audio: np.ndarray, sample_rate: int) -> np.ndarray: ...

    def fadtk_distance(self, reference: np.ndarray, estimate: np.ndarray) -> float: ...

    def fadtk_fma_pop_distance(self, estimate: np.ndarray) -> float: ...

    def verify_fma_pop(self) -> dict[str, Any]: ...

    def aesthetics(self, audio: np.ndarray, sample_rate: int) -> dict[str, float]: ...


def _cache_dir(config: dict[str, Any], cache_dir: Path | None) -> Path:
    return (cache_dir or Path(config["cache"]["directory"])).expanduser().resolve()


def _cache_manifest(cache: Path) -> Path:
    return cache / "perceptual_cache_manifest.json"


def _sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file() and item.name != "perceptual_cache_manifest.json":
            digest.update(str(item.relative_to(path)).encode("utf-8"))
            digest.update(sha256_file(item).encode("ascii"))
    return digest.hexdigest()


def _verify_cache(cache: Path) -> dict[str, Any]:
    manifest_path = _cache_manifest(cache)
    if not manifest_path.is_file():
        raise RuntimeError("Run openrestore-score setup-perceptual before perceptual scoring")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("cache_sha256") != _sha256_tree(cache):
        raise RuntimeError(
            "Perceptual model cache does not match its verified setup manifest; run setup-perceptual again"
        )
    return manifest


def _require_gpu(device: str) -> Any:
    try:
        import torch
    except ImportError as error:
        raise RuntimeError(
            "Install OpenRestore perceptual dependencies: pip install '.[perceptual]'"
        ) from error
    if not device.startswith("cuda") or not torch.cuda.is_available():
        raise RuntimeError("Perceptual scoring is GPU-only and requires an available CUDA device")
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    return torch


def _package_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "unavailable"


class LearnedBackends:
    """Real LAION-CLAP, FADTK, and Audiobox backends used by the GPU command."""

    identifier = "openrestore_perceptual_fadtk_v0_1"

    def __init__(self, cache_dir: Path, device: str):
        self.cache_dir = cache_dir
        self.device = device
        self.torch = _require_gpu(device)
        os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))
        try:
            from audiobox_aesthetics.infer import initialize_predictor
            from fadtk import FrechetAudioDistance
            from fadtk.fad import calc_embd_statistics, calc_frechet_distance
            from fadtk.model_loader import CLAPLaionModel
            from laion_clap import CLAP_Module
        except ImportError as error:
            raise RuntimeError(
                "Install OpenRestore perceptual dependencies: pip install '.[perceptual]'"
            ) from error
        self._calc_embd_statistics = calc_embd_statistics
        self._calc_frechet_distance = calc_frechet_distance
        self.clap_model = CLAP_Module(enable_fusion=False)
        self.clap_model.load_ckpt()
        self.clap_model.eval()
        self.fadtk_model = CLAPLaionModel(type="music")
        self.fadtk_model.load_model()
        self.fadtk = FrechetAudioDistance(
            ml=self.fadtk_model, audio_load_worker=0, load_model=False
        )
        self.aesthetics_predictor = initialize_predictor()

    def _temporary_wav(
        self, audio: np.ndarray, sample_rate: int, target_rate: int, pcm16: bool
    ) -> Path:
        mono = np.asarray(audio, dtype=np.float32).mean(axis=1)
        if sample_rate != target_rate:
            mono = librosa.resample(mono, orig_sr=sample_rate, target_sr=target_rate)
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        handle.close()
        path = Path(handle.name)
        if pcm16:
            sf.write(
                path,
                np.clip(mono * 32768.0, -32768, 32767).astype(np.int16),
                target_rate,
                subtype="PCM_16",
            )
        else:
            sf.write(path, mono, target_rate, subtype="PCM_16")
        return path

    def clap(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        path = self._temporary_wav(audio, sample_rate, 48_000, pcm16=False)
        try:
            value = self.clap_model.get_audio_embedding_from_filelist([str(path)], use_tensor=False)
            return np.asarray(value, dtype=np.float64).reshape(1, -1)
        finally:
            path.unlink(missing_ok=True)

    def fadtk(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Match ARIEL's load_embedding workaround around FADTK/TorchCodec."""
        path = self._temporary_wav(audio, sample_rate, int(self.fadtk.ml.sr), pcm16=True)
        try:
            wav_data = self.fadtk.ml.load_wav(str(path))
            value = np.asarray(self.fadtk.ml.get_embedding(wav_data), dtype=np.float64)
            return value.reshape(1, -1) if value.ndim == 1 else value
        finally:
            path.unlink(missing_ok=True)

    def fadtk_distance(self, reference: np.ndarray, estimate: np.ndarray) -> float:
        if len(reference) < 2 or len(estimate) < 2:
            raise ValueError("FADTK requires at least two examples in each distribution")
        mean_ref, covariance_ref = self._calc_embd_statistics(reference)
        mean_estimate, covariance_estimate = self._calc_embd_statistics(estimate)
        return float(
            self._calc_frechet_distance(
                mean_ref, covariance_ref, mean_estimate, covariance_estimate
            )
        )

    def fadtk_fma_pop_distance(self, estimate: np.ndarray) -> float:
        if len(estimate) < 2:
            raise ValueError("FADTK requires at least two examples in each distribution")
        mean_reference, covariance_reference = self.fadtk.load_stats("fma_pop")
        mean_estimate, covariance_estimate = self._calc_embd_statistics(estimate)
        return float(
            self._calc_frechet_distance(
                mean_reference, covariance_reference, mean_estimate, covariance_estimate
            )
        )

    def verify_fma_pop(self) -> dict[str, Any]:
        mean, covariance = self.fadtk.load_stats("fma_pop")
        return {
            "backend": "fadtk:clap-laion-music",
            "reference": "fma_pop",
            "embedding_dimension": int(np.asarray(mean).shape[0]),
            "statistics_shape": list(np.asarray(covariance).shape),
        }

    def aesthetics(self, audio: np.ndarray, sample_rate: int) -> dict[str, float]:
        path = self._temporary_wav(audio, sample_rate, 44_100, pcm16=False)
        try:
            result = self.aesthetics_predictor.forward([{"path": str(path)}])[0]
        finally:
            path.unlink(missing_ok=True)
        return {name: float(result[name]) for name in ("CE", "CU", "PC", "PQ")}


def _embedding_cache_path(cache_dir: Path, backend: str, audio_sha: str) -> Path:
    return cache_dir / "embeddings" / backend / f"{audio_sha}.npz"


def _cached_embedding(
    backend: PerceptualBackend,
    cache_dir: Path,
    backend_name: str,
    audio_path: Path,
    audio: np.ndarray,
    sample_rate: int,
) -> np.ndarray:
    key = hashlib.sha256(
        f"{sha256_file(audio_path)}:{backend.identifier}:{backend_name}:v0_1".encode()
    ).hexdigest()
    path = _embedding_cache_path(cache_dir, backend_name, key)
    if path.is_file():
        return np.load(path)["embedding"]
    value = np.asarray(getattr(backend, backend_name)(audio, sample_rate), dtype=np.float64)
    if value.ndim != 2 or not value.size or not np.isfinite(value).all():
        raise ValueError(f"{backend_name} emitted invalid embedding for {audio_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, embedding=value)
    return value


def _cached_aesthetics(
    backend: PerceptualBackend,
    cache_dir: Path,
    audio_path: Path,
    audio: np.ndarray,
    sample_rate: int,
) -> dict[str, float]:
    key = hashlib.sha256(
        f"{sha256_file(audio_path)}:{backend.identifier}:aesthetics:v0_1".encode()
    ).hexdigest()
    path = _embedding_cache_path(cache_dir, "aesthetics", key)
    if path.is_file():
        return {name: float(value) for name, value in json.loads(path.read_text()).items()}
    value = backend.aesthetics(audio, sample_rate)
    if set(value) != {"CE", "CU", "PC", "PQ"} or not np.isfinite(list(value.values())).all():
        raise ValueError(f"Audiobox emitted invalid scores for {audio_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return value


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    left, right = left.reshape(-1), right.reshape(-1)
    return float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right) + 1e-12))


def _summaries(rows: list[dict[str, Any]], backend: PerceptualBackend) -> dict[str, Any]:
    def summary(group: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {"items": len(group)}
        clap = [row["metrics"]["clap_cosine"] for row in group]
        result["clap_cosine"] = {
            state: float(np.mean([entry[state] for entry in clap]))
            for state in ("degraded", "restored", "improvement")
        }
        for name in ("CE", "CU", "PC", "PQ"):
            values = [row["metrics"]["audiobox"][name] for row in group]
            result[f"audiobox_{name.lower()}"] = {
                state: float(np.mean([entry[state] for entry in values]))
                for state in ("degraded", "restored", "improvement")
            }
        try:
            clean = np.concatenate([row["fadtk"]["clean"] for row in group])
            degraded = np.concatenate([row["fadtk"]["degraded"] for row in group])
            restored = np.concatenate([row["fadtk"]["restored"] for row in group])
            local_degraded = backend.fadtk_distance(clean, degraded)
            local_restored = backend.fadtk_distance(clean, restored)
            fma_degraded = backend.fadtk_fma_pop_distance(degraded)
            fma_restored = backend.fadtk_fma_pop_distance(restored)
            for name, degraded_value, restored_value in (
                ("fadtk_clean", local_degraded, local_restored),
                ("fadtk_fma_pop", fma_degraded, fma_restored),
            ):
                result[name] = {
                    "degraded": degraded_value,
                    "restored": restored_value,
                    "improvement": degraded_value - restored_value,
                }
        except ValueError as error:
            result["distributional_metrics"] = {"available": False, "reason": str(error)}
        return result

    def grouped(field: str) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[field])].append(row)
        return {name: summary(group) for name, group in sorted(groups.items())}

    return {
        "overall": summary(rows),
        **{
            f"by_{field}": grouped(field)
            for field in ("category", "effect", "severity", "split", "dataset")
        },
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    overall = report["overall"]
    lines = [
        "# OpenRestore Perceptual Metric Report",
        "",
        "This report is diagnostic only. It defines no leaderboard aggregate or rank.",
        "",
        "Higher is better for CLAP cosine and Audiobox CE/CU/PC/PQ. Lower is better for FADTK. Improvements are oriented so positive means better than degraded audio.",
        "",
        f"Scored items: {report['items']['scored']}",
        "",
        "## Overall",
        "",
        "| Metric | Degraded | Restored | Improvement |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name in (
        "clap_cosine",
        "fadtk_clean",
        "fadtk_fma_pop",
        "audiobox_ce",
        "audiobox_cu",
        "audiobox_pc",
        "audiobox_pq",
    ):
        if name in overall:
            metric = overall[name]
            lines.append(
                f"| {name} | {metric['degraded']:.6f} | {metric['restored']:.6f} | {metric['improvement']:.6f} |"
            )
    lines.extend(
        [
            "",
            "## Category Summary",
            "",
            "| Category | Items | CLAP improvement |",
            "| --- | ---: | ---: |",
        ]
    )
    for name, value in report["by_category"].items():
        lines.append(f"| {name} | {value['items']} | {value['clap_cosine']['improvement']:.6f} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup_perceptual(config_path: Path, cache_dir: Path | None = None) -> dict[str, Any]:
    config = load_yaml(config_path)
    cache = _cache_dir(config, cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    backend = LearnedBackends(cache, str(config["device"]["default"]))
    fma_reference = backend.verify_fma_pop()
    del backend
    manifest = {
        "metric_pack": config["metric_pack"],
        "packages": {
            name: _package_version(name)
            for name in ("torch", "torchaudio", "laion-clap", "fadtk", "audiobox-aesthetics")
        },
        "cache_sha256": _sha256_tree(cache),
        "fma_pop_reference": fma_reference,
    }
    _cache_manifest(cache).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def perceptual_score(
    degraded_manifest: Path,
    degraded_root: Path,
    clean_root: Path,
    restored_manifest: Path,
    config_path: Path,
    output_dir: Path,
    cache_dir: Path | None = None,
    device: str = "cuda",
    submission_id: str | None = None,
    backend: PerceptualBackend | None = None,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    if submission_id:
        config = {**config, "submission_id": submission_id}
    cache = _cache_dir(config, cache_dir)
    cache_manifest: dict[str, Any] = (
        {"backend": backend.identifier} if backend else _verify_cache(cache)
    )
    if backend is None:
        backend = LearnedBackends(cache, device)
    tolerance = int(config["validation"]["duration_tolerance_samples"])
    validated, failures = validate_restored_manifest(
        degraded_manifest, restored_manifest, duration_tolerance_samples=tolerance
    )
    rows: list[dict[str, Any]] = []
    for item in validated:
        source, restored_file = item["degraded"], item["restored_file"]
        try:
            rate, channels = int(source["sample_rate"]), int(source["channels"])
            samples = round(float(source["duration_seconds"]) * rate)
            clean = _audio(
                _resolve(clean_root, source["clean_path"]), rate, channels, samples, tolerance
            )
            degraded = _audio(
                _resolve(degraded_root, source["degraded_path"]), rate, channels, samples, tolerance
            )
            restored = _audio(restored_file, rate, channels, samples, tolerance)
            files = {
                "clean": _resolve(clean_root, source["clean_path"]),
                "degraded": _resolve(degraded_root, source["degraded_path"]),
                "restored": restored_file,
            }
            audios = {"clean": clean, "degraded": degraded, "restored": restored}
            clap = {
                name: _cached_embedding(backend, cache, "clap", files[name], audios[name], rate)
                for name in files
            }
            fadtk = {
                name: _cached_embedding(backend, cache, "fadtk", files[name], audios[name], rate)
                for name in files
            }
            aesthetics = {
                name: _cached_aesthetics(backend, cache, files[name], audios[name], rate)
                for name in files
            }
            clap_metric = {
                "degraded": _cosine(clap["clean"], clap["degraded"]),
                "restored": _cosine(clap["clean"], clap["restored"]),
            }
            clap_metric["improvement"] = clap_metric["restored"] - clap_metric["degraded"]
            aes_metrics = {}
            for name in ("CE", "CU", "PC", "PQ"):
                aes_metrics[name] = {
                    "degraded": aesthetics["degraded"][name],
                    "restored": aesthetics["restored"][name],
                    "improvement": aesthetics["restored"][name] - aesthetics["degraded"][name],
                }
            rows.append(
                {
                    "id": source["id"],
                    "split": source.get("split"),
                    "dataset": source.get("dataset"),
                    "severity": source.get("severity"),
                    "effect": effect_name(source),
                    "category": category_for_row(source),
                    "metrics": {"clap_cosine": clap_metric, "audiobox": aes_metrics},
                    "fadtk": fadtk,
                }
            )
        except Exception as error:
            failures.append(
                {"id": source["id"], "code": "perceptual_metric_failure", "message": str(error)}
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "perceptual_failures.json").write_text(
        json.dumps({"failures": failures}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if failures:
        raise ValueError(
            f"Perceptual scoring rejected {len(failures)} failures; see {output_dir / 'perceptual_failures.json'}"
        )
    report = {
        "benchmark_version": config["benchmark_version"],
        "submission_id": config["submission_id"],
        "metric_pack": config["metric_pack"],
        "ranking": "diagnostic_only_no_aggregate",
        "items": {"scored": len(rows), "failures": 0},
        "metric_definitions": {
            "clap_cosine": {"direction": "higher"},
            "fadtk_clean": {"direction": "lower", "reference": "clean"},
            "fadtk_fma_pop": {"direction": "lower", "reference": "fma_pop"},
            **{
                f"audiobox_{name.lower()}": {"direction": "higher"}
                for name in ("CE", "CU", "PC", "PQ")
            },
        },
        "fma_pop_reference": cache_manifest.get("fma_pop_reference", backend.verify_fma_pop()),
        "model_cache": cache_manifest,
        "artifacts": {
            "per_item_scores": "per_item_perceptual_scores.jsonl",
            "restoration_metadata": "restoration_metadata.jsonl",
            "report": "perceptual_report.md",
            "failures": "perceptual_failures.json",
        },
        **_summaries(rows, backend),
    }
    serializable_rows = [
        {key: value for key, value in row.items() if key != "fadtk"} for row in rows
    ]
    write_jsonl(output_dir / "per_item_perceptual_scores.jsonl", serializable_rows)
    write_jsonl(
        output_dir / "restoration_metadata.jsonl",
        restoration_metadata(validated, degraded_root, clean_root),
    )
    (output_dir / "perceptual_scores.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_markdown(report, output_dir / "perceptual_report.md")
    return report
