# OpenRestore Degradation Pipeline: IT Handoff

## Purpose

This document is the operational contract for hosting the current OpenRestore degradation pipeline. It describes the code IT must run as supplied by the research/audio side, the required inputs and outputs, and the infrastructure responsibilities around it.

IT hosts, schedules, stores, monitors, and secures the pipeline. IT must not change degradation algorithms, effect parameters, seed derivation, recipe definitions, or output metadata semantics. Changes to those belong to the research/audio side and require a versioned code/config release.

The current implementation is a local CPU pipeline. It creates canonical WAV outputs and JSONL manifests; it does not yet write HDF5 degraded shards.

## Current Scope

The active single-effect registry contains 25 degradations:

- 19 ARIEL/SonicMaster-parity effects
- 6 OpenRestore additions: `noise`, `hum`, `codec`, `bandwidth`, `channel_damage`, and `distant_mic_capture`

The canonical recipe file is:

```
configs/degradations/single/v0_1.yaml
```

Recipes are deterministic for a given code revision, config, clean manifest, and global seed. They use randomized parameter ranges during normal dataset generation. A separate `medium_preview` configuration is for listening review only and is not a release recipe.

## Required Runtime

- Python 3.11 or newer
- FFmpeg available on `PATH` for codec recipes
- Python dependencies declared in `pyproject.toml`
- CPU capacity; no GPU is required for the current degradation runner
- Writable local scratch space for FFmpeg codec round-trips
- Writable output storage for WAVs, JSONL manifests, checksums, and logs

Install the pipeline from the repository revision selected for the run:

```bash
python3 -m pip install -e .
```

Validate the release config before a batch run:

```bash
openrestore-degrade validate-config \
  --config configs/degradations/single/v0_1.yaml

openrestore-degrade list-recipes \
  --config configs/degradations/single/v0_1.yaml
```
Validate a versioned artifact schema with:

```bash
openrestore-validate index --input tests/fixtures/index.json
```

Supported schema kinds are `index`, `degradation_tracking`, `submission_manifest`, `scores`, and `leaderboard_entry`.


## Input Contract

The renderer takes a JSONL clean manifest and a clean-audio root.

Each row must provide at least:

```json
{
  "id": "stable-clean-item-id",
  "dataset": "sonicmaster_clean",
  "split": "train",
  "clean_path": "train/sonicmaster_clean/item.wav"
}
```

The actual input path is:

```
<clean-root>/<clean_path>
```

Requirements:

- Source audio must be 44.1 kHz. The runner rejects other sample rates.
- Mono input is duplicated to stereo; inputs with more than two channels are reduced to the first two channels.
- `id`, `dataset`, and `split` must be stable across reruns. They affect output IDs, paths, and seeds.
- The input manifest is read-only from the runner's perspective.

## Render Command

Use a unique staging/output directory for every run:

```bash
openrestore-degrade render \
  --manifest /data/openrestore/manifests/clean.jsonl \
  --clean-root /data/openrestore/clean \
  --output-root /data/openrestore/runs/<run-id>/degraded \
  --config /app/configs/degradations/single/v0_1.yaml \
  --output-manifest /data/openrestore/runs/<run-id>/degraded.jsonl \
  --checksums /data/openrestore/runs/<run-id>/degraded_checksums.jsonl \
  --seed 20260730
```

The run count is:

```
number of clean-manifest rows x number of recipes
```

Do not run multiple jobs that write to the same `output-root`, output manifest, or checksum file. Parallelize only by partitioning the input manifest and assigning each partition an isolated output directory and manifest/checksum paths. Merging partition outputs is a research-owned follow-up task; do not invent a merge format.

## Output Contract

For each clean item and recipe, the runner writes:

```
<output-root>/<split>/<dataset>/<recipe-id>/<clean-id>--<recipe-id>.wav
```

Output audio is PCM16 WAV, 44.1 kHz, stereo, duration-matched to the clean input, finite, and peak-limited.

The output manifest contains one JSONL row per degraded file. It preserves clean-row fields and adds:

- `id`: `<clean-id>--<recipe-id>`
- `clean_id`
- `degraded_path`: relative to `output-root`
- `degradation_recipe_id`
- `recipe_type`
- `severity`
- `degradation_seed`
- `degradation_tracking`
- `degradation_params`
- `degraded_audio_sha256`

`degradation_tracking` contains the item-level seed and compact per-operation summaries. `degradation_params` contains the complete sampled operation chain. The checksum JSONL contains `path` and `sha256` for every rendered WAV.

IT must retain the output WAV tree, output manifest, checksum manifest, exact config file, global seed, code commit, dependency environment, and job logs as one immutable run artifact.

## Optional Assets

Two effects need external assets:

- `mic`: ARIEL-compatible microphone transfer functions (`.npy`)
- `real`: compatible real RIR WAV files

The canonical config deliberately does not hard-code machine-specific paths. Before a release-scale run, the research/audio side must provide a release-approved config whose relevant operations contain mounted asset paths, for example:

```yaml
- id: single_mic
  recipe_type: single
  severity: ariel_random
  operations:
    - primitive: ariel
      variant: mic
      parameters:
        mic_ir_dir: /assets/openrestore/mic_irs
```

Mount assets read-only at those exact paths. Do not substitute local ARIEL paths such as `/home/.../ARIEL` in a hosted release. Asset licensing, content selection, and recipe parameters remain research-owned.

## Reproducibility and Acceptance Checks

Before accepting a run:

```bash
python3 -m unittest discover -s tests
openrestore-degrade validate-config --config <config>
```

After rendering, verify:

1. output-manifest row count equals the expected run count;
2. every `degraded_path` exists below `output-root`;
3. every SHA-256 in the output manifest and checksum manifest matches its WAV;
4. each degraded file is 44.1 kHz stereo and duration-matched;
5. the retained metadata records the intended seed, config, and code revision.

The repository currently has a verified local medium listening preview: 75 WAVs, three songs, and 25 effects. This is a smoke-test reference, not a release dataset.

## IT Responsibilities Now

- Provide a versioned Python/FFmpeg runtime.
- Provide read-only clean-audio and optional-asset mounts.
- Provide isolated per-run writable storage and sufficient temporary scratch space.
- Execute the supplied validation and render commands.
- Capture standard output/error, exit code, start/end time, host/job identity, code commit, dependency image/version, config digest, and global seed.
- Persist output audio, manifests, checksums, config, and logs atomically after a successful run.
- Schedule retries only for infrastructure failures. Do not silently retry or alter scientific parameters after an audio/pipeline failure.
- Separate infrastructure failures, such as quota, mount, worker, timeout, or network failures, from renderer/asset/config failures.
- Do not expose hidden evaluation audio or its manifests to public jobs.

## Known Gaps Before Release-Scale Hosting

- The renderer writes WAVs and JSONL, not degraded HDF5 shards or the canonical dataset `index.jsonl`.
- `paired`, `organic`, and `stress` configs exist but are not yet reconciled with the 25-effect registry.
- Full per-effect behavioral and deterministic test coverage is still incomplete.
- Microphone and real-RIR assets are not yet packaged as release-approved OpenRestore artifacts.
- The final parameter distributions still need structured listening calibration.
- A formal partition-merge and resume protocol has not yet been defined.

IT can host controlled single-effect runs now. Release-scale production should wait for the research-owned fixes above or run only an explicitly approved, versioned scope.

## Ownership Boundary

Research/audio owns:

- DSP code and dependencies
- recipes, effects, parameter ranges, and seeds
- asset selection and licensing
- metadata schema semantics
- validation criteria and release approval

IT owns:

- runtime image, job orchestration, storage, logs, retries, monitoring, access control, backups, and resource limits
- secure mounting of public, private, and optional asset storage
- reliable execution of the exact supplied command and retention of its artifacts

For project-level sequencing and future infrastructure tasks, see `OpenRestore_Split_Roadmap.md`. For the degradation taxonomy and benchmark semantics, see `OpenRestore.md`.
