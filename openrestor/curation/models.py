"""Optional offline model probes for local curation clips.

The pinned IAMD AST and CLAP models are reused. Scores remain independent
signals and are not interpreted as calibrated probabilities or ground truth.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

AXES = ("CE", "CU", "PC", "PQ")
AST_ID = "MIT/ast-finetuned-audioset-10-10-0.4593"
AST_REV = "f826b80d28226b62986cc218e5cec390b1096902"
INTEREST_LABELS = ("Music", "Musical instrument", "Singing", "Speech", "Sound effect",
                   "Noise", "Outside, urban or manmade", "Vehicle", "Traffic noise, roadway noise")
CLAP_ID = "laion/clap-htsat-unfused"
CLAP_REV = "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
PROMPT_VERSION = "contrastive-200-v1"
# Retain the exact pinned pilot prompts; scores from the pilot remain comparable.
PROMPTS = {
    "produced_music": (
        "A clear, well-produced recording of a complete song with instruments and vocals.",
        "A clean studio recording of a musical performance with distinct instruments.",
        "A high-quality recording of an ensemble playing a complete piece of music.",
        "A clear, balanced live concert recording of music.",
    ),
    "degraded_music": (
        "A distant, muffled recording of a band playing music in another room.",
        "A noisy, low-quality phone recording of someone singing a song.",
        "A distorted amateur recording of music with room noise and hiss.",
        "A thin, poorly recorded live musical performance with distant instruments.",
    ),
    "non_music": (
        "A field recording of a city street with traffic and people talking, not music.",
        "An isolated sound effect or environmental noise without a song.",
        "A person speaking or giving a radio talk with no musical performance.",
        "A recording of ambient outdoor sounds rather than music.",
    ),
    "rudimentary_synthetic": (
        "A simple MIDI sequence played with a basic soundfont rather than a produced song.",
        "A test tone or oscillator demonstration instead of a musical production.",
        "A rudimentary computer-generated melody with cheap synthetic instrument sounds.",
        "A short tracker or basic sequencer test with repetitive beeps.",
    ),
    "legitimate_electronic_music": (
        "A polished electronic music production with synthesizers and a deliberate arrangement.",
        "A complete ambient electronic music composition with layered textures.",
        "A well-produced experimental electronic song with intentional sound design.",
        "A deliberate chiptune music composition, not a test tone or sound effect.",
    ),
}


def group_scores(similarities: list[float]) -> dict[str, float]:
    if len(similarities) != sum(len(group) for group in PROMPTS.values()):
        raise ValueError("wrong number of CLAP similarities")
    scores = {}
    offset = 0
    for name, prompts in PROMPTS.items():
        scores[name] = sum(similarities[offset:offset + len(prompts)]) / len(prompts)
        offset += len(prompts)
    return scores


def prepare_offline_cache(cache_dir: Path) -> None:
    os.environ["HF_HOME"] = str(cache_dir.resolve())
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def _waveform(path: Path, target_rate: int):
    import torchaudio

    info = torchaudio.info(str(path))
    start = max(0, int((info.num_frames / info.sample_rate - 10) / 2))
    frames = min(info.num_frames - round(start * info.sample_rate), 10 * info.sample_rate)
    waveform, _ = torchaudio.load(str(path), frame_offset=round(start * info.sample_rate),
                                  num_frames=frames)
    mono = waveform.mean(dim=0)
    if waveform.shape[0] > 2:
        # Preserve the total energy of wide masters such as 7.1.4 instead of
        # making them appear 10+ dB quieter through a plain channel average.
        mono = mono * math.sqrt(waveform.shape[0])
    if info.sample_rate != target_rate:
        mono = torchaudio.functional.resample(mono, info.sample_rate, target_rate)
    return mono.numpy(), start, start + frames / info.sample_rate


class OfflineProbes:
    def __init__(self, cache_dir: Path):
        prepare_offline_cache(cache_dir)
        self._ast = None
        self._clap = None
        self._audiobox = None

    def ast(self, path: Path) -> dict:
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        if self._ast is None:
            extractor = AutoFeatureExtractor.from_pretrained(AST_ID, revision=AST_REV, local_files_only=True)
            model = AutoModelForAudioClassification.from_pretrained(
                AST_ID, revision=AST_REV, use_safetensors=True, local_files_only=True).eval()
            labels = [model.config.id2label[index] for index in range(model.config.num_labels)]
            self._ast = (extractor, model, labels)
        extractor, model, labels = self._ast
        waveform, start, end = _waveform(path, 16000)
        inputs = extractor(waveform, sampling_rate=16000, return_tensors="pt")
        with torch.inference_mode():
            values = torch.sigmoid(model(**inputs).logits[0]).tolist()
        return {"interest_labels": {name: values[labels.index(name)]
                                    for name in INTEREST_LABELS if name in labels},
                "model_id": AST_ID, "model_revision": AST_REV, "window_in_clip_s": [start, end]}

    def clap(self, path: Path) -> dict:
        import torch
        import torch.nn.functional as F
        from transformers import ClapModel, ClapProcessor

        if self._clap is None:
            processor = ClapProcessor.from_pretrained(CLAP_ID, revision=CLAP_REV, local_files_only=True)
            model = ClapModel.from_pretrained(CLAP_ID, revision=CLAP_REV, local_files_only=True).eval()
            texts = [prompt for group in PROMPTS.values() for prompt in group]
            with torch.inference_mode():
                encoded = processor(text=texts, padding=True, return_tensors="pt")
                text_vectors = F.normalize(model.get_text_features(**encoded), dim=-1)
            self._clap = (processor, model, text_vectors)
        processor, model, text_vectors = self._clap
        waveform, start, end = _waveform(path, 48000)
        inputs = processor(audios=waveform, sampling_rate=48000, return_tensors="pt")
        with torch.inference_mode():
            audio_vector = F.normalize(model.get_audio_features(**inputs), dim=-1)
            similarities = (audio_vector @ text_vectors.T)[0].tolist()
        scores = group_scores(similarities)
        return {"group_scores": scores, "model_id": CLAP_ID, "model_revision": CLAP_REV,
                "prompt_version": PROMPT_VERSION, "window_in_clip_s": [start, end]}

    def aesthetics(self, path: Path) -> dict:
        if self._audiobox is None:
            from audiobox_aesthetics.infer import initialize_predictor

            self._audiobox = initialize_predictor()
        import soundfile as sf

        info = sf.info(path)
        start = max(0, int((info.duration - 10) / 2))
        # audiobox-aesthetics multiplies these values by the sample rate and
        # passes them directly as torchaudio frame counts.  Keep the endpoint
        # integral so short clips do not fail with ``float object cannot be
        # interpreted as an integer``; this changes no model or scoring rule.
        end = max(start + 1, int(math.ceil(min(info.duration, start + 10))))
        raw = self._audiobox.forward([{"path": str(path), "start_time": start, "end_time": end}])[0]
        scores = {axis: float(raw[axis]) for axis in AXES}
        if not all(math.isfinite(value) for value in scores.values()):
            raise ValueError(f"nonfinite Audiobox result: {path}")
        return scores


def needs_probe(segment: dict, model: str) -> bool:
    if model == "ast":
        value = segment.get("ast") or {}
        return value.get("model_revision") != AST_REV
    if model == "clap":
        value = segment.get("clap") or {}
        return value.get("model_revision") != CLAP_REV or value.get("prompt_version") != PROMPT_VERSION
    if model == "aesthetics":
        value = segment.get("aesthetics") or {}
        return not all(isinstance(value.get(axis), (int, float)) and math.isfinite(value[axis])
                       for axis in AXES)
    raise ValueError(f"unknown model probe: {model}")
