"""Source ingestion, deterministic splitting, canonical clip rendering, and release checks."""

from __future__ import annotations

import json
import math
import subprocess
import tarfile
import wave
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .core import SourceItem, audio_files, probe_audio, read_jsonl, sha256_file, stable_fraction, write_jsonl


CANONICAL_SAMPLE_RATE = 44_100
CLIP_SECONDS = 30


def _source_id(root: Path, audio_path: Path) -> str:
    return audio_path.relative_to(root).with_suffix("").as_posix().replace("/", "--")


def ingest(config: dict[str, Any], output: Path, probe: bool = True) -> list[dict[str, Any]]:
    root = Path(config["source_root"])
    if not root.is_dir():
        raise FileNotFoundError(f"Source root does not exist: {root}")
    items: list[dict[str, Any]] = []
    for audio_path in audio_files(root):
        metadata = probe_audio(audio_path) if probe else {"duration_seconds": 0.0, "sample_rate": 0, "channels": 0}
        if probe and metadata["duration_seconds"] < float(config.get("min_source_seconds", CLIP_SECONDS)):
            continue
        item = SourceItem(
            dataset=config["dataset"],
            source_id=_source_id(root, audio_path),
            audio_path=str(audio_path.resolve()),
            role=config["role"],
            split=config["fixed_split"],
            source_sha256=sha256_file(audio_path),
            **metadata,
        )
        items.append(item.to_dict())
    write_jsonl(output, items)
    return items


def split_sonicmaster(rows: Iterable[dict[str, Any]], seed: int, train_fraction: float, validation_fraction: float) -> list[dict[str, Any]]:
    if not 0 < train_fraction < 1 or not 0 <= validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("Split fractions must leave a non-empty public test fraction")
    assigned: list[dict[str, Any]] = []
    for row in rows:
        value = stable_fraction(row["source_id"], seed)
        split = "train" if value < train_fraction else "validation" if value < train_fraction + validation_fraction else "test"
        assigned.append({**row, "split": split})
    return assigned


def validate_split_policy(rows: Iterable[dict[str, Any]]) -> None:
    seen: dict[tuple[str, str], str] = {}
    for row in rows:
        dataset, source_id, split = row["dataset"], row["source_id"], row["split"]
        key = (dataset, source_id)
        if key in seen and seen[key] != split:
            raise ValueError(f"Source leaked across splits: {dataset}/{source_id}")
        seen[key] = split
        if dataset == "sonicmaster_clean" and split not in {"train", "validation", "test"}:
            raise ValueError(f"Invalid SonicMaster split: {split}")
        if dataset in {"sdd", "musdb18_hq"} and split != "validation":
            raise ValueError(f"{dataset} is validation-only, got {split}")


def combine_and_split(index_paths: list[Path], output: Path, seed: int, train_fraction: float, validation_fraction: float) -> list[dict[str, Any]]:
    rows = [row for path in index_paths for row in read_jsonl(path)]
    output_rows: list[dict[str, Any]] = []
    for dataset, group in _group_by_dataset(rows).items():
        output_rows.extend(split_sonicmaster(group, seed, train_fraction, validation_fraction) if dataset == "sonicmaster_clean" else group)
    output_rows.sort(key=lambda row: (row["dataset"], row["source_id"]))
    validate_split_policy(output_rows)
    write_jsonl(output, output_rows)
    return output_rows


def _group_by_dataset(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["dataset"]].append(row)
    return groups


def _clip_start(source_id: str, source_duration: float, clip_index: int, seed: int) -> float:
    available = math.floor(source_duration) - CLIP_SECONDS
    if available < 0:
        raise ValueError(f"Source shorter than {CLIP_SECONDS}s: {source_id}")
    return float(math.floor(stable_fraction(f"{source_id}:{clip_index}", seed) * (available + 1)))


def _render_clip(source: Path, output: Path, start_seconds: float, normalize: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start_seconds), "-i", str(source), "-t", str(CLIP_SECONDS)]
    if normalize:
        command.extend(["-af", "loudnorm=I=-18:LRA=11:TP=-1.0"])
    command.extend(["-ar", str(CANONICAL_SAMPLE_RATE), "-ac", "2", "-c:a", "pcm_s16le", str(output)])
    subprocess.run(command, check=True)


def _wave_quality(path: Path) -> dict[str, float | int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != CANONICAL_SAMPLE_RATE or handle.getnchannels() != 2:
            raise ValueError(f"Non-canonical rendered clip: {path}")
        samples = handle.readframes(handle.getnframes())
        if handle.getsampwidth() != 2:
            raise ValueError(f"Expected 16-bit PCM output: {path}")
    values = memoryview(samples).cast("h")
    peak = max((abs(value) for value in values), default=0) / 32768
    rms = math.sqrt(sum(value * value for value in values) / max(len(values), 1)) / 32768
    duration = len(values) / (2 * CANONICAL_SAMPLE_RATE)
    return {"peak": peak, "rms": rms, "duration_seconds": duration}


def segment(rows: Iterable[dict[str, Any]], output_root: Path, manifest: Path, checksums: Path, seed: int, clips_per_source: int, normalize: bool, min_rms: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    checksum_rows: list[dict[str, str]] = []
    for source in rows:
        for clip_index in range(clips_per_source):
            start = _clip_start(source["source_id"], source["duration_seconds"], clip_index, seed)
            item_id = f"{source['dataset']}--{source['source_id']}--{clip_index:02d}"
            relative_path = Path(source["split"]) / source["dataset"] / f"{item_id}.wav"
            output_path = output_root / relative_path
            _render_clip(Path(source["audio_path"]), output_path, start, normalize)
            quality = _wave_quality(output_path)
            if abs(float(quality["duration_seconds"]) - CLIP_SECONDS) > 0.01 or float(quality["rms"]) < min_rms:
                output_path.unlink(missing_ok=True)
                continue
            checksum = sha256_file(output_path)
            result.append({
                "id": item_id,
                "dataset": source["dataset"],
                "split": source["split"],
                "source_id": source["source_id"],
                "clean_path": relative_path.as_posix(),
                "start_seconds": start,
                "duration_seconds": CLIP_SECONDS,
                "sample_rate": CANONICAL_SAMPLE_RATE,
                "channels": 2,
                "normalization": "loudnorm I=-18 LRA=11 TP=-1.0" if normalize else "none",
                "quality": quality,
                "audio_sha256": checksum,
            })
            checksum_rows.append({"path": relative_path.as_posix(), "sha256": checksum})
    result.sort(key=lambda row: row["id"])
    write_jsonl(manifest, result)
    write_jsonl(checksums, checksum_rows)
    return result


def write_shards(output_root: Path, manifest_rows: Iterable[dict[str, Any]], shards_dir: Path, shard_size: int) -> list[Path]:
    shards_dir.mkdir(parents=True, exist_ok=True)
    rows = list(manifest_rows)
    shard_paths: list[Path] = []
    for index in range(0, len(rows), shard_size):
        shard_path = shards_dir / f"shard-{index // shard_size:05d}.tar"
        with tarfile.open(shard_path, "w") as archive:
            for row in rows[index : index + shard_size]:
                audio_path = output_root / row["clean_path"]
                archive.add(audio_path, arcname=row["clean_path"], recursive=False)
        shard_paths.append(shard_path)
    return shard_paths


def iter_shard(shard_path: Path) -> Iterable[str]:
    with tarfile.open(shard_path) as archive:
        yield from (member.name for member in archive.getmembers() if member.isfile())


def verify_checksums(root: Path, checksums: Path) -> list[str]:
    failures: list[str] = []
    for row in read_jsonl(checksums):
        path = root / row["path"]
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            failures.append(row["path"])
    return failures


def statistics(manifest_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(manifest_rows)
    groups = Counter((row["split"], row["dataset"]) for row in rows)
    return {
        "items": len(rows),
        "total_hours": round(sum(float(row["duration_seconds"]) for row in rows) / 3600, 3),
        "by_split": dict(sorted(Counter(row["split"] for row in rows).items())),
        "by_dataset_and_split": {f"{dataset}/{split}": count for (split, dataset), count in sorted(groups.items())},
        "canonical_format": {"sample_rate": CANONICAL_SAMPLE_RATE, "channels": 2, "duration_seconds": CLIP_SECONDS},
    }


def write_statistics(manifest: Path, output: Path) -> dict[str, Any]:
    report = statistics(read_jsonl(manifest))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def audit(config: dict[str, Any], output: Path, probe_limit: int = 25) -> dict[str, Any]:
    root = Path(config["source_root"])
    files = audio_files(root)
    sampled = [probe_audio(path) for path in files[:probe_limit]]
    report = {
        "dataset": config["dataset"],
        "version": config.get("version", "unspecified"),
        "source_root": str(root),
        "role": config["role"],
        "license": config["license"],
        "redistribution": config["redistribution"],
        "audio_file_count": len(files),
        "probed_file_count": len(sampled),
        "sampled_sample_rates": dict(sorted(Counter(item["sample_rate"] for item in sampled).items())),
        "sampled_channels": dict(sorted(Counter(item["channels"] for item in sampled).items())),
        "quality_notes": config["quality_notes"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
