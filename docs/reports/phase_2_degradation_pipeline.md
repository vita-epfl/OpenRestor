# Phase 2 Report: Degradation Pipeline

## Purpose

Phase 2 creates paired training and evaluation data by applying one explicitly selected degradation to a canonical clean clip. Each output is traceable to the clean input, configuration recipe, seed, fully sampled parameters, and checksum. Randomness applies only to the selected effects parameters; effect choices are neither sampled nor combined.

## Implementation Map

| Path | Responsibility |
| --- | --- |
| openrestore/degradations/core.py | Audio I/O, canonicalization, seeded sampling, peak safety, checksums, and FFmpeg codec round trips. |
| openrestore/degradations/ariel_effects.py | OpenRestore-local adaptation of the legacy SonicMaster/ARIEL effect implementations. |
| openrestore/degradations/effects.py | Effect registry, legacy primitive handlers, ARIEL-effect dispatch, and distant-microphone capture. |
| openrestore/degradations/pipeline.py | Recipe loading, per-item deterministic seeds, operation execution, WAV rendering, manifest rows, checksums, HDF5 shards, and release index writing. |
| openrestore/degradations/cli.py | `openrestore-degrade` rendering plus private-release planning, partition, merge, and validation commands. |
| openrestore/degradations/release.py | Frozen-input verification, clean-release validation, deterministic 40-source plans, retry-safe partition receipts, merge, and release validation. |
| configs/degradations/single/v0_1.yaml | Active, effect-first v0.1 single-effect recipes. |
| configs/releases/private_v0_1.yaml | Immutable private v0.1 contract for 25,849 clean clips and 620,376 degraded examples. |
| configs/degradations/review_boundaries/v0_2.yaml | Fixed mild/strong listening endpoints for the OpenRestore additions. |
| tests/test_degradations.py | Determinism, canonical-audio, parameter-sampling, runner, and CLI tests. |
| OpenRestore.md | Effect-level registry, including origin, group, rationale, and status. |

## Implemented Single-Effect Set

The active configuration contains exactly 24 canonical classes: spectral_eq, mic, lowpass, highpass, telephone_band, low_sample_rate, compression, clipping, saturation_overdrive, reverb_small, reverb_big, reverb_mix, reverb_real, distant_mic_capture, noise, hum, clicks_crackle, dropouts_glitches, codec, neural_codec, transcode_chain, stereo_collapse, channel_damage, and pitch_speed_instability. Historical SonicMaster names remain callable as compatibility aliases but are not active benchmark IDs.

distant_mic_capture is the far-from-source recording simulation: a deterministic local room model, direct-to-reverberant balance, bandwidth reduction, and microphone self-noise. It runs without external RIR assets. The `reverb_real` and `mic` ARIEL-compatible effects can use optional external assets when configured, but the baseline renderer and tests do not require them.

## Structure And Flow

1. A clean manifest from Phase 1 supplies item_id and the canonical clean audio path.
2. render loads a recipe configuration and selects recipe operations.
3. For every item and operation, the runner derives a deterministic seed from the global seed, item ID, recipe ID, and operation index.
4. Parameter ranges are sampled from that seed. Mild, medium, and strong are severity bands, not fixed parameter values.
5. The renderer applies the effect, restores canonical sample rate/channel layout, checks finite samples and peak safety, and writes a WAV.
6. It writes one output-manifest row per degraded example and a separate SHA-256 checksum record.
7. `shard` packages rendered WAVs into compressed HDF5 files and writes a release index with `degraded_audio_shard` plus `degraded_audio_shard_index` for every row.

Every degraded manifest row preserves clean-row context and adds clean_path, degraded_path, degradation_recipe_id, severity, degradation_seed, degradation_tracking, degradation_params, and degraded_audio_sha256. The ARIEL/SonicMaster `mud` recipe is an exact 2nd-order Chebyshev-II 200-500 Hz band-pass replacement, not a dry-signal-plus-boost mix. The `vocal` recipe is likewise exact: a 2nd-order Chebyshev-II 350-3500 Hz band-stop over the entire mix, not vocal source separation.

degradation_tracking is the compact audit trail. degradation_params stores the complete sampled operation chain so an example can be recreated exactly.

## Primary Commands

    openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml
    openrestore-degrade list-recipes --config configs/degradations/single/v0_1.yaml
    openrestore-degrade render --manifest build/clean/clean_manifest.jsonl --clean-root build/clean/audio --output-root build/degraded --config configs/degradations/single/v0_1.yaml --output-manifest build/degraded/manifest.jsonl --checksums build/degraded/checksums.jsonl --seed 20260714
    openrestore-degrade shard --output-root build/degraded --manifest build/degraded/manifest.jsonl --shards-dir build/release/shards --output-index build/release/index.jsonl --shard-size 960

    # Freeze only after the canonical clean manifest and WAV checksums pass.
    openrestore-degrade plan-release --clean-manifest build/clean/manifest.jsonl --clean-root build/clean/audio --release-config configs/releases/private_v0_1.yaml --output build/private-releases/openrestore-paired-v0.1/plan.json
    openrestore-degrade render-partition --plan build/private-releases/openrestore-paired-v0.1/plan.json --partition-id sonicmaster_clean--train--00000 --clean-manifest build/clean/manifest.jsonl --clean-root build/clean/audio --release-config configs/releases/private_v0_1.yaml --work-root build/degradation-staging --release-root build/private-releases/openrestore-paired-v0.1
    openrestore-degrade merge-release --plan build/private-releases/openrestore-paired-v0.1/plan.json --release-root build/private-releases/openrestore-paired-v0.1 --output-index build/private-releases/openrestore-paired-v0.1/index.jsonl --receipt build/private-releases/openrestore-paired-v0.1/release-receipt.json
    openrestore-degrade validate-release --plan build/private-releases/openrestore-paired-v0.1/plan.json --release-root build/private-releases/openrestore-paired-v0.1 --receipt build/private-releases/openrestore-paired-v0.1/release-receipt.json

The editable install exposes openrestore-degrade; python -m openrestore.degradations.cli is the fallback when a shell has not been refreshed after installation.

## Verification In Place

Automated tests confirm canonical output properties, finite samples, determinism for a fixed seed, changed sampled values for a changed seed, recipe rendering, output-manifest creation, checksums, HDF5 shard/index layout, CLI execution, all active-effect dispatch paths, and actionable failure messages for missing assets, FFmpeg, and invalid room bounds. `python -m unittest tests.test_degradations` passes all eight tests.

A local medium listening preview exists under build/degradation_preview/degraded_all_effects_medium_v4. Boundary review uses review_boundaries/v0_2.yaml: fixed minimum and maximum endpoints for each OpenRestore addition. The 75-output medium preview has also been packaged as `build/degradation_preview/release_candidate_v0_1`: eight HDF5 shards and an index whose paths are portable within that directory. All of these remain review artifacts, not benchmark releases.

## Remaining Phase 2 Work

- Publish the reviewed asset bundle to the approved artifact store and record its archive URL, license/provenance, and archive SHA-256 in the release record. IT installation and file verification are specified in `docs/degradation_assets.md`.
- Freeze the shard-backed miniature candidate with the accepted parameter configuration and asset artifact.
- The earlier 25-class pilot is superseded by this 24-class registry. Run a new scheduler-owned pilot, record throughput/compression and staging capacity, then schedule the frozen 648-partition plan with 960 outputs per normal partition. Publication stays blocked pending source-license and degradation-asset provenance approval.

## Next Steps For IT

This is the Phase 2 IT checklist from the roadmap:

- [ ] Provide hosted compute for running the research-owned degradation command at release scale.
- [ ] Configure job scheduling, retries, logs, and monitoring around degradation runs.
- [ ] Store degraded shards, manifests, checksums, and logs in agreed hosted artifact locations.
- [ ] Provide enough parallel execution capacity for large dataset builds without changing the degradation code.
- [ ] Report infrastructure, quota, and timeout failures separately from scientific/pipeline failures.

### Handoff Details

The runtime needs Python 3.11, FFmpeg, and the dependencies declared in pyproject.toml; docker/Dockerfile is the starting environment. Use read-only clean inputs and separate degraded-output storage. IT must install the exact Git-ignored v0.1 asset bundle at `assets/degradations/v0_1/`; see `docs/degradation_assets.md` and verify every file with `docs/degradation_assets_v0_1.sha256`. Never use developer-local ARIEL paths. Keep the global seed, config snapshot, Git revision, output manifest, checksums, logs, and failure list for each partition, and ensure retries cannot change item seeds or overwrite validated results.

## Next Steps For Research

- Publish the v0.1 binary asset archive and record its release provenance.
- Freeze the shard-backed miniature candidate using the accepted configuration and asset archive.
- Define release acceptance criteria before production-scale degradation rendering.
