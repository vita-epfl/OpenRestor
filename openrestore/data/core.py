"""Core, dependency-light utilities for the OpenRestore dataset pipeline."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

AUDIO_EXTENSIONS = {".flac", ".wav", ".mp3", ".m4a", ".ogg", ".aiff", ".aif"}


@dataclass(frozen=True)
class SourceItem:
    dataset: str
    source_id: str
    audio_path: str
    role: str
    split: str
    duration_seconds: float
    sample_rate: int
    channels: int
    source_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def stable_fraction(value: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


def audio_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.suffix.lower() in AUDIO_EXTENSIONS)


def probe_audio(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    stream = next(
        (item for item in payload.get("streams", []) if item.get("codec_type") == "audio"), None
    )
    if stream is None:
        raise ValueError(f"No audio stream: {path}")
    return {
        "duration_seconds": float(payload["format"]["duration"]),
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
    }
