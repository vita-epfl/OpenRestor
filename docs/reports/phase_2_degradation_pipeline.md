# Phase 2 Report: Degradation Pipeline

## Status

In progress. The current v0.1 single-effect renderer is implemented and verified with unit, CLI, and listening-preview runs. The complete Phase 2 release workflow is not yet finished: normal-parameter calibration, release-approved external assets, the `volume` decision, and production batch orchestration remain open.

## Purpose

Phase 2 creates paired training and evaluation data by applying one explicitly selected degradation to a canonical clean clip. Each output is traceable to the clean input, configuration recipe, seed, fully sampled parameters, and checksum. Randomness applies only to the selected effects parameters; effect choices are neither sampled nor combined.

## Implementation Map

| Path | Responsibility |
| --- | --- |
| openrestore/degradations/core.py | Audio I/O, canonicalization, seeded sampling, peak safety, checksums, and FFmpeg codec round trips. |
| openrestore/degradations/ariel_effects.py | OpenRestore-local adaptation of the 19 selected SonicMaster/ARIEL effect implementations. |
| openrestore/degradations/effects.py | Effect registry, legacy primitive handlers, ARIEL-effect dispatch, and distant-microphone capture. |
| openrestore/degradations/pipeline.py | Recipe loading, per-item deterministic seeds, operation execution, WAV rendering, manifest rows, checksums, HDF5 shards, and release index writing. |
| openrestore/degradations/cli.py | `openrestore-degrade` commands: render, shard, validate-config, and list-recipes. |
| configs/degradations/single/v0_1.yaml | Active, effect-first v0.1 single-effect recipes. |
| configs/degradations/review_boundaries/v0_2.yaml | Fixed mild/strong listening endpoints for the OpenRestore additions. |
| tests/test_degradations.py | Determinism, canonical-audio, parameter-sampling, runner, and CLI tests. |
| OpenRestore.md | Effect-level registry, including origin, group, rationale, and status. |

## Implemented Single-Effect Set

The active configuration contains 25 effects.

- SonicMaster/ARIEL baseline: comp, punch, xband, mic, bright, dark, airy, boom, clarity, mud, warm, vocal, small, big, mix, real, stereo, clip, and volume.
- OpenRestore additions: noise, hum, clicks_crackle, codec, bandwidth, and distant_mic_capture.

distant_mic_capture is the far-from-source recording simulation: a deterministic local room model, direct-to-reverberant balance, bandwidth reduction, and microphone self-noise. It runs without external RIR assets. The real and mic ARIEL-compatible effects can use optional external assets when configured, but the baseline renderer and tests do not require them.

## Structure And Flow

1. A clean manifest from Phase 1 supplies item_id and the canonical clean audio path.
2. render loads a recipe configuration and selects recipe operations.
3. For every item and operation, the runner derives a deterministic seed from the global seed, item ID, recipe ID, and operation index.
4. Parameter ranges are sampled from that seed. Mild, medium, and strong are severity bands, not fixed parameter values.
5. The renderer applies the effect, restores canonical sample rate/channel layout, checks finite samples and peak safety, and writes a WAV.
6. It writes one output-manifest row per degraded example and a separate SHA-256 checksum record.
7. `shard` packages rendered WAVs into compressed HDF5 files and writes a release index with `degraded_audio_shard` plus `degraded_audio_shard_index` for every row.

Every degraded manifest row preserves clean-row context and adds clean_path, degraded_path, degradation_recipe_id, severity, degradation_seed, degradation_tracking, degradation_params, and degraded_audio_sha256.

degradation_tracking is the compact audit trail. degradation_params stores the complete sampled operation chain so an example can be recreated exactly.

## Primary Commands

    openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml
    openrestore-degrade list-recipes --config configs/degradations/single/v0_1.yaml
    openrestore-degrade render --manifest build/clean/clean_manifest.jsonl --clean-root build/clean/audio --output-root build/degraded --config configs/degradations/single/v0_1.yaml --output-manifest build/degraded/manifest.jsonl --checksums build/degraded/checksums.jsonl --seed 20260714
    openrestore-degrade shard --output-root build/degraded --manifest build/degraded/manifest.jsonl --shards-dir build/release/shards --output-index build/release/index.jsonl --shard-size 1000

The editable install exposes openrestore-degrade; python -m openrestore.degradations.cli is the fallback when a shell has not been refreshed after installation.

## Verification In Place

Automated tests confirm canonical output properties, finite samples, determinism for a fixed seed, changed sampled values for a changed seed, recipe rendering, output-manifest creation, checksums, HDF5 shard/index layout, CLI execution, all active-effect dispatch paths, and actionable failure messages for missing assets, FFmpeg, and invalid room bounds. `python -m unittest tests.test_degradations` passes all eight tests.

A local medium listening preview exists under build/degradation_preview/degraded_all_effects_medium_v4. Boundary review uses review_boundaries/v0_2.yaml: fixed minimum and maximum endpoints for each OpenRestore addition. The 75-output medium preview has also been packaged as `build/degradation_preview/release_candidate_v0_1`: eight HDF5 shards and an index whose paths are portable within that directory. All of these remain review artifacts, not benchmark releases.

## Remaining Phase 2 Work

- Calibrate and formally accept the normal parameter ranges through effect-by-effect listening, including the newly reviewed minimum/maximum endpoints.
- Package or acquire release-approved microphone transfer functions and real RIRs, with provenance and checksums; the release cannot depend on developer-local ARIEL paths.
- Decide whether `volume` is benchmark-critical or SonicMaster-parity-only. `channel_damage` is no longer in the active registry.
- Freeze the shard-backed miniature candidate only after the parameter and asset decisions; then implement production-scale deterministic partitioning, retry/resume behavior, and validated merging.

## Next Steps For IT

This is the Phase 2 IT checklist from the roadmap:

- [ ] Provide hosted compute for running the research-owned degradation command at release scale.
- [ ] Configure job scheduling, retries, logs, and monitoring around degradation runs.
- [ ] Store degraded shards, manifests, checksums, and logs in agreed hosted artifact locations.
- [ ] Provide enough parallel execution capacity for large dataset builds without changing the degradation code.
- [ ] Report infrastructure, quota, and timeout failures separately from scientific/pipeline failures.

### Handoff Details

The runtime needs Python 3.11, FFmpeg, and the dependencies declared in pyproject.toml; docker/Dockerfile is the starting environment. Use read-only clean inputs and separate degraded-output storage. Optional RIR and microphone-transfer-function assets must be mounted through explicit configuration, never developer-local ARIEL paths. Keep the global seed, config snapshot, Git revision, output manifest, checksums, logs, and failure list for each partition, and ensure retries cannot change item seeds or overwrite validated results.

## Next Steps For Research

- Finish the single-effect review and freeze the v0.1 severity ranges.
- Specify the compound recipe rules only after individual effects are accepted.
- Define the release acceptance criteria for a degraded corpus before running it at scale.
