# OpenRestore Split Implementation Roadmap

This roadmap splits the OpenRestore implementation into research/audio responsibilities and Information Technology ("IT") backend engineering responsibilities. It is written for a small collaborative team where the research engineer owns the scientific validity, audio processing, evaluation design, and baseline behavior, while IT/software engineers own robust infrastructure, packaging, services, automation, storage, and release mechanics.

OpenRestore is a benchmark rather than a single restoration model. The critical shared contract is simple: each item is a 30-second 44.1 kHz musical clip with one degraded input, one clean reference, deterministic degradation metadata, and a portable manifest row. Public train/validation/test data are based on the Song Describer Dataset ("SDD"). Official leaderboard scoring uses a hidden organizer-only evaluation set.

## Ownership Summary

| Area | Research/audio engineer owns | IT/software engineers own | Shared decision points |
| --- | --- | --- | --- |
| Benchmark definition | Task scope, audio format, degradation taxonomy, metric interpretation, source acceptance criteria | Encoding those rules into schemas, validation, Continuous Integration ("CI") checks, and documentation builds | Final benchmark contract and release acceptance criteria |
| Dataset curation | Audio quality audit, listening review, SDD segmentation policy, hidden evaluation curation, approved training-pool rules | Download/cache tooling, storage layout, manifests, shard generation, checksums, access controls | Dataset versions, licensing status, public vs private release boundaries |
| Degradations | Digital Signal Processing ("DSP") algorithms, real-world profiles, severity bands, perceptual descriptors, reproducibility tests | Batch orchestration, config plumbing, job execution, artifact tracking | Config format, seed policy, metadata written per item |
| Metrics | Metric selection, audio metric implementations, Average Absolute Error ("AAE") descriptors, baseline interpretation | Scoring pipeline, result schemas, aggregation jobs, report export, leaderboard JavaScript Object Notation ("JSON") | Primary score, per-family reports, failure handling |
| Baselines | No-restoration, simple DSP, small learned model design/training/evaluation | Container packaging, reproducible runs, artifact publishing | Baseline release gates and score sanity checks |
| Submission evaluation | Scientific constraints for valid output and fair evaluation | Container runner, sandboxing, timeouts, logs, storage, submission manifests | Inference interface and invalid-output policy |
| Release | Dataset card content, benchmark report, scientific claims, citation details | Website, static leaderboard, Digital Object Identifier ("DOI") packaging, Continuous Integration/Continuous Delivery ("CI/CD"), mirrors | Public release checklist |

## Phase 0 - Project Contracts And Repository Skeleton

Goal: freeze the minimum viable benchmark contract before implementation becomes fragmented.

### Research/audio engineer tasks

- [ ] Finalize the benchmark task: one degraded mixed musical clip in, one restored clip out.
- [ ] Confirm canonical audio settings:
  - [ ] 30-second clips.
  - [ ] 44.1 kHz sample rate.
  - [ ] Stereo preferred, with explicit mono handling rules.
  - [ ] Output must preserve duration, sample rate, channel count, and item identifier ("ID").
- [ ] Finalize the 20 real-world degradation profiles and their initial severity bands.
- [ ] Decide which metrics are required for the first release and which stay experimental.
- [ ] Define the scientific meaning of the main leaderboard track and external-data track.

### IT/software engineer tasks

- [ ] Create the Python package/repository skeleton:
  - [ ] `openrestore/data`
  - [ ] `openrestore/degradations`
  - [ ] `openrestore/metrics`
  - [ ] `openrestore/evaluation`
  - [ ] `openrestore/submissions`
  - [ ] `openrestore/leaderboard`
  - [ ] `configs`
  - [ ] `schemas`
  - [ ] `scripts`
  - [ ] `tests`
  - [ ] `docker`
  - [ ] `site`
- [ ] Add packaging and developer tooling:
  - [ ] `pyproject.toml`
  - [ ] formatter/linter configuration
  - [ ] test runner
  - [ ] basic CI
- [ ] Implement JSON Schema validation harnesses for:
  - [ ] `index.jsonl`
  - [ ] degradation tracking
  - [ ] submission manifests
  - [ ] scores
  - [ ] leaderboard entries

### Shared deliverables

- [ ] Versioned benchmark contract document.
- [ ] Initial repository layout.
- [ ] Minimal schema files and validation commands.
- [ ] One tiny fixture dataset used by tests.

## Phase 1 - Dataset Audit, Ingestion, And Splitting

Goal: build a trustworthy data pipeline before generating large degraded releases.

### Research/audio engineer tasks

- [ ] Perform source audits for each candidate dataset:
  - [ ] SDD as public benchmark source.
  - [ ] Secret custom dataset as hidden evaluation source.
  - [ ] SonicMaster clean originals, filtered Free Music Archive ("FMA"), and Music Demixing Dataset 2018 High Quality ("MUSDB18-HQ") mixtures as optional approved training-pool sources.
  - [ ] British Broadcasting Corporation ("BBC") Sound Effects, Freesound, Freesound Dataset 50K ("FSD50K"), and music, speech, and noise corpus ("MUSAN") as degradation material only.
- [ ] For each dataset, produce a decision record:
  - [ ] dataset name and version
  - [ ] access Uniform Resource Locator ("URL")
  - [ ] intended OpenRestore role
  - [ ] license terms
  - [ ] redistribution status
  - [ ] quality notes
  - [ ] final status: `accepted`, `accepted with filtering`, `internal-only`, or `rejected`
- [ ] Define SDD source-level split rules so no recording leaks across train/validation/test.
- [ ] Define deterministic 30-second segmentation rules:
  - [ ] window start policy
  - [ ] partial segment policy
  - [ ] silence rejection
  - [ ] loudness/headroom normalization
  - [ ] channel conversion policy
- [ ] Run structured listening review on sampled clips and document failure modes.

### IT/software engineer tasks

- [ ] Implement dataset access and local cache tooling.
- [ ] Implement ingestion modules that can be run reproducibly from config:
  - [ ] SDD ingestion
  - [ ] optional training-pool ingestion
  - [ ] degradation-material ingestion
  - [ ] hidden evaluation ingestion, with private storage separation
- [ ] Implement portable manifest generation with release-relative paths.
- [ ] Implement stable source-level split assignment.
- [ ] Implement shard writing and reading, initially using the storage backend selected by the team.
- [ ] Implement checksum generation and verification.
- [ ] Implement automated audio quality checks:
  - [ ] duration bounds
  - [ ] sample rate
  - [ ] channel count
  - [ ] silence ratio
  - [ ] clipped-sample ratio
  - [ ] loudness distribution
  - [ ] decode failures
  - [ ] duplicate or near-duplicate candidates where practical

### Shared deliverables

- [ ] `configs/datasets/sdd.yaml`
- [ ] dataset audit records
- [ ] public train/validation/test split manifests
- [ ] private evaluation manifest template
- [ ] reproducible miniature dataset build
- [ ] dataset statistics report

## Phase 2 - Degradation Pipeline

Goal: generate deterministic, realistic degraded musical audio with complete metadata.

### Research/audio engineer tasks

- [ ] Implement or validate primitive DSP modules:
  - [ ] Equalization ("EQ") and spectral coloration
  - [ ] bandwidth limitation
  - [ ] dynamics and limiting
  - [ ] gain/loudness changes
  - [ ] clipping and saturation
  - [ ] additive noise, ambience, hum, and interference
  - [ ] clicks, crackle, pops, and burst defects
  - [ ] dropouts and glitches
  - [ ] room acoustics and Room Impulse Response ("RIR") convolution
  - [ ] microphone, speaker, and device response
  - [ ] stereo, phase, and spatial damage
  - [ ] conventional codec/transcoding artifacts
  - [ ] temporal pitch/speed instability
- [ ] Implement the first 20 real-world profiles:
  - [ ] `room_rir`
  - [ ] `far_field_distance`
  - [ ] `off_axis_mic`
  - [ ] `consumer_mic`
  - [ ] `speaker_playback`
  - [ ] `background_ambience`
  - [ ] `crowd_bleed`
  - [ ] `broadband_noise`
  - [ ] `electrical_hum`
  - [ ] `clicks_crackle`
  - [ ] `dropouts_glitches`
  - [ ] `gain_clipping`
  - [ ] `saturation_overdrive`
  - [ ] `overcompression_limiter`
  - [ ] `bandwidth_loss`
  - [ ] `telephone_band`
  - [ ] `low_sample_rate`
  - [ ] `lossy_codec`
  - [ ] `transcode_chain`
  - [ ] `pitch_speed_instability`
- [ ] Define severity bands for every profile.
- [ ] Define compact `degradation_tracking` values and full recipe metadata for every operation.
- [ ] Create controlled audio fixtures to test reproducibility and expected perceptual effect.
- [ ] Listen to representative outputs and tune parameter ranges so artifacts are realistic but not impossible.

### IT/software engineer tasks

- [ ] Build config-driven degradation execution:
  - [ ] deterministic seeds
  - [ ] recipe loading
  - [ ] batch processing
  - [ ] progress logging
  - [ ] resumable jobs
  - [ ] error reporting
- [ ] Implement artifact writing:
  - [ ] degraded audio shards
  - [ ] updated `index.jsonl`
  - [ ] per-item recipe references
  - [ ] checksums
- [ ] Add unit and integration tests around determinism:
  - [ ] same input/config/seed produces identical metadata and stable audio checksums within the accepted tolerance
  - [ ] changing the seed changes sampled parameters where expected
- [ ] Add parallel execution support for large dataset builds.
- [ ] Add validation that every degraded row has:
  - [ ] clean reference path
  - [ ] degraded path
  - [ ] profile ID
  - [ ] causal family IDs
  - [ ] severity
  - [ ] prompt or descriptor metadata where applicable

### Shared deliverables

- [ ] `configs/degradations/single`
- [ ] `configs/degradations/organic`
- [ ] `configs/degradations/stress`
- [ ] deterministic degradation Command-Line Interface ("CLI")
- [ ] first degraded miniature release
- [ ] profile-by-profile listening and validation notes

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
  - [ ] FAD-LAION against Free Music Archive Pop reference statistics ("FAD-LAION-FMA-Pop")
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

### IT/software engineer tasks

- [ ] Build the scoring pipeline:
  - [ ] read clean/degraded/restored audio
  - [ ] validate file correspondence
  - [ ] compute selected metrics
  - [ ] cache expensive embeddings/statistics
  - [ ] aggregate metrics by profile, family, severity, split, and source subset
- [ ] Implement `scores.json` schema and validation.
- [ ] Implement report generation:
  - [ ] summary tables
  - [ ] per-degradation breakdowns
  - [ ] degraded baseline vs restored improvement
  - [ ] failure-rate and invalid-output reporting
- [ ] Add CI tests for metric code on tiny fixtures.
- [ ] Add runtime controls for heavy metrics that may require Graphics Processing Units ("GPUs") or external model downloads.

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
  - [ ] profile-aware or metadata-aware corrections where appropriate
  - [ ] transparent methods only
  - [ ] no hidden training data
- [ ] Train or adapt a small learned baseline:
  - [ ] use only public OpenRestore training data for the main-track version
  - [ ] document architecture, training data, loss functions, and limitations
  - [ ] report per-profile strengths and weaknesses
- [ ] Use baseline outputs to detect broken degradations or misleading metrics.

### IT/software engineer tasks

- [ ] Package every baseline as runnable code and optionally as containers.
- [ ] Add baseline run scripts for public validation/test.
- [ ] Store baseline outputs, logs, checksums, and scores.
- [ ] Add baseline entries to the static leaderboard format.
- [ ] Ensure baselines can be rerun from a clean checkout plus documented data access.

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
  - [ ] approved-training-pool main track
  - [ ] external-data track
- [ ] Review evaluation logs and metrics for anomalous submissions.

### IT/software engineer tasks

- [ ] Implement submission manifest parsing and validation.
- [ ] Implement organizer-side container runner:
  - [ ] pull image by digest
  - [ ] mount input and output directories
  - [ ] pass metadata path
  - [ ] run declared command
  - [ ] enforce timeouts and resource limits
  - [ ] collect logs
- [ ] Implement output validation before scoring.
- [ ] Implement secure storage of:
  - [ ] submission manifests
  - [ ] container digests
  - [ ] logs
  - [ ] restored outputs
  - [ ] output checksums
  - [ ] metrics
- [ ] Implement local example container so participants can test the interface.

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

### IT/software engineer tasks

- [ ] Build public artifact packaging:
  - [ ] public manifests
  - [ ] public audio assets where redistribution is allowed
  - [ ] degradation configs
  - [ ] metric configs
  - [ ] schemas
  - [ ] checksums
  - [ ] baseline definitions
- [ ] Publish or prepare upload to:
  - [ ] Hugging Face Datasets
  - [ ] Zenodo
  - [ ] static project website
- [ ] Build static leaderboard generation from `leaderboard.json`.
- [ ] Set up release CI:
  - [ ] schema validation
  - [ ] checksum validation
  - [ ] miniature dataset rebuild
  - [ ] leaderboard rebuild
  - [ ] documentation build

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

- [ ] Extend infrastructure for listening-test data collection if needed.
- [ ] Add model registry or baseline artifact registry if baseline count grows.
- [ ] Improve compute scheduling for expensive hidden evaluations.
- [ ] Add richer leaderboard filtering, comparison, and version snapshots.

### Shared deliverables

- [ ] v0.2 extension plan
- [ ] listening-test protocol
- [ ] updated benchmark report
- [ ] backward-compatible leaderboard versioning

## Interface Contracts Between Research And IT

Application Programming Interfaces ("APIs") here means the stable file, metadata, recipe, metric, and container contracts between the scientific/audio side and the backend/software side.


### Dataset item contract

Each generated row in `index.jsonl` must contain:

- [ ] stable `id`
- [ ] `source_id`
- [ ] `split`
- [ ] source dataset metadata
- [ ] segment start/end/duration
- [ ] sample rate and channel count
- [ ] clean audio storage path
- [ ] degraded audio storage path
- [ ] degradation profile/family metadata
- [ ] prompt or descriptor metadata where applicable
- [ ] rights and attribution fields

### Degradation contract

Each degradation recipe must define:

- [ ] profile ID
- [ ] severity band
- [ ] ordered operations
- [ ] random seed behavior
- [ ] allowed parameter ranges
- [ ] causal family labels
- [ ] perceptual descriptor labels
- [ ] compact manifest metadata
- [ ] full reproducibility metadata

### Metric contract

Each metric implementation must define:

- [ ] input audio requirements
- [ ] whether it is clip-level or dataset-level
- [ ] whether higher or lower is better
- [ ] degraded-vs-clean baseline behavior
- [ ] restored-vs-clean scoring behavior
- [ ] aggregation rules
- [ ] failure behavior
- [ ] version string

### Submission contract

Each participant container must:

- [ ] read degraded audio from `/input`
- [ ] read metadata from `/input/index.jsonl`
- [ ] write restored audio to `/output`
- [ ] preserve item IDs
- [ ] produce one output file per input item
- [ ] avoid manual intervention
- [ ] declare training data
- [ ] use fixed weights by digest or checksum

## Suggested First 12-Week Implementation Plan

| Weeks | Research/audio focus | IT/backend focus | Joint milestone |
| --- | --- | --- | --- |
| 1-2 | Freeze task, metrics shortlist, source audit templates, degradation profile definitions | Repository skeleton, schemas, validation Command-Line Interface ("CLI"), CI | Contract and skeleton ready |
| 3-4 | SDD split rules, quality checks, listening review, first fixture clips | Ingestion pipeline, manifest writer, shard reader/writer | Miniature clean dataset builds |
| 5-6 | First degradation modules and 5-8 profiles | Config-driven degradation runner and deterministic tests | Miniature degraded dataset builds |
| 7-8 | Core reconstruction metrics and initial AAE descriptors | Scoring pipeline, `scores.json`, aggregation report | No-restoration scores generated |
| 9-10 | Simple DSP baseline, metric sanity checks | Baseline packaging, output validation, leaderboard JSON | Public validation report draft |
| 11-12 | Small learned baseline plan or prototype, release text | Static docs/leaderboard, release packaging, checksums | v0.1 release candidate |

## Immediate Next Tasks

### You should start with

- [ ] Finalize the first-release metric shortlist.
- [ ] Turn the 20 profiles into concrete audio recipes with severity ranges.
- [ ] Define SDD segmentation and listening-review criteria.
- [ ] Create the first tiny set of clean/degraded audio fixtures for tests.
- [ ] Implement or prototype the first DSP modules: filtering, clipping, hum/noise, crackle, low sample rate, telephone band, and pitch instability.

### IT should start with

- [ ] Build the package skeleton and CI.
- [ ] Implement JSON Schema validation for the manifest and submission files.
- [ ] Implement ingestion and manifest-writing scaffolding.
- [ ] Implement shard read/write abstraction.
- [ ] Implement CLI entry points for dataset validation, degradation runs, scoring, and leaderboard generation.

### First joint review should answer

- [ ] Are the manifest fields sufficient for both training and hidden evaluation?
- [ ] Can the degradation recipes be reproduced from config plus seed?
- [ ] Can the backend run a full miniature pipeline end to end?
- [ ] Do no-restoration scores behave as the expected lower bound?
- [ ] Are public and hidden data paths cleanly separated?
