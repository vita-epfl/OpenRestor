# OpenRestore Guide

## What OpenRestore Is

OpenRestore is a reproducible benchmark for restoring degraded 30-second music clips. A system receives one degraded 44.1 kHz stereo WAV and produces one restored WAV with the same item ID, channel layout, sample rate, and duration. OpenRestore generates known degradations from clean music, so every scored item has a paired clean reference.

The benchmark reports separate diagnostic metrics. It does not currently define a combined score or leaderboard rank.

## What Is Public And What Is Private

| Artifact | Availability | Purpose |
| --- | --- | --- |
| Repository code, configurations, schemas, documentation, and tests | Public | Build datasets, render degradations, and inspect the benchmark implementation. |
| Validation and evaluation package (`openrestor-score`), metric configurations, schemas, templates, and command documentation | Public and downloadable from the Git repository and versioned release archive | Validate restored WAVs and generate the same local CPU and optional GPU diagnostic reports used by OpenRestore. The interface is model-agnostic, so it can be called from any training or inference pipeline. |
| Optional perceptual-model cache: CLAP, FADTK LAION Music/FMA-Pop reference, and Audiobox Aesthetics | Downloaded by `openrestor-score setup-perceptual` into a user- or IT-selected cache directory | The setup script downloads the approved checkpoint assets through the model backends, then records package versions, FMA-Pop reference provenance, and a cache hash in `perceptual_cache_manifest.json`. The GPU scorer refuses an absent or modified cache. |
| Public release manifests, checksums, clean clips/shards, and paired OpenRestore-rendered degraded clips/shards | Downloadable with a benchmark release | Train on approved clean data and run consistent validation/public-test inference on the exact released degraded inputs. Each degraded manifest row joins one input to its clean reference and full degradation metadata. |
| SonicMaster clean originals | Obtain under the upstream release terms | Default main-track training source; held-out items also support validation and public test. |
| SDD and MUSDB18-HQ source audio | Obtain under their respective terms | Separately reported public transfer/local-evaluation sets. They are not main-track training or in-distribution public-test data. |
| Degradation asset bundle: Poliphone microphone IRs and real RIR WAVs | Versioned release artifact, outside Git | Required only to render the corresponding microphone and real-room degradations. See [degradation_assets.md](degradation_assets.md). |
| Hidden evaluation audio, clean references, and hidden manifests | Organizer-only | Official evaluation. These files are never distributed to participants. |

FMA-Pop is not an OpenRestore music dataset. FADTK uses its built-in FMA-Pop reference statistics only for an optional perceptual diagnostic.

## Dataset Roles

- **Main-track training:** SonicMaster clean originals only.
- **Validation/model selection:** held-out SonicMaster clean audio only.
- **Public in-distribution test:** held-out SonicMaster clean audio.
- **Public transfer/local evaluation:** SDD and MUSDB18-HQ mixture audio, reported separately by dataset.
- **Hidden official evaluation:** a separate organizer-controlled music dataset.
- **Organic degradation material:** sound-effect/noise sources may supply degradation layers but never clean benchmark music.

SonicMaster's original degraded pairs are not reused. OpenRestore renders its own tracked degradations from the clean source audio.

## What Users Do

1. Install the repository and obtain only the source/release artifacts permitted for the track they are using.
2. Train a restoration system on the approved main-track data, or declare external data for a separate external-data track.
3. Use the supplied degraded manifest and WAVs for validation, public-test, or transfer-evaluation inference. Each degradation row identifies the degraded audio and its recipe metadata.
4. Write a restored WAV for every input item and one `restoration_outputs.jsonl` row for every item.
5. Run local validation and scoring before a submission. CPU scoring works with the base installation; learned perceptual scoring is an optional GPU pack.

Users do not need to render their own degradations to train or evaluate from an official release: released validation, public-test, and transfer-evaluation packages contain the corresponding OpenRestore-rendered degraded WAVs, their clean references where the split is public, manifests, and checksums. The renderer is provided so research and organizers can reproduce, inspect, extend, and build approved dataset releases.

## Public Evaluation Code

OpenRestore publishes the validation and evaluation scripts as the downloadable `openrestor-score` package, including metric configurations, schemas, templates, and documentation. Users should run the supplied scorer rather than reimplement the metrics, so reports remain comparable across models. The interface is deliberately pipeline-agnostic: it does not import a model, training framework, checkpoint format, or inference library. Any system can participate by reading a degraded manifest, writing canonical restored WAVs, and emitting `restoration_outputs.jsonl`.

The CPU scorer is part of the base package and runs locally wherever the clean references are available. The GPU perceptual pack is optional: install it, then run `openrestor-score setup-perceptual` once to download and verify the approved CLAP, FADTK, and Audiobox model cache. Both commands produce versioned, machine-readable reports as well as Markdown summaries, making them suitable for local experiments, training-validation hooks, and later organizer-side execution.

## Local Validation And Evaluation

The CPU scorer compares degraded-to-clean and restored-to-clean audio using waveform and spectral metrics plus degradation-aware diagnostics. For `reverb_*` and `distant_mic_capture`, it also reports paired residual-room diagnostics: `rt60_s`, `drr_db`, and `late_tail_db`, estimated from the clean-to-evaluated transfer rather than from music in isolation:

```bash
openrestor-score validate-restored \
  --degraded-manifest degraded/index.jsonl \
  --restored-manifest outputs/restoration_outputs.jsonl

openrestor-score score \
  --degraded-manifest degraded/index.jsonl \
  --degraded-root degraded/audio \
  --clean-root clean/audio \
  --restored-manifest outputs/restoration_outputs.jsonl \
  --config configs/evaluation/metrics.yaml \
  --output-dir outputs/cpu_scores
```

This writes `scores.json`, `per_item_scores.jsonl`, `restoration_metadata.jsonl`, `report.md`, and `failures.json`. `restoration_metadata.jsonl` is created by the trusted scorer after joining participant output with benchmark-owned clean/degraded provenance.

The optional GPU command adds CLAP similarity, FADTK against the local clean distribution and FADTK's built-in FMA-Pop reference, plus Audiobox CE/CU/PC/PQ. See [phase_3_scoring.md](phase_3_scoring.md) for installation and cache setup.

## Degradations

The v0.1 registry contains 24 canonical degradation classes. Every render is deterministic from the item, recipe, and seed; the manifest stores the selected effect, sampled parameters, provenance, and output checksum.

```bash
openrestor-degrade validate-config --config configs/degradations/single/v0_1.yaml
openrestor-degrade list-recipes --config configs/degradations/single/v0_1.yaml
```

Use the renderer when reproducing or preparing an approved degradation release. Do not replace release assets or alter recipe configurations while comparing methods: that changes the benchmark input distribution.

## Local Output Contract

For each supplied degraded item, provide a valid restored WAV and one row in `restoration_outputs.jsonl`:

```json
{"id":"<degraded-manifest id>","restored_audio_path":"relative/or/absolute/output.wav","restored_latent_shape":null,"duration_sec":null,"inference_steps":null,"batch_time_seconds":null,"timestamp":null}
```

`id` and `restored_audio_path` are required. The other fields are optional run metadata. Relative output paths resolve from the JSONL file. The scorer rejects duplicate or unknown IDs, missing items/files, non-finite audio, or sample-rate, channel, and duration mismatches.

## Official Hidden Evaluation

Official hidden evaluation is planned for Phase 5. Participants do **not** submit restored hidden-evaluation audio. They submit an immutable OCI/Docker image by digest, its build recipe (`Dockerfile` or equivalent), a submission manifest, model weights included in the image or fetched during an approved build, and an inference command. The organizers run that image themselves against the hidden degraded split.

The Phase 5 container interface will use these fixed in-container locations and environment variables:

| Container resource | Value | Access |
| --- | --- | --- |
| Hidden degraded manifest | `/input/degraded/index.jsonl` via `OPENRESTORE_INPUT_MANIFEST` | Read-only |
| Hidden degraded WAV root | `/input/degraded/audio` via `OPENRESTORE_INPUT_ROOT` | Read-only |
| Restored WAV directory | `/output/audio` via `OPENRESTORE_OUTPUT_ROOT` | Write-only for the submission |
| Required restoration manifest | `/output/restoration_outputs.jsonl` via `OPENRESTORE_OUTPUT_MANIFEST` | Write-only for the submission |

The declared `inference_command` must read those environment variables, restore every input item, and write canonical 44.1 kHz stereo WAVs plus the required restoration manifest. This keeps hidden-set paths out of participant code: the organizer supplies the same fixed mounts and variables to every container. The clean references are never mounted into the participant container.

The organizer evaluation procedure is:

1. Validate the submission manifest, immutable image digest, track declaration, and container interface on public fixture audio.
2. Run the declared inference command with network disabled, hidden degraded inputs mounted read-only, an empty output mount, and enforced time, memory, disk, and GPU limits.
3. Run `openrestor-score validate-restored` on the generated output. Duplicate IDs, missing files, invalid WAVs, mismatched canonical audio, or incomplete manifests fail the run rather than being silently skipped.
4. Join valid output with the private clean references outside the submission container, then run the public CPU scorer and the selected organizer perceptual pack.
5. Retain the image digest, submission manifest, command, resource configuration, logs, checksums, trusted `restoration_metadata.jsonl`, and metric reports. Publish only the approved scores and summaries, never hidden audio or private reference paths.

OpenRestore will provide a submission-container template and an organizer dry-run command before this track opens. The exact schema and execution wrapper are Phase 5 work; the mount and output contract above is the interface they must implement.

## Where To Go Next

- [Benchmark contract](benchmark_contract.md): task and ownership rules.
- [Dataset audits](dataset_audits.md): source-license and role decisions.
- [Degradation assets](degradation_assets.md): required RIR and microphone artifact bundle.
- [Phase 3 scoring](phase_3_scoring.md): restored-output validation and CPU/GPU scoring commands.
- [Phase reports](reports/): implementation detail and IT handoffs by project phase.
