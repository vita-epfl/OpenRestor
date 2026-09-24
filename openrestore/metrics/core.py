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
    # Reverb-aware residual transfer diagnostics.
    "rt60_s": "lower",
    "drr_db": "higher",
    "late_tail_db": "lower",
}

EFFECT_CATEGORIES = {
    # Canonical v0.1 benchmark IDs.
    "spectral_eq": "spectral_eq",
    "smartphone_capture": "smartphone_capture",
    "mic": "mic",
    "lowpass": "lowpass",
    "highpass": "highpass",
    "telephone_band": "telephone_band",
    "low_sample_rate": "low_sample_rate",
    "compression": "compression",
    "clipping": "clipping",
    "saturation_overdrive": "saturation_overdrive",
    "reverb_small": "reverb",
    "reverb_big": "reverb",
    "reverb_mix": "reverb",
    "reverb_real": "reverb",
    "distant_mic_capture": "distant_mic_capture",
    "noise": "noise",
    "hum": "hum",
    "clicks_crackle": "clicks_crackle",
    "dropouts_glitches": "dropouts_glitches",
    "codec": "codec",
    "neural_codec": "neural_codec",
    "transcode_chain": "transcode_chain",
    "stereo_collapse": "stereo_collapse",
    "channel_damage": "channel_damage",
    "pitch_speed_instability": "pitch_speed_instability",
    # Backward-compatible names for historical manifests.
    "comp": "compression",
    "punch": "compression",
    "xband": "spectral_eq",
    "bright": "spectral_eq",
    "dark": "spectral_eq",
    "airy": "spectral_eq",
    "boom": "spectral_eq",
    "clarity": "lowpass",
    "mud": "spectral_eq",
    "warm": "spectral_eq",
    "vocal": "spectral_eq",
    "small": "reverb",
    "big": "reverb",
    "mix": "reverb",
    "real": "reverb",
    "stereo": "stereo_collapse",
    "clip": "clipping",
    "volume": "legacy_volume",
    "bandwidth": "lowpass",
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
    recipe = str(row.get("degradation_recipe_id", ""))
    name = effect_name(row)
    # Preserve historical category names for manifests whose recipe IDs use
    # the old ``single_*`` namespace; canonical bare IDs use the new taxonomy.
    if recipe.startswith("single_"):
        legacy_categories = {
            "noise": "noise_interference",
            "hum": "noise_interference",
            "clicks_crackle": "noise_interference",
            "codec": "codec_transmission",
            "bandwidth": "bandwidth_loss",
            "comp": "dynamics",
            "punch": "dynamics",
            "clip": "clipping_saturation",
            "stereo": "stereo_spatial",
            "volume": "amplitude",
            "xband": "eq_coloration", "bright": "eq_coloration", "dark": "eq_coloration",
            "airy": "eq_coloration", "boom": "eq_coloration", "clarity": "eq_coloration",
            "mud": "eq_coloration", "warm": "eq_coloration", "vocal": "eq_coloration",
            "mic": "eq_coloration", "small": "reverb_room", "big": "reverb_room",
            "mix": "reverb_room", "real": "reverb_room", "distant_mic_capture": "reverb_room",
        }
        if name in legacy_categories:
            return legacy_categories[name]
    return EFFECT_CATEGORIES.get(name, "other")


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
    reverb = _reverb_diagnostics(reference, estimate, sample_rate, analysis)
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
        **reverb,
    }


def _transfer_impulse(
    reference: np.ndarray, estimate: np.ndarray, sample_rate: int, max_ir_seconds: float, regularization: float
) -> np.ndarray:
    """Estimate the causal clean-to-evaluated transfer impulse by Wiener deconvolution."""
    reference_mono = _mono(reference)
    estimate_mono = _mono(estimate)
    n_fft = 1 << max(1, len(reference_mono) - 1).bit_length()
    reference_spectrum = np.fft.rfft(reference_mono, n=n_fft)
    estimate_spectrum = np.fft.rfft(estimate_mono, n=n_fft)
    reference_power = np.abs(reference_spectrum) ** 2
    floor = max(float(np.max(reference_power)) * regularization, EPSILON)
    transfer = estimate_spectrum * np.conj(reference_spectrum) / (reference_power + floor)
    impulse = np.fft.irfft(transfer, n=n_fft).real
    return impulse[: min(len(impulse), max(1, round(max_ir_seconds * sample_rate)))]


def _reverb_diagnostics(
    reference: np.ndarray, estimate: np.ndarray, sample_rate: int, analysis: dict[str, Any]
) -> dict[str, float]:
    """Return residual RT60, DRR, and late-tail energy from a clean-to-output transfer.

    This is deliberately a transfer estimate, rather than an RT60 estimate of a
    music recording in isolation: it is therefore meaningful for paired
    clean/degraded/restored clips even when the clean music itself contains room
    sound.  Values are most informative for reverb and distant-capture items.
    """
    settings = analysis.get("reverb_diagnostics", {})
    reference_energy = float(np.mean(np.square(reference, dtype=np.float64)))
    relative_error = float(np.mean(np.square(estimate - reference, dtype=np.float64)) / (reference_energy + EPSILON))
    # Preserve the physically meaningful identity limit: no added room response.
    if relative_error <= float(settings.get("identity_relative_error", 1e-12)):
        return {"rt60_s": 0.0, "drr_db": 80.0, "late_tail_db": -80.0}
    impulse = _transfer_impulse(
        reference,
        estimate,
        sample_rate,
        float(settings.get("max_ir_seconds", 3.0)),
        float(settings.get("regularization", 1e-4)),
    )
    energy = np.square(impulse, dtype=np.float64)
    direct_samples = max(1, round(float(settings.get("direct_window_ms", 2.5)) * sample_rate / 1000))
    early_samples = max(direct_samples, round(float(settings.get("early_window_ms", 50.0)) * sample_rate / 1000))
    late_samples = max(early_samples, round(float(settings.get("late_start_ms", 80.0)) * sample_rate / 1000))
    direct_energy = float(np.sum(energy[:direct_samples]))
    reverberant_energy = float(np.sum(energy[direct_samples:]))
    early_energy = float(np.sum(energy[:early_samples]))
    late_energy = float(np.sum(energy[late_samples:]))
    drr_db = float(np.clip(10.0 * np.log10((direct_energy + EPSILON) / (reverberant_energy + EPSILON)), -80.0, 80.0))
    late_tail_db = float(np.clip(10.0 * np.log10((late_energy + EPSILON) / (early_energy + EPSILON)), -80.0, 20.0))
    # A near-delta transfer has no meaningful decay slope; define its residual
    # RT60 as zero rather than fitting numerical deconvolution noise.
    # Wiener deconvolution has a small numerical tail even for an identity
    # transfer. Treat that floor as no residual reverberation.
    if reverberant_energy <= direct_energy * 1e-3:
        rt60_s = 0.0
    else:
        decay = np.cumsum(energy[::-1])[::-1]
        decay_db = 10.0 * np.log10((decay + EPSILON) / (decay[0] + EPSILON))
        times = np.arange(len(decay_db), dtype=np.float64) / sample_rate
        mask = (decay_db <= -5.0) & (decay_db >= -35.0)
        if np.count_nonzero(mask) < 8:
            rt60_s = 0.0
        else:
            slope, _ = np.polyfit(times[mask], decay_db[mask], 1)
            rt60_s = float(np.clip(-60.0 / slope if slope < -EPSILON else 0.0, 0.0, float(settings.get("max_rt60_seconds", 12.0))))
    return {"rt60_s": rt60_s, "drr_db": drr_db, "late_tail_db": late_tail_db}


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
    if category in {"spectral_eq", "smartphone_capture", "mic", "eq_coloration"}:
        bands = [(20, 120), (120, 400), (400, 2000), (2000, 6000), (6000, 12000), (12000, 20000)]
        return np.array([_band_ratio(audio, sample_rate, low, high) for low, high in bands])
    if category in {"lowpass", "highpass", "telephone_band", "low_sample_rate", "bandwidth_loss"}:
        return np.array(
            [
                _band_ratio(audio, sample_rate, 7000, sample_rate / 2),
                librosa.feature.spectral_rolloff(y=mono, sr=sample_rate)[0].mean(),
            ]
        )
    if category in {"noise", "hum", "clicks_crackle", "dropouts_glitches", "noise_interference"}:
        flatness = librosa.feature.spectral_flatness(y=mono)[0].mean()
        return np.array([flatness, _band_ratio(audio, sample_rate, 8000, sample_rate / 2)])
    if category in {"clipping", "saturation_overdrive", "clipping_saturation"}:
        peak = np.max(np.abs(mono)) + EPSILON
        return np.array(
            [np.mean(np.abs(mono) >= 0.98 * peak), peak / (np.sqrt(np.mean(mono * mono)) + EPSILON)]
        )
    if category in {"compression", "dynamics"}:
        frames = _frame_rms(audio, 2048, 1024)
        return np.array(
            [np.std(frames), np.max(np.abs(mono)) / (np.sqrt(np.mean(mono * mono)) + EPSILON)]
        )
    if category in {"reverb", "distant_mic_capture", "reverb_room"}:
        energy = mono * mono
        split = max(1, int(len(energy) * 0.1))
        return np.array([np.sum(energy[split:]) / (np.sum(energy[:split]) + EPSILON)])
    if category in {"stereo_collapse", "channel_damage", "stereo_spatial"}:
        left, right = audio[:, 0], audio[:, 1]
        mid, side = (left + right) * 0.5, (left - right) * 0.5
        return np.array(
            [
                np.corrcoef(left, right)[0, 1],
                np.sqrt(np.mean(side * side)) / (np.sqrt(np.mean(mid * mid)) + EPSILON),
                np.sqrt(np.mean(left * left)) / (np.sqrt(np.mean(right * right)) + EPSILON),
            ]
        )
    if category in {"codec", "neural_codec", "transcode_chain", "codec_transmission"}:
        return np.array(
            [
                librosa.feature.spectral_flatness(y=mono)[0].mean(),
                _band_ratio(audio, sample_rate, 10000, sample_rate / 2),
            ]
        )
    if category in {"pitch_speed_instability", "amplitude"}:
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
