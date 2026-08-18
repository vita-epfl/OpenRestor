# OpenRestore Guide

## What OpenRestore Is

OpenRestore is a reproducible benchmark for restoring degraded 30-second music clips. A system receives one degraded 44.1 kHz stereo WAV and produces one restored WAV with the same item ID, channel layout, sample rate, and duration. OpenRestore generates known degradations from clean music, so every scored item has a paired clean reference.

The benchmark reports separate diagnostic metrics. It does not currently define a combined score or leaderboard rank.

## What Is Public And What Is Private

| Artifact | Availability | Purpose |
| --- | --- | --- |
| Repository code, configurations, schemas, documentation, and tests | Public | Build datasets, render degradations, validate outputs, and score local results reproducibly. |
| Public release manifests, checksums, clean clips/shards, and paired OpenRestore-rendered degraded clips/shards | Downloadable with a benchmark release | Train on approved clean data and run consistent validation/public-test inference on the exact released degraded inputs. Each degraded manifest row joins one input to its clean reference and full degradation metadata. |
| SonicMaster clean originals | Obtain under the upstream release terms | Default main-track training source; held-out items also support validation and public test. |
| SDD and MUSDB18-HQ source audio | Obtain under their respective terms | Validation-only transfer and mixed-music checks. They are not main-track training or public-test data. |
| Degradation asset bundle: Poliphone microphone IRs and real RIR WAVs | Versioned release artifact, outside Git | Required only to render the corresponding microphone and real-room degradations. See [degradation_assets.md](degradation_assets.md). |
| Hidden evaluation audio, clean references, and hidden manifests | Organizer-only | Official evaluation. These files are never distributed to participants. |

FMA-Pop is not an OpenRestore music dataset. FADTK uses its built-in FMA-Pop reference statistics only for an optional perceptual diagnostic.

## Dataset Roles

- **Main-track training:** SonicMaster clean originals only.
- **Validation:** held-out SonicMaster clean audio, SDD, and MUSDB18-HQ mixture audio.
- **Public test:** held-out SonicMaster clean audio.
- **Hidden official evaluation:** a separate organizer-controlled music dataset.
- **Organic degradation material:** sound-effect/noise sources may supply degradation layers but never clean benchmark music.

SonicMaster's original degraded pairs are not reused. OpenRestore renders its own tracked degradations from the clean source audio.

## What Users Do

1. Install the repository and obtain only the source/release artifacts permitted for the track they are using.
2. Train a restoration system on the approved main-track data, or declare external data for a separate external-data track.
3. Use the supplied degraded manifest and WAVs for validation or public test inference. Each degradation row identifies the degraded audio and its recipe metadata.
4. Write a restored WAV for every input item and one `restoration_outputs.jsonl` row for every item.
5. Run local validation and scoring before a submission. CPU scoring works with the base installation; learned perceptual scoring is an optional GPU pack.

Users do not need to render their own degradations to train or evaluate from an official release: released validation and public-test packages contain the corresponding OpenRestore-rendered degraded WAVs, their clean references where the split is public, manifests, and checksums. The renderer is provided so research and organizers can reproduce, inspect, extend, and build approved dataset releases.

## Public Evaluation Code

OpenRestore publishes the validation and evaluation code. Users should run the supplied scorer rather than reimplement the metrics, so reports remain comparable across models. The interface is deliberately pipeline-agnostic: it does not import a model, training framework, checkpoint format, or inference library. Any system can participate by reading a degraded manifest, writing canonical restored WAVs, and emitting `restoration_outputs.jsonl`.

The CPU scorer is part of the base package and runs locally wherever the clean references are available. The GPU perceptual pack is optional. Both commands produce versioned, machine-readable reports as well as Markdown summaries, making them suitable for local experiments, training-validation hooks, and later organizer-side execution.

## Local Validation And Evaluation

The CPU scorer compares degraded-to-clean and restored-to-clean audio using waveform and spectral metrics plus degradation-aware diagnostics:

```bash
openrestore-score validate-restored \
  --degraded-manifest degraded/index.jsonl \
  --restored-manifest outputs/restoration_outputs.jsonl

openrestore-score score \
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

The v0.1 registry contains 25 single effects. Every render is deterministic from the item, recipe, and seed; the manifest stores the selected effect, sampled parameters, provenance, and output checksum.

```bash
openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml
openrestore-degrade list-recipes --config configs/degradations/single/v0_1.yaml
```

Use the renderer when reproducing or preparing an approved degradation release. Do not replace release assets or alter recipe configurations while comparing methods: that changes the benchmark input distribution.

## What A Submission Must Contain

For each supplied degraded item, provide a valid restored WAV and one row in `restoration_outputs.jsonl`:

```json
{"id":"<degraded-manifest id>","restored_audio_path":"relative/or/absolute/output.wav","restored_latent_shape":null,"duration_sec":null,"inference_steps":null,"batch_time_seconds":null,"timestamp":null}
```

`id` and `restored_audio_path` are required. The other fields are optional run metadata. Relative output paths resolve from the JSONL file. The scorer rejects duplicate or unknown IDs, missing items/files, non-finite audio, or sample-rate, channel, and duration mismatches.

For an official containerized submission, participants also provide the required submission manifest, inference code, weights, and an inference command. Organizers run that container on the hidden degraded inputs and retain the resulting restoration manifest and reports.

## Where To Go Next

- [Benchmark contract](benchmark_contract.md): task and ownership rules.
- [Dataset audits](dataset_audits.md): source-license and role decisions.
- [Degradation assets](degradation_assets.md): required RIR and microphone artifact bundle.
- [Phase 3 scoring](phase_3_scoring.md): restored-output validation and CPU/GPU scoring commands.
- [Phase reports](reports/): implementation detail and IT handoffs by project phase.
