"""Primitive OpenRestore v0.1 degradation effects."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal

from .core import butter_filter, limit_audio, match_length, rms, run_ffmpeg_codec
from .ariel_effects import apply_ariel_effect


def apply_operation(
    audio: np.ndarray,
    sample_rate: int,
    primitive: str,
    variant: str | None,
    params: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, Any]]:
    handlers = {
        "ariel": ariel,
        "distant_mic_capture": distant_mic_capture,
        "eq_coloration": eq_coloration,
        "dynamics": dynamics,
        "reverb_room": reverb_room,
        "gain_level": gain_level,
        "clipping_distortion": clipping_distortion,
        "stereo_spatial": stereo_spatial,
        "bandwidth_filtering": bandwidth_filtering,
        "noise_interference": noise_interference,
        "device_mic_response": device_mic_response,
        "codec_resampling": codec_resampling,
    }
    if primitive not in handlers:
        raise ValueError(f"Unknown primitive: {primitive}")
    return handlers[primitive](audio, sample_rate, variant, params, rng)


def ariel(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    if not variant:
        raise ValueError("An ARIEL operation requires an effect variant")
    return apply_ariel_effect(audio, sample_rate, variant, params, rng)


def distant_mic_capture(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    """Simulate a physically distant microphone capture, rather than a dry/wet reverb mix."""
    try:
        import pyroomacoustics as pra
    except ImportError as error:
        raise RuntimeError("distant_mic_capture requires pyroomacoustics") from error

    room_size = np.asarray(params.get("room_size_m", [12.0, 16.0, 5.0]), dtype=float)
    distance = float(params.get("distance_m", rng.uniform(5.0, 8.0)))
    absorption = float(params.get("absorption", rng.uniform(0.12, 0.28)))
    source = np.array([room_size[0] * 0.35, room_size[1] * 0.45, 1.5])
    microphone = source + np.array([distance, 0.0, -0.2])
    if microphone[0] >= room_size[0] - 0.5:
        source[0] = room_size[0] - distance - 0.6
        microphone[0] = room_size[0] - 0.6
    room = pra.ShoeBox(room_size, absorption=absorption, max_order=10, fs=sample_rate)
    room.add_source(source)
    room.add_microphone_array(np.array([microphone]).T)
    room.compute_rir()
    rir = room.rir[0][0]
    rir = rir[np.argmax(rir):]
    captured = np.column_stack(
        [signal.fftconvolve(audio[:, channel], rir, mode="full")[: len(audio)] for channel in range(audio.shape[1])]
    )
    air_cutoff = float(params.get("air_absorption_cutoff_hz", rng.uniform(4_500, 7_000)))
    captured = butter_filter(captured, sample_rate, "lowpass", air_cutoff, order=2)
    snr_db = float(params.get("room_noise_snr_db", rng.uniform(30, 38)))
    if snr_db < 100:
        noise = rng.normal(0, 1, captured.shape).astype(np.float32)
        captured += noise * (rms(captured) / max(rms(noise) * (10 ** (snr_db / 20)), 1e-8))
    input_rms, output_rms = rms(audio), rms(captured)
    if output_rms > 1e-8:
        captured *= input_rms / output_rms
    return limit_audio(captured), {
        "variant": variant or "room_capture",
        "room_size_m": room_size.tolist(),
        "source_position_m": source.tolist(),
        "microphone_position_m": microphone.tolist(),
        "distance_m": distance,
        "absorption": absorption,
        "air_absorption_cutoff_hz": air_cutoff,
        "room_noise_snr_db": snr_db,
    }


def eq_coloration(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("mode", "tilt")
    gain_db = float(params.get("gain_db", 3.0))
    amount = (10 ** (abs(gain_db) / 20) - 1.0) * (1 if gain_db >= 0 else -1)
    if variant in {"boom", "muddiness"}:
        cutoff = float(params.get("frequency_hz", 180 if variant == "boom" else 420))
        band = butter_filter(audio, sample_rate, "lowpass", cutoff, order=2)
        result = audio + amount * band
    elif variant in {"dark", "missing_air", "airy_lack_high_frequencies"}:
        cutoff = float(params.get("cutoff_hz", 8_000))
        result = butter_filter(audio, sample_rate, "lowpass", cutoff, order=3)
    elif variant in {"brightness", "harsh"}:
        cutoff = float(params.get("frequency_hz", 4_000))
        high = audio - butter_filter(audio, sample_rate, "lowpass", cutoff, order=2)
        result = audio + amount * high
    elif variant == "comb_filter_phase_coloration":
        delay_ms = float(params.get("delay_ms", 4.0))
        mix = float(params.get("mix", 0.35))
        delay = max(1, int(sample_rate * delay_ms / 1000))
        delayed = np.vstack([np.zeros((delay, audio.shape[1]), dtype=np.float32), audio[:-delay]])
        result = audio + mix * delayed
        params = {**params, "delay_samples": delay}
    else:
        cutoff = float(params.get("frequency_hz", 1_000))
        low = butter_filter(audio, sample_rate, "lowpass", cutoff, order=2)
        high = audio - low
        result = low * (1 - amount * 0.5) + high * (1 + amount * 0.5)
    return limit_audio(result), {**params, "variant": variant}


def dynamics(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("mode", "compression")
    if variant == "agc_pumping":
        target = float(params.get("target_rms", 0.12))
        strength = float(params.get("strength", 0.65))
        frame = max(256, int(sample_rate * float(params.get("window_ms", 250)) / 1000))
        env = _moving_rms(audio, frame)
        gain = (target / np.maximum(env, 1e-4)) ** strength
        gain = np.clip(gain, float(params.get("min_gain", 0.35)), float(params.get("max_gain", 2.5)))
        result = audio * gain[:, None]
        return limit_audio(result), {**params, "variant": variant}
    threshold_db = float(params.get("threshold_db", -18))
    ratio = float(params.get("ratio", 4.0))
    makeup_db = float(params.get("makeup_db", 2.0))
    threshold = 10 ** (threshold_db / 20)
    envelope = _moving_rms(audio, max(64, int(sample_rate * float(params.get("attack_ms", 10)) / 1000)))
    over = np.maximum(envelope / max(threshold, 1e-6), 1.0)
    gain = over ** (1 / ratio - 1)
    result = audio * gain[:, None] * (10 ** (makeup_db / 20))
    return limit_audio(result), {**params, "variant": variant}


def _moving_rms(audio: np.ndarray, frame: int) -> np.ndarray:
    mono = np.mean(audio, axis=1)
    kernel = np.ones(frame, dtype=np.float32) / frame
    power = np.convolve(mono * mono, kernel, mode="same")
    return np.sqrt(power + 1e-12)


def reverb_room(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    room = variant or params.get("room", "small")
    wet = float(params.get("wet", 0.18))
    decay = float(params.get("decay_seconds", {"small": 0.35, "big": 1.2, "mixed": 0.7}.get(room, 0.5)))
    predelay = int(sample_rate * float(params.get("predelay_ms", 12)) / 1000)
    ir_length = max(predelay + 32, int(sample_rate * decay))
    times = np.arange(ir_length, dtype=np.float32) / sample_rate
    ir = np.exp(-times / max(decay / 4, 1e-3)) * rng.normal(0, 1, ir_length).astype(np.float32)
    ir[:predelay] = 0
    ir[predelay] += 1.0
    ir /= max(float(np.max(np.abs(ir))), 1e-6)
    wet_audio = np.column_stack([signal.fftconvolve(audio[:, ch], ir, mode="full")[: len(audio)] for ch in range(audio.shape[1])])
    result = (1 - wet) * audio + wet * wet_audio
    return limit_audio(result), {**params, "variant": room, "ir_source": "deterministic_synthetic"}


def gain_level(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    gain_db = float(params.get("gain_db", -8.0))
    result = audio * (10 ** (gain_db / 20))
    pre_peak = float(np.max(np.abs(audio)))
    post_peak = float(np.max(np.abs(result)))
    hidden = bool(post_peak > 1.0)
    return limit_audio(result), {**params, "variant": variant or "gain", "pre_peak": pre_peak, "post_peak": post_peak, "hidden_clipping": hidden}


def clipping_distortion(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("curve", "soft")
    drive = float(params.get("drive", 1.8))
    driven = audio * drive
    if variant == "hard":
        threshold = float(params.get("threshold", 0.7))
        result = np.clip(driven, -threshold, threshold) / threshold
    elif variant == "asymmetric":
        result = np.where(driven >= 0, np.tanh(driven), np.tanh(driven * 0.65))
    else:
        result = np.tanh(driven)
    clipped_ratio = float(np.mean(np.abs(driven) >= 1.0))
    return limit_audio(result), {**params, "variant": variant, "clipped_sample_ratio": clipped_ratio}


def stereo_spatial(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("mode", "width")
    left, right = audio[:, 0], audio[:, 1]
    if variant == "mono":
        mono = np.mean(audio, axis=1)
        result = np.column_stack([mono, mono])
    elif variant == "one_channel_damage":
        damaged = right * (10 ** (float(params.get("right_gain_db", -8)) / 20))
        if bool(params.get("right_lowpass", True)):
            damaged = butter_filter(damaged[:, None], sample_rate, "lowpass", float(params.get("cutoff_hz", 4_000)), 2)[:, 0]
        if bool(params.get("invert_polarity", False)):
            damaged = -damaged
        delay = int(params.get("delay_samples", 0))
        if delay > 0:
            damaged = np.concatenate([np.zeros(delay, dtype=np.float32), damaged[:-delay]])
        result = np.column_stack([left, damaged])
    else:
        width = float(params.get("width", 0.45))
        mid = (left + right) * 0.5
        side = (left - right) * 0.5 * width
        result = np.column_stack([mid + side, mid - side])
    corr = float(np.corrcoef(result[:, 0], result[:, 1])[0, 1]) if len(result) > 1 else 1.0
    return limit_audio(result), {**params, "variant": variant, "channel_correlation": corr}


def bandwidth_filtering(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("mode", "lowpass")
    if variant == "telephone":
        result = butter_filter(audio, sample_rate, "bandpass", (300, 3_400), order=4)
    elif variant == "highpass":
        result = butter_filter(audio, sample_rate, "highpass", float(params.get("cutoff_hz", 120)), order=3)
    elif variant == "low_sample_rate":
        intermediate = int(params.get("intermediate_sample_rate", 12_000))
        down = signal.resample_poly(audio, intermediate, sample_rate, axis=0)
        result = signal.resample_poly(down, sample_rate, intermediate, axis=0)
        result = match_length(result.astype(np.float32), len(audio))
    else:
        result = butter_filter(audio, sample_rate, "lowpass", float(params.get("cutoff_hz", 8_000)), order=4)
    return limit_audio(result), {**params, "variant": variant}


def noise_interference(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("mode", "broadband")
    snr_db = float(params.get("snr_db", 20))
    if variant == "hum":
        freq = float(params.get("frequency_hz", 50))
        harmonics = int(params.get("harmonics", 4))
        t = np.arange(len(audio), dtype=np.float32) / sample_rate
        noise = sum(np.sin(2 * math.pi * freq * (i + 1) * t) / (i + 1) for i in range(harmonics))
        noise = np.column_stack([noise, noise]).astype(np.float32)
    elif variant == "clicks_crackle":
        click_rate_hz = float(params.get("click_rate_hz", 1.5))
        crackle_rate_hz = float(params.get("crackle_rate_hz", 14.0))
        click_level_db = float(params.get("click_level_db", -8.0))
        crackle_level_db = float(params.get("crackle_level_db", -26.0))
        click_count = int(rng.poisson(click_rate_hz * len(audio) / sample_rate))
        crackle_count = int(rng.poisson(crackle_rate_hz * len(audio) / sample_rate))
        noise = np.zeros_like(audio, dtype=np.float32)
        signal_rms = rms(audio)
        for count, level_db, width_range in ((click_count, click_level_db, (8, 48)), (crackle_count, crackle_level_db, (2, 12))):
            for _ in range(count):
                start = int(rng.integers(0, len(audio)))
                width = int(rng.integers(*width_range))
                end = min(len(audio), start + width)
                envelope = np.exp(-np.arange(end - start, dtype=np.float32) / max(width / 5.0, 1.0))
                amplitude = signal_rms * (10 ** (level_db / 20)) * rng.choice([-1.0, 1.0])
                noise[start:end] += (amplitude * envelope)[:, None]
        result = audio + noise
        return limit_audio(result), {
            **params,
            "variant": variant,
            "click_count": click_count,
            "crackle_count": crackle_count,
        }
    elif variant == "buzz":
        noise = rng.normal(0, 1, audio.shape).astype(np.float32)
        noise = butter_filter(noise, sample_rate, "bandpass", (80, 5_000), order=2)
    else:
        noise = rng.normal(0, 1, audio.shape).astype(np.float32)
        if variant == "hiss":
            noise = noise - butter_filter(noise, sample_rate, "lowpass", 3_000, order=2)
    scale = rms(audio) / max(rms(noise) * (10 ** (snr_db / 20)), 1e-8)
    result = audio + noise * scale
    return limit_audio(result), {**params, "variant": variant, "actual_snr_db": snr_db}


def device_mic_response(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("mode", "consumer_mic")
    child_params: list[dict[str, Any]] = []
    result = butter_filter(audio, sample_rate, "bandpass", (float(params.get("low_hz", 120)), float(params.get("high_hz", 8_000))), order=3)
    child_params.append({"primitive": "bandwidth_filtering", "variant": "device_bandpass"})
    if variant == "bluetooth_small_speaker_recapture":
        result, eq_params = eq_coloration(result, sample_rate, "muddiness", {"gain_db": float(params.get("box_gain_db", 4)), "frequency_hz": 450}, rng)
        child_params.append({"primitive": "eq_coloration", "params": eq_params})
        result, clip_params = clipping_distortion(result, sample_rate, "soft", {"drive": float(params.get("drive", 1.25))}, rng)
        child_params.append({"primitive": "clipping_distortion", "params": clip_params})
    result, noise_params = noise_interference(result, sample_rate, "hiss", {"snr_db": float(params.get("self_noise_snr_db", 28))}, rng)
    child_params.append({"primitive": "noise_interference", "params": noise_params})
    mono_mix = float(params.get("mono_mix", 0.35))
    mono = np.mean(result, axis=1, keepdims=True)
    result = result * (1 - mono_mix) + np.repeat(mono, 2, axis=1) * mono_mix
    return limit_audio(result), {**params, "variant": variant, "child_operations": child_params}


def codec_resampling(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("codec", "mp3")
    if variant == "resampling":
        intermediate = int(params.get("intermediate_sample_rate", 16_000))
        down = signal.resample_poly(audio, intermediate, sample_rate, axis=0)
        result = signal.resample_poly(down, sample_rate, intermediate, axis=0)
        return limit_audio(match_length(result.astype(np.float32), len(audio))), {**params, "variant": variant}
    bitrate = str(params.get("bitrate", "96k"))
    result = run_ffmpeg_codec(audio, sample_rate, variant, bitrate)
    return limit_audio(result), {**params, "variant": variant}
