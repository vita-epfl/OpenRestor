#!/usr/bin/env python3
"""Find likely cross-dataset audio duplicates from already-local files.

This conservative tool is report-only: it decodes local WAV/FLAC/AIFF files,
computes gain-normalised spectral fingerprints over representative windows and
reports candidate duplicate groups. It never downloads, deletes, copies, or
changes rights metadata. Candidate groups require human verification.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

SCHEMA = "clean-corpus-acoustic-dedup-v1"
SUPPORTED = {"WAV", "WAVEX", "FLAC", "AIFF"}


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"manifest row is not an object at {path}:{number}")
            yield row


def source_key(row: dict) -> str:
    dataset = str(row.get("dataset") or "").strip()
    source_id = str(row.get("source_id") or row.get("identifier") or "").strip()
    if not dataset or not source_id:
        raise ValueError("each row needs dataset and source_id/identifier")
    return f"{dataset}:{source_id}"


def _windows(duration: float, seconds: float) -> list[float]:
    if duration <= 0:
        return []
    if duration <= seconds:
        return [0.0]
    return sorted({0.0, max(0.0, (duration - seconds) / 2), max(0.0, duration - seconds)})


def _resample(mono: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return mono.astype(np.float64, copy=False)
    factor = math.gcd(int(source_rate), int(target_rate))
    return resample_poly(mono.astype(np.float64, copy=False),
                         target_rate // factor, source_rate // factor)


def _window_embedding(data: np.ndarray, sample_rate: int, target_rate: int = 8000) -> np.ndarray:
    mono = np.asarray(data, dtype=np.float64)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if not len(mono):
        return np.zeros(36, dtype=np.float64)
    mono = _resample(mono, sample_rate, target_rate)
    mono -= float(np.mean(mono))
    rms = float(np.sqrt(np.mean(mono * mono)))
    if rms > 1e-12:
        mono /= rms
    frame = min(2048, max(256, len(mono)))
    hop = max(128, frame // 2)
    if len(mono) < frame:
        mono = np.pad(mono, (0, frame - len(mono)))
    count = 1 + max(0, (len(mono) - frame) // hop)
    frames = np.stack([mono[index * hop:index * hop + frame] for index in range(count)])
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(frame), axis=1)) ** 2 + 1e-12
    frequencies = np.fft.rfftfreq(frame, 1.0 / target_rate)
    edges = np.geomspace(40.0, target_rate / 2, 33)
    bands = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (frequencies >= low) & (frequencies < high)
        bands.append(np.log1p(np.mean(spectrum[:, mask], axis=1)).mean() if mask.any() else 0.0)
    values = np.asarray(bands, dtype=np.float64)
    values -= values.mean()
    scale = np.linalg.norm(values)
    if scale > 1e-12:
        values /= scale
    energy = np.log1p(np.mean(frames * frames, axis=1))
    coarse = np.asarray([energy.mean(), energy.std(), np.percentile(energy, 10),
                         np.percentile(energy, 90)], dtype=np.float64)
    coarse -= coarse.mean()
    scale = np.linalg.norm(coarse)
    if scale > 1e-12:
        coarse /= scale
    return np.concatenate([values, coarse])


def _fingerprint(path: Path, window_seconds: float) -> dict:
    with sf.SoundFile(path) as audio:
        if audio.format not in SUPPORTED:
            raise ValueError(f"unsupported source format {audio.format}")
        duration = len(audio) / audio.samplerate
        embeddings = []
        for start in _windows(duration, window_seconds):
            audio.seek(round(start * audio.samplerate))
            data = audio.read(round(window_seconds * audio.samplerate), dtype="float32",
                              always_2d=True)
            embeddings.append(_window_embedding(data, audio.samplerate))
        if not embeddings:
            raise ValueError("empty audio")
        vector = np.mean(np.stack(embeddings), axis=0)
        norm = float(np.linalg.norm(vector))
        if norm > 1e-12:
            vector /= norm
        quantized = np.clip(np.rint(vector * 32), -127, 127).astype(np.int8).tobytes()
        return {"duration_seconds": duration, "sample_rate": int(audio.samplerate),
                "channels": int(audio.channels), "fingerprint": hashlib.sha256(quantized).hexdigest(),
                "embedding": vector.tolist()}


def _similarity(left: dict, right: dict) -> float:
    a = np.asarray(left["embedding"], dtype=np.float64)
    b = np.asarray(right["embedding"], dtype=np.float64)
    return float(np.clip(np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12), -1.0, 1.0))


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                          for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def local_sources(rows: list[dict]) -> tuple[list[dict], int]:
    """Select declared local paths; a missing declared file still fails visibly."""
    selected = [row for row in rows if row.get("audio_path")]
    return selected, len(rows) - len(selected)


def audit(rows: list[dict], *, window_seconds: float = 20.0,
          similarity_threshold: float = .985,
          duration_tolerance: float = .03) -> tuple[list[dict], dict]:
    if window_seconds <= 0 or not 0 < similarity_threshold <= 1 or duration_tolerance < 0:
        raise ValueError("invalid fingerprint parameters")
    entries, seen = [], set()
    for row in rows:
        key = source_key(row)
        if key in seen:
            raise ValueError(f"duplicate source key: {key}")
        seen.add(key)
        path = Path(str(row.get("audio_path") or ""))
        entry = {"source_key": key, "audio_path": str(path), "status": "error"}
        try:
            if not path.is_file():
                raise FileNotFoundError(path)
            entry.update(_fingerprint(path, window_seconds), status="fingerprinted")
        except (OSError, RuntimeError, ValueError) as error:
            entry["error"] = f"{type(error).__name__}: {error}"
        entries.append(entry)

    parent = list(range(len(entries)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    candidates = []
    buckets = collections.defaultdict(list)
    for index, entry in enumerate(entries):
        if entry["status"] == "fingerprinted":
            buckets[round(math.log1p(entry["duration_seconds"]), 2)].append(index)
    for members in buckets.values():
        for position, left in enumerate(members):
            for right in members[position + 1:]:
                a, b = entries[left], entries[right]
                delta = abs(a["duration_seconds"] - b["duration_seconds"]) / max(
                    a["duration_seconds"], b["duration_seconds"], 1e-9)
                if delta > duration_tolerance:
                    continue
                similarity = _similarity(a, b)
                if similarity >= similarity_threshold:
                    union(left, right)
                    candidates.append({"left": a["source_key"], "right": b["source_key"],
                                       "similarity": round(similarity, 6),
                                       "duration_delta_fraction": round(delta, 6)})

    groups = collections.defaultdict(list)
    for index, entry in enumerate(entries):
        if entry["status"] == "fingerprinted":
            groups[find(index)].append(index)
    output = []
    for index, entry in enumerate(entries):
        row = {key: value for key, value in entry.items() if key != "embedding"}
        if entry["status"] == "fingerprinted":
            members = sorted(groups[find(index)], key=lambda item: entries[item]["source_key"])
            group_id = hashlib.sha256("\n".join(entries[item]["source_key"] for item in members)
                                      .encode()).hexdigest()[:20]
            row.update({"acoustic_dedup_group_id": "acoustic:" + group_id,
                        "acoustic_dedup_representative": index == members[0],
                        "acoustic_duplicate_source_keys": [entries[item]["source_key"] for item in members]})
        output.append(row)
    output.sort(key=lambda row: row["source_key"])
    report = {"schema_version": SCHEMA, "input_sources": len(rows),
              "fingerprinted_sources": sum(e["status"] == "fingerprinted" for e in entries),
              "failed_sources": sum(e["status"] != "fingerprinted" for e in entries),
              "acoustic_duplicate_groups": sum(len(m) > 1 for m in groups.values()),
              "candidate_duplicate_pairs": len(candidates), "candidate_pairs": candidates,
              "parameters": {"window_seconds": window_seconds,
                              "similarity_threshold": similarity_threshold,
                              "duration_tolerance": duration_tolerance},
              "audio_accessed": True, "rights_changed": False,
              "deletion_performed": False, "human_verification_required": True}
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--window-seconds", type=float, default=20.0)
    parser.add_argument("--similarity-threshold", type=float, default=.985)
    parser.add_argument("--duration-tolerance", type=float, default=.03)
    parser.add_argument("--local-only", action="store_true",
                        help="Audit only rows with a declared local audio path")
    args = parser.parse_args()
    manifest_rows = [row for path in args.input for row in read_jsonl(path)]
    rows, skipped = local_sources(manifest_rows) if args.local_only else (manifest_rows, 0)
    if not rows:
        raise ValueError("no local audio sources selected")
    result, report = audit(rows, window_seconds=args.window_seconds,
                           similarity_threshold=args.similarity_threshold,
                           duration_tolerance=args.duration_tolerance)
    report["input_manifest_sources"] = len(manifest_rows)
    report["skipped_without_audio_path"] = skipped
    report["local_only"] = args.local_only
    _write_jsonl(args.out, result)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Audited {len(rows)} local sources; {report['acoustic_duplicate_groups']} candidate groups")


if __name__ == "__main__":
    main()
