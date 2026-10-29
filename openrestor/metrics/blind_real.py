"""Blind-Real scoring: no clean reference, and aggregation that respects source items.

Two constraints shape this, and both are the opposite of how the paired tracks work.

**There is no clean reference**, so no similarity-to-clean metric exists. Nor is
input-to-output similarity usable as a primary score: a system that correctly removes
hiss moves away from its input, and rewarding closeness would punish it for working.
What is left are no-reference estimates of the output alone, read as a change relative
to the same estimate on the input.

**Clips are not independent.** An Internet Archive item can contribute two excerpts, and
the two share a venue, a microphone, a taper and a mix. Averaging over clips would let a
two-excerpt item count twice as much as a one-excerpt item, so scores aggregate clip,
then identifier, then dataset.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .core import EPSILON

# Lower is better for these; the rest read higher-is-better.
LOWER_IS_BETTER = ("noise_floor_db", "clipped_sample_ratio", "spectral_flatness")


def _mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim <= 1:
        return audio
    mono = audio.mean(axis=1)
    channels = audio.shape[1]
    return mono * np.sqrt(channels) if channels > 2 else mono


def no_reference_descriptors(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    """Estimate quality-related properties of one signal, with no reference available.

    Every one of these is a proxy with a known failure mode, documented beside it. They
    are reported together precisely because no single one of them is trustworthy alone.
    """
    mono = _mono(np.asarray(audio, dtype=np.float64))
    if mono.size == 0:
        return {}
    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(mono.size, 1.0 / sample_rate)
    total = float(spectrum.sum()) + EPSILON

    # Bandwidth actually present: where the cumulative spectrum reaches 99% of its energy.
    # Fails on content that is genuinely dark rather than band-limited.
    cumulative = np.cumsum(spectrum) / total
    # ``searchsorted`` returns ``len(freqs)`` when numerical rounding leaves the
    # final cumulative value just below the target.  Clamp the index so very
    # short/silent clips still produce a descriptor instead of an IndexError.
    bandwidth_index = min(len(freqs) - 1, int(np.searchsorted(cumulative, 0.99)))
    bandwidth_hz = float(freqs[bandwidth_index])

    # Noise floor: the 10th percentile of frame energy, in dB. Fails on music with no
    # quiet frames, where it measures the music rather than the floor.
    frame = max(1, int(0.05 * sample_rate))
    frames = mono[: mono.size - mono.size % frame].reshape(-1, frame)
    floor = float(np.percentile(np.sqrt((frames ** 2).mean(axis=1)), 10)) if frames.size else 0.0
    noise_floor_db = 20.0 * math.log10(floor + EPSILON)

    # Hard clipping: samples sitting at full scale. Fails on deliberately limited masters.
    clipped = float(np.mean(np.abs(mono) >= 0.999))

    # Crest factor: peak over RMS, in dB. Low values mean heavy compression or clipping.
    rms = float(np.sqrt(np.mean(mono ** 2)))
    crest_db = 20.0 * math.log10((float(np.abs(mono).max()) + EPSILON) / (rms + EPSILON))

    # Spectral flatness: high for noise-like signal, low for tonal. A broadband hiss
    # raises it; so does a cymbal-heavy passage.
    power = spectrum ** 2 + EPSILON
    flatness = float(np.exp(np.mean(np.log(power))) / np.mean(power))

    # High-frequency share, a coarse brightness measure.
    high = float(spectrum[freqs >= 8000].sum()) / total

    return {
        "bandwidth_hz": bandwidth_hz,
        "noise_floor_db": noise_floor_db,
        "clipped_sample_ratio": clipped,
        "crest_factor_db": crest_db,
        "spectral_flatness": flatness,
        "high_frequency_share": high,
    }


def score_clip(degraded: np.ndarray, restored: np.ndarray, sample_rate: int) -> dict[str, float]:
    """Describe the input and the output, and report the change between them.

    The deltas are the interesting part, but they are descriptive, not a verdict: a
    system can raise bandwidth by inventing high frequencies, and these numbers cannot
    tell that apart from recovering real ones.
    """
    before = no_reference_descriptors(degraded, sample_rate)
    after = no_reference_descriptors(restored, sample_rate)
    row = {f"input_{k}": v for k, v in before.items()}
    row.update({f"output_{k}": v for k, v in after.items()})
    for key in after:
        if key in before:
            row[f"delta_{key}"] = after[key] - before[key]
    return row


def aggregate(
    clip_rows: Iterable[dict[str, Any]], identifier_field: str = "internet_archive_identifier"
) -> dict[str, Any]:
    """Average clips within a source item, then items within the dataset.

    The middle stage is the point. Averaging clips directly would weight a two-excerpt
    recording twice as heavily as a one-excerpt recording, letting a handful of items
    steer the dataset figure.
    """
    rows = list(clip_rows)
    if not rows:
        return {"clips": 0, "identifiers": 0, "dataset": {}, "per_identifier": []}

    metric_keys = sorted({k for row in rows for k, v in row.items() if isinstance(v, (int, float)) and not isinstance(v, bool)})
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(identifier_field))].append(row)

    per_identifier = []
    for identifier in sorted(grouped):
        clips = grouped[identifier]
        means = {}
        for key in metric_keys:
            values = [float(c[key]) for c in clips if key in c]
            if values:
                means[key] = float(np.mean(values))
        per_identifier.append({"identifier": identifier, "clips": len(clips), "metrics": means})

    dataset = {}
    for key in metric_keys:
        values = [item["metrics"][key] for item in per_identifier if key in item["metrics"]]
        if values:
            dataset[key] = {
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "std": float(np.std(values)),
                "identifiers": len(values),
            }
    return {
        "clips": len(rows),
        "identifiers": len(per_identifier),
        "aggregation": "clip -> identifier -> dataset",
        "dataset": dataset,
        "per_identifier": per_identifier,
    }


def score_blind_real(
    manifest_rows: list[dict[str, Any]],
    degraded_root: Path,
    restored_paths: dict[str, Path],
    progress: bool = False,
) -> dict[str, Any]:
    """Score every manifest item whose restoration was supplied, then aggregate.

    A missing restoration is reported rather than skipped silently: a partial run must
    not be presentable as a complete score.
    """
    from ..degradations.core import read_audio

    clip_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    failed: list[str] = []
    for index, row in enumerate(manifest_rows, start=1):
        item_id = str(row["id"])
        restored = restored_paths.get(item_id)
        if restored is None:
            missing.append(item_id)
            continue
        try:
            degraded, rate = read_audio(degraded_root / row["audio_path"])
            output, out_rate = read_audio(restored)
            if out_rate != rate or output.shape != degraded.shape:
                failed.append(f"{item_id}: format mismatch {out_rate}Hz {output.shape} vs {rate}Hz {degraded.shape}")
                continue
            metrics = score_clip(degraded, output, rate)
        except Exception as error:  # noqa: BLE001 - one bad item must not end scoring
            failed.append(f"{item_id}: {type(error).__name__}: {error}")
            continue
        clip_rows.append({
            "id": item_id,
            "internet_archive_identifier": row.get("internet_archive_identifier"),
            "confidence_tier": row.get("confidence_tier"),
            **metrics,
        })
        if progress and (index % 50 == 0 or index == len(manifest_rows)):
            print(f"[blind-real-score] {index}/{len(manifest_rows)}", flush=True)

    report = aggregate(clip_rows)
    report["missing_restorations"] = missing
    report["failures"] = failed
    report["scored_clips"] = len(clip_rows)
    report["expected_clips"] = len(manifest_rows)
    report["complete"] = not missing and not failed
    report["caveats"] = [
        "No clean reference exists, so no similarity-to-clean metric is reported.",
        "Input-to-output similarity is deliberately not a score: correct restoration moves away from the input.",
        "Every descriptor is a proxy with a documented failure mode; none is a verdict on its own.",
        "A rise in bandwidth cannot be distinguished here from invented high frequencies.",
        "Clips of one source item share venue, microphone and mix, which is why items are averaged before the dataset.",
    ]
    return report
