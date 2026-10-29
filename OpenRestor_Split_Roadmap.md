# OpenRestor Split Implementation Roadmap

This roadmap splits the OpenRestor implementation into the runnable research/audio pipeline and the hosted Information Technology ("IT") platform around it. It is written for a small collaborative team where the research engineer owns what will be hosted: the scientific validity, audio processing, dataset generation, degradation code, metric code, baselines, schemas, command-line tools, and reproducible local pipeline. IT/software engineers own how that runnable pipeline is hosted, secured, deployed, monitored, scaled, stored, and exposed to users.

OpenRestor is a benchmark rather than a single restoration model. It has three evaluation tracks, built and released in order:

| Track | What it measures | Degradations per item | Clean reference |
| --- | --- | --- | --- |
| **Diagnostic** | capability per degradation type, attributable to one cause | exactly one, from the 21 canonical classes | yes |
| **Blind-Synthetic** | blind restoration when the degradation is unknown and may be compound | 0 to 3, random type, order and intensity | yes |
| **Blind-Real** | generalisation to genuinely degraded recordings | unknown, naturally occurring | **no** |

The Diagnostic track carries the original contract: each item is a 30-second 44.1 kHz musical clip with one degraded input, one clean reference, deterministic degradation metadata, and a portable manifest row. Main-track training uses SonicMaster clean originals only. Validation/model selection uses held-out SonicMaster clean audio. The source-separated SonicMaster public test is the in-distribution test. The Song Describer Dataset ("SDD") and Music Demixing Dataset 2018 High Quality ("MUSDB18-HQ") mixture audio are separately reported local-only transfer evaluations for users who lawfully hold the sources. Official leaderboard scoring uses a hidden organizer-only evaluation set.

## Benchmark Architecture

OpenRestor plans four evaluation sets. Three are paired against a clean reference and one is
not; the intended public sets are **not yet cleared for audio upload**.

| Set | Degradations | Clean reference | Splits | Availability |
| --- | --- | --- | --- | --- |
| **Diagnostic** | exactly one of 21 synthetic classes | yes | train / validation / test | private; zero audio in initial release |
| **Blind-Synthetic** | 0 to 3 synthetic, random type, order and intensity | yes | train / validation / test | private; zero audio in initial release |
| **Blind-Real Public** | none added; real recordings degraded by their own history | **no** | **test only** | candidate; provenance approval pending |
| **Official Hidden** | secret OpenRestor degradations on contract-cleared concert masters | yes, organizer-only | evaluation only | **organizer-only; access agreement pending** |

Blind training happens on Blind-Synthetic, which has the splits and clean targets for it.
Blind-Real Public is intended to let users test naturally degraded material locally after
provenance clearance. Official Hidden requires an agreement for private clean concert masters
before secret paired leaderboard scoring can operate.

Current state, 2026-10-19. **Diagnostic** is rendered: 648/648 shards, 542,829 paired examples, zero failures, and the private release validates end to end (`status: complete`). **Blind-Synthetic** is rendered: 60/60 slices, 25,849 examples, 7.95% deliberately left clean. **Blind-Real Public** is an internal pack: 113 scored items, 210 clips, 70 minutes, plus 172 clean-control clips; uploader provenance review is pending. **Official Hidden** has a Montreux Jazz Festival candidate source but no audio may be ingested before a rights agreement.

Of the two synthetic corpora, 96.7% comes from SonicMaster, but the completed Jamendo audit
found only 856 current CC BY records and left 8,856 IDs unresolved. No synthetic audio is
cleared until written clarification establishes broader rights or a much smaller per-track
subset is approved and repackaged. The project was renamed from OpenRestore to OpenRestor on
2026-10-15; two frozen identifiers keep the former spelling on purpose.

Blind-Real Public remains unpaired and uses its separate no-reference protocol. Official
Hidden is paired and uses organizer-side full-reference metrics.

A handoff note for whoever picks this up is in `docs/reports/handoff_2026-10-16.md`: current state, the identifiers that must not be renamed, the licence findings, and the failure mode this project keeps hitting.

### What remains, by release scope

1. **First tools/RIR release:** complete contributor, ownership, dependency and funding
   inventory; get supervisor/TTO approval for the exact EPFL academic licence, manifests,
   Apache-adapted code boundary and distribution mode. Keep the 14 RIR notices/hashes and
   Git commit/tag; no public upload before approval.
2. **Blind-Real extension:** review uploader provenance per clip, record independent
   evidence and approval, then regenerate its pack. This is independent of Jamendo.
3. **Full synthetic benchmark later:** resolve SonicMaster's per-track rights with written
   clarification or direct artist/source evidence before approving any audio. The
   25,000-ID API snapshot alone does not authorize redistribution. SDD/MUSDB remain local.
4. **Scientific quality:** run baselines (Phase 4) and ratify the Blind-Real metrics at
   n=210. These are needed for benchmark claims but do not block the tools/RIR candidate.
5. **Operations and hidden evaluation:** follow up with RCP Dataset as a Service, settle
   storage/access, and obtain a written agreement before ingesting any Montreux masters.

### Deliberately not prerequisites

These are secondary analyses, not gates on building the datasets:

- Mass human QA listening.
- Distribution matching against Blind-Synthetic with MAD, MERT or another distributional measure.
- Any listening study. The benchmark must not develop a hard dependency on one.

## Ownership Summary

| Area | Research/audio engineer owns | IT/software engineers own | Shared decision points |
| --- | --- | --- | --- |
| Benchmark definition | Task scope, audio format, degradation taxonomy, metric interpretation, source acceptance criteria, and runnable validation rules | Host the agreed contract in services, documentation, submission forms, and automated checks | Final benchmark contract and release acceptance criteria |
| Dataset curation and generation | Audits, split policy, ingestion code, segmentation code, quality checks, manifests, and local dataset build command | Hosted storage, access control, backups, mirrors, data-transfer tooling, and private evaluation storage | Dataset versions, licensing status, public vs private release boundaries |
| Degradations | DSP algorithms, primitive and recipe definitions, severity bands, deterministic runner, metadata, and reproducibility tests | Hosted batch execution, compute scheduling, logs, artifact storage, and monitoring around the runner | Config format, seed policy, metadata written per item |
| Metrics and reports | Metric implementations, AAE descriptors, score schemas, aggregation logic, report generator, and local scoring command | Hosted scoring jobs, result storage, cache management, report publishing, and leaderboard data serving | Primary score, per-family reports, failure handling |
| Baselines | Baseline methods, training/inference code, example runs, and runnable baseline containers or scripts | Container registry, artifact hosting, scheduled reruns, and public baseline result publication | Baseline release gates and score sanity checks |
| Submission evaluation | Local evaluator interface, output validity rules, submission manifest schema, and example participant container | Hosted container runner, sandboxing, timeouts, credentials, logs, private outputs, and operational security | Inference interface and invalid-output policy |
| Release | Dataset card content, benchmark report, scientific claims, release artifacts, and reproducible release command | Website, static leaderboard, DOI packaging, CI/CD, mirrors, storage quotas, and uptime | Public release checklist |

## Handoff Rule

The research/audio deliverable is a runnable local pipeline: documented commands, configs, schemas, tests, example data, and optional containers that can build datasets, generate degradations, run baselines, score outputs, and produce release artifacts. IT should not be responsible for inventing or rewriting the scientific/audio pipeline. IT is responsible for hosting that pipeline: storage, credentials, runners, scheduling, monitoring, deployment, backups, public pages, and private evaluation security.

## Phase 0 - Project Contracts And Repository Skeleton

Goal: freeze the minimum viable benchmark contract before implementation becomes fragmented.

### Research/audio engineer tasks

- [x] Finalize the benchmark task: one degraded mixed musical clip in, one restored clip out.
- [x] Confirm canonical audio settings:
  - [x] 30-second clips.
  - [x] 44.1 kHz sample rate.
  - [x] Stereo preferred, with explicit mono handling rules.
  - [x] Output must preserve duration, sample rate, channel count, and item identifier ("ID").
- [x] Freeze the v0.1 primitive degradation set and initial randomized severity-band policy.
- [x] Decide which metrics are required for the first release and which stay experimental.
- [x] Define the scientific meaning of the main leaderboard track and external-data track.
- [x] Create the Python package/repository skeleton that IT will later host:
  - [x] `openrestor/data`
  - [x] `openrestor/degradations`
  - [x] `openrestor/metrics`
  - [x] `openrestor/evaluation`
  - [x] `openrestor/submissions`
  - [x] `openrestor/leaderboard`
  - [x] `configs`
  - [x] `schemas`
  - [x] `scripts`
  - [x] `tests`
  - [x] `docker`
  - [x] `site`
- [x] Add local packaging and developer tooling for the runnable pipeline:
  - [x] `pyproject.toml`
  - [x] formatter/linter configuration
  - [x] test runner
  - [x] basic CI configuration that IT can wire into hosted CI/CD
- [x] Implement JSON Schema validation harnesses for:
  - [x] `index.jsonl`
  - [x] degradation tracking
  - [x] submission manifests
  - [x] scores
  - [x] leaderboard entries

### IT/software engineer tasks

- [ ] Confirm the target hosting environment for the runnable pipeline:
  - [ ] internal server, Kubernetes, GitLab runner, cloud runner, or another agreed platform
  - [ ] CPU/GPU availability
  - [ ] storage quotas
  - [ ] expected job duration limits
- [ ] Define deployment requirements for the pipeline package:
  - [ ] container registry location
  - [ ] secrets and credential handling
  - [ ] environment variables
  - [ ] logs and monitoring expectations
  - [ ] backup policy
- [ ] Define how IT will run the delivered command-line tools in hosted CI/CD and scheduled jobs.

### Shared deliverables

- [x] Versioned benchmark contract document.
- [x] Initial repository layout.
- [x] Minimal schema files and validation commands.
- [x] One tiny fixture dataset used by tests.

## Phase 1 - Dataset Audit, Ingestion, And Splitting

Goal: build a trustworthy data pipeline before generating large degraded releases.

### Research/audio engineer tasks

- [x] Perform source audits for each candidate dataset:
  - [x] SonicMaster clean originals as the only main-track training source and as the public test source through source-separated held-out items.
  - [x] SDD as an optional local-only transfer-evaluation source.
  - [x] Music Demixing Dataset 2018 High Quality ("MUSDB18-HQ") mixtures as an optional local-only academic transfer-evaluation source.
  - [x] Secret custom dataset as hidden evaluation source.
- [x] For each dataset, produce a decision record:
  - [x] dataset name and version
  - [x] access Uniform Resource Locator ("URL")
  - [x] intended OpenRestor role
  - [x] license terms
  - [x] redistribution status
  - [x] quality notes
- [x] Define SonicMaster source-level split rules so no recording leaks across train/validation/public test.
- [x] Define SDD and MUSDB18-HQ local transfer selection rules so these items remain separate from main-track training, public artifacts and SonicMaster model-selection validation.
- [x] Define deterministic 30-second segmentation rules:
  - [x] window start policy
  - [x] partial segment policy
  - [x] silence rejection
  - [x] loudness/headroom normalization
  - [x] channel conversion policy
- [x] Run structured listening review on sampled clips and document failure modes for SonicMaster, SDD, and MUSDB18-HQ.
- [x] Implement the runnable dataset pipeline that IT will host:
  - [x] dataset ingestion commands
  - [x] deterministic splitting command
  - [x] 30-second segmentation command
  - [x] manifest writer
  - [x] shard writer/reader
  - [x] checksum generation and verification
  - [x] automated audio quality checks
  - [x] dataset statistics report command

### IT/software engineer tasks

- [ ] Provide hosted storage locations for public, private, release, and temporary dataset artifacts.
- [ ] Implement access control for private evaluation data and restricted source datasets.
- [ ] Provide transfer/sync tooling so the runnable dataset pipeline can read inputs and write outputs in hosted storage.
- [ ] Configure backups, retention, quotas, and checksums for hosted dataset artifacts.
- [ ] Run the research-owned dataset pipeline in the hosted environment and report infrastructure failures separately from pipeline failures.

### Shared deliverables

- [x] `configs/datasets/sonicmaster_clean.yaml`
- [x] `configs/datasets/sdd_transfer.yaml`
- [x] `configs/datasets/musdb18_hq_transfer.yaml`
- [x] dataset audit records
- [x] SonicMaster public train/validation/test split manifests
- [x] SDD and MUSDB18-HQ local transfer manifests
- [x] private evaluation manifest template and Montreux Jazz candidate template
- [x] reproducible miniature dataset build
- [x] dataset statistics report

## Phase 2 - Degradation Pipeline (Diagnostic Track)

Goal: generate deterministic, realistic degraded musical audio with complete metadata, with exactly one degradation per item so every failure is attributable to one cause.

### Current v0.1 Contract

OpenRestor is now effect-first. The active single-effect registry has exactly 21 canonical classes. Categories remain metadata and reporting groups, not recipe IDs. Every output has one explicitly selected effect; the runner never samples effect choices or combines effects. Normal dataset recipes use deterministic randomized parameters within that selected effect; medium_preview is a separate, fixed-central listening profile.

### Research/audio engineer tasks

- [x] Define and document the 21-class v0.1 registry, including origin, group, relevance, status, and benchmark role.
- [x] Port the ARIEL/SonicMaster single effects, folded into the canonical classes. Legacy names such as `comp`, `punch`, `xband`, `bright`, `dark`, `airy`, `boom`, `clarity`, `mud`, `warm`, `vocal` and `stereo` remain callable aliases for reproducing historical manifests but are not benchmark classes. `volume` is removed, and `telephone_band` and `transcode_chain` must not be reintroduced as classes.
- [x] Implement the OpenRestor additions: noise, hum, clicks_crackle, dropouts_glitches, neural_codec, channel_damage, pitch_speed_instability, distant_mic_capture, and the asset-free smartphone_capture that replaced the measured-IR `mic` class.
- [x] Keep simulated room behavior local through `pyroomacoustics`; support optional ARIEL-compatible microphone-transfer-function and real-RIR assets without requiring them for the core test suite.
- [x] Implement deterministic per-item and per-operation seeds, with sampled values recorded in output metadata.
- [x] Implement full operation tracking: recipe ID, severity label, seed, operation ID/variant, sampled parameters, output path, and SHA-256 checksum.
- [x] Implement the local `openrestor-degrade` command:
  - [x] YAML config loading and validation
  - [x] recipe listing
  - [x] deterministic batch WAV rendering
  - [x] output JSONL manifest and per-file checksums
  - [x] local progress logging
  - [x] deterministic HDF5 shard packaging and shard-index writing
- [x] Add generated stereo fixtures and deterministic pipeline tests.
- [x] Run medium listening previews over the active registry with verified manifest paths and checksums.
- [x] Perform an initial listening review and tune the medium hum profile to an audible 50 Hz signal with harmonics.
- [x] Add fixed minimum/maximum listening-boundary recipes in `configs/degradations/review_boundaries/`; normal datasets still sample deterministically within approved ranges.

### Remaining research/audio work

- [x] Add execution/metadata/determinism coverage for all 21 active classes. Tests execute every non-asset class twice with fixed seeds; the `real` missing-asset path is tested explicitly.
- [x] Calibrate normal dataset parameter distributions through the completed listening review. No real degraded-music corpus will be integrated for v0.1.
- [x] Create and ship the release-asset contract for the reviewed 14 real RIR WAVs (the 20 Poliphone microphone IRs were retired with the `mic` class). The bundle is tracked at `assets/degradations/v0_1/`; IT checks out the release revision and verifies it using `docs/degradation_assets.md` and `docs/degradation_assets_v0_1.sha256`.
- [x] Make the Git tag and commit the canonical RIR artifact. A standalone `build/release_assets/openrestor-degradation-assets-v0_1.tar.gz` is optional transport for a host that requires one file and is generated by `scripts/package_degradation_assets.sh`; it is not a publication gate.
- [x] Add degraded HDF5 shard writing and a release index that points each row at `degraded_audio_shard` and `degraded_audio_shard_index`. The WAV manifest remains the rendering provenance; the shard index is the release-facing reader contract.
- [x] Build the v0.1 paired degradation sets for SonicMaster plus local-only SDD and MUSDB18-HQ transfer evaluation. The rendered private corpus is frozen; publication is a separate licence-filtered view and never includes SDD/MUSDB audio.
- [ ] Freeze a release manifest for each paired public split. It must include clean and degraded relative paths or shard locations, recipe ID, sampled degradation metadata, dataset/split labels, audio properties, and SHA-256 checksums.
- [ ] Package the public paired release as canonical WAVs and/or documented HDF5 shards with portable indexes, checksums, the exact degradation configuration, asset-bundle version, Git revision, and release notes. Do not publish an artifact until source redistribution terms are confirmed.
- [x] Define and test failure handling for unavailable assets, FFmpeg failures, and oversized room simulations. Asset and FFmpeg errors are actionable; distant-room `max_order` is bounded to 0-10 and invalid geometry is rejected before simulation.

### Checkable evidence

- [x] `python -m unittest tests.test_degradations`: 12 tests passing, including all-class execution, HDF5, CLI shard, and failure-path coverage.
- [x] validate-config passes for the active single-effect configuration.
- [x] Every stored SHA-256 checksum in the listening previews matches its file.

### IT/software engineer tasks

- [ ] Provide hosted compute for running the research-owned degradation command at release scale.
- [ ] Configure job scheduling, retries, logs, and monitoring around degradation runs.
- [ ] Store degraded shards, manifests, checksums, and logs in agreed hosted artifact locations.
- [ ] Host versioned public paired-degradation releases for download: train, validation, and public-test degraded audio/shards where source terms permit, plus their clean/degraded manifests, portable shard indexes, checksums, configs, and release notes.
- [ ] Publish stable download URLs and a dataset/release record for every public artifact; preserve prior versions and make the matching code/config revision discoverable.
- [ ] Keep hidden-evaluation degraded sets, clean references, manifests, and reports in organizer-only storage with no participant download path.
- [ ] Provide enough parallel execution capacity for large dataset builds without changing the degradation code.
- [ ] Report infrastructure, quota, and timeout failures separately from scientific/pipeline failures.

### Shared deliverables

- [x] `configs/degradations/single/v0_1.yaml` with the 21-class single registry.
- [x] deterministic degradation Command-Line Interface ("CLI").
- [x] first local listening previews across the 21 canonical classes, including the validated `smartphone_capture` endpoints.
- [x] first local shard-backed degraded miniature candidate with a portable `index.jsonl`. It remains a candidate until ranges and approved external assets are frozen.
- [ ] v0.1 public paired degradation release for every approved public split: downloadable degraded audio/shards, clean/degraded manifests, portable indexes, checksums, recipe config, asset-bundle version, Git revision, and release notes.
- [ ] hosted private paired degradation release for the hidden evaluation split, with the same provenance but no public download path.

## Phase 2B - Blind-Synthetic Benchmark

Goal: measure blind restoration, where the system is not told what went wrong and more than one thing may have.

Implemented and stable; its logic is not to be changed. Chains carry 0 to 3 degradations with continuous intensities, about 8% of items are left clean as a no-op control, and degradation metadata is published for train and validation but withheld at inference on test.

This is a separate dataset with its own train, validation and test splits. It does not replace the Diagnostic track and does not change the 21 canonical classes.

### Research/audio engineer tasks

- [x] Define the compound sampling policy, in `configs/degradations/blind_synthetic/v0_1.yaml`:
  - [x] a random number of degradations per item, 0 to 3, weighted `{0: 0.08, 1: 0.32, 2: 0.34, 3: 0.26}`. Realised: 2,054 / 8,302 / 8,698 / 6,795, so genuinely variable
  - [x] random types drawn from the 21 canonical classes
  - [x] random application order
  - [x] random intensities, `strong_random` per class with every sampled value recorded
- [x] Define a small compatibility matrix: `exclusive_groups` for room, codec, overload and stereo, plus `incompatible_pairs`. Pairwise rules, not predefined recipes.
- [x] Reserve a percentage of **clean, undegraded** items. Realised 7.95% overall and **10.6% of the test split**; clean items also occur in train and validation, which is harmless and lets a model learn not to over-process.
- [x] Implement the compound runner with deterministic per-item seeds, recording the full ordered chain. `BLIND_RECIPE_ID` is a constant so operation seeds do not shift.
- [x] Define the metadata exposure policy: `withhold_degradation_metadata` strips the chain while keeping the id, the degraded path and the audio properties, so an item can still be restored and scored.
- [x] Build the splits from the same frozen SonicMaster source assignment. Realised: 23,500 train, 500 validation, 1,000 test, plus the two transfer sets.
- [x] Freeze a release manifest with clean and degraded paths, the ordered chain, seeds, audio properties and checksums. 25,849 rows, `checksums.jsonl` alongside.

### IT/software engineer tasks

- [x] Run the compound degradation build at release scale. 60/60 slices in 0.57 h, 25,849 rows merged, zero failures.
- [ ] Publish the train/validation/test release, and serve test items **without** their degradation metadata. Blocked on written clarification of the SonicMaster collection label or approval and repackaging of a filtered subset.

### Shared deliverables

- [x] compound degradation configuration and compatibility matrix
- [x] Blind-Synthetic train/validation/test release with manifests and checksums
- [x] documented metadata-exposure boundary between train/validation and test

## Publication of the paired corpus

The frozen v0.1 corpus is 542,829 examples. SonicMaster makes up 96.7%, but the completed
Jamendo audit contradicts its collection label and publication is blocked pending written
clarification or approval of a filtered subset:

| source | examples | terms | published |
| --- | --- | --- | --- |
| SonicMaster clean | 525,000 | collection labelled CC BY 2.0; current Jamendo audit found only 856 CC BY IDs | **no, pending clarification** |
| Song Describer (transfer) | 14,805 | per track: 209 NoDerivatives, 301 NonCommercial, 195 unrestricted | no |
| MUSDB18-HQ (transfer) | 3,024 | academic use only | no |

Both sides of a pair follow the source licence, because the clean side is also a derivative:
a 30-second excerpt with loudness normalisation. NoDerivatives bars both sides.

**Blind-Synthetic draws on the same three sources** — 144 MUSDB18-HQ, 705 Song Describer,
25,000 SonicMaster — so the same decisions apply to it. A strict current CC BY-only filter
would retain only 17,976 Diagnostic examples and 856 Blind-Synthetic examples. Written
confirmation from AMAAI/Jamendo could establish broader rights than the current API snapshot.

The frozen release is never edited to achieve this — its plan records a SHA-256 of its own
config. `scripts/build_publication_subset.py` derives both rights profiles from a private
per-media register; approved items would be reconstructed into new source-filtered shards,
indexes and hashes. The initial candidate contains zero Diagnostic/Blind-Synthetic audio.
The rendered SonicMaster Diagnostic inventory is 626 partitions, 2.2 TB of
degraded audio and 124 GB of clean clips, but it remains blocked pending the licence decision.
The 77 GB of degraded and 4.2 GB of clean SDD/MUSDB material stay local-only for transfer
evaluation.

- [x] Audit all 25,000 SonicMaster/Jamendo `source_id` values. The current API results
      contradict the collection-level CC BY 2.0 label; evidence is recorded in
      `docs/reports/sonicmaster_jamendo_licence_audit_2026-10-16.md`.
- [ ] Obtain written confirmation that covers the underlying audio, commercial redistribution
      and adaptations, or approve and package a much smaller per-track subset.
- [x] Make both per-media publication profiles fail closed without touching the frozen release.
- [x] Apply the same policy to Blind-Synthetic, which draws on the same three sources.
- [ ] Generate the per-track attribution file from the accepted SonicMaster/Jamendo audit.
- [ ] Clear `degradation_asset_provenance_approval`: the RIR bundle is Public Domain and
      CC BY only, documented, checksummed and now in the repository.
- [ ] Clear `source_redistribution_license_approval` for the SonicMaster component only.

### Hosting

The three published sets go on EPFL's **DASH** (Dataset sharing as a service): an S3 bucket
created by the unit through `portal-xaas.epfl.ch`, then a read-only proxy link from RCP at
`https://datasets.epfl.ch/<name>`. The service is free; the S3 storage is billed under the
u1 model, and the volume is the open question — roughly 2.4 TB if both synthetic corpora
ship as audio. Blind-Real Public is 678 MB and ready now.

The audio ships rather than a generation recipe. The degradation tools exist so users can
reproduce degradations on **their own** audio, not so they have to build the datasets we
distribute.

## Phase 2C - Blind-Real Public

Goal: let a system be evaluated locally on real recordings degraded by their own history.

**Test only.** No clean reference, no degradation label, and **no synthetic degradation is ever added**. There is no train or validation split: blind training happens on Blind-Synthetic, and this set exists to measure generalisation to real material.

### Why there is no train split

The completed 2,320-shard IAMD scan settles it. The permissive, high-confidence live material simply is not there:

| | |
| --- | --- |
| Segments scanned | 4,246,139 |
| CC0 + CC BY segments | 579,826 |
| Distinct permissive identifiers | 18,758 |
| **Distinct identifiers with high-confidence live metadata** | **131** |
| Clips at a cap of 2 per identifier | **about 262** |

131 source items cannot carry a train, validation and test split. **The filter is not to be loosened to inflate the set**: admitting `weak_keyword` would reach 567 identifiers and admitting CC BY-SA as well would reach 972, but the evidence behind those is a bare "live" in free text, which this scan showed carries almost no signal.

### Selection policy

- Source: high-confidence IAMD candidates, resolved through `identifier` to the Internet Archive item, from which the best available original is downloaded. IAMD's own 320 kbps MP3 segments are never used.
- Licences: **CC0 and CC BY only** for now. BY-SA is not admitted.
- Confidence: **`structured` and `strong_phrase` only**. `weak_keyword` is excluded.
- Cap: at most **2 clips per `identifier`**, and at most **3 identifiers per artist group**. Identifiers are grouped whenever they share any credited name, because source-disjointness by identifier does not stop one act dominating: before the cap, Daniel Romano's Outfit held 14 of 113 items across three spellings of the credit, and Ambient Samurai 14 more.
- Two excerpts of one item come from **two different tracks**. Two windows of one song sound alike however far apart they are cut, so the variety has to come from the track, not the offset.

### Realised set

| | |
| --- | --- |
| Clips | **210** of 20 seconds, 70 minutes total |
| Distinct Internet Archive items | **113**, at most 2 clips each |
| Distinct artists | **104** artist groups, at most 3 items each |
| Confidence | 114 `strong_phrase`, 78 `none`, 12 `weak_keyword`, 6 `structured` |
| Licences | 208 CC BY, 2 CC0 |
| Source codecs | 161 MP3, 27 FLAC, 22 PCM |
| Clean control, not scored | **92** items, 172 clips |

The `none` tier is not a defect: round two dropped the live-metadata requirement, so most of
its items carry no live evidence at all. The clean control set holds the items a listener
judged to need no restoration; it is excluded from scoring and exists so a system that
damages already-good audio cannot hide it.

**The set is not lossless.** For 87 of the 113 items the uploader's own original is an MP3, some at 128 kbps. Fetching that original is still right, since IAMD's 320 kbps segment is a re-encode of the same file, but no release text may imply otherwise.

### Processing choices

**No loudness normalisation.** Every other set here is normalised, because there the degradation is applied on top of a controlled clean signal. In this set the degradation *is* the recording's history and level problems are part of it, so normalising would quietly repair one of the things a system is meant to handle. Clips record `normalization: none`.

**Resampled to 44.1 kHz stereo regardless.** That is format canonicalisation, not repair: a system must return audio in the format it received, so inputs have to be uniform. Each clip records its source sample rate, channel count and codec.

**Excerpts of one item come from different tracks.** Drawing both windows independently from one recording produced overlapping pairs, one of them a second apart; drawing them from disjoint bands of the same track fixed the overlap but not the real problem, which was two excerpts of the same song. They now come from two different tracks of the item, and an item offering only one usable track yields one excerpt.

### Wording discipline

The retained items are **distinct Internet Archive source items with high-confidence live-recording metadata**. They are *not* verified concerts: nothing in the pipeline listened to them or confirmed the event. Release text, dataset cards and papers must use the longer phrasing.

Every item keeps its provenance and its live evidence: the confidence level, and the field or phrase that triggered it.

### Evaluation aggregation

Scores aggregate in three stages: **clip, then `identifier`, then dataset.** Without the middle stage a source item contributing two excerpts would count twice as much as one contributing a single excerpt, which would let a handful of items steer the result.

### Curation pipeline

- [x] 1. Scan metadata only from the IAMD parquet shards. **Complete: 2,320/2,320 shards, 4,246,139 rows, zero failures.**
- [x] 2. Filter permissive licences.
- [x] 3. Detect live candidates on word boundaries, graded by confidence.
- [x] 4. Deduplicate by Internet Archive identifier.
- [x] 5. Cap clips per identifier.
- [x] 6. Rank candidates automatically.
- [x] 7. Frozen-list writer with per-item provenance.
- [x] 8. Build and freeze the Blind-Real Public manifest from the high-confidence identifiers, reproducibly via `scripts/build_blind_real_public.py`. **After the AcoustID screen, the per-artist cap, the desk rejections and the listening pass: 63 identifiers, 120 clips, 40 minutes, 100% CC BY.**
- [x] 11. Listen to every item and curate. **113 presented, 23 rejected on listening, 21 by extension of a unanimous verdict across an act, 63 kept.** 27 of the rejections needed no restoration and are kept outside the scored set in `clean_control_manifest.jsonl`, since Blind-Real on its own then cannot show whether a system damages already-good audio; the paired Diagnostic set is what measures that. Recorded in `build/blind_real/qa_pass1_report.json`.
- [x] 9. Download the best available Internet Archive original for each. **130/130, 3.8 GB, each verified against the Archive's own SHA-1.**
- [x] 10. Cut deterministic excerpts and record the exact bounds. **120 excerpts of 20 s, 40 minutes.**
- [x] 11. Attach provenance and confidence metadata to every clip.
- [ ] 12. Write the evaluation script with clip then identifier then dataset aggregation.
- [x] 12. Validate and package the release. `scripts/validate_blind_real_release.py` asserts every invariant the release claims (1,922 checks: no overlap between the scored and clean sets, nothing rejected or unlistened admitted, a recorded verdict per item, no item drawing two excerpts from one track, every clip 20.00 s / 44.1 kHz / stereo, no restrictive licence, attribution complete). `scripts/package_blind_real_release.py` writes the release: FLAC audio, both manifests with the source SHA-1 per clip, attribution tables, dataset card, `SHA256SUMS`, and `verify_clip.py`. **710 MB, 390 files.**
- [ ] 13. Define the no-reference Blind-Real metrics, after the set exists. **Proposed below, pending ratification.**

### Proposed Blind-Real metric set

The machinery already exists in the GPU perceptual pack; what was missing was deciding
which of it constitutes the reported score, since most of the pack assumes a paired clean
reference that this set does not have. Two backends need none:

**Reported.** `fadtk_fma_pop_distance` and `aesthetics` (Audiobox CE/CU/PC/PQ), each
computed on the input as well as the output, so the figure is a change rather than an
absolute. Plus a second FAD against the **clean control set** as the reference
distribution: 92 items of the same Internet Archive provenance and genre mix, which is far
better matched to this material than FMA-Pop, whose distance partly measures distance from
pop music rather than from clean music.

**Over-processing, reported alongside.** The same two metrics on the clean control set. A
system that improves degraded audio while damaging audio that needed nothing must not be
able to hide that, and this is what the clean control set is for.

**Diagnostic only, never the score.** The six signal descriptors in
`openrestor/metrics/blind_real.py`. They stay because they describe what a system did to
the signal, but they are demoted on evidence: tested against a listener's own verdicts
over 120 degraded and 49 too-clean clips they separated the two at chance, AUC 0.35 to
0.56, with the noise floor pointing the wrong way. A descriptor that cannot detect
degradation cannot score its removal. Measurements in
`build/blind_real/descriptor_separation.json`.

**Excluded by construction.** Any similarity to a clean reference, which does not exist
here; and input-to-output similarity as a primary metric, because a system that correctly
removes hiss moves away from its input and rewarding closeness punishes it for working.

**Caveats that must ship with the numbers.** FAD is biased at small sample sizes and this
set is 210 clips, so a FAD figure is only comparable against another computed on the same
clips, never across sets of different size. Audiobox Aesthetics predicts listener
judgements of production quality, which is not the same quantity as restoration fidelity.

### Why the audio ships, rather than an index plus a downloader

CC BY permits redistribution once attribution is satisfied, and it is, on every clip. The
deciding argument is reproducibility: a test set distributed as Internet Archive links is
not a fixed test set, because items are removed or replaced — we removed a dozen ourselves
during curation — so two people "downloading the same dataset" months apart would evaluate
on different audio. That is how AudioSet and MusicCaps lost reproducibility.

The downloader therefore ships as a **verification** tool instead of a distribution
mechanism: each clip records its source file, that file's SHA-1 as the Archive served it,
and the exact cut, so anyone can re-derive a clip and compare it sample for sample.
Tested on three clips spanning both sets and both download rounds. No public index or audio
is released for Official Hidden, where even source identities and restored outputs remain
private.

### Not prerequisites

Mass human QA listening, MAD or MERT distribution matching, and any new degradation taxonomy are out of scope for this phase.

### IT/software engineer tasks

- [ ] Provide a crawl and download path to Internet Archive originals with retry and rate-limit handling.
- [ ] Host the curated excerpts, their provenance records and their attribution file.

### Shared deliverables

- [x] catalogue scan, licence and confidence filters, deduplication, cap, ranking, frozen-list writer
- [x] IAMD scan report
- [ ] frozen public test manifest over the 131 high-confidence identifiers
- [ ] downloaded originals and deterministic excerpts
- [ ] evaluation script with identifier-level aggregation

## Phase 2D - Official Hidden Paired Evaluation

Goal: measure restoration with paired metrics on rights-cleared concert masters that no
participant can have trained on as an identified evaluation set.

Test split only, organizer-only, and **deliberately not sourced from IAMD**, so that training on all of IAMD does not amount to training on this set.

### Source

Rights-cleared concert masters supplied directly through an authorised partner channel. A
candidate is the Montreux Jazz Festival archive, subject to a written agreement covering
storage, excerpting, degraded derivatives, ML evaluation, server-side participant software
and publication of aggregate metrics. Public YouTube copies are not scraped or used as the
acquisition path.

### Non-publication rule

- [ ] The audio is **never published**. Neither are its URLs, video IDs or timestamps. Publishing any of those would let a participant reconstruct the set.
- [ ] A complete manifest is kept **internally**, recording for every item: agreement reference, rights status, content hash, exact excerpt bounds and degradation provenance. Source identities and agreements never enter the public repository.
- [ ] Participants never receive these files. They submit a container; the organizers run it.

### Evaluation

Server-side, by executing the containers participants submit, using the same frozen container interface as the hidden Diagnostic evaluation in Phase 5. Hidden degraded inputs are mounted read-only; clean masters and references are available only to the organizer-side scorer.

### Why it exists

To measure generalisation on genuinely unseen real recordings, and to keep the public Blind-Real test from being contaminated or gamed. It **does not replace the public test**, which is what makes local development possible.

### Research/audio engineer tasks

- [x] Define the per-item rights evidence standard and rejection rule in `docs/hidden_evaluation.md`.
- [x] Add the private rights-register schema, `schemas/hidden_rights_record.schema.json`.
- [ ] Obtain and review a written agreement for the proposed Montreux Jazz Festival masters.
- [ ] Curate the set and keep it in organizer-controlled storage only.
- [ ] Verify no overlap of artist, concert or recording with the public Blind-Real set.

### IT/software engineer tasks

- [ ] Store the audio, manifest and provenance in organizer-only storage with no participant download path.
- [ ] Mount the hidden inputs read-only into submitted containers and keep them out of logs and error messages.

### Shared deliverables

- [ ] internal provenance manifest with licence or permission evidence per item
- [ ] organizer-only hidden Blind-Real test set
- [ ] documented non-publication policy

## Phase 3 - Metrics, AAE Diagnostics, And Reports

Goal: make scores scientifically meaningful and operationally reproducible.

### Per-Track Metric Protocols

The three tracks cannot share one protocol, because only two of them have a clean reference.

| Track | Protocol |
| --- | --- |
| Diagnostic | Full paired reconstruction metrics plus per-class AAE. The class label is known, so AAE is reported per degradation class. |
| Blind-Synthetic | The same paired metrics, but AAE is reported over the ordered degradation chain rather than a single class. Add an over-restoration measure on the clean test items, where the correct behaviour is to change nothing. |
| Blind-Real | No clean reference exists, so **no similarity-to-clean metric is possible**. Do not use input-to-output similarity as a primary metric either: it penalises legitimate correction. Use several complementary no-reference and perceptual metrics instead, and document their limits explicitly. No heavy human evaluation is planned for now. |

- [ ] Define and freeze the three protocols above, including which metrics are official and which stay experimental per track.
- [ ] Implement the over-restoration measure for the clean items in the Blind-Synthetic test split.
- [ ] Select and validate the no-reference metric set for Blind-Real, and write down what each one cannot tell us.

### Research/audio engineer tasks

- [x] Implement and validate CPU pairwise reconstruction metrics: L1, RMSE/L2, SNR, SI-SDR, SI-SNR, LSD, multi-resolution STFT distance, log-mel distance, and LTAS distance.
- [x] Implement CPU log-mel SSIM and spectral-profile KL divergence.
- [x] Add CLAP audio embedding similarity in the GPU perceptual pack. SDD audio-text consistency remains deferred.
- [x] Add FADTK (LAION Music, local clean and built-in FMA-Pop references) and Audiobox metrics in the GPU perceptual pack with pinned models and fail-closed cache/model handling:
  - [x] FADTK `clap-laion-music` restored vs clean distribution
  - [x] FADTK local clean-reference score using LAION Music embeddings
  - [x] FADTK against its built-in FMA-Pop reference distribution using the same `clap-laion-music` backend as ARIEL.
  - [x] Meta Audiobox Aesthetics Content Enjoyment ("CE"), Content Usefulness ("CU"), Production Complexity ("PC"), and Production Quality ("PQ")
- [x] Implement first transparent AAE descriptors, aggregated by category with individual-effect detail:
  - [x] EQ/coloration
  - [x] bandwidth loss
  - [x] noise/ambience
  - [x] clipping/saturation
  - [x] dynamics
  - [x] reverb/room
  - [x] stereo/spatial
  - [x] codec/transmission, marked experimental until robust
- [x] Define metric caveats and interpretation rules for the diagnostic report; no leaderboard aggregate is defined.
- [x] Build the runnable CPU scoring and reporting pipeline that IT can host:
  - [x] read clean/degraded/restored audio
  - [x] validate file correspondence and fail closed on invalid/missing output
  - [x] compute selected CPU metrics and AAE diagnostics
  - [ ] cache expensive embeddings/statistics locally when the optional GPU pack is implemented
  - [x] aggregate metrics by category, effect, severity, split, and dataset
  - [x] write `scores.json`
  - [x] generate summary, per-item, category, and effect reports
  - [x] report failure counts and invalid outputs

### IT/software engineer tasks

- [ ] Publish the versioned, downloadable validation/evaluation package: `openrestor-score`, metric configurations, schemas, templates, documentation, and a release archive or tagged repository revision.
- [ ] Host the research-owned scoring command for public and hidden evaluation jobs.
- [ ] Provide GPU-capable workers if selected metrics require them.
- [ ] Run `openrestor-score setup-perceptual` in the shared GPU cache to download and verify the approved CLAP, FADTK LAION Music/FMA-Pop, and Audiobox assets; manage that cache, embeddings, and reference statistics in the hosted environment.
- [ ] Store scores, reports, logs, and intermediate metric artifacts in hosted storage.
- [ ] Publish generated reports and leaderboard-ready JSON artifacts to the agreed internal or public location.

### Shared deliverables

- [x] public local scoring command and restored-output contract
- [ ] downloadable versioned evaluation package and release notes
- [x] `configs/evaluation/metrics.yaml`
- [x] metric validation fixtures
- [x] `scores.json` schema
- [x] first metric report for the no-restoration baseline: zero invalid outputs and zero reported improvement, as expected.

## Phase 4 - Baselines

Goal: make the leaderboard interpretable from the first release.

### Research/audio engineer tasks

- [ ] Implement no-restoration baseline:
  - [ ] copy degraded input to output
  - [ ] verify exact format preservation
- [ ] Implement simple DSP baseline:
  - [ ] primitive-aware or metadata-aware corrections where appropriate
  - [ ] transparent methods only
  - [ ] no hidden training data
- [ ] Train or adapt a small learned baseline:
  - [ ] use only SonicMaster clean-original training data for the main-track version
  - [ ] document architecture, training data, loss functions, and limitations
  - [ ] report per-primitive-family strengths and weaknesses
- [ ] Use baseline outputs to detect broken degradations or misleading metrics.
- [ ] Package every baseline as runnable local code, with container recipes where useful.
- [ ] Add baseline run commands for public validation/test.
- [ ] Produce baseline outputs, logs, checksums, and scores for the first release candidate.

### IT/software engineer tasks

- [ ] Host baseline containers, weights, restored outputs, scores, and logs in the agreed artifact storage.
- [ ] Configure hosted reruns of the research-owned baseline commands when a release candidate changes.
- [ ] Publish baseline results to the leaderboard site or internal review page.
- [ ] Ensure hosted baseline reruns use the exact release data, container digest, and command supplied by the research pipeline.

### Shared deliverables

- [ ] no-restoration baseline scores
- [ ] simple DSP baseline scores
- [ ] small learned baseline training and inference documentation
- [ ] baseline containers or reproducible scripts

## Phase 5 - Container Submission And Organizer Evaluation

Goal: support official hidden evaluation without exposing evaluation audio. Participants submit a runnable immutable container, not precomputed hidden-set outputs.

### Frozen container interface to implement

The organizer mounts only hidden degraded data at `/input` and provides these environment variables to the declared `inference_command`:

| Variable | In-container value | Permission |
| --- | --- | --- |
| `OPENRESTOR_INPUT_MANIFEST` | `/input/degraded/index.jsonl` | read-only |
| `OPENRESTOR_INPUT_ROOT` | `/input/degraded/audio` | read-only |
| `OPENRESTOR_OUTPUT_ROOT` | `/output/audio` | write-only |
| `OPENRESTOR_OUTPUT_MANIFEST` | `/output/restoration_outputs.jsonl` | write-only |

The command must read these variables, restore every manifest item, and write canonical 44.1 kHz stereo WAVs plus `restoration_outputs.jsonl`. Clean references and their paths are never available inside the participant container. The organizer controls the fixed mounts, so participants need no hidden-path changes in their Dockerfile or code.

### Research/audio engineer tasks

- [ ] Extend and freeze the participant submission manifest:
  - [ ] immutable OCI image digest and build recipe reference
  - [ ] `inference_command` using the fixed environment-variable interface
  - [ ] track and training-data disclosure
  - [ ] model-weight location/checksum and requested runtime resources
- [ ] Define scientific validity checks for participant outputs:
  - [ ] complete one-to-one item ID correspondence and no untracked outputs
  - [ ] 44.1 kHz sample rate, stereo channel count, and duration tolerance
  - [ ] finite samples, safe peak/loudness bounds, readable WAV encoding
  - [ ] required `restoration_outputs.jsonl` schema and path resolution
- [ ] Freeze the invalid-submission policy: malformed manifest, missing/invalid output, timeout, resource breach, and inference failure are hard failures; never score a partial hidden run.
- [ ] Define training-data disclosure rules for SonicMaster-clean-only main and external-data tracks.
- [ ] Implement the local organizer evaluation command that IT will host:
  - [ ] validate submission metadata and image digest
  - [ ] run a fixture smoke test with the fixed `/input` and `/output` mounts
  - [ ] execute the hidden inference run
  - [ ] run `openrestor-score validate-restored` before any scoring
  - [ ] join outputs with private clean references outside the participant container
  - [ ] run CPU and approved perceptual reports
  - [ ] write logs, checksums, trusted restoration metadata, and audit metadata
- [ ] Review evaluation logs and metrics for anomalous submissions.
- [ ] Provide a participant container template that consumes only the declared variables.

### IT/software engineer tasks

- [ ] Publish the versioned submission-container template and validation/evaluation package for participants to download.
- [ ] Host the organizer evaluation command in a secure container execution environment.
- [ ] Pull submitted images by immutable digest; build only from the submitted, audited recipe when a build is required.
- [ ] Run images with network disabled, hidden `/input` mounted read-only, an empty `/output` mounted writable, no clean mount, and no participant-visible secrets.
- [ ] Enforce non-root execution where feasible, read-only container filesystems, time, CPU, memory, disk, and GPU limits.
- [ ] Run the same public validation/scoring package after inference, with private clean references accessible only to the organizer-side scorer.
- [ ] Store submission manifests, container digests, commands, runtime configuration, logs, restored outputs, checksums, trusted metadata, and metrics securely.
- [ ] Expose operational status and failure logs to organizers without exposing hidden evaluation audio or private paths.

### Shared deliverables

- [ ] extended `submission_manifest.schema.json` and documented field definitions
- [ ] example submission manifest
- [ ] example inference `Dockerfile`/container using the fixed environment variables
- [ ] local organizer dry-run command and public fixture
- [ ] hidden evaluation dry run using internal fixtures
- [ ] documented organizer evaluation procedure and invalid-submission policy

## Phase 6 - Release, Website, And Leaderboard

Goal: publish a citable, reproducible first OpenRestor release.

### Research/audio engineer tasks

- [ ] Write the dataset card and scientific benchmark documentation.
- [ ] Write metric descriptions, caveats, and recommended reporting language.
- [ ] Prepare baseline analysis and benchmark report.
- [ ] Verify that public release claims match actual data, licenses, metrics, and baselines.
- [ ] Prepare citation guidance and release notes.
- [ ] Build the public release artifact bundle that IT will publish:
  - [ ] public manifests
  - [ ] public audio assets where redistribution is allowed
  - [ ] degradation configs
  - [ ] metric configs
  - [ ] schemas
  - [ ] checksums
  - [ ] baseline definitions
  - [ ] release validation command

### IT/software engineer tasks

- [ ] Publish the research-owned release artifact bundle to the agreed hosting targets:
  - [ ] Hugging Face Datasets
  - [ ] Zenodo
  - [ ] static project website
  - [ ] internal private storage for hidden evaluation artifacts
- [ ] Deploy the static leaderboard and documentation site generated by the runnable pipeline.
- [ ] Wire the research-owned validation commands into hosted CI/CD.
- [ ] Configure mirrors, backups, storage quotas, and uptime monitoring for public and private release assets.

### Shared deliverables

- [ ] OpenRestor v0.1 public release
- [ ] DOI snapshot
- [ ] public leaderboard page
- [ ] release checklist signed off by both research and IT owners

## Phase 7 - Scientific Extensions After v0.1

Goal: expand only after the core benchmark is stable.

### Research/audio engineer tasks

- [ ] Add subjective listening tests.
- [ ] Add stronger learned or generative baselines when licenses and training assumptions are clear:
  - [ ] audio-to-audio diffusion
  - [ ] Schrodinger-bridge restoration
  - [ ] flow matching
  - [ ] specialist bandwidth-extension models
  - [ ] codec artifact removers
  - [ ] inpainting models
- [ ] Validate whether new metrics correlate with listening results.
- [ ] Consider specialized tracks:
  - [ ] bandwidth extension
  - [ ] codec repair
  - [ ] device-capture restoration
  - [ ] remastering

### IT/software engineer tasks

- [ ] Host listening-test collection tools if the research side delivers a protocol and runnable interface.
- [ ] Host model and baseline artifact registries if the number of baselines grows.
- [ ] Improve compute scheduling for expensive hidden evaluations.
- [ ] Deploy richer leaderboard filtering, comparison, and version snapshots from research-approved leaderboard data.

### Shared deliverables

- [ ] v0.2 extension plan
- [ ] listening-test protocol
- [ ] updated benchmark report
- [ ] backward-compatible leaderboard versioning

## Suggested First 12-Week Implementation Plan

| Weeks | Research/audio focus | IT/hosting focus | Joint milestone |
| --- | --- | --- | --- |
| 1-2 | Freeze task, metrics shortlist, source audit templates, primitive degradation definitions; create runnable package skeleton and schemas | Define hosting target, storage, secrets, runners, and CI/CD expectations | Contract, skeleton, and hosting contract ready |
| 3-4 | Implement ingestion pipeline, manifest writer, shard reader/writer, quality checks, and first fixture clips | Provide hosted storage and data-transfer paths for inputs/outputs | Miniature clean dataset builds locally and can run in hosted storage |
| 5-6 | Implement the frozen degradation primitives, randomized severity sampling, config-driven runner, and deterministic tests | Provide hosted batch compute, logs, and artifact storage | Miniature degraded dataset builds locally and in hosted runner |
| 7-8 | Implement core metrics, initial AAE descriptors, scoring pipeline, `scores.json`, and aggregation report | Provide hosted scoring workers, caches, and report storage | No-restoration scores generated locally and hosted |
| 9-10 | Implement simple DSP baseline, output validation, metric sanity checks, and leaderboard JSON generation | Host baseline artifacts and publish generated leaderboard data | Public validation report draft |
| 11-12 | Prepare small learned baseline plan or prototype, release text, release bundle, and checksums | Deploy static docs/leaderboard and publish release bundle | v0.1 release candidate |
