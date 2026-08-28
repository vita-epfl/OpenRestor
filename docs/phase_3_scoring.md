# Phase 3 Local Scoring

## Restoration Manifest

Every inference system writes one row per degraded item to `restoration_outputs.jsonl`. Use [restoration_outputs.jsonl](templates/restoration_outputs.jsonl) as the template.

```json
{"id":"<degraded-manifest id>","restored_audio_path":"relative/or/absolute/output.wav","restored_latent_shape":null,"duration_sec":null,"inference_steps":null,"batch_time_seconds":null,"timestamp":null}
```

`id` and `restored_audio_path` are required. The timing, latent-shape, and step fields are nullable because not every restoration system exposes them. Relative paths resolve from the manifest directory. The scorer rejects duplicate, unknown, missing, unreadable, non-finite, wrong-rate, wrong-channel, and wrong-duration outputs; it never silently scores a partial submission.

The scorer joins these participant fields to trusted benchmark data and writes `restoration_metadata.jsonl`. That artifact contains the clean/degraded paths, effect, source ID, dataset, split, severity, and deterministic degradation provenance. Participants must not invent or copy hidden clean-path metadata.

```bash
openrestore-validate restoration_outputs --input restoration_outputs.jsonl
openrestore-score validate-restored \
  --degraded-manifest degraded/index.jsonl \
  --restored-manifest restoration_outputs.jsonl
```

## CPU Metrics

```bash
openrestore-score no-restoration \
  --degraded-manifest degraded/index.jsonl \
  --degraded-root degraded/audio \
  --output-root baseline/audio \
  --output-manifest baseline/restoration_outputs.jsonl

openrestore-score score \
  --degraded-manifest degraded/index.jsonl \
  --degraded-root degraded/audio \
  --clean-root clean/audio \
  --restored-manifest baseline/restoration_outputs.jsonl \
  --config configs/evaluation/metrics.yaml \
  --output-dir baseline/scores
```

CPU scoring writes `scores.json`, `per_item_scores.jsonl`, `restoration_metadata.jsonl`, `report.md`, and `failures.json`. These are diagnostic metrics only; they define no rank or aggregate.

## GPU Perceptual Metrics

Install and cache the optional pack once on every scoring machine:

```bash
pip install '.[perceptual]'
openrestore-score setup-perceptual \
  --config configs/evaluation/perceptual.yaml \
  --cache-dir ~/.cache/openrestore/perceptual-v0_1
```

The setup command downloads the pinned CLAP, FADTK, and Audiobox weights, and records versions and hashes in `perceptual_cache_manifest.json`. IT and benchmark users run the same command. The FMA-Pop comparison uses the built-in `fadtk` `fma_pop` statistics for the same `clap-laion-music` backend as ARIEL. No separately supplied FMA statistics file is needed.

```bash
openrestore-score perceptual \
  --degraded-manifest degraded/index.jsonl \
  --degraded-root degraded/audio \
  --clean-root clean/audio \
  --restored-manifest outputs/restoration_outputs.jsonl \
  --config configs/evaluation/perceptual.yaml \
  --cache-dir ~/.cache/openrestore/perceptual-v0_1 \
  --output-dir outputs/perceptual_scores
```

The GPU-only command writes `perceptual_scores.json`, `per_item_perceptual_scores.jsonl`, `restoration_metadata.jsonl`, `perceptual_report.md`, and `perceptual_failures.json`. It reports CLAP cosine similarity, FADTK restored-vs-clean and FADTK restored-vs-FMA-Pop, and Audiobox CE/CU/PC/PQ. Higher is better for CLAP and Audiobox; lower is better for FAD. Every reported improvement is positive when restored audio is better than degraded audio.
