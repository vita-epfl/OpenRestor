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
        # Canonical benchmark operations. The original primitives above remain
        # callable so historic configs can still be reproduced.
        "spectral_eq": spectral_eq,
        "compression": compression,
        "clipping": clipping,
        "saturation_overdrive": saturation_overdrive,
        "dropouts_glitches": dropouts_glitches,
        "neural_codec": neural_codec,
        "transcode_chain": transcode_chain,
        "stereo_collapse": stereo_collapse,
        "channel_damage": channel_damage,
        "pitch_speed_instability": pitch_speed_instability,
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



def spectral_eq(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    """Strong, one-mode spectral coloration replacing the old individual EQ recipes."""
    mode = variant or str(params.get("mode", "multi_band"))
    ariel_modes = {
        "multi_band": "xband",
        "high_shelf_cut": "bright",
        "high_shelf_boost": "dark",
        "air_cut": "airy",
        "low_shelf_cut": "boom",
        "low_shelf_thin": "warm",
    }
    if mode in ariel_modes:
        result, source = apply_ariel_effect(audio, sample_rate, ariel_modes[mode], params, rng)
        return limit_audio(result), {"variant": mode, "source_effect": source}
    if mode == "low_mid_emphasis":
        centre_hz = float(params.get("centre_hz", rng.uniform(250, 500)))
        width_hz = float(params.get("width_hz", rng.uniform(160, 300)))
        low, high = max(80.0, centre_hz - width_hz / 2), min(2_000.0, centre_hz + width_hz / 2)
        band = butter_filter(audio, sample_rate, "bandpass", (low, high), order=2)
        gain_db = float(params.get("gain_db", rng.uniform(8, 15)))
        result = audio + band * (10 ** (gain_db / 20) - 1)
        return limit_audio(result), {"variant": mode, "centre_hz": centre_hz, "width_hz": width_hz, "gain_db": gain_db}
    if mode == "midrange_notch":
        attenuation_db = float(params.get("attenuation_db", rng.uniform(10, 20)))
        sos = signal.cheby2(2, attenuation_db, [350, 3_500], "bandstop", fs=sample_rate, output="sos")
        return signal.sosfilt(sos, audio, axis=0), {"variant": mode, "attenuation_db": attenuation_db}
    if mode == "broad_tilt":
        pivot_hz = float(params.get("pivot_hz", rng.uniform(800, 2_000)))
        tilt_db = float(params.get("tilt_db", rng.choice([-1, 1]) * rng.uniform(7, 14)))
        low = butter_filter(audio, sample_rate, "lowpass", pivot_hz, order=2)
        high = audio - low
        result = low * (10 ** (-tilt_db / 40)) + high * (10 ** (tilt_db / 40))
        return limit_audio(result), {"variant": mode, "pivot_hz": pivot_hz, "tilt_db": tilt_db}
    raise ValueError(f"Unknown spectral_eq mode: {mode}")


def compression(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    mode = variant or str(params.get("mode", "strong_compression"))
    source_effect = "punch" if mode == "transient_softening" else "comp"
    if mode not in {"strong_compression", "transient_softening"}:
        raise ValueError(f"Unknown compression mode: {mode}")
    result, source = apply_ariel_effect(audio, sample_rate, source_effect, params, rng)
    return limit_audio(result), {"variant": mode, "source_effect": source}


def clipping(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    result, source = apply_ariel_effect(audio, sample_rate, "clip", params, rng)
    return limit_audio(result), {"variant": variant or "hard_clip", "source_effect": source}


def saturation_overdrive(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    curve = variant or str(params.get("curve", "soft"))
    drive = float(params.get("drive", rng.uniform(3.0, 6.0)))
    return clipping_distortion(audio, sample_rate, curve, {**params, "drive": drive}, rng)


def _dropout_ranges(samples: int, sample_rate: int, rng: np.random.Generator, rate_hz: float, min_ms: float, max_ms: float) -> list[tuple[int, int]]:
    count = max(1, int(rng.poisson(rate_hz * samples / sample_rate)))
    ranges: list[tuple[int, int]] = []
    for _ in range(count):
        start = int(rng.integers(0, samples))
        width = int(sample_rate * rng.uniform(min_ms, max_ms) / 1000)
        ranges.append((start, min(samples, start + max(1, width))))
    return ranges


def dropouts_glitches(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    mode = variant or str(params.get("mode", "mixed"))
    ranges = _dropout_ranges(
        len(audio), sample_rate, rng, float(params.get("rate_hz", rng.uniform(2.0, 6.0))),
        float(params.get("min_duration_ms", 12)), float(params.get("max_duration_ms", 65)),
    )
    result = audio.copy()
    for start, end in ranges:
        if mode == "repeat" and start > 0:
            source_start = max(0, start - (end - start))
            result[start:end] = result[source_start : source_start + end - start]
        elif mode == "noise":
            noise = rng.normal(0, rms(audio) * 0.45, (end - start, audio.shape[1]))
            result[start:end] = noise.astype(np.float32)
        elif mode == "attenuate":
            result[start:end] *= 10 ** (float(params.get("attenuation_db", -28)) / 20)
        else:
            result[start:end] = 0
    return limit_audio(result), {"variant": mode, "dropout_count": len(ranges), "ranges_samples": ranges}


def neural_codec(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    """Deterministic low-rate latent-quantization proxy; no model weights are shipped."""
    intermediate = int(params.get("intermediate_sample_rate", rng.choice([8_000, 12_000, 16_000])))
    bits = int(params.get("quantization_bits", rng.choice([5, 6, 7])))
    down = signal.resample_poly(audio, intermediate, sample_rate, axis=0)
    mu = 255.0
    encoded = np.sign(down) * np.log1p(mu * np.abs(down)) / np.log1p(mu)
    levels = 2**bits - 1
    encoded = np.round((encoded + 1) * levels / 2) * 2 / levels - 1
    decoded = np.sign(encoded) * np.expm1(np.abs(encoded) * np.log1p(mu)) / mu
    result = signal.resample_poly(decoded, sample_rate, intermediate, axis=0)
    return limit_audio(match_length(result.astype(np.float32), len(audio))), {
        "variant": variant or "latent_quantization_proxy",
        "intermediate_sample_rate": intermediate,
        "quantization_bits": bits,
        "implementation": "deterministic_neural_codec_proxy",
    }


def transcode_chain(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    chain = variant or str(params.get("chain", "mp3_then_opus"))
    stages = {
        "mp3_then_opus": (("mp3", str(params.get("mp3_bitrate", "40k"))), ("opus", str(params.get("opus_bitrate", "32k")))),
        "aac_then_mp3": (("aac", str(params.get("aac_bitrate", "48k"))), ("mp3", str(params.get("mp3_bitrate", "32k")))),
    }
    if chain not in stages:
        raise ValueError(f"Unknown transcode chain: {chain}")
    result = audio
    for codec, bitrate in stages[chain]:
        result = run_ffmpeg_codec(result, sample_rate, codec, bitrate)
    return limit_audio(result), {"variant": chain, "stages": [{"codec": codec, "bitrate": bitrate} for codec, bitrate in stages[chain]]}


def stereo_collapse(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    result, source = apply_ariel_effect(audio, sample_rate, "stereo", params, rng)
    wet = float(params.get("wet", 1.0))
    if not 0.0 <= wet <= 1.0:
        raise ValueError("stereo_collapse wet must be between 0 and 1")
    result = audio * (1.0 - wet) + result * wet
    return limit_audio(result), {"variant": variant or "combined_channels", "wet": wet, "source_effect": source}


def channel_damage(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    mode = variant or str(params.get("mode", "bandwidth_loss"))
    target = int(params.get("target_channel", 1))
    if target not in (0, 1):
        raise ValueError("channel_damage target_channel must be 0 or 1")
    result = audio.copy()
    damaged = result[:, target]
    if mode == "bandwidth_loss":
        damaged = butter_filter(damaged[:, None], sample_rate, "lowpass", float(params.get("cutoff_hz", rng.uniform(1_200, 4_000))), 3)[:, 0]
    elif mode == "attenuation":
        damaged *= 10 ** (float(params.get("gain_db", rng.uniform(-24, -9))) / 20)
    elif mode == "delay":
        delay = int(sample_rate * float(params.get("delay_ms", rng.uniform(8, 45))) / 1000)
        damaged = np.concatenate([np.zeros(delay, dtype=np.float32), damaged[:-delay]])
    elif mode == "polarity_inversion":
        damaged = -damaged
    elif mode == "dropout":
        for start, end in _dropout_ranges(len(audio), sample_rate, rng, 3.0, 12, 65):
            damaged[start:end] = 0
    elif mode == "noise":
        noise = rng.normal(0, 1, len(damaged)).astype(np.float32)
        damaged = damaged + noise * (rms(damaged) / max(rms(noise) * 10 ** (float(params.get("snr_db", rng.uniform(3, 12))) / 20), 1e-8))
    elif mode == "distortion":
        damaged = np.tanh(damaged * float(params.get("drive", rng.uniform(3, 7))))
    else:
        raise ValueError(f"Unknown channel_damage mode: {mode}")
    result[:, target] = damaged
    return limit_audio(result), {"variant": mode, "target_channel": target}


def pitch_speed_instability(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    """Wow/flutter-like time warp, retaining clip length and stereo coherence."""
    samples = len(audio)
    time = np.arange(samples, dtype=np.float64) / sample_rate
    wow_rate = float(params.get("wow_rate_hz", rng.uniform(0.25, 1.0)))
    wow_depth = float(params.get("wow_depth_percent", rng.uniform(0.8, 2.2))) / 100
    flutter_rate = float(params.get("flutter_rate_hz", rng.uniform(4.0, 10.0)))
    flutter_depth = float(params.get("flutter_depth_percent", rng.uniform(0.25, 0.8))) / 100
    phase = rng.uniform(0, 2 * np.pi, 2)
    speed = 1 + wow_depth * np.sin(2 * np.pi * wow_rate * time + phase[0]) + flutter_depth * np.sin(2 * np.pi * flutter_rate * time + phase[1])
    positions = np.cumsum(speed)
    positions = (positions - positions[0]) * (samples - 1) / max(positions[-1] - positions[0], 1)
    result = np.column_stack([np.interp(positions, np.arange(samples), audio[:, channel]) for channel in range(audio.shape[1])]).astype(np.float32)
    return limit_audio(result), {"variant": variant or "wow_flutter", "wow_rate_hz": wow_rate, "wow_depth_percent": wow_depth * 100, "flutter_rate_hz": flutter_rate, "flutter_depth_percent": flutter_depth * 100}

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
    max_order = int(params.get("max_order", 10))
    if room_size.shape != (3,) or np.any(room_size <= 1.0):
        raise ValueError("distant_mic_capture room_size_m must contain three values above 1 metre")
    if not 0.0 < distance < room_size[0] - 0.5:
        raise ValueError("distant_mic_capture distance_m must fit inside the simulated room")
    if not 0.0 <= absorption < 1.0:
        raise ValueError("distant_mic_capture absorption must be in [0, 1)")
    if not 0 <= max_order <= 10:
        raise ValueError("distant_mic_capture max_order must be between 0 and 10")
    source = np.array([room_size[0] * 0.35, room_size[1] * 0.45, 1.5])
    microphone = source + np.array([distance, 0.0, -0.2])
    if microphone[0] >= room_size[0] - 0.5:
        source[0] = room_size[0] - distance - 0.6
        microphone[0] = room_size[0] - 0.6
    room = pra.ShoeBox(room_size, absorption=absorption, max_order=max_order, fs=sample_rate)
    room.add_source(source)
    room.add_microphone_array(np.array([microphone]).T)
    try:
        room.compute_rir()
    except Exception as error:
        raise RuntimeError("distant_mic_capture room simulation failed") from error
    rir = room.rir[0][0]
    rir = rir[np.argmax(rir):]
    captured = np.column_stack(
        [signal.fftconvolve(audio[:, channel], rir, mode="full")[: len(audio)] for channel in range(audio.shape[1])]
    )
    air_cutoff = float(params.get("air_absorption_cutoff_hz", rng.uniform(4_500, 7_000)))
    captured = butter_filter(captured, sample_rate, "lowpass", air_cutoff, order=2)
    snr_db = float(params.get("room_noise_snr_db", 1_000))
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
        "max_order": max_order,
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
        low_hz = float(params.get("low_hz", 300))
        high_hz = float(params.get("high_hz", 3_400))
        result = butter_filter(audio, sample_rate, "bandpass", (low_hz, high_hz), order=4)
        return limit_audio(result), {**params, "variant": variant, "low_hz": low_hz, "high_hz": high_hz}
    elif variant == "highpass":
        result = butter_filter(audio, sample_rate, "highpass", float(params.get("cutoff_hz", 120)), order=3)
    elif variant == "low_sample_rate":
        intermediate = int(params.get("intermediate_sample_rate", 12_000))
        down = signal.resample_poly(audio, intermediate, sample_rate, axis=0)
        result = signal.resample_poly(down, sample_rate, intermediate, axis=0)
        result = match_length(result.astype(np.float32), len(audio))
    else:
        # Keep the SonicMaster/ARIEL clarity filter available as a canonical
        # low-pass preset while retaining the configurable Butterworth form.
        if str(params.get("preset", "butterworth")) in {"sonicmaster", "clarity"}:
            result, tracking = apply_ariel_effect(audio, sample_rate, "clarity", params, rng)
            return limit_audio(result), {**params, **tracking, "variant": variant, "preset": "sonicmaster"}
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
        click_level_db = float(params.get("click_level_db", -2.0))
        crackle_level_db = float(params.get("crackle_level_db", -18.0))
        click_duration_ms = float(params.get("click_duration_ms", 3.0))
        crackle_duration_ms = float(params.get("crackle_duration_ms", 0.5))
        click_count = int(rng.poisson(click_rate_hz * len(audio) / sample_rate))
        crackle_count = int(rng.poisson(crackle_rate_hz * len(audio) / sample_rate))
        noise = np.zeros_like(audio, dtype=np.float32)
        signal_rms = rms(audio)
        for count, level_db, duration_ms in ((click_count, click_level_db, click_duration_ms), (crackle_count, crackle_level_db, crackle_duration_ms)):
            for _ in range(count):
                start = int(rng.integers(0, len(audio)))
                width = max(1, int(sample_rate * duration_ms / 1000))
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
            "click_duration_ms": click_duration_ms,
            "crackle_duration_ms": crackle_duration_ms,
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


def _peaking_eq(audio: np.ndarray, sample_rate: int, frequency_hz: float, gain_db: float, q: float) -> np.ndarray:
    """Second-order peaking filter, the resonance a small capsule imposes on its passband."""
    amplitude = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * frequency_hz / sample_rate
    alpha = np.sin(w0) / (2 * q)
    b = np.array([1 + alpha * amplitude, -2 * np.cos(w0), 1 - alpha * amplitude])
    a = np.array([1 + alpha / amplitude, -2 * np.cos(w0), 1 - alpha / amplitude])
    return signal.lfilter(b / a[0], a / a[0], audio, axis=0)


def _moving_rms(audio: np.ndarray, window: int) -> np.ndarray:
    """Centred moving RMS in linear time, so long clips stay cheap."""
    power = np.mean(audio ** 2, axis=1)
    cumulative = np.cumsum(np.concatenate(([0.0], power)))
    index = np.arange(len(power))
    low = np.clip(index - window // 2, 0, len(power))
    high = np.clip(index - window // 2 + window, 0, len(power))
    return np.sqrt((cumulative[high] - cumulative[low]) / np.maximum(high - low, 1)) + 1e-8


def _smartphone_capture(
    audio: np.ndarray, sample_rate: int, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    """Close-range capture by a handset: no room, but a badly band-limited resonant capsule.

    This is the counterpart to distant_mic_capture, which models the room and distance
    while leaving the microphone ideal. Here the microphone is the degradation: the low
    end is lost to a small capsule and the handset rumble filter, a resonance colours the
    upper midrange, automatic gain control flattens the level, and the preamp clips before
    the capsule and codec impose a bandwidth ceiling.
    """
    highpass_hz = float(params.get("highpass_hz", rng.uniform(90, 250)))
    resonance_hz = float(params.get("resonance_hz", rng.uniform(2_500, 5_000)))
    resonance_db = float(params.get("resonance_db", rng.uniform(4, 9)))
    resonance_q = float(params.get("resonance_q", rng.uniform(1.0, 2.0)))
    dip_hz = float(params.get("dip_hz", rng.uniform(700, 1_500)))
    dip_db = float(params.get("dip_db", rng.uniform(2, 5)))
    lowpass_hz = float(params.get("lowpass_hz", rng.uniform(7_000, 14_000)))
    agc_strength = float(params.get("agc_strength", rng.uniform(0.4, 0.8)))
    drive = float(params.get("drive", rng.uniform(1.5, 3.0)))
    self_noise_snr_db = float(params.get("self_noise_snr_db", rng.uniform(38, 52)))
    if not 0.0 <= agc_strength <= 1.0:
        raise ValueError("smartphone_capture agc_strength must be between 0 and 1")
    if highpass_hz >= lowpass_hz:
        raise ValueError("smartphone_capture highpass_hz must sit below lowpass_hz")

    result = butter_filter(audio, sample_rate, "highpass", highpass_hz, order=2)
    result = _peaking_eq(result, sample_rate, resonance_hz, resonance_db, resonance_q)
    result = _peaking_eq(result, sample_rate, dip_hz, -dip_db, 1.2)
    window = max(1, int(sample_rate * float(params.get("agc_window_seconds", 0.25))))
    envelope = _moving_rms(result, window)
    target = float(params.get("agc_target_rms", 0.08))
    result = result * np.clip((target / envelope) ** agc_strength, 0.25, 4.0)[:, None]
    # The preamp gives up before the capsule and codec set the ceiling, so the
    # bandwidth limit has to come last or its harmonics survive above the cutoff.
    result = np.tanh(result * drive) / np.tanh(drive)
    result = butter_filter(result, sample_rate, "lowpass", lowpass_hz, order=4)
    noise = rng.normal(0, 1, result.shape).astype(np.float32)
    result = result + noise * (rms(result) / max(rms(noise) * (10 ** (self_noise_snr_db / 20)), 1e-8))
    input_rms, output_rms = rms(audio), rms(result)
    if output_rms > 1e-8:
        result = result * (input_rms / output_rms)
    return result.astype(np.float32), {
        "highpass_hz": highpass_hz, "resonance_hz": resonance_hz, "resonance_db": resonance_db,
        "resonance_q": resonance_q, "dip_hz": dip_hz, "dip_db": dip_db, "lowpass_hz": lowpass_hz,
        "agc_strength": agc_strength, "drive": drive, "self_noise_snr_db": self_noise_snr_db,
    }


def device_mic_response(
    audio: np.ndarray, sample_rate: int, variant: str | None, params: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, dict[str, Any]]:
    variant = variant or params.get("mode", "consumer_mic")
    if variant == "smartphone_capture":
        result, sampled = _smartphone_capture(audio, sample_rate, params, rng)
        return limit_audio(result), {**sampled, "variant": variant}
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
