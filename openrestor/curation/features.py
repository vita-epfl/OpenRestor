"""Local audio feature extraction and import of existing IAMD pilot features.

Every record groups its sampled segments under one source key. Rights metadata
is carried separately and never enters an acoustic score.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import welch

from openrestor.metrics.blind_real import no_reference_descriptors
from .metadata import metadata_cues


SCHEMA = "openrestor-curation-features-v1"
# Version 2 adds a WAV clip fallback for multichannel sources that libsndfile
# cannot encode as FLAC (for example AlbumDB's 12-channel 7.1.4 masters).
EXTRACTOR_VERSION = 2
FORMATS = {"WAV", "WAVEX", "FLAC", "AIFF"}
ACOUSTIC_KEYS = ("near_silent_sample_ratio", "clipped_sample_ratio_channels",
                 "peak_dbfs", "rms_dbfs", "bandwidth_hz", "noise_floor_db",
                 "clipped_sample_ratio", "crest_factor_db", "spectral_flatness",
                 "high_frequency_share", "rolloff_85_hz", "dynamic_range_db",
                 "hiss_proxy", "hum_tonality_proxy", "rolloff_95_hz",
                 "frame_rms_iqr_db", "noise_margin_db", "bandwidth_fraction")

# These fields belong to the curation record rather than to the extracted
# audio passages.  Keep them when a manifest is adapted or an extraction cache
# is reused, so a feature refresh cannot erase human decisions or their audit
# trail.  ``segments`` is deliberately absent: extraction owns that field and
# must rebuild it when the source or sampling policy changes.
CURATION_FIELDS = ("features", "segment_decisions", "source_decision",
                   "curation_decision", "pipeline_decision", "pipeline_reasons",
                   "clean_score", "annotations", "annotation_history", "curation")
PROVENANCE_FIELDS = ("source_sha256", "original_sha256", "audio_sha256", "checksum",
                     "original_format", "lossless_status", "technical_candidate",
                     "provenance_candidate", "redistributable_candidate", "split")
MANIFEST_FIELDS = PROVENANCE_FIELDS + CURATION_FIELDS


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on {path}:{number}") from error


def write_jsonl_atomic(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temporary, path)


def source_key(dataset: str, source_id: str) -> str:
    if not dataset or not source_id or ":" in dataset:
        raise ValueError("dataset and source_id are required; dataset cannot contain ':'")
    return f"{dataset}:{source_id}"


def representative_windows(duration: float, seconds: float = 24.0) -> list[tuple[float, float]]:
    if duration <= 0 or seconds <= 0:
        return []
    if duration < seconds:
        return [(0.0, duration)]
    if duration < 3 * seconds + 2:
        return [((duration - seconds) / 2, seconds)]
    return [(max(0.0, min(duration - seconds, duration * fraction - seconds / 2)), seconds)
            for fraction in (0.1, 0.5, 0.9)]


def _ratio(numerator: np.ndarray, denominator: np.ndarray) -> float:
    return float(numerator.sum() / max(float(denominator.sum()), 1e-12))


def _energy_preserving_mono(data: np.ndarray) -> np.ndarray:
    """Downmix without attenuating wide multichannel masters.

    The historical mean downmix is retained for mono/stereo.  For more than
    two channels, multiplying the mean by ``sqrt(channels)`` preserves total
    RMS energy and avoids treating a 7.1.4 master as near-silent merely because
    its channels were averaged.
    """
    mono = data.mean(axis=1, dtype=np.float64)
    channels = data.shape[1] if data.ndim == 2 else 1
    if channels > 2:
        mono = mono * math.sqrt(channels)
    return mono


def acoustic_features(data: np.ndarray, sample_rate: int) -> dict:
    """Cheap proxies; hiss/hum and bandwidth are review signals, not vetoes."""
    if data.ndim != 2 or data.shape[0] == 0 or sample_rate <= 0:
        raise ValueError("expected a nonempty frames×channels array")
    mono = _energy_preserving_mono(data)
    absolute = np.abs(data)
    rms = float(np.sqrt(np.mean(mono * mono)))
    frame_size = max(1, round(sample_rate * .05))
    frames = mono[:len(mono) // frame_size * frame_size].reshape(-1, frame_size)
    frame_rms = np.sqrt(np.mean(frames * frames, axis=1)) if len(frames) else np.array([rms])
    dynamic_range = float(20 * math.log10((np.percentile(frame_rms, 90) + 1e-12) /
                                          (np.percentile(frame_rms, 10) + 1e-12)))
    # Welch PSD avoids allocating an FFT proportional to the full source length.
    freqs, power = welch(mono, fs=sample_rate, nperseg=min(len(mono), 8192))
    cumulative = np.cumsum(power)
    rolloff = float(freqs[min(len(freqs) - 1, int(np.searchsorted(cumulative, .85 * cumulative[-1])))])
    rolloff_95 = float(freqs[min(len(freqs) - 1, int(np.searchsorted(cumulative, .95 * cumulative[-1])))])
    hiss = _ratio(power[freqs >= 8000], power) if sample_rate > 16000 else 0.0
    bass = (freqs >= 40) & (freqs <= 80)
    local = power[bass]
    hum = float(max((power[np.abs(freqs - frequency) <= 2].max(initial=0)
                     for frequency in (50, 60)), default=0) /
                max(float(np.median(local)) if len(local) else 0, 1e-12))
    frame_percentiles = np.maximum(np.percentile(frame_rms, [25, 75]), 1e-12)
    rms_dbfs = 20 * math.log10(max(rms, 1e-12))
    # The historical descriptor uses one full-source FFT. Bound its working set
    # by taking a centered window at the *original* sample rate. Decimation would
    # alias high frequencies and made the previous bandwidth/hiss fields invalid.
    descriptor_data, descriptor_rate = data, sample_rate
    if len(data) > 262144:
        start = (len(data) - 262144) // 2
        descriptor_data = data[start:start + 262144]
    descriptors = no_reference_descriptors(descriptor_data, descriptor_rate)
    noise_floor_db = float(descriptors["noise_floor_db"])
    return {
        "near_silent_sample_ratio": float(np.mean(absolute < .001)),
        "clipped_sample_ratio_channels": float(np.mean(absolute >= .999)),
        "peak_dbfs": 20 * math.log10(max(float(absolute.max()), 1e-12)),
        "rms_dbfs": rms_dbfs,
        **descriptors,
        "rolloff_85_hz": rolloff,
        "rolloff_95_hz": rolloff_95,
        "dynamic_range_db": dynamic_range,
        "frame_rms_iqr_db": float(20 * math.log10(frame_percentiles[1] / frame_percentiles[0])),
        "noise_margin_db": float(rms_dbfs - noise_floor_db),
        "bandwidth_fraction": float(descriptors.get("bandwidth_hz", 0.0) / max(sample_rate / 2, 1)),
        "hiss_proxy": hiss,
        "hum_tonality_proxy": hum,
    }


def _fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path.resolve()), "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def normalise_metadata(value: object) -> dict:
    metadata = value or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    if not isinstance(metadata.get("metadata_cues") or {}, dict):
        raise ValueError("metadata_cues must be an object")
    result = dict(metadata)
    result.setdefault("metadata_cues", metadata_cues(result))
    return result


def _manifest_provenance(row: dict) -> dict:
    """Carry manifest identity/rights classification into feature caches.

    Acoustic extraction must not erase the checksum or the three independent
    candidate gates.  These fields are metadata only and never affect a score.
    """
    return {field: row[field] for field in PROVENANCE_FIELDS if field in row}


def manifest_curation(row: dict) -> dict:
    """Return curation annotations/history without taking ownership of segments."""
    return {field: row[field] for field in CURATION_FIELDS if field in row}


def refresh_manifest_fields(cached: dict, source: dict) -> None:
    """Replace metadata-only fields; removed fields must not survive a cache hit."""
    for field in MANIFEST_FIELDS:
        cached.pop(field, None)
    cached.update(_manifest_provenance(source))
    cached.update(manifest_curation(source))


def extract_local_source(row: dict, clips_dir: Path, *, seconds: float = 24.0) -> dict:
    """Read one local WAV/FLAC/AIFF; never fetch or convert a lossy source."""
    dataset, identifier = str(row.get("dataset") or ""), str(row.get("source_id") or "")
    key = source_key(dataset, identifier)
    path = Path(str(row.get("audio_path") or ""))
    metadata, rights = normalise_metadata(row.get("metadata")), row.get("rights") or {}
    if not isinstance(rights, dict):
        raise ValueError(f"{key}: rights must be an object")
    if not path.is_file():
        raise FileNotFoundError(f"local source absent: {path}")
    segments = []
    with sf.SoundFile(path) as audio:
        if audio.format not in FORMATS:
            raise ValueError(f"{key}: source format {audio.format} is not WAV/FLAC/AIFF")
        duration = len(audio) / audio.samplerate
        if duration <= 0:
            raise ValueError(f"{key}: empty audio source")
        # A changed source or sampling policy must never reuse an old listening
        # clip (or its cached model scores).
        cache_identity = json.dumps({"source_key": key, "fingerprint": _fingerprint(path),
                                     "segment_seconds": seconds}, sort_keys=True)
        token = hashlib.sha256(cache_identity.encode()).hexdigest()[:20]
        for index, (start, length) in enumerate(representative_windows(duration, seconds), 1):
            audio.seek(round(start * audio.samplerate))
            data = audio.read(round(length * audio.samplerate), dtype="float32", always_2d=True)
            if not len(data):
                continue
            # libFLAC supports at most eight channels through libsndfile. Keep
            # wider masters lossless in a temporary PCM WAV clip instead of
            # dropping the source or silently downmixing it.
            clip_format = "FLAC" if audio.channels <= 8 else "WAV"
            clip_suffix = "flac" if clip_format == "FLAC" else "wav"
            clip_path = clips_dir / f"{token}-p{index}.{clip_suffix}"
            clips_dir.mkdir(parents=True, exist_ok=True)
            if not clip_path.exists():
                sf.write(clip_path, data, audio.samplerate, format=clip_format, subtype="PCM_24")
            segments.append({"segment_id": f"{key}#p{index}", "start_s": start,
                             "duration_s": len(data) / audio.samplerate,
                             "clip_path": str(clip_path.resolve()),
                             "clip_format": clip_format,
                             "acoustic": acoustic_features(data, audio.samplerate),
                             "aesthetics": None, "ast": None, "clap": None})
        result = {"schema": SCHEMA, "dataset": dataset, "source_id": identifier,
                "source_key": key, "audio_path": str(path.resolve()),
                "file_fingerprint": _fingerprint(path), "format": audio.format,
                "sample_rate": audio.samplerate, "channels": audio.channels,
                "duration_s": duration, "segments": segments,
                "metadata": metadata, "rights": rights,
                "extractor": {"version": EXTRACTOR_VERSION, "segment_seconds": seconds}}
        result.update(_manifest_provenance(row))
        result.update(manifest_curation(row))
        return result


def import_iamd_pilot(pilot_dir: Path) -> list[dict]:
    """Adapt only the already measured 50+150 IAMD pilot to the generic schema."""
    selection = [row for row in read_jsonl(pilot_dir / "selection.jsonl")
                 if row.get("pilot_batch") in {"smoke_50", "expand_200"}]
    if len(selection) != 200 or len({row["identifier"] for row in selection}) != 200:
        raise ValueError("IAMD measured selection must contain exactly 200 distinct sources")
    scores = {row["identifier"]: row for row in read_jsonl(pilot_dir / "scores.jsonl")}
    ast = {row["identifier"]: row for row in read_jsonl(pilot_dir / "ast_content_probe.jsonl")}
    clap = {row["identifier"]: row for row in read_jsonl(pilot_dir / "clap_contrastive_probe.jsonl")}
    result = []
    for row in selection:
        identifier = row["identifier"]
        score = scores.get(identifier)
        if not score or score.get("status") != "measured" or not score.get("excerpts"):
            raise ValueError(f"IAMD source lacks measured segments: {identifier}")
        segments = []
        for index, part in enumerate(score["excerpts"], 1):
            clip = Path(part["clip_path"])
            if not clip.is_file() or clip.parent.resolve() != (pilot_dir / "clips").resolve():
                raise ValueError(f"IAMD clip absent/outside pilot: {clip}")
            segment = {"segment_id": f"iamd:{identifier}#p{index}",
                       "start_s": part["start_s"], "duration_s": part["duration_s"],
                       "clip_path": str(clip.resolve()),
                       "acoustic": {key: part[key] for key in ACOUSTIC_KEYS if key in part},
                       "aesthetics": part.get("audiobox_axes") or None,
                       "ast": None, "clap": None}
            if ast.get(identifier, {}).get("status") == "scored" and ast[identifier].get("clip_path") == str(clip):
                segment["ast"] = {"interest_labels": ast[identifier]["interest_labels"],
                                  "model_revision": ast[identifier]["model_revision"]}
            if clap.get(identifier, {}).get("status") == "scored" and clap[identifier].get("clip_path") == str(clip):
                segment["clap"] = {"group_scores": clap[identifier]["group_scores"],
                                   "model_revision": clap[identifier]["model_revision"],
                                   "prompt_version": clap[identifier]["prompt_version"]}
            segments.append(segment)
        path = Path(row["local_original_path"])
        metadata = {"title": row.get("title"), "creator": row.get("creator"),
                    "collection": row.get("collection"), "genre": row.get("genre_proxy"),
                    "description": row.get("description"), "subject": row.get("subject"),
                    "filename": row.get("name")}
        # Recompute generic cues so policy revisions see newly added patterns
        # (the historical pilot cache may contain an older cue vocabulary).
        metadata["metadata_cues"] = metadata_cues(metadata)
        result.append({"schema": SCHEMA, "dataset": "iamd", "source_id": identifier,
                       "source_key": source_key("iamd", identifier), "audio_path": str(path.resolve()),
                       "file_fingerprint": _fingerprint(path), "format": score.get("detected_format"),
                       "sample_rate": score.get("sample_rate"), "channels": score.get("channels"),
                       "duration_s": score.get("duration_s"), "segments": segments,
                       "metadata": metadata,
                       "rights": {"archive_license_url": row.get("archive_license_url"),
                                  "archive_licence_category": row.get("archive_licence_category"),
                                  "provenance_candidate": row.get("provenance_candidate"),
                                  "status": "unreviewed"},
                       "extractor": {"version": 1, "source": "iamd_pilot_cached"}})
    return sorted(result, key=lambda row: row["source_key"])


def enrich_local_acoustics(records: list[dict], *, only_missing: bool = True) -> list[dict]:
    """Recompute cheap no-reference quality descriptors from existing local clips.

    This deliberately does not run any model and never downloads or rewrites source
    audio.  It is a resumable enrichment step so historical IAMD model caches remain
    immutable while newer datasets can use the same feature names.
    """
    enriched = []
    for record in records:
        row = dict(record)
        metadata = dict(record.get("metadata") or {})
        metadata["metadata_cues"] = metadata_cues(metadata)
        row["metadata"] = metadata
        row["segments"] = []
        for segment in record.get("segments") or []:
            part = dict(segment)
            path = Path(str(part.get("clip_path") or ""))
            if not path.is_file():
                raise FileNotFoundError(f"clip absent for {record.get('source_key')}: {path}")
            acoustic = dict(part.get("acoustic") or {})
            if not only_missing or any(key not in acoustic for key in
                                      ("rolloff_95_hz", "frame_rms_iqr_db", "noise_margin_db",
                                       "bandwidth_fraction")):
                data, rate = sf.read(path, dtype="float32", always_2d=True)
                acoustic.update(acoustic_features(data, rate))
            part["acoustic"] = acoustic
            row["segments"].append(part)
        row["extractor"] = {**(record.get("extractor") or {}),
                             "acoustic_enrichment_version": 2}
        enriched.append(row)
    return enriched
