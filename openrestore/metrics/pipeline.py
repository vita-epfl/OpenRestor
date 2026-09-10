"""Manifest validation, scoring, aggregation, and no-restoration baseline generation."""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from openrestore.degradations.core import load_yaml, read_jsonl, sha256_file, write_jsonl

from .core import METRIC_DIRECTIONS, aae_metrics, category_for_row, effect_name, pairwise_metrics


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _audio(
    path: Path, expected_rate: int, expected_channels: int, expected_samples: int, tolerance: int
) -> np.ndarray:
    info = sf.info(path)
    if info.samplerate != expected_rate:
        raise ValueError(f"sample_rate {info.samplerate}, expected {expected_rate}")
    if info.channels != expected_channels:
        raise ValueError(f"channels {info.channels}, expected {expected_channels}")
    audio, _ = sf.read(path, always_2d=True, dtype="float32")
    if not np.isfinite(audio).all():
        raise ValueError("non-finite samples")
    if abs(len(audio) - expected_samples) > tolerance:
        raise ValueError(f"samples {len(audio)}, expected {expected_samples} within {tolerance}")
    if len(audio) != expected_samples:
        audio = (
            audio[:expected_samples]
            if len(audio) > expected_samples
            else np.pad(audio, ((0, expected_samples - len(audio)), (0, 0)))
        )
    return audio


def validate_restored_manifest(
    degraded_manifest: Path,
    restored_manifest: Path,
    restored_root: Path | None = None,
    duration_tolerance_samples: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    degraded_rows = read_jsonl(degraded_manifest)
    restored_rows = read_jsonl(restored_manifest)
    failures: list[dict[str, Any]] = []
    degraded_by_id = {str(row.get("id")): row for row in degraded_rows}
    if len(degraded_by_id) != len(degraded_rows):
        failures.append(
            {
                "code": "duplicate_degraded_id",
                "message": "The degraded manifest contains duplicate ids",
            }
        )
    restored_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(restored_rows, start=1):
        item_id, path = row.get("id"), row.get("restored_audio_path")
        if not isinstance(item_id, str) or not item_id or not isinstance(path, str) or not path:
            failures.append(
                {
                    "line": index,
                    "code": "invalid_restored_row",
                    "message": "id and restored_audio_path are required strings",
                }
            )
            continue
        if item_id in restored_by_id:
            failures.append(
                {
                    "line": index,
                    "id": item_id,
                    "code": "duplicate_restored_id",
                    "message": "Duplicate restored id",
                }
            )
            continue
        restored_by_id[item_id] = row
        if item_id not in degraded_by_id:
            failures.append(
                {
                    "line": index,
                    "id": item_id,
                    "code": "unknown_restored_id",
                    "message": "No matching degraded item",
                }
            )
    for item_id in degraded_by_id:
        if item_id not in restored_by_id:
            failures.append(
                {"id": item_id, "code": "missing_restored_id", "message": "No restored output row"}
            )
    root = restored_root or restored_manifest.parent
    validated: list[dict[str, Any]] = []
    for item_id, row in restored_by_id.items():
        if item_id not in degraded_by_id:
            continue
        path = _resolve(root, row["restored_audio_path"])
        if not path.is_file():
            failures.append(
                {"id": item_id, "code": "missing_restored_audio_file", "message": str(path)}
            )
            continue
        degraded = degraded_by_id[item_id]
        try:
            _audio(
                path,
                int(degraded["sample_rate"]),
                int(degraded["channels"]),
                round(float(degraded["duration_seconds"]) * int(degraded["sample_rate"])),
                duration_tolerance_samples,
            )
        except Exception as error:
            failures.append(
                {"id": item_id, "code": "invalid_restored_audio", "message": str(error)}
            )
            continue
        validated.append(
            {"degraded": degraded_by_id[item_id], "restored": row, "restored_file": path}
        )
    return validated, failures


def restoration_metadata(
    validated: list[dict[str, Any]], degraded_root: Path, clean_root: Path
) -> list[dict[str, Any]]:
    """Join participant run fields to trusted clean and degraded provenance."""
    result: list[dict[str, Any]] = []
    for item in validated:
        degraded, restored = item["degraded"], item["restored"]
        result.append(
            {
                "id": degraded["id"],
                "degraded_audio_path": str(_resolve(degraded_root, degraded["degraded_path"])),
                "clean_audio_path": str(_resolve(clean_root, degraded["clean_path"])),
                "degradation_type": effect_name(degraded),
                "source_id": str(
                    degraded.get("clean_id") or degraded.get("source_id") or degraded["id"]
                ),
                "restored_audio_path": str(item["restored_file"]),
                "restored_latent_shape": restored.get("restored_latent_shape"),
                "duration_sec": restored.get("duration_sec"),
                "inference_steps": restored.get("inference_steps"),
                "batch_time_seconds": restored.get("batch_time_seconds"),
                "timestamp": restored.get("timestamp"),
                "dataset": degraded.get("dataset"),
                "split": degraded.get("split"),
                "severity": degraded.get("severity"),
                "degradation_recipe_id": degraded.get("degradation_recipe_id"),
                "degradation_tracking": degraded.get("degradation_tracking"),
            }
        )
    return result


def _score_failures(output_dir: Path, failures: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "failures.json").write_text(
        json.dumps({"failures": failures}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def score(
    degraded_manifest: Path,
    degraded_root: Path,
    clean_root: Path,
    restored_manifest: Path,
    config_path: Path,
    output_dir: Path,
    submission_id: str | None = None,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    if submission_id:
        config = {**config, "submission_id": submission_id}
    tolerance = int(config["validation"]["duration_tolerance_samples"])
    validated, failures = validate_restored_manifest(
        degraded_manifest, restored_manifest, duration_tolerance_samples=tolerance
    )
    item_rows: list[dict[str, Any]] = []
    for item in validated:
        row, restored_file = item["degraded"], item["restored_file"]
        item_id = row["id"]
        try:
            sample_rate = int(row["sample_rate"])
            channels = int(row["channels"])
            expected_samples = round(float(row["duration_seconds"]) * sample_rate)
            clean = _audio(
                _resolve(clean_root, row["clean_path"]),
                sample_rate,
                channels,
                expected_samples,
                tolerance,
            )
            degraded = _audio(
                _resolve(degraded_root, row["degraded_path"]),
                sample_rate,
                channels,
                expected_samples,
                tolerance,
            )
            restored = _audio(restored_file, sample_rate, channels, expected_samples, tolerance)
            degraded_metrics = pairwise_metrics(clean, degraded, config)
            restored_metrics = pairwise_metrics(clean, restored, config)
            metrics = {
                name: {
                    "degraded": degraded_metrics[name],
                    "restored": restored_metrics[name],
                    "improvement": (degraded_metrics[name] - restored_metrics[name])
                    if direction == "lower"
                    else (restored_metrics[name] - degraded_metrics[name]),
                }
                for name, direction in METRIC_DIRECTIONS.items()
            }
            category = category_for_row(row)
            item_rows.append(
                {
                    "id": item_id,
                    "restored_audio_path": str(restored_file),
                    "split": row.get("split"),
                    "dataset": row.get("dataset"),
                    "severity": row.get("severity"),
                    "degradation_recipe_id": row.get("degradation_recipe_id"),
                    "effect": effect_name(row),
                    "category": category,
                    "metrics": metrics,
                    "aae": aae_metrics(clean, degraded, restored, category, sample_rate),
                }
            )
        except Exception as error:
            failures.append({"id": item_id, "code": "invalid_audio", "message": str(error)})
    _score_failures(output_dir, failures)
    if failures:
        raise ValueError(
            f"Scoring rejected {len(failures)} manifest/audio failures; see "
            f"{output_dir / 'failures.json'}"
        )
    write_jsonl(output_dir / "per_item_scores.jsonl", item_rows)
    write_jsonl(
        output_dir / "restoration_metadata.jsonl",
        restoration_metadata(validated, degraded_root, clean_root),
    )
    report = _report(config, item_rows, output_dir)
    (output_dir / "scores.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_markdown(report, output_dir / "report.md")
    return report


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, direction in METRIC_DIRECTIONS.items():
        result[name] = {"direction": direction}
        for state in ("degraded", "restored", "improvement"):
            result[name][state] = float(np.mean([row["metrics"][name][state] for row in rows]))
    result["aae"] = {
        key: float(np.mean([row["aae"][key] for row in rows]))
        for key in ("degraded", "restored", "reduction")
    }
    return result


def _group(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    return {
        name: {"items": len(group), "metrics": _metric_summary(group)}
        for name, group in sorted(groups.items())
    }


def _report(config: dict[str, Any], rows: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    return {
        "benchmark_version": str(config["benchmark_version"]),
        "submission_id": str(config["submission_id"]),
        "metric_pack": str(config["metric_pack"]),
        "ranking": "diagnostic_only_no_aggregate",
        "items": {"scored": len(rows), "failures": 0},
        "metric_definitions": {
            name: {"direction": direction} for name, direction in METRIC_DIRECTIONS.items()
        },
        "overall": _metric_summary(rows),
        "by_category": _group(rows, "category"),
        "by_effect": _group(rows, "effect"),
        "by_severity": _group(rows, "severity"),
        "by_split": _group(rows, "split"),
        "by_dataset": _group(rows, "dataset"),
        "artifacts": {
            "per_item_scores": "per_item_scores.jsonl",
            "restoration_metadata": "restoration_metadata.jsonl",
            "report": "report.md",
            "failures": "failures.json",
        },
        "deferred_metric_pack": ["CLAP", "PANNS", "FAD", "FAD_LAION", "Audiobox"],
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# OpenRestore Metric Report",
        "",
        "This report is diagnostic only. It defines no leaderboard aggregate or rank.",
        "",
        "Lower is better for distances/errors; higher is better for SNR, SI-SDR, SI-SNR, and SSIM. "
        "`improvement` is always positive when restoration improves over degraded audio.",
        "",
        f"Scored items: {report['items']['scored']}",
        "",
        "## Category Summary",
        "",
        "| Category | Items | L1 restored | SNR restored | LSD restored | AAE reduction |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, data in report["by_category"].items():
        metrics = data["metrics"]
        lines.append(
            f"| {category} | {data['items']} | {metrics['l1']['restored']:.6f} | "
            f"{metrics['snr_db']['restored']:.3f} | {metrics['lsd_db']['restored']:.3f} | "
            f"{metrics['aae']['reduction']:.3f} |"
        )
    lines.extend(
        ["", "## Effect Summary", "", "| Effect | Items | AAE reduction |", "| --- | ---: | ---: |"]
    )
    for effect, data in report["by_effect"].items():
        lines.append(f"| {effect} | {data['items']} | {data['metrics']['aae']['reduction']:.3f} |")
    lines.extend(
        [
            "",
            "Learned embedding, distributional, and aesthetic metrics are deferred "
            "to the optional GPU metric pack.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def no_restoration(
    degraded_manifest: Path, degraded_root: Path, output_root: Path, output_manifest: Path
) -> list[dict[str, str]]:
    rows = read_jsonl(degraded_manifest)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, str]] = []
    for row in rows:
        source = _resolve(degraded_root, row["degraded_path"])
        target = output_root / f"{row['id']}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        result.append(
            {
                "id": row["id"],
                "restored_audio_path": target.relative_to(output_manifest.parent).as_posix(),
                "restored_latent_shape": None,
                "duration_sec": float(row["duration_seconds"]),
                "inference_steps": None,
                "batch_time_seconds": None,
                "timestamp": None,
                "restored_audio_sha256": sha256_file(target),
            }
        )
    write_jsonl(output_manifest, result)
    return result
