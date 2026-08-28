#!/usr/bin/env python3
"""Render clean, degraded, and delta spectrograms from a degradation manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy import signal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--clean-root", type=Path, required=True)
    parser.add_argument("--degraded-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--nperseg", type=int, default=2048)
    parser.add_argument("--noverlap", type=int, default=1536)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_mono(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    return np.mean(audio, axis=1), sample_rate


def spectrogram(
    audio: np.ndarray, sample_rate: int, nperseg: int, noverlap: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frequencies, times, spectrum = signal.stft(
        audio,
        fs=sample_rate,
        nperseg=nperseg,
        noverlap=noverlap,
        boundary=None,
        padded=False,
    )
    db = 20.0 * np.log10(np.maximum(np.abs(spectrum), 1e-6))
    keep = (frequencies >= 20.0) & (frequencies <= min(20_000.0, sample_rate / 2.0))
    return frequencies[keep], times, db[keep]


def draw_spectrogram(
    axis: plt.Axes,
    times: np.ndarray,
    frequencies: np.ndarray,
    values: np.ndarray,
    *,
    title: str,
    cmap: str,
    vmin: float,
    vmax: float,
):
    mesh = axis.pcolormesh(
        times, frequencies, values, shading="auto", cmap=cmap, vmin=vmin, vmax=vmax
    )
    axis.set_yscale("log")
    axis.set_ylim(20, frequencies[-1])
    axis.set_ylabel("Hz")
    axis.set_title(title)
    return mesh


def render_row(row: dict[str, object], args: argparse.Namespace) -> Path:
    clean_path = args.clean_root / str(row["clean_path"])
    degraded_path = args.degraded_root / str(row["degraded_path"])
    clean, sample_rate = read_mono(clean_path)
    degraded, degraded_sample_rate = read_mono(degraded_path)
    if sample_rate != degraded_sample_rate:
        raise ValueError(f"Sample-rate mismatch: {clean_path} and {degraded_path}")

    length = min(len(clean), len(degraded))
    frequencies, times, clean_db = spectrogram(
        clean[:length], sample_rate, args.nperseg, args.noverlap
    )
    _, _, degraded_db = spectrogram(
        degraded[:length], sample_rate, args.nperseg, args.noverlap
    )
    delta_db = np.clip(degraded_db - clean_db, -30.0, 30.0)

    figure, axes = plt.subplots(
        3, 1, figsize=(16, 10), sharex=True, constrained_layout=True
    )
    clean_mesh = draw_spectrogram(
        axes[0], times, frequencies, clean_db, title="Clean", cmap="magma", vmin=-100, vmax=0
    )
    draw_spectrogram(
        axes[1],
        times,
        frequencies,
        degraded_db,
        title="Degraded",
        cmap="magma",
        vmin=-100,
        vmax=0,
    )
    delta_mesh = draw_spectrogram(
        axes[2],
        times,
        frequencies,
        delta_db,
        title="Delta: degraded minus clean (dB)",
        cmap="RdBu_r",
        vmin=-30,
        vmax=30,
    )
    axes[2].set_xlabel("Seconds")
    figure.suptitle(str(row["degradation_recipe_id"]))
    figure.colorbar(clean_mesh, ax=axes[:2], label="Magnitude (dBFS)", shrink=0.75)
    figure.colorbar(delta_mesh, ax=axes[2], label="Difference (dB)", shrink=0.75)

    relative_output = Path(str(row["degraded_path"])).with_suffix(".png")
    output_path = args.output_root / relative_output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=150)
    plt.close(figure)
    return output_path


def main() -> None:
    args = parse_args()
    rows = read_rows(args.manifest)
    for index, row in enumerate(rows, start=1):
        output_path = render_row(row, args)
        print(f"[{index}/{len(rows)}] {output_path}")


if __name__ == "__main__":
    main()
