"""Config-driven degradation rendering pipeline."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

from .core import (
    CANONICAL_SAMPLE_RATE,
    load_yaml,
    read_audio,
    read_jsonl,
    sample_parameters,
    sha256_file,
    stable_seed,
    write_audio,
    write_jsonl,
)
from .effects import apply_operation

REQUIRED_PRIMITIVES = {
    "ariel",
    "distant_mic_capture",
    "eq_coloration",
    "dynamics",
    "reverb_room",
    "gain_level",
    "clipping_distortion",
    "stereo_spatial",
    "bandwidth_filtering",
    "noise_interference",
    "device_mic_response",
    "codec_resampling",
}


def _log(progress: bool, message: str) -> None:
    if progress:
        print(message, file=sys.stderr, flush=True)


def validate_config(config: dict[str, Any]) -> None:
    recipes = config.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        raise ValueError("Degradation config must contain a non-empty recipes list")
    seen: set[str] = set()
    for recipe in recipes:
        recipe_id = recipe.get("id")
        if not recipe_id or recipe_id in seen:
            raise ValueError(f"Invalid or duplicate recipe id: {recipe_id}")
        seen.add(recipe_id)
        if not isinstance(recipe.get("severity"), str) or not recipe["severity"]:
            raise ValueError(f"Invalid severity for {recipe_id}")
        operations = recipe.get("operations")
        if not isinstance(operations, list) or len(operations) != 1:
            raise ValueError(f"Recipe {recipe_id} must contain exactly one operation")
        for operation in operations:
            primitive = operation.get("primitive")
            if primitive not in REQUIRED_PRIMITIVES:
                raise ValueError(f"Recipe {recipe_id} uses unknown primitive: {primitive}")


def list_recipes(config: dict[str, Any]) -> list[dict[str, Any]]:
    validate_config(config)
    return [
        {
            "id": recipe["id"],
            "severity": recipe["severity"],
            "primitives": [operation["primitive"] for operation in recipe["operations"]],
        }
        for recipe in config["recipes"]
    ]


def render_degradations(
    manifest: Path,
    clean_root: Path,
    output_root: Path,
    config_path: Path,
    output_manifest: Path,
    checksums: Path,
    seed: int,
    progress: bool = False,
) -> list[dict[str, Any]]:
    config = load_yaml(config_path)
    validate_config(config)
    clean_rows = read_jsonl(manifest)
    output_rows: list[dict[str, Any]] = []
    checksum_rows: list[dict[str, str]] = []
    total = len(clean_rows) * len(config["recipes"])
    processed = 0
    _log(progress, f"[degrade] rendering {total} degraded examples")
    for clean_row in clean_rows:
        clean_path = clean_root / clean_row["clean_path"]
        audio, sample_rate = read_audio(clean_path)
        if sample_rate != CANONICAL_SAMPLE_RATE:
            raise ValueError(f"Expected {CANONICAL_SAMPLE_RATE} Hz input: {clean_path}")
        for recipe in config["recipes"]:
            processed += 1
            degraded, operation_params = apply_recipe(
                audio, sample_rate, clean_row["id"], recipe, seed
            )
            recipe_id = recipe["id"]
            degraded_id = f"{clean_row['id']}--{recipe_id}"
            relative_path = (
                Path(clean_row["split"]) / clean_row["dataset"] / recipe_id / f"{degraded_id}.wav"
            )
            degraded_path = output_root / relative_path
            write_audio(degraded_path, degraded, sample_rate)
            digest = sha256_file(degraded_path)
            tracking = _tracking(recipe, operation_params, seed, clean_row["id"])
            output_row = {
                **clean_row,
                "id": degraded_id,
                "clean_id": clean_row["id"],
                "degraded_path": relative_path.as_posix(),
                "degradation_recipe_id": recipe_id,
                "severity": recipe["severity"],
                "degradation_seed": stable_seed(seed, clean_row["id"], recipe_id),
                "degradation_tracking": tracking,
                "degradation_params": operation_params,
                "degraded_audio_sha256": digest,
            }
            output_rows.append(output_row)
            checksum_rows.append({"path": relative_path.as_posix(), "sha256": digest})
            if progress and (processed == 1 or processed % 50 == 0 or processed == total):
                _log(progress, f"[degrade] {processed}/{total} rendered")
    write_jsonl(output_manifest, output_rows)
    write_jsonl(checksums, checksum_rows)
    _log(progress, f"[degrade] wrote {len(output_rows)} rows to {output_manifest}")
    return output_rows


def apply_recipe(
    audio: np.ndarray,
    sample_rate: int,
    item_id: str,
    recipe: dict[str, Any],
    global_seed: int,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    result = np.array(audio, copy=True)
    operation_rows: list[dict[str, Any]] = []
    recipe_id = recipe["id"]
    for index, operation in enumerate(recipe["operations"]):
        operation_seed = stable_seed(global_seed, item_id, recipe_id, index)
        sampled = sample_parameters(operation.get("parameters", {}), operation_seed)
        if recipe.get("severity") == "medium_preview":
            sampled["preview_strength"] = "medium"
        rng = np.random.default_rng(operation_seed)
        result, actual = apply_operation(
            result,
            sample_rate,
            operation["primitive"],
            operation.get("variant"),
            sampled,
            rng,
        )
        operation_rows.append(
            {
                "operation_index": index,
                "primitive": operation["primitive"],
                "variant": actual.get("variant", operation.get("variant")),
                "seed": operation_seed,
                "parameters": actual,
            }
        )
    return result, operation_rows


def _tracking(
    recipe: dict[str, Any], operations: list[dict[str, Any]], global_seed: int, item_id: str
) -> dict[str, Any]:
    return {
        "recipe_id": recipe["id"],
        "severity": recipe["severity"],
        "item_seed": stable_seed(global_seed, item_id, recipe["id"]),
        "operations": [
            {
                "primitive": op["primitive"],
                "variant": op.get("variant"),
                "seed": op["seed"],
                "summary": _compact_params(op["parameters"]),
            }
            for op in operations
        ],
    }


def _compact_params(params: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in params.items():
        if key == "child_operations":
            compact[key] = [child.get("primitive") for child in value]
        elif isinstance(value, (str, int, float, bool)) or value is None:
            compact[key] = value
    return compact


def write_hdf5_shards(
    output_root: Path,
    manifest_path: Path,
    shards_dir: Path,
    output_index: Path,
    shard_size: int = 1_000,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """Package rendered degraded WAVs into deterministic HDF5 shards and write their index."""
    try:
        import h5py
    except ImportError as error:
        raise RuntimeError("HDF5 sharding requires the h5py package") from error

    rows = read_jsonl(manifest_path)
    if shard_size < 1:
        raise ValueError("shard_size must be at least 1")
    shards_dir.mkdir(parents=True, exist_ok=True)
    indexed_rows: list[dict[str, Any]] = []
    shard_total = (len(rows) + shard_size - 1) // shard_size
    _log(progress, f"[degrade-shard] writing {len(rows)} examples into {shard_total} HDF5 shards")
    text_type = h5py.string_dtype(encoding="utf-8")

    for shard_number, start in enumerate(range(0, len(rows), shard_size)):
        chunk = rows[start : start + shard_size]
        decoded = [read_audio(output_root / row["degraded_path"])[0] for row in chunk]
        first_shape = decoded[0].shape if decoded else (0, 2)
        if any(audio.shape != first_shape for audio in decoded):
            raise ValueError("HDF5 sharding requires canonical equal-length degraded audio")
        shard_path = shards_dir / f"degraded-{shard_number:05d}.h5"
        with h5py.File(shard_path, "w") as shard:
            shard.attrs["format"] = "openrestore.degraded.v0.1"
            shard.attrs["sample_rate"] = CANONICAL_SAMPLE_RATE
            shard.attrs["samples"] = first_shape[0]
            shard.attrs["channels"] = first_shape[1]
            shard.create_dataset("audio", data=np.stack(decoded), compression="gzip", shuffle=True)
            shard.create_dataset("item_id", data=[str(row["id"]) for row in chunk], dtype=text_type)
            shard.create_dataset(
                "clean_id", data=[str(row["clean_id"]) for row in chunk], dtype=text_type
            )
            shard.create_dataset(
                "degraded_path", data=[str(row["degraded_path"]) for row in chunk], dtype=text_type
            )
            shard.create_dataset(
                "manifest_json",
                data=[json.dumps(row, sort_keys=True) for row in chunk],
                dtype=text_type,
            )
        shard_reference = os.path.relpath(shard_path, output_index.parent).replace(os.sep, "/")
        for offset, row in enumerate(chunk):
            indexed_rows.append(
                {
                    **row,
                    "degraded_audio_shard": shard_reference,
                    "degraded_audio_shard_index": offset,
                }
            )
        _log(progress, f"[degrade-shard] wrote {shard_number + 1}/{shard_total}: {shard_path}")

    write_jsonl(output_index, indexed_rows)
    return indexed_rows
