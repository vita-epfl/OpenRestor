# Phase 3 Local Scoring

## Scope

`openrestore-score` is the CPU-only, diagnostic scoring pipeline for OpenRestore v0.1. It produces separate objective metrics and degradation-aware AAE diagnostics. It does not define a leaderboard rank or a combined score.

The optional GPU metric pack is deliberately deferred: CLAP, PANNS, FAD, FAD-LAION, and Audiobox metrics will be added later without changing the restored-output manifest or CPU score contract.

## Restored Output Contract

Every inference system must write one JSON object per degraded input to a restored-output JSONL file. Use [restored_outputs.jsonl](templates/restored_outputs.jsonl) as the template.

```json
{"id":"<degraded-manifest id>","restored_path":"relative/path/to/restored.wav"}
```

`id` must exactly match the degraded manifest row ID. `restored_path` is relative to the restored JSONL file unless absolute. The scorer rejects duplicate, unknown, missing, unreadable, non-finite, wrong-rate, wrong-channel, and wrong-duration outputs. It writes `failures.json` and exits unsuccessfully rather than scoring a partial set.

This is the required local-inference output format and the future participant-container output format. The template is validated with:

```bash
openrestore-validate restored_outputs --input restored_outputs.jsonl
openrestore-score validate-restored --degraded-manifest degraded/index.jsonl --restored-manifest restored_outputs.jsonl
```

## Commands

```bash
openrestore-score no-restoration \
  --degraded-manifest degraded/index.jsonl \
  --degraded-root degraded/audio \
  --output-root baseline/audio \
  --output-manifest baseline/restored_outputs.jsonl

openrestore-score score \
  --degraded-manifest degraded/index.jsonl \
  --degraded-root degraded/audio \
  --clean-root clean/audio \
  --restored-manifest baseline/restored_outputs.jsonl \
  --config configs/evaluation/metrics.yaml \
  --output-dir baseline/scores
```

The no-restoration helper copies each degraded WAV without processing and emits the required JSONL. It is the baseline floor for metric review.

## Artifacts And Interpretation

`score` writes `scores.json`, `per_item_scores.jsonl`, `report.md`, and `failures.json`. `scores.json` has overall, category, effect, severity, and split summaries. Categories are the primary AAE summaries; individual effects are supporting detail.

Lower is better for errors and distances. Higher is better for SNR, SI-SDR, SI-SNR, and log-mel SSIM. Every `improvement` value is oriented so positive means restoration improved over its degraded input. AAE reduction compares the restoration descriptor error against the degraded descriptor error. Codec AAE is transparent but experimental.
