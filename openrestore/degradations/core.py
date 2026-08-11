"""Shared audio, seeding, and recipe helpers for degradation rendering."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

CANONICAL_SAMPLE_RATE = 44_100


def stable_seed(*parts: object) -> int:
    payload = ":".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        audio = audio[:, :2]
    return np.asarray(audio, dtype=np.float32), int(sample_rate)


def write_audio(path: Path, audio: np.ndarray, sample_rate: int = CANONICAL_SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, limit_audio(audio), sample_rate, subtype="PCM_16")


def limit_audio(audio: np.ndarray, peak: float = 0.98) -> np.ndarray:
    result = np.nan_to_num(np.asarray(audio, dtype=np.float32), copy=False)
    max_abs = float(np.max(np.abs(result))) if result.size else 0.0
    if max_abs > peak:
        result = result * (peak / max_abs)
    return np.clip(result, -1.0, 1.0).astype(np.float32)


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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def sample_value(value: Any, rng: np.random.Generator) -> Any:
    if isinstance(value, dict) and "min" in value and "max" in value:
        minimum, maximum = value["min"], value["max"]
        if isinstance(minimum, int) and isinstance(maximum, int):
            return int(rng.integers(minimum, maximum + 1))
        return float(rng.uniform(float(minimum), float(maximum)))
    if isinstance(value, dict) and "choices" in value:
        choices = list(value["choices"])
        return choices[int(rng.integers(0, len(choices)))]
    if isinstance(value, list):
        return [sample_value(item, rng) for item in value]
    if isinstance(value, dict):
        return {key: sample_value(item, rng) for key, item in value.items()}
    return value


def sample_parameters(parameters: dict[str, Any], seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    return {key: sample_value(value, rng) for key, value in parameters.items()}


def butter_filter(
    audio: np.ndarray,
    sample_rate: int,
    kind: str,
    cutoff: float | tuple[float, float],
    order: int = 2,
) -> np.ndarray:
    nyquist = sample_rate / 2
    if isinstance(cutoff, tuple):
        normalized = [max(1e-5, min(freq / nyquist, 0.999)) for freq in cutoff]
    else:
        normalized = max(1e-5, min(cutoff / nyquist, 0.999))
    sos = signal.butter(order, normalized, btype=kind, output="sos")
    return signal.sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio)) + 1e-12))


def run_ffmpeg_codec(audio: np.ndarray, sample_rate: int, codec: str, bitrate: str) -> np.ndarray:
    with TemporaryDirectory() as directory:
        tmp = Path(directory)
        input_path = tmp / "input.wav"
        coded_path = tmp / f"coded.{_codec_extension(codec)}"
        output_path = tmp / "output.wav"
        write_audio(input_path, audio, sample_rate)
        encode = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-b:a",
            bitrate,
            str(coded_path),
        ]
        decode = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(coded_path),
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            str(output_path),
        ]
        subprocess.run(encode, check=True)
        subprocess.run(decode, check=True)
        result, _ = read_audio(output_path)
    return match_length(result, len(audio))


def _codec_extension(codec: str) -> str:
    return {"mp3": "mp3", "aac": "m4a", "opus": "opus"}.get(codec, "mp3")


def match_length(audio: np.ndarray, samples: int) -> np.ndarray:
    if len(audio) > samples:
        return audio[:samples]
    if len(audio) < samples:
        pad = np.zeros((samples - len(audio), audio.shape[1]), dtype=np.float32)
        return np.vstack([audio, pad])
    return audio
