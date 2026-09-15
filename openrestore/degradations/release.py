"""Production-scale, partitioned degradation release orchestration."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import h5py

from .core import load_yaml, read_jsonl, sha256_file, write_jsonl
from .pipeline import render_degradations, validate_config, write_hdf5_shards


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _release_config(path: Path) -> dict[str, Any]:
    config = load_yaml(path)
    required = {
        "release_id",
        "private_output_root",
        "expected_degraded_examples",
        "seed",
        "recipe_config",
        "asset_checksums",
        "frozen_split_manifest",
        "frozen_split_sha256",
        "clips_per_source",
        "clip_seconds",
        "sources_per_partition",
        "shard_size",
        "partitions",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"Release config missing: {', '.join(sorted(missing))}")
    if int(config["clips_per_source"]) != 1 or int(config["clip_seconds"]) != 30:
        raise ValueError("Production release requires exactly one 30-second clip per source")
    if int(config["sources_per_partition"]) < 1 or int(config["shard_size"]) < 1:
        raise ValueError("sources_per_partition and shard_size must be positive")
    if not isinstance(config["partitions"], list) or not config["partitions"]:
        raise ValueError("Release config partitions must be a non-empty list")
    split_manifest = Path(config["frozen_split_manifest"])
    if sha256_file(split_manifest) != config["frozen_split_sha256"]:
        raise ValueError("Frozen SonicMaster split manifest checksum does not match release config")
    return config


def _expected_partition_counts(config: dict[str, Any]) -> dict[tuple[str, str], int]:
    values: dict[tuple[str, str], int] = {}
    for entry in config["partitions"]:
        dataset, split, sources = (
            entry.get("dataset"),
            entry.get("split"),
            entry.get("expected_sources"),
        )
        if (
            not isinstance(dataset, str)
            or not isinstance(split, str)
            or not isinstance(sources, int)
            or sources < 1
        ):
            raise ValueError(
                "Each release partition requires dataset, split, and positive expected_sources"
            )
        key = (dataset, split)
        if key in values:
            raise ValueError(f"Duplicate release partition: {dataset}/{split}")
        values[key] = sources
    return values


def validate_clean_release(
    clean_manifest: Path, clean_root: Path, release_config: Path
) -> dict[str, int]:
    """Fail closed unless every declared clean source is canonical and checksum-valid."""
    config = _release_config(release_config)
    expected = _expected_partition_counts(config)
    rows = read_jsonl(clean_manifest)
    seen: set[str] = set()
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        clean_id = str(row.get("id", ""))
        if not clean_id or clean_id in seen:
            raise ValueError(f"Missing or duplicate clean ID: {clean_id}")
        seen.add(clean_id)
        key = (str(row.get("dataset")), str(row.get("split")))
        if key not in expected:
            raise ValueError(
                f"Clean manifest includes undeclared release partition: {key[0]}/{key[1]}"
            )
        if (
            float(row.get("duration_seconds", 0)) != 30
            or int(row.get("sample_rate", 0)) != 44_100
            or int(row.get("channels", 0)) != 2
        ):
            raise ValueError(f"Non-canonical clean item: {clean_id}")
        clean_path = clean_root / str(row.get("clean_path", ""))
        if not clean_path.is_file():
            raise ValueError(f"Missing clean audio for release item: {clean_id}")
        if sha256_file(clean_path) != row.get("audio_sha256"):
            raise ValueError(f"Clean audio checksum mismatch: {clean_id}")
        counts[key] += 1
    if dict(counts) != expected:
        rendered = {
            f"{dataset}/{split}": count for (dataset, split), count in sorted(counts.items())
        }
        required = {
            f"{dataset}/{split}": count for (dataset, split), count in sorted(expected.items())
        }
        raise ValueError(f"Clean source count mismatch: expected {required}, got {rendered}")
    return {f"{dataset}/{split}": count for (dataset, split), count in sorted(counts.items())}


def create_partition_plan(
    clean_manifest: Path, release_config: Path, output: Path, clean_root: Path | None = None
) -> dict[str, Any]:
    """Freeze deterministic source partitions from a validated clean manifest."""
    config = _release_config(release_config)
    recipe_path = Path(config["recipe_config"])
    recipe = load_yaml(recipe_path)
    validate_config(recipe)
    rows = read_jsonl(clean_manifest)
    if clean_root is not None:
        validate_clean_release(clean_manifest, clean_root, release_config)
    expected = _expected_partition_counts(config)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("dataset")), str(row.get("split")))
        if key not in expected:
            raise ValueError(
                f"Clean manifest includes undeclared release partition: {key[0]}/{key[1]}"
            )
        if (
            float(row.get("duration_seconds", 0)) != 30
            or int(row.get("sample_rate", 0)) != 44_100
            or int(row.get("channels", 0)) != 2
        ):
            raise ValueError(f"Non-canonical clean item: {row.get('id')}")
        grouped.setdefault(key, []).append(row)
    if set(grouped) != set(expected):
        raise ValueError("Clean manifest is missing a declared release partition")
    partitions: list[dict[str, Any]] = []
    source_count = int(config["sources_per_partition"])
    recipe_count = len(recipe["recipes"])
    if int(config["shard_size"]) != source_count * recipe_count:
        raise ValueError("shard_size must equal sources_per_partition times active recipe count")
    if sum(expected.values()) * recipe_count != int(config["expected_degraded_examples"]):
        raise ValueError(
            "Release expected_degraded_examples does not match partitions and active recipes"
        )
    for dataset, split in sorted(expected):
        items = sorted(grouped[(dataset, split)], key=lambda row: str(row["id"]))
        if len(items) != expected[(dataset, split)]:
            raise ValueError(
                f"Expected {expected[(dataset, split)]} clean items for {dataset}/{split}, got {len(items)}"
            )
        for index, start in enumerate(range(0, len(items), source_count)):
            chunk = items[start : start + source_count]
            partition_id = f"{dataset}--{split}--{index:05d}"
            partitions.append(
                {
                    "id": partition_id,
                    "dataset": dataset,
                    "split": split,
                    "source_count": len(chunk),
                    "expected_outputs": len(chunk) * recipe_count,
                    "clean_ids": [str(row["id"]) for row in chunk],
                    "clean_manifest_sha256": _sha256_json(chunk),
                }
            )
    frozen_inputs = {
        "git_revision": _git_revision(),
        "clean_manifest_sha256": sha256_file(clean_manifest),
        "release_config_sha256": sha256_file(release_config),
        "recipe_config_sha256": sha256_file(recipe_path),
        "asset_checksums_sha256": sha256_file(Path(config["asset_checksums"])),
        "frozen_split_manifest": str(config["frozen_split_manifest"]),
        "frozen_split_sha256": config["frozen_split_sha256"],
        "private_output_root": str(Path(config["private_output_root"]).resolve()),
        "seed": int(config["seed"]),
        "recipe_ids": [item["id"] for item in recipe["recipes"]],
    }
    plan = {
        "format": "openrestore.release-plan.v0.1",
        "release_id": config["release_id"],
        "frozen_inputs": frozen_inputs,
        "partitions": partitions,
    }
    _write_json_atomic(output, plan)
    return plan


def _partition(plan: dict[str, Any], partition_id: str) -> dict[str, Any]:
    matches = [item for item in plan.get("partitions", []) if item.get("id") == partition_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown partition: {partition_id}")
    return matches[0]


def _validate_shard(shard_path: Path, expected_outputs: int) -> None:
    if not shard_path.is_file():
        raise ValueError(f"Missing degraded HDF5 shard: {shard_path}")
    with h5py.File(shard_path, "r") as shard:
        if shard.attrs.get("format") != "openrestore.degraded.v0.1":
            raise ValueError(f"Invalid degraded HDF5 format: {shard_path}")
        if (
            int(shard.attrs.get("sample_rate", 0)) != 44_100
            or int(shard.attrs.get("samples", 0)) != 1_323_000
            or int(shard.attrs.get("channels", 0)) != 2
        ):
            raise ValueError(f"Invalid degraded HDF5 canonical audio properties: {shard_path}")
        if shard["audio"].shape != (expected_outputs, 1_323_000, 2):
            raise ValueError(f"Unexpected degraded HDF5 audio shape: {shard_path}")
        if len(shard["item_id"]) != expected_outputs:
            raise ValueError(f"Unexpected degraded HDF5 item count: {shard_path}")


def _receipt_is_valid(
    receipt_path: Path, partition: dict[str, Any], plan: dict[str, Any], release_root: Path
) -> bool:
    if not receipt_path.is_file():
        return False
    receipt = _read_json(receipt_path)
    if receipt.get("status") != "complete" or receipt.get("partition_id") != partition["id"]:
        return False
    if receipt.get("plan_sha256") != _sha256_json(plan):
        return False
    shard_path = release_root / receipt.get("shard_path", "")
    index_path = release_root / receipt.get("index_path", "")
    checksums_path = release_root / receipt.get("checksums_path", "")
    try:
        _validate_shard(shard_path, int(partition["expected_outputs"]))
        if len(read_jsonl(index_path)) != int(partition["expected_outputs"]):
            return False
        return (
            sha256_file(shard_path) == receipt.get("shard_sha256")
            and sha256_file(index_path) == receipt.get("index_sha256")
            and sha256_file(checksums_path) == receipt.get("checksums_sha256")
        )
    except (OSError, ValueError):
        return False


def _render_partition(
    plan_path: Path,
    partition_id: str,
    clean_manifest: Path,
    clean_root: Path,
    release_config: Path,
    work_root: Path,
    release_root: Path,
) -> dict[str, Any]:
    """Render, package, validate, and receipt one retry-safe partition."""
    plan = _read_json(plan_path)
    partition = _partition(plan, partition_id)
    config = _release_config(release_config)
    if sha256_file(clean_manifest) != plan.get("frozen_inputs", {}).get("clean_manifest_sha256"):
        raise ValueError("Clean manifest does not match the frozen partition plan")
    if sha256_file(release_config) != plan.get("frozen_inputs", {}).get("release_config_sha256"):
        raise ValueError("Release config does not match the frozen partition plan")
    if sha256_file(Path(config["recipe_config"])) != plan.get("frozen_inputs", {}).get(
        "recipe_config_sha256"
    ):
        raise ValueError("Recipe config does not match the frozen partition plan")
    if sha256_file(Path(config["asset_checksums"])) != plan.get("frozen_inputs", {}).get(
        "asset_checksums_sha256"
    ):
        raise ValueError("Asset checksum file does not match the frozen partition plan")
    if release_root.resolve() != Path(config["private_output_root"]).resolve():
        raise ValueError("Release root does not match the declared private_output_root")
    receipt_path = release_root / "receipts" / f"{partition_id}.json"
    if _receipt_is_valid(receipt_path, partition, plan, release_root):
        return _read_json(receipt_path)
    rows_by_id = {str(row["id"]): row for row in read_jsonl(clean_manifest)}
    missing = [item for item in partition["clean_ids"] if item not in rows_by_id]
    if missing:
        raise ValueError(f"Partition clean items missing from manifest: {', '.join(missing[:5])}")
    rows = [rows_by_id[item] for item in partition["clean_ids"]]
    for row in rows:
        clean_path = clean_root / str(row["clean_path"])
        if not clean_path.is_file() or sha256_file(clean_path) != row.get("audio_sha256"):
            raise ValueError(f"Frozen clean audio is missing or changed: {row['id']}")
    partition_root = work_root / partition_id
    if partition_root.exists():
        if partition_root.resolve().parent != work_root.resolve():
            raise ValueError(f"Unsafe partition work path: {partition_root}")
        shutil.rmtree(partition_root)
    partition_root.mkdir(parents=True)
    partition_manifest = partition_root / "clean.jsonl"
    write_jsonl(partition_manifest, rows)
    rendered_manifest = partition_root / "degraded.jsonl"
    checksums = partition_root / "checksums.jsonl"
    wav_root = partition_root / "wav"
    rendered = render_degradations(
        partition_manifest,
        clean_root,
        wav_root,
        Path(config["recipe_config"]),
        rendered_manifest,
        checksums,
        int(config["seed"]),
    )
    if len(rendered) != int(partition["expected_outputs"]):
        raise ValueError(f"Unexpected render count for {partition_id}")
    shard_dir = release_root / "shards" / partition_id
    index_path = release_root / "partitions" / partition_id / "index.jsonl"
    indexed = write_hdf5_shards(
        wav_root,
        rendered_manifest,
        shard_dir,
        index_path,
        shard_size=int(partition["expected_outputs"]),
    )
    if len(indexed) != len(rendered):
        raise ValueError(f"Unexpected shard index count for {partition_id}")
    shard_path = shard_dir / "degraded-00000.h5"
    _validate_shard(shard_path, len(rendered))
    if any(
        sha256_file(wav_root / row["degraded_path"]) != row["degraded_audio_sha256"]
        for row in rendered
    ):
        raise ValueError(f"WAV checksum validation failed for {partition_id}")
    retained_checksums = index_path.with_name("checksums.jsonl")
    shutil.copy2(checksums, retained_checksums)
    shard_relative = shard_path.relative_to(release_root).as_posix()
    receipt = {
        "format": "openrestore.partition-receipt.v0.1",
        "status": "complete",
        "partition_id": partition_id,
        "plan_sha256": _sha256_json(plan),
        "source_manifest_sha256": plan["frozen_inputs"]["clean_manifest_sha256"],
        "release_config_sha256": plan["frozen_inputs"]["release_config_sha256"],
        "git_revision": plan["frozen_inputs"]["git_revision"],
        "frozen_split_sha256": plan["frozen_inputs"]["frozen_split_sha256"],
        "recipe_config_sha256": plan["frozen_inputs"]["recipe_config_sha256"],
        "asset_checksums_sha256": plan["frozen_inputs"]["asset_checksums_sha256"],
        "seed": plan["frozen_inputs"]["seed"],
        "item_count": len(rendered),
        "shard_path": shard_relative,
        "shard_sha256": sha256_file(shard_path),
        "index_path": index_path.relative_to(release_root).as_posix(),
        "index_sha256": sha256_file(index_path),
        "checksums_path": retained_checksums.relative_to(release_root).as_posix(),
        "checksums_sha256": sha256_file(retained_checksums),
        "failure_list": [],
        "completion_state": "hdf5-and-index-validated",
        "logs": [],
    }
    _write_json_atomic(receipt_path, receipt)
    shutil.rmtree(wav_root)
    return receipt


def render_partition(
    plan_path: Path,
    partition_id: str,
    clean_manifest: Path,
    clean_root: Path,
    release_config: Path,
    work_root: Path,
    release_root: Path,
) -> dict[str, Any]:
    """Run one partition and leave a structured failed receipt if it errors."""
    try:
        return _render_partition(
            plan_path,
            partition_id,
            clean_manifest,
            clean_root,
            release_config,
            work_root,
            release_root,
        )
    except Exception as error:
        try:
            plan = _read_json(plan_path)
            partition = _partition(plan, partition_id)
            _write_json_atomic(
                release_root / "receipts" / f"{partition_id}.json",
                {
                    "format": "openrestore.partition-receipt.v0.1",
                    "status": "failed",
                    "partition_id": partition["id"],
                    "plan_sha256": _sha256_json(plan),
                    "failure_list": [f"{type(error).__name__}: {error}"],
                    "completion_state": "failed",
                    "logs": [],
                },
            )
        except Exception:
            pass
        raise


def merge_release(
    plan_path: Path, release_root: Path, output_index: Path, output_receipt: Path
) -> dict[str, Any]:
    """Validate all partition receipts and publish one immutable release index."""
    plan = _read_json(plan_path)
    rows: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for partition in plan["partitions"]:
        receipt_path = release_root / "receipts" / f"{partition['id']}.json"
        if not _receipt_is_valid(receipt_path, partition, plan, release_root):
            raise ValueError(f"Missing or invalid partition receipt: {partition['id']}")
        receipt = _read_json(receipt_path)
        index_path = release_root / receipt["index_path"]
        if sha256_file(index_path) != receipt["index_sha256"]:
            raise ValueError(f"Partition index checksum mismatch: {partition['id']}")
        checksums_path = release_root / receipt["checksums_path"]
        if sha256_file(checksums_path) != receipt["checksums_sha256"]:
            raise ValueError(f"Partition checksum list mismatch: {partition['id']}")
        part_rows = read_jsonl(index_path)
        if len(part_rows) != int(partition["expected_outputs"]):
            raise ValueError(f"Unexpected partition index count: {partition['id']}")
        for row in part_rows:
            row = dict(row)
            row["degraded_audio_shard"] = (
                (release_root / Path(receipt["index_path"]).parent / row["degraded_audio_shard"])
                .resolve()
                .relative_to(release_root.resolve())
                .as_posix()
            )
            row["degraded_audio_shard_sha256"] = receipt["shard_sha256"]
            rows.append(row)
        receipts.append(receipt)
    rows.sort(key=lambda row: str(row["id"]))
    ids = [str(row["id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate degraded IDs across partitions")
    expected_outputs = sum(int(partition["expected_outputs"]) for partition in plan["partitions"])
    if len(rows) != expected_outputs:
        raise ValueError(f"Expected {expected_outputs} release rows, got {len(rows)}")
    write_jsonl(output_index, rows)
    receipt = {
        "format": "openrestore.release-receipt.v0.1",
        "status": "complete",
        "release_id": plan["release_id"],
        "plan_sha256": _sha256_json(plan),
        "index_path": output_index.relative_to(release_root).as_posix(),
        "index_sha256": sha256_file(output_index),
        "item_count": len(rows),
        "partition_count": len(receipts),
        "by_dataset_and_split": {
            f"{dataset}/{split}": count
            for (dataset, split), count in sorted(
                Counter((row["dataset"], row["split"]) for row in rows).items()
            )
        },
        "frozen_inputs": plan["frozen_inputs"],
    }
    _write_json_atomic(output_receipt, receipt)
    return receipt


def validate_release(plan_path: Path, release_root: Path, release_receipt: Path) -> dict[str, Any]:
    """Check release completeness, metadata identity, HDF5 offsets, and checksums."""
    plan = _read_json(plan_path)
    receipt = _read_json(release_receipt)
    if receipt.get("plan_sha256") != _sha256_json(plan) or receipt.get("status") != "complete":
        raise ValueError("Release receipt does not match plan")
    index_path = release_root / receipt["index_path"]
    if sha256_file(index_path) != receipt["index_sha256"]:
        raise ValueError("Release index checksum mismatch")
    rows = read_jsonl(index_path)
    if len(rows) != int(receipt["item_count"]):
        raise ValueError("Release index item count mismatch")
    expected: Counter[tuple[str, str]] = Counter()
    for partition in plan["partitions"]:
        expected[(partition["dataset"], partition["split"])] += int(partition["expected_outputs"])
    actual = Counter((row.get("dataset"), row.get("split")) for row in rows)
    if actual != expected:
        raise ValueError(
            f"Release dataset/split counts mismatch: expected {dict(expected)}, got {dict(actual)}"
        )
    required = {
        "id",
        "clean_id",
        "dataset",
        "split",
        "degradation_recipe_id",
        "degradation_params",
        "degradation_seed",
        "duration_seconds",
        "sample_rate",
        "channels",
        "audio_sha256",
        "degraded_audio_sha256",
        "degraded_audio_shard",
        "degraded_audio_shard_index",
        "degraded_audio_shard_sha256",
    }
    ids = [str(row.get("id", "")) for row in rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("Release degraded IDs are missing or non-unique")
    by_clean: dict[str, set[str]] = {}
    shard_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"Release row is missing required metadata: {sorted(missing)}")
        if (
            float(row["duration_seconds"]) != 30
            or int(row["sample_rate"]) != 44_100
            or int(row["channels"]) != 2
        ):
            raise ValueError(f"Release row has non-canonical clean metadata: {row['id']}")
        by_clean.setdefault(str(row["clean_id"]), set()).add(str(row["degradation_recipe_id"]))
        shard_rows.setdefault(str(row["degraded_audio_shard"]), []).append(row)
    expected_recipes = set(plan["frozen_inputs"]["recipe_ids"])
    if any(recipes != expected_recipes for recipes in by_clean.values()):
        raise ValueError("Every clean item must have exactly the frozen active recipe set")
    for shard, indexed_rows in sorted(shard_rows.items()):
        shard_path = release_root / shard
        _validate_shard(shard_path, len(indexed_rows))
        if sha256_file(shard_path) != indexed_rows[0]["degraded_audio_shard_sha256"]:
            raise ValueError(f"Release shard checksum mismatch: {shard}")
        if any(
            row["degraded_audio_shard_sha256"] != indexed_rows[0]["degraded_audio_shard_sha256"]
            for row in indexed_rows
        ):
            raise ValueError(f"Inconsistent release shard checksum metadata: {shard}")
        with h5py.File(shard_path, "r") as handle:
            for row in indexed_rows:
                offset = int(row["degraded_audio_shard_index"])
                if offset < 0 or offset >= len(handle["item_id"]):
                    raise ValueError(f"Invalid HDF5 shard offset: {row['id']}")
                stored_id = handle["item_id"][offset]
                if isinstance(stored_id, bytes):
                    stored_id = stored_id.decode("utf-8")
                if str(stored_id) != str(row["id"]):
                    raise ValueError(f"HDF5 shard offset does not match release row: {row['id']}")
    return receipt
