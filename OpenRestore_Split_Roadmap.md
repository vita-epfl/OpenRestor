# OpenRestore Split Implementation Roadmap

This roadmap splits the OpenRestore implementation into the runnable research/audio pipeline and the hosted Information Technology ("IT") platform around it. It is written for a small collaborative team where the research engineer owns what will be hosted: the scientific validity, audio processing, dataset generation, degradation code, metric code, baselines, schemas, command-line tools, and reproducible local pipeline. IT/software engineers own how that runnable pipeline is hosted, secured, deployed, monitored, scaled, stored, and exposed to users.

OpenRestore is a benchmark rather than a single restoration model. The critical shared contract is simple: each item is a 30-second 44.1 kHz musical clip with one degraded input, one clean reference, deterministic degradation metadata, and a portable manifest row. Main-track training uses SonicMaster clean originals only. Validation uses held-out SonicMaster clean audio, the Song Describer Dataset ("SDD"), and Music Demixing Dataset 2018 High Quality ("MUSDB18-HQ") mixture audio. Public test uses held-out SonicMaster clean audio. Official leaderboard scoring uses a hidden organizer-only evaluation set.

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
- [ ] Create the Python package/repository skeleton that IT will later host:
  - [x] `openrestore/data`
  - [ ] `openrestore/degradations`
  - [ ] `openrestore/metrics`
  - [ ] `openrestore/evaluation`
  - [ ] `openrestore/submissions`
  - [ ] `openrestore/leaderboard`
  - [x] `configs`
  - [ ] `schemas`
  - [ ] `scripts`
  - [x] `tests`
  - [ ] `docker`
  - [ ] `site`
- [ ] Add local packaging and developer tooling for the runnable pipeline:
  - [x] `pyproject.toml`
  - [x] formatter/linter configuration
  - [x] test runner
  - [ ] basic CI configuration that IT can wire into hosted CI/CD
- [ ] Implement JSON Schema validation harnesses for:
  - [ ] `index.jsonl`
  - [ ] degradation tracking
  - [ ] submission manifests
  - [ ] scores
  - [ ] leaderboard entries

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

- [ ] Versioned benchmark contract document.
- [ ] Initial repository layout.
- [ ] Minimal schema files and validation commands.
- [x] One tiny fixture dataset used by tests.

## Phase 1 - Dataset Audit, Ingestion, And Splitting

Goal: build a trustworthy data pipeline before generating large degraded releases.

### Research/audio engineer tasks

- [x] Perform source audits for each candidate dataset:
  - [x] SonicMaster clean originals as the only main-track training source and as the public test source through source-separated held-out items.
  - [x] SDD as a validation source only.
  - [x] Music Demixing Dataset 2018 High Quality ("MUSDB18-HQ") mixtures as a validation source only.
  - [x] Secret custom dataset as hidden evaluation source.
- [x] For each dataset, produce a decision record:
  - [x] dataset name and version
  - [x] access Uniform Resource Locator ("URL")
  - [x] intended OpenRestore role
  - [x] license terms
  - [x] redistribution status
  - [x] quality notes
- [x] Define SonicMaster source-level split rules so no recording leaks across train/validation/public test.
- [x] Define SDD and MUSDB18-HQ validation selection rules so validation items remain separate from main-track training.
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
- [x] `configs/datasets/sdd_validation.yaml`
- [x] `configs/datasets/musdb18_hq_validation.yaml`
- [x] dataset audit records
- [x] SonicMaster public train/validation/test split manifests
- [x] SDD and MUSDB18-HQ validation manifests
- [x] private evaluation manifest template
- [x] reproducible miniature dataset build
- [x] dataset statistics report

## Phase 2 - Degradation Pipeline

Goal: generate deterministic, realistic degraded musical audio with complete metadata.

### Current v0.1 Contract

OpenRestore is now effect-first. The active single-effect registry has 25 rows: the 19 ARIEL/SonicMaster parity effects plus six OpenRestore additions (`noise`, `hum`, `codec`, `bandwidth`, `channel_damage`, and `distant_mic_capture`). Categories remain metadata and reporting groups, not the recipe IDs. Normal dataset recipes use deterministic randomized ranges; `medium_preview` is a separate, fixed-central listening profile.

### Research/audio engineer tasks

- [x] Define and document the 25-effect v0.1 registry, including origin, group, relevance, status, and benchmark role.
- [x] Port the 19 ARIEL/SonicMaster single effects: `comp`, `punch`, `xband`, `mic`, `bright`, `dark`, `airy`, `boom`, `clarity`, `mud`, `warm`, `vocal`, `small`, `big`, `mix`, `real`, `stereo`, `clip`, and `volume`.
- [x] Implement the six OpenRestore additions: `noise`, `hum`, `codec`, `bandwidth`, `channel_damage`, and `distant_mic_capture`.
- [x] Keep simulated room behavior local through `pyroomacoustics`; support optional ARIEL-compatible microphone-transfer-function and real-RIR assets without requiring them for the core test suite.
- [x] Implement deterministic per-item and per-operation seeds, with sampled values recorded in output metadata.
- [x] Implement full operation tracking: recipe ID/type, severity label, seed, operation ID/variant, sampled parameters, output path, and SHA-256 checksum.
- [x] Implement the local `openrestore-degrade` command:
  - [x] YAML config loading and validation
  - [x] recipe listing
  - [x] deterministic batch WAV rendering
  - [x] output JSONL manifest and per-file checksums
  - [x] local progress logging
- [x] Add generated stereo fixtures and deterministic pipeline tests.
- [x] Run a three-song, 25-effect medium listening preview: 75 WAVs with verified manifest paths and checksums.
- [x] Perform an initial listening review and tune the medium hum profile to an audible 50 Hz signal with harmonics.

### Remaining research/audio work

- [ ] Add effect-level automated tests for all 25 active effects. Current tests cover the generic runner and core primitives, but not every ARIEL/OpenRestore effect's audible behavior, metadata, and deterministic checksum.
- [ ] Complete structured listening notes for every effect and decide whether `channel_damage` remains distinct enough from `stereo` for the final registry.
- [ ] Calibrate normal dataset parameter distributions from listening review and, where possible, real degraded music. The current medium profile is for review, not a final scientific distribution.
- [ ] Package or acquire release-approved microphone transfer functions and real RIR assets. The current preview uses local ARIEL asset paths; the released pipeline must not depend on `/home/.../ARIEL`.
- [ ] Decide whether `volume` is benchmark-critical or remains SonicMaster-parity-only, given overlap with existing ARIEL volume behavior.
- [ ] Design and validate `paired`, `organic`, and `stress` recipes only after the single-effect registry is frozen. Existing config files validate, but they have not been reconciled with the new effect-first registry.
- [ ] Add degraded HDF5 shard writing and integration with the canonical dataset `index.jsonl`; the current renderer writes canonical WAVs plus a separate output manifest.
- [ ] Define failure handling for unavailable assets, FFmpeg failures, and long-running room simulations, then add coverage for those paths.

### Checkable evidence

- [x] `python3 -m unittest discover -s tests`: 6 tests passing.
- [x] `validate-config` passes for `single`, `paired`, `organic`, and `stress` configuration files.
- [x] The medium preview has 75 valid WAVs across 25 effects; every stored SHA-256 checksum matches its file.

### IT/software engineer tasks

- [ ] Provide hosted compute for running the research-owned degradation command at release scale.
- [ ] Configure job scheduling, retries, logs, and monitoring around degradation runs.
- [ ] Store degraded shards, manifests, checksums, and logs in agreed hosted artifact locations.
- [ ] Provide enough parallel execution capacity for large dataset builds without changing the degradation code.
- [ ] Report infrastructure, quota, and timeout failures separately from scientific/pipeline failures.

### Shared deliverables

- [x] `configs/degradations/single/v0_1.yaml` with the 25-effect single registry.
- [x] deterministic degradation Command-Line Interface ("CLI").
- [x] first local listening preview: 75 degraded examples across 25 effects.
- [ ] effect-by-effect listening and validation notes.
- [ ] reconciled `paired`, `organic`, and `stress` configs.
- [ ] first shard-backed degraded miniature release.

## Phase 3 - Metrics, AAE Diagnostics, And Reports

Goal: make scores scientifically meaningful and operationally reproducible.

### Research/audio engineer tasks

- [ ] Implement and validate pairwise reconstruction metrics:
  - [ ] L1 absolute error
  - [ ] L2 squared error
  - [ ] Signal-to-Noise Ratio ("SNR")
  - [ ] Scale-Invariant Signal-to-Distortion Ratio ("SI-SDR") or Scale-Invariant Signal-to-Noise Ratio ("SI-SNR")
  - [ ] Log-Spectral Distance ("LSD")
  - [ ] multi-resolution Short-Time Fourier Transform ("STFT") distance
  - [ ] mel-spectral distance
  - [ ] Long-Term Average Spectrum ("LTAS") distance
- [ ] Implement structural and embedding metrics where feasible:
  - [ ] Structural Similarity Index Measure ("SSIM") on log-mel or magnitude spectrograms
  - [ ] Contrastive Language-Audio Pretraining ("CLAP") audio embedding similarity
  - [ ] CLAP audio-text consistency for SDD captions if used
- [ ] Implement or integrate distributional and perceptual metrics:
  - [ ] Frechet Audio Distance ("FAD") restored vs clean
  - [ ] FAD with Large-scale Artificial Intelligence Open Network ("LAION") audio embeddings ("FAD-LAION") restored vs clean
  - [ ] FAD-LAION against a selected high-quality music reference distribution, if a suitable redistributable reference is approved
  - [ ] Meta Audiobox Aesthetics Content Enjoyment ("CE"), Content Usefulness ("CU"), Production Complexity ("PC"), and Production Quality ("PQ"), if practical for the release environment
- [ ] Implement first AAE descriptors:
  - [ ] EQ/coloration
  - [ ] bandwidth loss
  - [ ] noise/ambience
  - [ ] clipping/saturation
  - [ ] dynamics
  - [ ] reverb/room
  - [ ] stereo/spatial
  - [ ] codec/transmission, marked experimental until robust
- [ ] Define metric caveats and interpretation rules for the benchmark report.
- [ ] Build the runnable scoring and reporting pipeline that IT will host:
  - [ ] read clean/degraded/restored audio
  - [ ] validate file correspondence
  - [ ] compute selected metrics
  - [ ] cache expensive embeddings/statistics locally when possible
  - [ ] aggregate metrics by primitive family, recipe type, severity, split, and source subset
  - [ ] write `scores.json`
  - [ ] generate summary and per-degradation reports
  - [ ] report failure rates and invalid outputs

### IT/software engineer tasks

- [ ] Host the research-owned scoring command for public and hidden evaluation jobs.
- [ ] Provide GPU-capable workers if selected metrics require them.
- [ ] Manage caches for external metric models, embeddings, and reference statistics in the hosted environment.
- [ ] Store scores, reports, logs, and intermediate metric artifacts in hosted storage.
- [ ] Publish generated reports and leaderboard-ready JSON artifacts to the agreed internal or public location.

### Shared deliverables

- [ ] public local evaluation command
- [ ] `configs/evaluation/metrics.yaml`
- [ ] metric validation fixtures
- [ ] `scores.json` schema
- [ ] first metric report for the no-restoration baseline

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

Goal: support official hidden evaluation without exposing evaluation audio.

### Research/audio engineer tasks

- [ ] Define scientific validity checks for participant outputs:
  - [ ] duration tolerance
  - [ ] sample-rate match
  - [ ] channel-count match
  - [ ] loudness bounds
  - [ ] invalid samples
  - [ ] item ID/file naming
  - [ ] no extra outputs
- [ ] Define invalid submission policy:
  - [ ] hard failures
  - [ ] partial failures
  - [ ] timeout behavior
  - [ ] how missing files affect scores
- [ ] Define training-data disclosure rules for:
  - [ ] SonicMaster-clean-only main track
  - [ ] external-data track
- [ ] Review evaluation logs and metrics for anomalous submissions.
- [ ] Implement the local organizer evaluation command that IT will host:
  - [ ] parse and validate submission manifests
  - [ ] run the declared inference command on fixture data
  - [ ] validate outputs before scoring
  - [ ] compute scores with the research-owned scoring pipeline
  - [ ] write logs, checksums, and audit metadata
- [ ] Provide an example participant container for interface testing.

### IT/software engineer tasks

- [ ] Host the organizer evaluation command in a secure container execution environment.
- [ ] Pull submitted images by digest and run them with the approved mounts, timeouts, and resource limits.
- [ ] Manage secrets, network policy, private evaluation mounts, and output permissions.
- [ ] Store submission manifests, container digests, logs, restored outputs, checksums, and metrics securely.
- [ ] Expose operational status and failure logs to organizers without exposing hidden evaluation audio.

### Shared deliverables

- [ ] `submission_manifest.schema.json`
- [ ] example submission manifest
- [ ] example inference container
- [ ] hidden evaluation dry run using internal fixtures
- [ ] documented organizer evaluation procedure

## Phase 6 - Release, Website, And Leaderboard

Goal: publish a citable, reproducible first OpenRestore release.

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

- [ ] OpenRestore v0.1 public release
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
