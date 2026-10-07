"""Cut deterministic Blind-Real excerpts from downloaded Internet Archive originals.

Two choices here are deliberate and worth stating.

**No loudness normalisation.** Every other set in the benchmark is loudness-normalised,
because there the degradation is applied by us on top of a controlled clean signal. Here
the degradation *is* the recording's history, and level problems are part of that
history. Normalising would quietly repair one of the things a restoration system is
supposed to deal with.

**Resampled to 44.1 kHz stereo anyway.** That is format canonicalisation, not repair: the
benchmark contract is that a system returns audio with the same duration, sample rate and
channel layout it received, so inputs have to be uniform. The source's own rate, channel
count and codec are recorded per clip so nothing is hidden.
"""

from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path
from typing import Any

from .core import stable_fraction
from .pipeline import CANONICAL_SAMPLE_RATE

# A clip must not start in the first or last moments of a recording: those are where
# applause, tuning, announcements and fade-outs live.
EDGE_MARGIN_SECONDS = 15.0


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def probe_format(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels,codec_name,bit_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    parts = result.stdout.strip().split(",")
    out: dict[str, Any] = {}
    if len(parts) >= 1 and parts[0]:
        out["source_codec"] = parts[0]
    for key, index in (("source_sample_rate", 1), ("source_channels", 2), ("source_bit_rate", 3)):
        if len(parts) > index and parts[index] not in ("", "N/A"):
            try:
                out[key] = int(parts[index])
            except ValueError:
                pass
    return out


def clip_start(
    identifier: str,
    clip_index: int,
    duration: float,
    excerpt: float,
    seed: int,
    attempt: int = 0,
    clips_per_identifier: int = 1,
) -> float:
    """Pick a deterministic window inside the usable middle of a recording.

    Each clip of an item is drawn from its own band of the recording, so two clips of
    the same item can never overlap. Drawing both from the whole range independently
    produced near-duplicate pairs, which defeats the per-item cap: an overlapping pair
    is one excerpt counted twice.
    """
    usable = duration - 2 * EDGE_MARGIN_SECONDS - excerpt
    if usable <= 0:
        # Too short for margins: fall back to centring the excerpt.
        return max(0.0, (duration - excerpt) / 2.0)
    bands = max(1, clips_per_identifier)
    band = usable / bands
    if band < excerpt:
        # Not enough room for disjoint bands of a full excerpt; fall back to one band so
        # the caller still gets a valid window rather than a silently overlapping one.
        bands, band, clip_index = 1, usable, 0
    key = f"{identifier}:{clip_index}" if attempt == 0 else f"{identifier}:{clip_index}:attempt{attempt}"
    offset = stable_fraction(key, seed) * max(0.0, band - excerpt if bands > 1 else band)
    return EDGE_MARGIN_SECONDS + math.floor(clip_index * band + offset)


def cut_excerpt(source: Path, output: Path, start: float, seconds: float) -> None:
    """Cut, resample and downmix. No loudness filter: see the module docstring."""
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-i", str(source),
         "-t", str(seconds), "-ar", str(CANONICAL_SAMPLE_RATE), "-ac", "2",
         "-c:a", "pcm_s16le", str(output)],
        check=True,
    )


def clip_quality(path: Path) -> dict[str, float]:
    import numpy as np

    with wave.open(str(path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
        raw = handle.readframes(frames)
    values = np.frombuffer(raw, dtype="<i2")
    if not values.size:
        return {"peak": 0.0, "rms": 0.0, "duration_seconds": 0.0}
    squared = values.astype(np.float64)
    return {
        "peak": float(np.abs(values).max()) / 32768,
        "rms": math.sqrt(float(np.mean(squared * squared))) / 32768,
        "duration_seconds": frames / rate,
    }


def extract_clips(
    downloaded: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    originals_root: Path,
    output_root: Path,
    excerpt_seconds: float = 20.0,
    clips_per_identifier: int = 2,
    seed: int = 20260714,
    min_rms: float = 0.005,
    attempts: int = 4,
    progress: bool = True,
) -> list[dict[str, Any]]:
    """Cut the excerpts and build the Blind-Real Public test manifest.

    A near-silent window is retried with a different deterministic offset, the same way
    the clean segmentation does: in a concert recording a quiet window is usually a gap
    between songs, not music.
    """
    local = {str(r["identifier"]): r for r in downloaded if r.get("local_path")}
    by_identifier: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_identifier.setdefault(str(row["internet_archive_identifier"]), []).append(row)

    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for position, identifier in enumerate(sorted(by_identifier), start=1):
        record = local.get(identifier)
        if record is None:
            skipped.append(f"{identifier}: not downloaded")
            continue
        source = originals_root / str(record["local_path"])
        try:
            duration = probe_duration(source)
            source_format = probe_format(source)
        except (subprocess.CalledProcessError, ValueError) as error:
            skipped.append(f"{identifier}: unreadable ({type(error).__name__})")
            continue
        if duration < excerpt_seconds:
            skipped.append(f"{identifier}: shorter than the excerpt ({duration:.1f}s)")
            continue

        provenance = by_identifier[identifier][0]
        wanted = min(clips_per_identifier, len(by_identifier[identifier]))
        # Two excerpts only make sense if two disjoint windows fit inside the margins.
        # Otherwise emit one: a second copy of the same window would be a duplicate
        # dressed up as a second sample.
        room = duration - 2 * EDGE_MARGIN_SECONDS
        if room < wanted * excerpt_seconds:
            wanted = max(1, int(room // excerpt_seconds))
        for clip_index in range(wanted):
            item_id = f"blind_real--{identifier}--{clip_index:02d}"
            relative = Path("blind_real_test") / f"{item_id}.wav"
            target = output_root / relative
            accepted = None
            for attempt in range(attempts):
                start = clip_start(identifier, clip_index, duration, excerpt_seconds, seed, attempt, wanted)
                cut_excerpt(source, target, start, excerpt_seconds)
                quality = clip_quality(target)
                if (abs(quality["duration_seconds"] - excerpt_seconds) <= 0.05
                        and quality["rms"] >= min_rms):
                    accepted = (start, quality)
                    break
                target.unlink(missing_ok=True)
            if accepted is None:
                skipped.append(f"{item_id}: no usable window after {attempts} attempts")
                continue
            start, quality = accepted
            evidence = provenance.get("selection", {}).get("live_evidence", {})
            rows.append({
                "id": item_id,
                "dataset": "blind_real",
                "split": "blind_real_test",
                "internet_archive_identifier": identifier,
                "internet_archive_metadata": f"https://archive.org/metadata/{identifier}",
                "audio_path": relative.as_posix(),
                "clip_index": clip_index,
                "start_seconds": start,
                "duration_seconds": quality["duration_seconds"],
                "sample_rate": CANONICAL_SAMPLE_RATE,
                "channels": 2,
                "normalization": "none",
                "quality": quality,
                "source_file": record.get("used_file_name") or record.get("file_name"),
                "source_format": record.get("used_file_format") or record.get("file_format"),
                "source_duration_seconds": duration,
                **source_format,
                "license_type": provenance.get("license_type"),
                "license_url": provenance.get("license_url") or record.get("item_licenseurl"),
                "attribution": provenance.get("attribution") or record.get("item_creator"),
                "title": record.get("item_title") or provenance.get("title"),
                "venue": provenance.get("venue"),
                "date": provenance.get("date") or record.get("item_date"),
                "collection": provenance.get("collection") or record.get("item_collection"),
                "live_evidence": evidence,
                "confidence_tier": _tier(evidence),
            })
        if progress and (position % 20 == 0 or position == len(by_identifier)):
            print(f"[clips] {position}/{len(by_identifier)} identifiers, {len(rows)} clips, {len(skipped)} skipped", flush=True)

    if progress and skipped:
        print(f"[clips] {len(skipped)} skipped; first: {skipped[0]}", flush=True)
    rows.sort(key=lambda r: str(r["id"]))
    return rows


def _tier(evidence: dict[str, Any]) -> str:
    if evidence.get("structured_fields"):
        return "structured"
    if evidence.get("strong_phrases"):
        return "strong_phrase"
    if evidence.get("keyword_hits"):
        return "weak_keyword"
    return "none"


def clip_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter

    identifiers = Counter(r["internet_archive_identifier"] for r in rows)
    return {
        "clips": len(rows),
        "distinct_identifiers": len(identifiers),
        "max_clips_per_identifier": max(identifiers.values()) if identifiers else 0,
        "confidence_tiers": dict(Counter(r["confidence_tier"] for r in rows).most_common()),
        "licence_distribution": dict(Counter(str(r["license_type"]) for r in rows).most_common()),
        "source_codecs": dict(Counter(str(r.get("source_codec")) for r in rows).most_common()),
        "source_sample_rates": dict(Counter(str(r.get("source_sample_rate")) for r in rows).most_common()),
        "total_seconds": round(sum(r["duration_seconds"] for r in rows), 1),
    }
