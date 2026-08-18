# Phase 3 Report: Metrics, AAE Diagnostics, And Reports

## Status

Implemented: CPU local scoring, strict participant restoration manifests, trusted restoration metadata joins, and an optional GPU perceptual metric pack. No leaderboard aggregate is defined.

## Current Pipeline

Participants write `restoration_outputs.jsonl`: each row supplies an OpenRestore item ID, a restored WAV path, and nullable run metadata such as inference steps and batch time. `openrestore-score` validates every output, joins trusted degraded-manifest data, and writes `restoration_metadata.jsonl`. This ensures that clean/degraded paths, source ID, effect, severity, split, dataset, and degradation tracking are benchmark-owned rather than participant-provided.

The CPU report contains L1, RMSE, SNR, SI-SDR, SI-SNR, LSD, MRSTFT, log-mel, LTAS, SSIM, spectral KL, and category/effect AAE diagnostics. The no-restoration baseline on the 75-item preview had zero artificial improvement.

The separate GPU pack preserves ARIEL's learned-metric behavior: CLAP audio cosine similarity, `fadtk` using the `clap-laion-music` backend for restored-vs-clean and restored-vs-built-in-`fma_pop`, and Audiobox CE/CU/PC/PQ. FADTK embeddings use ARIEL's PCM temporary-WAV workaround around TorchCodec. The public `setup-perceptual` command downloads the model weights and loads the built-in FMA-Pop statistics before recording package versions and cache hashes.

## Remaining Release Work

- Run the opt-in real-GPU integration test after the FADTK, CLAP, and Audiobox cache is prepared; current CI uses deterministic mock backends and does not download models.
- Review CPU and perceptual baseline reports before defining any official leaderboard policy. SDD audio-text and PANNS remain deferred.

## IT Handoff

IT hosts the same package extras and `setup-perceptual` cache used by public users. Evaluation jobs need read-only clean/degraded input, participant restoration output, the verified model cache, CUDA, and writable report storage. Cache/hash failures, invalid submissions, and model inference errors are emitted separately as structured failures.
