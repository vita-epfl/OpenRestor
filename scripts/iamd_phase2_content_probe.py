#!/usr/bin/env python3
"""Probe music/speech/environment tags on existing IAMD 50/200 pilot clips only.

This is a review signal, not a calibrated classifier or a rejection rule. It
downloads model weights on first use but never downloads or scans new audio.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.iamd_phase2_pilot import (DEFAULT_OUT, ROOT, pilot_200_rows, read_jsonl,
                                       smoke_rows, write_jsonl)

MODEL_ID = "MIT/ast-finetuned-audioset-10-10-0.4593"
MODEL_REVISION = "f826b80d28226b62986cc218e5cec390b1096902"
OUTPUT_NAME = "ast_content_probe.jsonl"
INTEREST_LABELS = ("Music", "Musical instrument", "Singing", "Speech", "Sound effect",
                   "Noise", "Outside, urban or manmade", "Vehicle", "Traffic noise, roadway noise")


def planned_windows(out: Path, *, total_sources: int = 50) -> list[dict]:
    if total_sources not in (50, 200):
        raise ValueError("content probe is limited to the 50- or 200-source pilot")
    scores = {row["identifier"]: row for row in read_jsonl(out / "scores.jsonl")}
    result = []
    selected = smoke_rows(out) if total_sources == 50 else pilot_200_rows(out)
    for row in selected:
        score = scores.get(row["identifier"], {})
        if score.get("status") != "measured" or not score.get("excerpts"):
            raise ValueError(f"measured excerpt missing: {row['identifier']}")
        excerpt = score["excerpts"][len(score["excerpts"]) // 2]
        clip = Path(excerpt["clip_path"])
        if (not clip.is_file() or clip.parent.resolve() != (out / "clips").resolve()
                or not clip.name.startswith(row["sample_id"] + "-p") or clip.suffix.lower() != ".flac"):
            raise ValueError(f"clip missing or outside smoke directory: {row['identifier']}")
        start, end = score.get("audiobox_pq_window_in_clip_s") or (0, 10)
        if not (0 <= start < end <= math.ceil(excerpt["duration_s"])):
            raise ValueError(f"invalid 10s window: {row['identifier']}")
        result.append({"identifier": row["identifier"], "sample_id": row["sample_id"],
                       "clip_path": str(clip), "start_s": start, "end_s": end})
    return result


def run(out: Path, *, identifiers: set[str] | None = None, max_items: int | None = None,
        total_sources: int = 50) -> dict:
    plan = planned_windows(out, total_sources=total_sources)
    if identifiers is not None:
        unknown = identifiers - {row["identifier"] for row in plan}
        if unknown:
            raise ValueError(f"not in the 50-source smoke batch: {sorted(unknown)}")
        plan = [row for row in plan if row["identifier"] in identifiers]
    if max_items is not None:
        if not 1 <= max_items <= total_sources:
            raise ValueError("max-items exceeds selected pilot scope")
        plan = plan[:max_items]
    destination = out / OUTPUT_NAME
    previous = {row["identifier"]: row for row in read_jsonl(destination)} if destination.exists() else {}
    pending = [row for row in plan if previous.get(row["identifier"], {}).get("status") != "scored"]
    if not pending:
        return {"requested": len(plan), "scored": len(plan), "attempted_this_run": 0}

    os.environ.setdefault("HF_HOME", str(ROOT / "build/metric_tools/hf_cache"))
    import torch
    import torchaudio
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    extractor = AutoFeatureExtractor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = AutoModelForAudioClassification.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, use_safetensors=True).eval()
    labels = [model.config.id2label[index] for index in range(model.config.num_labels)]
    for index, row in enumerate(pending, 1):
        try:
            clip = Path(row["clip_path"])
            sample_rate = torchaudio.info(str(clip)).sample_rate
            waveform, _ = torchaudio.load(str(clip), frame_offset=round(row["start_s"] * sample_rate),
                                          num_frames=round((row["end_s"] - row["start_s"]) * sample_rate))
            waveform = waveform.mean(dim=0)
            if sample_rate != 16000:
                waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
            inputs = extractor(waveform.numpy(), sampling_rate=16000, return_tensors="pt")
            with torch.inference_mode():
                values = torch.sigmoid(model(**inputs).logits[0]).tolist()
            ranked = sorted(range(len(values)), key=lambda key: values[key], reverse=True)
            previous[row["identifier"]] = {**row, "status": "scored", "model_id": MODEL_ID,
                                           "model_revision": MODEL_REVISION,
                                           "top_labels": [{"label": labels[key], "score": values[key]}
                                                          for key in ranked[:10]],
                                           "interest_labels": {label: values[labels.index(label)]
                                                               for label in INTEREST_LABELS if label in labels}}
        except (OSError, RuntimeError, ValueError, KeyError, IndexError) as error:
            previous[row["identifier"]] = {**row, "status": "error", "error": f"{type(error).__name__}: {error}"}
        write_jsonl(destination, [previous[key] for key in sorted(previous)])
        print(f"[AST {index}/{len(pending)}] {row['identifier']}: "
              f"{previous[row['identifier']]['status']}", flush=True)
    return {"requested": len(plan), "scored": sum(previous[row["identifier"]]["status"] == "scored"
                                                   for row in plan), "attempted_this_run": len(pending),
            "output": str(destination)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--identifiers", help="Comma-separated subset of the selected pilot identifiers")
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--total-sources", type=int, choices=(50, 200), default=50)
    args = parser.parse_args()
    identifiers = set(args.identifiers.split(",")) if args.identifiers else None
    print(json.dumps(run(args.out, identifiers=identifiers, max_items=args.max_items,
                         total_sources=args.total_sources), indent=2))


if __name__ == "__main__":
    main()
