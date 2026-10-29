#!/usr/bin/env python3
"""Contrastive CLAP review cues for existing IAMD pilot clips; never fetch audio.

The scores are relative text/audio similarities, not probabilities or rights
decisions. Prompt groups and the pinned checkpoint form a frozen pilot version.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.iamd_phase2_content_probe import planned_windows
from scripts.iamd_phase2_pilot import DEFAULT_OUT, ROOT, read_jsonl, write_jsonl

MODEL_ID = "laion/clap-htsat-unfused"
MODEL_REVISION = "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
PROMPT_VERSION = "contrastive-200-v1"
OUTPUT_NAME = "clap_contrastive_probe.jsonl"

# Equal-sized groups avoid silently rewarding a category for having more text
# variants. Electronic music is an explicit positive class, not a rejection.
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
    expected = sum(len(prompts) for prompts in PROMPTS.values())
    if len(similarities) != expected:
        raise ValueError(f"expected {expected} CLAP prompt similarities")
    scores = {}
    offset = 0
    for name, prompts in PROMPTS.items():
        group = similarities[offset:offset + len(prompts)]
        scores[name] = sum(group) / len(group)
        offset += len(prompts)
    return scores


def run(out: Path, *, identifiers: set[str] | None = None, max_items: int | None = None,
        total_sources: int = 200) -> dict:
    plan = planned_windows(out, total_sources=total_sources)
    if identifiers is not None:
        unknown = identifiers - {row["identifier"] for row in plan}
        if unknown:
            raise ValueError(f"identifiers outside measured pilot: {sorted(unknown)}")
        plan = [row for row in plan if row["identifier"] in identifiers]
    if max_items is not None:
        if not 1 <= max_items <= total_sources:
            raise ValueError("max-items exceeds pilot scope")
        plan = plan[:max_items]
    destination = out / OUTPUT_NAME
    previous = {row["identifier"]: row for row in read_jsonl(destination)} if destination.exists() else {}
    pending = [row for row in plan if not (
        previous.get(row["identifier"], {}).get("status") == "scored"
        and previous[row["identifier"]].get("model_revision") == MODEL_REVISION
        and previous[row["identifier"]].get("prompt_version") == PROMPT_VERSION)]
    if not pending:
        return {"requested": len(plan), "scored": len(plan), "attempted_this_run": 0}

    os.environ.setdefault("HF_HOME", str(ROOT / "build/metric_tools/hf_cache"))
    import torch
    import torch.nn.functional as F
    import torchaudio
    from transformers import ClapModel, ClapProcessor

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    processor = ClapProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = ClapModel.from_pretrained(MODEL_ID, revision=MODEL_REVISION).eval()
    texts = [prompt for prompts in PROMPTS.values() for prompt in prompts]
    with torch.inference_mode():
        text_inputs = processor(text=texts, padding=True, return_tensors="pt")
        text_vectors = F.normalize(model.get_text_features(**text_inputs), dim=-1)
    for index, row in enumerate(pending, 1):
        try:
            clip = Path(row["clip_path"])
            sample_rate = torchaudio.info(str(clip)).sample_rate
            waveform, _ = torchaudio.load(str(clip), frame_offset=round(row["start_s"] * sample_rate),
                                          num_frames=round((row["end_s"] - row["start_s"]) * sample_rate))
            waveform = waveform.mean(dim=0)
            if sample_rate != 48000:
                waveform = torchaudio.functional.resample(waveform, sample_rate, 48000)
            audio_inputs = processor(audios=waveform.numpy(), sampling_rate=48000, return_tensors="pt")
            with torch.inference_mode():
                audio_vector = F.normalize(model.get_audio_features(**audio_inputs), dim=-1)
                similarities = (audio_vector @ text_vectors.T)[0].tolist()
            scores = group_scores(similarities)
            ranked = sorted(scores, key=lambda key: scores[key], reverse=True)
            previous[row["identifier"]] = {
                **row, "status": "scored", "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                "prompt_version": PROMPT_VERSION, "group_scores": scores, "top_group": ranked[0],
                "top_margin": scores[ranked[0]] - scores[ranked[1]],
            }
        except (OSError, RuntimeError, ValueError, KeyError, IndexError) as error:
            previous[row["identifier"]] = {**row, "status": "error", "model_id": MODEL_ID,
                                           "model_revision": MODEL_REVISION,
                                           "prompt_version": PROMPT_VERSION,
                                           "error": f"{type(error).__name__}: {error}"}
        write_jsonl(destination, [previous[key] for key in sorted(previous)])
        print(f"[CLAP {index}/{len(pending)}] {row['identifier']}: "
              f"{previous[row['identifier']]['status']}", flush=True)
    return {"requested": len(plan),
            "scored": sum(previous[row["identifier"]]["status"] == "scored" for row in plan),
            "attempted_this_run": len(pending), "output": str(destination)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--total-sources", type=int, choices=(50, 200), default=200)
    parser.add_argument("--identifiers", help="Comma-separated subset of measured pilot identifiers")
    parser.add_argument("--max-items", type=int)
    args = parser.parse_args()
    identifiers = set(args.identifiers.split(",")) if args.identifiers else None
    print(json.dumps(run(args.out, identifiers=identifiers, max_items=args.max_items,
                         total_sources=args.total_sources), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
