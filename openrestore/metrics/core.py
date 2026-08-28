"""CPU-only objective metrics and degradation-aware AAE diagnostics."""

from __future__ import annotations

from typing import Any

import librosa
import numpy as np
from scipy import ndimage

EPSILON = 1e-8

METRIC_DIRECTIONS = {
    "l1": "lower",
    "rmse": "lower",
    "snr_db": "higher",
    "si_sdr_db": "higher",
    "si_snr_db": "higher",
    "lsd_db": "lower",
    "mrstft": "lower",
    "log_mel": "lower",
    "ltas": "lower",
    "log_mel_ssim": "higher",
    "spectral_kl": "lower",
}

EFFECT_CATEGORIES = {
    "comp": "dynamics",
    "punch": "dynamics",
    "xband": "eq_coloration",
    "mic": "eq_coloration",
    "bright": "eq_coloration",
    "dark": "eq_coloration",
    "airy": "eq_coloration",
    "boom": "eq_coloration",
    "clarity": "eq_coloration",
    "mud": "eq_coloration",
    "warm": "eq_coloration",
    "vocal": "eq_coloration",
    "small": "reverb_room",
    "big": "reverb_room",
    "mix": "reverb_room",
    "real": "reverb_room",
    "distant_mic_capture": "reverb_room",
    "clip": "clipping_saturation",
    "volume": "amplitude",
    "stereo": "stereo_spatial",
    "noise": "noise_interference",
    "hum": "noise_interference",
    "clicks_crackle": "noise_interference",
    "bandwidth": "bandwidth_loss",
    "codec": "codec_transmission",
}


def effect_name(row: dict[str, Any]) -> str:
    recipe = str(row.get("degradation_recipe_id", ""))
    for prefix in ("single_", "review_min_", "review_max_"):
        if recipe.startswith(prefix):
            return recipe[len(prefix) :]
    operations = row.get("degradation_params", [])
    if operations:
        parameters = operations[0].get("parameters", {})
        return str(
            parameters.get("effect")
            or parameters.get("variant")
            or operations[0].get("variant", recipe)
        )
    return recipe or "unknown"


def category_for_row(row: dict[str, Any]) -> str:
    return EFFECT_CATEGORIES.get(effect_name(row), "other")


def _mono(audio: np.ndarray) -> np.ndarray:
    return np.mean(audio, axis=1, dtype=np.float64)


def _stft(audio: np.ndarray, n_fft: int, hop_length: int) -> np.ndarray:
    return librosa.stft(
        _mono(audio), n_fft=n_fft, hop_length=hop_length, window="hann", center=True
    )


def _log_mel(
    audio: np.ndarray, sample_rate: int, n_fft: int, hop_length: int, n_mels: int
) -> np.ndarray:
    mel = librosa.feature.melspectrogram(
        y=_mono(audio),
        sr=sample_rate,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
        power=2.0,
    )
    return librosa.power_to_db(mel + EPSILON, ref=1.0)


def _si_ratio(reference: np.ndarray, estimate: np.ndarray) -> float:
    ref = reference.astype(np.float64).reshape(-1)
    est = estimate.astype(np.float64).reshape(-1)
    ref = ref - np.mean(ref)
    est = est - np.mean(est)
    target = np.dot(est, ref) * ref / (np.dot(ref, ref) + EPSILON)
    noise = est - target
    return float(
        10.0 * np.log10((np.dot(target, target) + EPSILON) / (np.dot(noise, noise) + EPSILON))
    )


def pairwise_metrics(
    reference: np.ndarray, estimate: np.ndarray, config: dict[str, Any]
) -> dict[str, float]:
    """Compute deterministic full-clip metrics for canonical stereo audio."""
    sample_rate = int(config["sample_rate"])
    analysis = config["analysis"]
    reference = np.asarray(reference, dtype=np.float64)
    estimate = np.asarray(estimate, dtype=np.float64)
    error = estimate - reference
    ref_energy = float(np.sum(reference * reference))
    error_energy = float(np.sum(error * error))
    n_fft = int(analysis["n_fft"])
    hop = int(analysis["hop_length"])
    ref_stft = np.abs(_stft(reference, n_fft, hop))
    est_stft = np.abs(_stft(estimate, n_fft, hop))
    log_ref = 20.0 * np.log10(ref_stft + EPSILON)
    log_est = 20.0 * np.log10(est_stft + EPSILON)
    lsd = float(np.mean(np.sqrt(np.mean((log_ref - log_est) ** 2, axis=0))))
    ltas_ref = np.mean(ref_stft, axis=1)
    ltas_est = np.mean(est_stft, axis=1)
    mel_ref = _log_mel(reference, sample_rate, n_fft, hop, int(analysis["n_mels"]))
    mel_est = _log_mel(estimate, sample_rate, n_fft, hop, int(analysis["n_mels"]))
    min_frames = min(mel_ref.shape[1], mel_est.shape[1])
    mel_ref, mel_est = mel_ref[:, :min_frames], mel_est[:, :min_frames]
    normal_ref = (mel_ref - mel_ref.min()) / (np.ptp(mel_ref) + EPSILON)
    normal_est = (mel_est - mel_est.min()) / (np.ptp(mel_est) + EPSILON)
    window = min(7, normal_ref.shape[0], normal_ref.shape[1])
    if window % 2 == 0:
        window -= 1
    ssim = _ssim(normal_ref, normal_est, max(window, 3))
    profile_ref = np.mean(ref_stft * ref_stft, axis=1) + EPSILON
    profile_est = np.mean(est_stft * est_stft, axis=1) + EPSILON
    profile_ref /= np.sum(profile_ref)
    profile_est /= np.sum(profile_est)
    mrstft = []
    for resolution in analysis["mrstft_resolutions"]:
        resolution = int(resolution)
        ref_multi = _stft(reference, resolution, resolution // 4)
        est_multi = _stft(estimate, resolution, resolution // 4)
        mrstft.append(
            float(np.mean(np.abs(ref_multi - est_multi)) / (np.mean(np.abs(ref_multi)) + EPSILON))
        )
    return {
        "l1": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error * error))),
        "snr_db": float(10.0 * np.log10((ref_energy + EPSILON) / (error_energy + EPSILON))),
        "si_sdr_db": _si_ratio(reference, estimate),
        "si_snr_db": _si_ratio(reference, estimate),
        "lsd_db": lsd,
        "mrstft": float(np.mean(mrstft)),
        "log_mel": float(np.sqrt(np.mean((mel_ref - mel_est) ** 2))),
        "ltas": float(np.mean(np.abs(ltas_ref - ltas_est) / (ltas_ref + EPSILON))),
        "log_mel_ssim": ssim,
        "spectral_kl": float(np.sum(profile_ref * np.log(profile_ref / profile_est))),
    }


def _ssim(reference: np.ndarray, estimate: np.ndarray, window: int) -> float:
    """Mean local SSIM over normalized log-mel spectrograms."""
    mean_ref = ndimage.uniform_filter(reference, size=window, mode="reflect")
    mean_est = ndimage.uniform_filter(estimate, size=window, mode="reflect")
    variance_ref = (
        ndimage.uniform_filter(reference * reference, size=window, mode="reflect")
        - mean_ref * mean_ref
    )
    variance_est = (
        ndimage.uniform_filter(estimate * estimate, size=window, mode="reflect")
        - mean_est * mean_est
    )
    covariance = (
        ndimage.uniform_filter(reference * estimate, size=window, mode="reflect")
        - mean_ref * mean_est
    )
    c1, c2 = 0.01**2, 0.03**2
    score = ((2 * mean_ref * mean_est + c1) * (2 * covariance + c2)) / (
        (mean_ref * mean_ref + mean_est * mean_est + c1) * (variance_ref + variance_est + c2)
    )
    return float(np.mean(score))


def _frame_rms(audio: np.ndarray, frame: int, hop: int) -> np.ndarray:
    mono = _mono(audio)
    frames = librosa.util.frame(mono, frame_length=frame, hop_length=hop)
    return np.sqrt(np.mean(frames * frames, axis=0) + EPSILON)


def _band_ratio(audio: np.ndarray, sample_rate: int, low: float, high: float) -> float:
    magnitude = np.abs(_stft(audio, 2048, 512)) ** 2
    frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    mask = (frequencies >= low) & (frequencies < min(high, sample_rate / 2))
    return float(np.sum(magnitude[mask]) / (np.sum(magnitude) + EPSILON))


def _descriptor(audio: np.ndarray, category: str, sample_rate: int) -> np.ndarray:
    mono = _mono(audio)
    if category == "eq_coloration":
        bands = [(20, 120), (120, 400), (400, 2000), (2000, 6000), (6000, 12000), (12000, 20000)]
        return np.array([_band_ratio(audio, sample_rate, low, high) for low, high in bands])
    if category == "bandwidth_loss":
        return np.array(
            [
                _band_ratio(audio, sample_rate, 7000, sample_rate / 2),
                librosa.feature.spectral_rolloff(y=mono, sr=sample_rate)[0].mean(),
            ]
        )
    if category == "noise_interference":
        flatness = librosa.feature.spectral_flatness(y=mono)[0].mean()
        return np.array([flatness, _band_ratio(audio, sample_rate, 8000, sample_rate / 2)])
    if category == "clipping_saturation":
        peak = np.max(np.abs(mono)) + EPSILON
        return np.array(
            [np.mean(np.abs(mono) >= 0.98 * peak), peak / (np.sqrt(np.mean(mono * mono)) + EPSILON)]
        )
    if category == "dynamics":
        frames = _frame_rms(audio, 2048, 1024)
        return np.array(
            [np.std(frames), np.max(np.abs(mono)) / (np.sqrt(np.mean(mono * mono)) + EPSILON)]
        )
    if category == "reverb_room":
        energy = mono * mono
        split = max(1, int(len(energy) * 0.1))
        return np.array([np.sum(energy[split:]) / (np.sum(energy[:split]) + EPSILON)])
    if category == "stereo_spatial":
        left, right = audio[:, 0], audio[:, 1]
        mid, side = (left + right) * 0.5, (left - right) * 0.5
        return np.array(
            [
                np.corrcoef(left, right)[0, 1],
                np.sqrt(np.mean(side * side)) / (np.sqrt(np.mean(mid * mid)) + EPSILON),
                np.sqrt(np.mean(left * left)) / (np.sqrt(np.mean(right * right)) + EPSILON),
            ]
        )
    if category == "codec_transmission":
        return np.array(
            [
                librosa.feature.spectral_flatness(y=mono)[0].mean(),
                _band_ratio(audio, sample_rate, 10000, sample_rate / 2),
            ]
        )
    if category == "amplitude":
        return np.array([np.sqrt(np.mean(mono * mono)), np.max(np.abs(mono))])
    return np.zeros(1)


def aae_metrics(
    clean: np.ndarray, degraded: np.ndarray, restored: np.ndarray, category: str, sample_rate: int
) -> dict[str, float | str]:
    clean_descriptor = _descriptor(clean, category, sample_rate)
    degraded_error = float(
        np.mean(np.abs(clean_descriptor - _descriptor(degraded, category, sample_rate)))
    )
    restored_error = float(
        np.mean(np.abs(clean_descriptor - _descriptor(restored, category, sample_rate)))
    )
    return {
        "category": category,
        "degraded": degraded_error,
        "restored": restored_error,
        "reduction": float(1.0 - restored_error / max(degraded_error, EPSILON)),
    }
