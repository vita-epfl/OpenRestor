"""Construct source-filtered candidates without touching frozen private corpora."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import h5py

from .degradations.core import sha256_file
from .rights import media_key, pack_family


def safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not value or ".." in path.parts or "." in path.parts:
        raise ValueError(f"Unsafe release-relative path: {value}")
    return path


def classify_index(index: Path, registry: dict[str, dict], profile: str) -> tuple[dict[str, list[dict]], Counter]:
    """Read one row at a time; retain only rights-approved rows in their pack family."""
    selected: dict[str, list[dict]] = defaultdict(list)
    withheld: Counter = Counter()
    with index.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            dataset, source_id = str(row["dataset"]), str(row["source_id"])
            record = registry.get(media_key(dataset, source_id))
            if record is None:
                raise ValueError(f"No per-media rights record for a {dataset} item")
            family = pack_family(record, profile)
            if family is None:
                withheld[dataset] += 1
            else:
                selected[family].append(row)
    return dict(selected), withheld


def _copy_clean(rows: list[dict], clean_root: Path, target: Path) -> None:
    seen = set()
    for row in rows:
        relative = safe_relative(str(row["clean_path"]))
        if relative in seen:
            continue
        seen.add(relative)
        source = clean_root / relative
        if sha256_file(source) != row["audio_sha256"]:
            raise ValueError("Clean audio checksum mismatch; refusing the pack")
        destination = target / "clean" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def repack_hdf5(rows: list[dict], frozen_root: Path, clean_root: Path, target: Path) -> list[dict]:
    """Rebuild each selected HDF5 shard with only approved offsets and new hashes."""
    if target.resolve() == frozen_root.resolve() or frozen_root.resolve() in target.resolve().parents:
        raise ValueError("Output may not be inside the frozen corpus")
    if target.exists() and any(target.iterdir()):
        raise ValueError("Output must be a new or empty directory")
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(safe_relative(str(row["degraded_audio_shard"])))].append(row)
    output: list[dict] = []
    for original_name, subset in sorted(groups.items()):
        source = frozen_root / original_name
        expected_hashes = {str(row["degraded_audio_shard_sha256"]) for row in subset}
        if len(expected_hashes) != 1 or sha256_file(source) not in expected_hashes:
            raise ValueError("Frozen shard hash mismatch; refusing the pack")
        dest = target / original_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(source, "r") as original, h5py.File(dest, "w") as filtered:
            for attr, value in original.attrs.items():
                filtered.attrs[attr] = value
            ordered = sorted(subset, key=lambda row: int(row["degraded_audio_shard_index"]))
            offsets = [int(row["degraded_audio_shard_index"]) for row in ordered]
            if len(offsets) != len(set(offsets)):
                raise ValueError("Duplicate selected shard offset")
            for offset, row in zip(offsets, ordered):
                stored = original["item_id"][offset]
                if (stored.decode("utf-8") if isinstance(stored, bytes) else str(stored)) != str(row["id"]):
                    raise ValueError("Frozen shard item ID mismatch")
            for name, dataset in original.items():
                kwargs: dict[str, Any] = {"shape": (len(offsets), *dataset.shape[1:]),
                                          "dtype": dataset.dtype}
                if dataset.compression and name == "audio":
                    kwargs.update(chunks=(1, *dataset.shape[1:]), compression=dataset.compression,
                                  shuffle=bool(dataset.shuffle))
                created = filtered.create_dataset(name, **kwargs)
                for new_offset, old_offset in enumerate(offsets):
                    created[new_offset] = dataset[old_offset]
        new_hash = sha256_file(dest)
        for new_offset, row in enumerate(ordered):
            output.append({**row, "degraded_audio_shard": original_name,
                           "degraded_audio_shard_index": new_offset,
                           "degraded_audio_shard_sha256": new_hash})
    _copy_clean(rows, clean_root, target)
    return output


def copy_blind_synthetic(rows: list[dict], audio_root: Path, clean_root: Path,
                         target: Path) -> list[dict]:
    if target.exists() and any(target.iterdir()):
        raise ValueError("Output must be a new or empty directory")
    for row in rows:
        relative = safe_relative(str(row["degraded_path"]))
        source = audio_root / relative
        if sha256_file(source) != row["degraded_audio_sha256"]:
            raise ValueError("Blind-Synthetic audio checksum mismatch")
        destination = target / "audio" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    _copy_clean(rows, clean_root, target)
    return rows


def validate_pack(rows: list[dict], registry: dict[str, dict], profile: str, family: str,
                  root: Path, corpus: str) -> None:
    """Recheck index, physical shard contents and source IDs before handoff."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = media_key(str(row["dataset"]), str(row["source_id"]))
        if key not in registry or pack_family(registry[key], profile) != family:
            raise ValueError("Excluded source_id found in publication index")
        if corpus == "diagnostic":
            grouped[str(safe_relative(str(row["degraded_audio_shard"])))].append(row)
        else:
            path = root / "audio" / safe_relative(str(row["degraded_path"]))
            if sha256_file(path) != row["degraded_audio_sha256"]:
                raise ValueError("Packaged Blind-Synthetic checksum mismatch")
    for path, subset in grouped.items():
        file = root / path
        digest = sha256_file(file)
        with h5py.File(file, "r") as shard:
            if len(shard["item_id"]) != len(subset):
                raise ValueError("Shard contains an unindexed/excluded item")
            if {int(row["degraded_audio_shard_index"]) for row in subset} != set(range(len(subset))):
                raise ValueError("Shard index omits or duplicates a physical item")
            for row in subset:
                if digest != row["degraded_audio_shard_sha256"]:
                    raise ValueError("Packaged shard hash mismatch")
                offset = int(row["degraded_audio_shard_index"])
                stored = shard["item_id"][offset]
                if (stored.decode("utf-8") if isinstance(stored, bytes) else str(stored)) != str(row["id"]):
                    raise ValueError("Shard contains an excluded or mismatched item")
