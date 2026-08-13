"""ARIEL/SonicMaster single-degradation effects, adapted to channel-last audio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import librosa
import numpy as np
from scipy import signal


def _normalize(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    return audio / peak if peak > 0 else audio.copy()


def _shelf(audio: np.ndarray, sample_rate: int, frequency: float, gain_db: float, kind: str) -> np.ndarray:
    """Same RBJ shelf design used by ARIEL's ``shelf_filter``."""
    amplitude = 10 ** (gain_db / 40)
    omega = 2 * np.pi * frequency / sample_rate
    alpha = np.sin(omega) / (2 * 0.707)
    cosine = np.cos(omega)
    if kind == "low":
        b0 = amplitude * ((amplitude + 1) - (amplitude - 1) * cosine + 2 * np.sqrt(amplitude) * alpha)
        b1 = 2 * amplitude * ((amplitude - 1) - (amplitude + 1) * cosine)
        b2 = amplitude * ((amplitude + 1) - (amplitude - 1) * cosine - 2 * np.sqrt(amplitude) * alpha)
        a0 = (amplitude + 1) + (amplitude - 1) * cosine + 2 * np.sqrt(amplitude) * alpha
        a1 = -2 * ((amplitude - 1) + (amplitude + 1) * cosine)
        a2 = (amplitude + 1) + (amplitude - 1) * cosine - 2 * np.sqrt(amplitude) * alpha
    else:
        b0 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosine + 2 * np.sqrt(amplitude) * alpha)
        b1 = -2 * amplitude * ((amplitude - 1) + (amplitude + 1) * cosine)
        b2 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosine - 2 * np.sqrt(amplitude) * alpha)
        a0 = (amplitude + 1) - (amplitude - 1) * cosine + 2 * np.sqrt(amplitude) * alpha
        a1 = 2 * ((amplitude - 1) - (amplitude + 1) * cosine)
        a2 = (amplitude + 1) - (amplitude - 1) * cosine - 2 * np.sqrt(amplitude) * alpha
    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return signal.sosfilt(sos, audio, axis=0)


def _compress(audio: np.ndarray, sample_rate: int, threshold_db: int, ratio: float, attack_ms: int, release_ms: int, gain_db: float) -> np.ndarray:
    """Literal channel-wise port of ARIEL's FeedForwardCompressor."""
    threshold = 10 ** (threshold_db / 20.0)
    attack = np.exp(-1.0 / (sample_rate * attack_ms / 1000.0))
    release = np.exp(-1.0 / (sample_rate * release_ms / 1000.0))
    previous_env = np.zeros(2)
    history = np.ones((2, 128))
    history_sum = np.full(2, 128.0)
    index = np.zeros(2, dtype=int)
    output = np.zeros_like(audio)
    exponent = 1.0 / ratio - 1.0
    for frame_index, frame in enumerate(audio):
        for channel, sample in enumerate(frame):
            squared = sample * sample
            coefficient = attack if squared > previous_env[channel] else release
            env = (1.0 - coefficient) * squared + coefficient * previous_env[channel]
            previous_env[channel] = env
            reduction = 1.0 if env < threshold else (env / threshold) ** exponent
            history_sum[channel] -= history[channel, index[channel]]
            history[channel, index[channel]] = reduction
            history_sum[channel] += reduction
            index[channel] = (index[channel] + 1) % 128
            output[frame_index, channel] = sample * history_sum[channel] / 128.0
    return output * (10 ** (gain_db / 20.0))


def _punch(audio: np.ndarray, sample_rate: int, attack_ms: int, release_ms: int, lookahead_ms: int) -> tuple[np.ndarray, float, float]:
    attack = np.exp(-1.0 / (sample_rate * attack_ms / 1000.0))
    release = np.exp(-1.0 / (sample_rate * release_ms / 1000.0))
    lookahead = int(sample_rate * lookahead_ms / 1000)
    mono = np.mean(audio, axis=1)
    padded = np.concatenate([np.zeros(lookahead), mono])
    envelope = np.zeros_like(padded)
    level = 0.0
    for index, sample in enumerate(np.abs(padded)):
        coefficient = attack if sample > level else release
        level = coefficient * (level - sample) + sample
        envelope[index] = level
    envelope_db = 20 * np.log10(envelope + 1e-6)
    median = float(np.median(envelope_db))
    p99 = float(np.percentile(envelope_db, 99))
    threshold = 0.7 * p99 + 0.3 * median
    reduction = min(max((p99 - median) * 0.7, 8), 15)
    mask = envelope_db > threshold
    output = audio.copy()
    for index in range(len(audio)):
        if index + lookahead < len(mask) and mask[index + lookahead]:
            output[index] *= 10 ** (-reduction / 20.0)
    return output, threshold, reduction


def _peak_eq(audio: np.ndarray, frequencies: np.ndarray, quality: float, gains: np.ndarray, sample_rate: int) -> np.ndarray:
    output = audio.astype(np.float32)
    for gain_db, frequency in zip(gains, frequencies):
        amplitude = 10 ** (gain_db / 20.0)
        omega = 2 * np.pi * frequency / sample_rate
        alpha = np.sin(omega) / (2 * quality)
        b = np.array([1 + alpha * amplitude, -2 * np.cos(omega), 1 - alpha * amplitude])
        a0 = 1 + alpha / amplitude
        a = np.array([1, (-2 * np.cos(omega)) / a0, (1 - alpha / amplitude) / a0])
        output = signal.sosfilt(np.array([[b[0] / a0, b[1] / a0, b[2] / a0, a[0], a[1], a[2]]]), output, axis=0)
    return output


def _room(audio: np.ndarray, sample_rate: int, room_size: np.ndarray, source: np.ndarray, microphone: np.ndarray, absorption: Any, mode: str) -> np.ndarray:
    try:
        import pyroomacoustics as pra
    except ImportError as error:
        raise RuntimeError("ARIEL room effects require pyroomacoustics") from error
    room = pra.ShoeBox(room_size, absorption=absorption, max_order=10, fs=sample_rate) if mode == "simple" else pra.ShoeBox(room_size, materials=absorption, max_order=10, fs=sample_rate)
    room.add_source(source)
    room.add_microphone_array(np.array([microphone]).T)
    room.compute_rir()
    rir = room.rir[0][0]
    rir = rir[np.argmax(rir):]
    return np.column_stack([signal.fftconvolve(audio[:, channel], rir, mode="full")[: len(audio)] for channel in range(2)])


def _load_mic(audio: np.ndarray, directory: str, mic_number: int) -> tuple[np.ndarray, str]:
    files = sorted(Path(directory).glob("*.npy"))
    if not files:
        raise FileNotFoundError("The `mic` effect requires parameters.mic_ir_dir containing ARIEL-compatible .npy IRs")
    path = files[mic_number % len(files)]
    impulse = np.load(path, allow_pickle=False)
    impulse = impulse / np.max(np.abs(impulse))
    impulse = impulse[np.argmax(impulse):]
    return np.column_stack([signal.fftconvolve(audio[:, channel], impulse, mode="full")[: len(audio)] for channel in range(2)]), path.stem


def _real_rir(audio: np.ndarray, directory: str, index: int) -> tuple[np.ndarray, str]:
    root = Path(directory)
    files = sorted(path for path in root.rglob("*.wav") if path.is_file()) if directory and root.is_dir() else []
    if not files:
        raise FileNotFoundError("The `real` effect requires parameters.real_rir_dir containing ARIEL-compatible WAV RIRs")
    path = files[index % len(files)]
    impulse, _ = librosa.load(path, sr=44_100, mono=False)
    if impulse.ndim == 1:
        impulse = impulse[np.newaxis, :]
    start = min(np.argmax(impulse, axis=1))
    impulse = impulse[:, start:]
    if impulse.shape[0] == 2:
        output = np.column_stack([signal.fftconvolve(audio[:, channel], impulse[channel], mode="full")[: len(audio)] for channel in range(2)])
    elif impulse.shape[0] == 4:
        output = np.zeros_like(audio)
        for channel in range(2):
            convolved = [signal.fftconvolve(audio[:, channel], impulse[index], mode="full")[: len(audio)] for index in range(4)]
            output[:, channel] = convolved[0] + 0.5 * convolved[1] + 0.2 * convolved[3]
    else:
        raise ValueError(f"Expected a stereo or B-format RIR: {path}")
    return output, path.stem


def apply_ariel_effect(audio: np.ndarray, sample_rate: int, effect: str, params: dict[str, Any], rng: np.random.Generator) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply one original ARIEL single effect and return its sampled tracking fields."""

    medium = params.get("preview_strength") == "medium"

    def integer(low: int, high: int) -> int:
        return (low + high) // 2 if medium else int(rng.integers(low, high + 1))

    def stepped(low: int, high: int, scale: float = 1.0) -> float:
        return ((low + high) / 2) / scale if medium else float(rng.integers(low, high + 1) / scale)

    def choice(values: list[float]) -> float:
        return values[len(values) // 2] if medium else float(rng.choice(values))
    if effect == "comp":
        threshold, ratio, gain, attack, release = integer(-45, -38), stepped(60, 450, 10), stepped(160, 250, 10), integer(3, 150), integer(80, 250)
        return _compress(audio, sample_rate, threshold, ratio, attack, release, gain), {"effect": effect, "threshold_db": threshold, "ratio": ratio, "attack_ms": attack, "release_ms": release, "manual_gain_db": gain}
    if effect == "punch":
        output, threshold, reduction = _punch(audio, sample_rate, 3, 150, 10)
        return output, {"effect": effect, "threshold_db": threshold, "reduction_db": reduction, "attack_ms": 3, "release_ms": 150, "lookahead_ms": 10}
    if effect == "xband":
        count = integer(8, 12); gains = np.array([-3, -2, -1, 2, 3] * ((count + 4) // 5))[:count] if medium else rng.integers(-6, 7, count); frequencies = np.geomspace(40, 16000, count)
        return _peak_eq(audio, frequencies, frequencies[-1] / (frequencies[-1] - frequencies[-2]) / 2, gains, sample_rate), {"effect": effect, "n_bands": count, "gains_db": gains.tolist()}
    if effect == "mic":
        number = integer(0, 19); output, name = _load_mic(audio, str(params.get("mic_ir_dir", "")), number)
        return output, {"effect": effect, "mic_number": number, "microphone": name}
    if effect in {"bright", "dark", "airy", "boom", "warm"}:
        limits = {"bright": (6, 15), "dark": (6, 15), "airy": (10, 20), "boom": (10, 20), "warm": (6, 20)}
        gain = integer(limits[effect][0], limits[effect][1])
        frequency, kind, signed_gain = {"bright": (6000, "high", -gain), "dark": (6000, "high", gain), "airy": (10000, "high", -gain), "boom": (120, "low", -gain), "warm": (400, "low", -gain)}[effect]
        return _shelf(audio, sample_rate, frequency, signed_gain, kind), {"effect": effect, "gain_db": gain}
    if effect == "clarity":
        order = integer(3, 5); b, a = signal.butter(order, 4000 / (sample_rate / 2), btype="low")
        return signal.lfilter(b, a, audio, axis=0), {"effect": effect, "order": order}
    if effect in {"mud", "vocal"}:
        gain = integer(6, 15 if effect == "mud" else 20)
        band, stop = ([200, 500], False) if effect == "mud" else ([350, 3500], True)
        sos = signal.cheby2(2, gain, band, btype="bandstop" if stop else "bandpass", fs=sample_rate, output="sos")
        return signal.sosfilt(sos, audio, axis=0), {"effect": effect, "gain": gain}
    if effect in {"small", "big", "mix"}:
        ranges = {"small": ((3, 3, 2.5), (4, 6, 1.5)), "big": ((7, 8, 4), (8, 10, 10)), "mix": ((4, 4, 2.5), (4, 3, 1))}
        start, span = ranges[effect]; room_size = np.array(start) + np.array(span) * (0.5 if medium else rng.random(3))
        source = rng.random(3) * (0.8 * room_size) + 0.1 * room_size; microphone = rng.random(3) * (0.8 * room_size) + 0.1 * room_size
        source[2] = rng.random() * room_size[2] * 0.7 + 0.3; microphone[2] = rng.random() * room_size[2] * 0.5 + 0.3
        if effect != "mix":
            absorption = 0.175 if medium else float(rng.random() * 0.25 + 0.05); output = _room(audio, sample_rate, room_size, source, microphone, absorption, "simple")
            return output, {"effect": effect, "room_size": room_size.tolist(), "source_position": source.tolist(), "mic_position": microphone.tolist(), "absorption": absorption}
        import pyroomacoustics as pra
        count = 1 if medium else int(rng.integers(1, 3)); selected = set(rng.choice(6, count, replace=False).tolist()); materials = []
        for wall in range(6):
            low, high = (np.array([.15,.15,.15,.15,.15,.25,.25,.25,.30,.35]), np.array([.50,.50,.50,.60,.70,.80,.85,.90,.90,.95])) if wall in selected else (np.array([.05,.05,.06,.08,.10,.12,.13,.15,.15,.17]), np.array([.15,.15,.15,.20,.20,.22,.23,.25,.25,.27]))
            materials.append(pra.Material(energy_absorption={"coeffs": low + (high - low) * rng.random(10), "center_freqs": np.array([125,250,500,1000,2000,4000,8000,12000,16000,20000])}))
        absorption = dict(zip(["east", "west", "north", "south", "ceiling", "floor"], materials)); output = _room(audio, sample_rate, room_size, source, microphone, absorption, "mix")
        return output, {"effect": effect, "room_size": room_size.tolist(), "source_position": source.tolist(), "mic_position": microphone.tolist(), "absorptive_walls": sorted(selected)}
    if effect == "real":
        index = integer(0, 11); output, name = _real_rir(audio, str(params.get("real_rir_dir", "")), index)
        return output, {"effect": effect, "rir_index": index, "rir_name": name}
    if effect == "stereo":
        mono = np.sum(audio, axis=1); return np.column_stack([mono, mono]), {"effect": effect, "mode": "combined_channels"}
    if effect == "clip":
        amount = choice([2.0, 3.0, 5.0]); return np.clip(amount * _normalize(audio), -1.0, 1.0), {"effect": effect, "clip_intensity": amount}
    if effect == "volume":
        amount = choice([0.001, 0.003, 0.01, 0.05]); return amount * _normalize(audio), {"effect": effect, "volume_multiplier": amount}
    raise ValueError(f"Unknown ARIEL effect: {effect}")
