# Phase 3 Report: Metrics, AAE Diagnostics, And Reports

## Status

Implemented: CPU-only local scoring, strict restored-output validation, separate diagnostic reports, and a no-restoration baseline helper. No leaderboard aggregate is defined. Learned embedding, distributional, and aesthetic metrics remain a future optional GPU metric pack.

## Implementation

The `openrestore-score` CLI validates a restored-output JSONL against a degraded manifest, scores clean/degraded/restored audio, and writes `scores.json`, `per_item_scores.jsonl`, `report.md`, and `failures.json`. The first run used the 75-item medium preview with the no-restoration helper: it completed with zero invalid outputs and every reported improvement was zero, as expected.

The CPU metric pack contains L1, RMSE, SNR, SI-SDR, SI-SNR, LSD, multi-resolution STFT distance, log-mel distance, LTAS distance, log-mel SSIM, and spectral-profile KL. It reports degraded-to-clean and restored-to-clean values, with improvement always oriented so positive is better.

AAE descriptors are reported primarily by category and then by effect: EQ/coloration, dynamics, reverb/room, amplitude, stereo/spatial, noise/interference, bandwidth loss, clipping/saturation, and experimental codec/transmission. The restored-output contract is documented in `docs/phase_3_scoring.md` and reused by future participant containers.

## Remaining Work

- Review the no-restoration metric report and use it to decide whether any metric needs recalibration before an official aggregate is considered.
- Add the optional GPU metric pack with pinned model versions, explicit weight/cache provisioning, and fail-closed model errors.
- Keep hidden-evaluation execution and leaderboard orchestration in Phases 5 and 6.

## IT Handoff

IT can host the CPU scorer directly with the repository dependencies. Jobs require read-only clean/degraded inputs, a restored-output JSONL plus audio, and writable report storage. The GPU metric pack is not a prerequisite for v0.1 CPU scoring.
