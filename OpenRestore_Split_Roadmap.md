# OpenRestore Split Implementation Roadmap

This roadmap splits the OpenRestore implementation into the runnable research/audio pipeline and the hosted Information Technology ("IT") platform around it. It is written for a small collaborative team where the research engineer owns what will be hosted: the scientific validity, audio processing, dataset generation, degradation code, metric code, baselines, schemas, command-line tools, and reproducible local pipeline. IT/software engineers own how that runnable pipeline is hosted, secured, deployed, monitored, scaled, stored, and exposed to users.

OpenRestore is a benchmark rather than a single restoration model. It has three evaluation tracks, built and released in order:

| Track | What it measures | Degradations per item | Clean reference |
| --- | --- | --- | --- |
| **Diagnostic** | capability per degradation type, attributable to one cause | exactly one, from the 21 canonical classes | yes |
| **Blind-Synthetic** | blind restoration when the degradation is unknown and may be compound | 0 to 3, random type, order and intensity | yes |
| **Blind-Real** | generalisation to genuinely degraded recordings | unknown, naturally occurring | **no** |

The Diagnostic track carries the original contract: each item is a 30-second 44.1 kHz musical clip with one degraded input, one clean reference, deterministic degradation metadata, and a portable manifest row. Main-track training uses SonicMaster clean originals only. Validation/model selection uses held-out SonicMaster clean audio. The source-separated SonicMaster public test is the in-distribution test. The Song Describer Dataset ("SDD") and Music Demixing Dataset 2018 High Quality ("MUSDB18-HQ") mixture audio are separately reported public transfer/local-evaluation sets. Official leaderboard scoring uses a hidden organizer-only evaluation set.

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
  - [x] `openrestore/data`
  - [x] `openrestore/degradations`
  - [x] `openrestore/metrics`
  - [x] `openrestore/evaluation`
  - [x] `openrestore/submissions`
  - [x] `openrestore/leaderboard`
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
  - [x] SDD as a public transfer/local-evaluation source only.
  - [x] Music Demixing Dataset 2018 High Quality ("MUSDB18-HQ") mixtures as a public transfer/local-evaluation source only.
  - [x] Secret custom dataset as hidden evaluation source.
- [x] For each dataset, produce a decision record:
  - [x] dataset name and version
  - [x] access Uniform Resource Locator ("URL")
  - [x] intended OpenRestore role
  - [x] license terms
  - [x] redistribution status
  - [x] quality notes
- [x] Define SonicMaster source-level split rules so no recording leaks across train/validation/public test.
- [x] Define SDD and MUSDB18-HQ public transfer selection rules so these items remain separate from main-track training and SonicMaster model-selection validation.
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
- [x] SDD and MUSDB18-HQ public transfer manifests
- [x] private evaluation manifest template
- [x] reproducible miniature dataset build
- [x] dataset statistics report

## Phase 2 - Degradation Pipeline (Diagnostic Track)

Goal: generate deterministic, realistic degraded musical audio with complete metadata, with exactly one degradation per item so every failure is attributable to one cause.

### Current v0.1 Contract

OpenRestore is now effect-first. The active single-effect registry has exactly 21 canonical classes. Categories remain metadata and reporting groups, not recipe IDs. Every output has one explicitly selected effect; the runner never samples effect choices or combines effects. Normal dataset recipes use deterministic randomized parameters within that selected effect; medium_preview is a separate, fixed-central listening profile.

### Research/audio engineer tasks

- [x] Define and document the 21-class v0.1 registry, including origin, group, relevance, status, and benchmark role.
- [x] Port the ARIEL/SonicMaster single effects, folded into the canonical classes. Legacy names such as `comp`, `punch`, `xband`, `bright`, `dark`, `airy`, `boom`, `clarity`, `mud`, `warm`, `vocal` and `stereo` remain callable aliases for reproducing historical manifests but are not benchmark classes. `volume` is removed, and `telephone_band` and `transcode_chain` must not be reintroduced as classes.
- [x] Implement the OpenRestore additions: noise, hum, clicks_crackle, dropouts_glitches, neural_codec, channel_damage, pitch_speed_instability, distant_mic_capture, and the asset-free smartphone_capture that replaced the measured-IR `mic` class.
- [x] Keep simulated room behavior local through `pyroomacoustics`; support optional ARIEL-compatible microphone-transfer-function and real-RIR assets without requiring them for the core test suite.
- [x] Implement deterministic per-item and per-operation seeds, with sampled values recorded in output metadata.
- [x] Implement full operation tracking: recipe ID, severity label, seed, operation ID/variant, sampled parameters, output path, and SHA-256 checksum.
- [x] Implement the local `openrestore-degrade` command:
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
- [x] Create the release-asset contract for the reviewed 12 real RIR WAVs (the 20 Poliphone microphone IRs were retired with the `mic` class). The Git-ignored bundle is project-owned at `assets/degradations/v0_1/`; IT installs and verifies the exact artifact using `docs/degradation_assets.md` and `docs/degradation_assets_v0_1.sha256`.
- [ ] Upload `build/release_assets/openrestore-degradation-assets-v0_1.tar.gz` and its SHA-256 file as a private GitHub/GitLab release asset tagged `degradation-assets-v0.1`; record its URL, archive SHA-256, and OpenAIR provenance and redistribution terms in the release record. Mirror the final approved public bundle to Zenodo only if those terms permit redistribution.
- [x] Add degraded HDF5 shard writing and a release index that points each row at `degraded_audio_shard` and `degraded_audio_shard_index`. The WAV manifest remains the rendering provenance; the shard index is the release-facing reader contract.
- [ ] Build the approved v0.1 paired degradation sets for every public clean split that OpenRestore releases: main-track SonicMaster training, held-out SonicMaster validation and public test, plus SDD and MUSDB18-HQ public transfer evaluation. Render the configured single effects, preserve the matching clean IDs, and keep the hidden evaluation set in a separate organizer-only build.
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

This is a separate dataset with its own train, validation and test splits. It does not replace the Diagnostic track and does not change the 21 canonical classes.

### Research/audio engineer tasks

- [ ] Define the compound sampling policy:
  - [ ] a random number of degradations per item, 0 to 3, genuinely variable rather than always three
  - [ ] random types drawn from the 21 canonical classes
  - [ ] random application order
  - [ ] random intensities, still `strong_random` per class with every sampled value recorded
- [ ] Define a small compatibility matrix that rejects absurd or redundant combinations, for example stacking two bandwidth classes or two reverberation classes. Keep it a matrix of pairwise rules, not a library of predefined recipes.
- [ ] Reserve a small percentage of **clean, undegraded** items in the test split, to measure whether a system over-restores audio that needs nothing.
- [ ] Implement the compound runner with deterministic per-item seeds, recording the full ordered operation chain.
- [ ] Define the metadata exposure policy: degradation metadata is published for train and validation so classifiers, routers and blind models can be trained, and is withheld at inference time on test.
- [ ] Build the train/validation/test splits from the same frozen SonicMaster source assignment, with no source leakage between them or into the Diagnostic track.
- [ ] Freeze a release manifest with clean and degraded paths, the ordered degradation chain, seeds, audio properties, and checksums.

### IT/software engineer tasks

- [ ] Run the compound degradation build at release scale with the same scheduling, retry and provenance guarantees as the Diagnostic build.
- [ ] Publish the train/validation/test release, and serve test items **without** their degradation metadata.

### Shared deliverables

- [ ] compound degradation configuration and compatibility matrix
- [ ] Blind-Synthetic train/validation/test release with manifests and checksums
- [ ] documented metadata-exposure boundary between train/validation and test

## Phase 2C - Blind-Real Benchmark

Goal: evaluate generalisation on real recordings that are degraded by their own history rather than by our code.

Test split only. No clean ground truth exists, and no degradation label is available at inference.

### Scope

The target is live and amateur music capture: concerts, audience and taper recordings, old festival captures, soundboard and tape transfers, consumer microphones. Old Montreux Jazz Festival recordings are the reference mental image. Extreme historical material such as cylinder recordings is explicitly out of scope, being too far from the application target.

### Research/audio engineer tasks

- [ ] Use the [Internet Archive Music Dataset (IAMD)](https://adasp.telecom-paris.fr/resources/2026-08-01-iamd-dataset/) as the **discovery catalogue**: it covers 4.1M captioned 30-second segments from 548k Creative Commons files, with Internet Archive metadata and per-item licence records.
- [ ] Do **not** use IAMD's own 320 kbps MP3 segments in the final benchmark. Resolve each candidate to its Internet Archive identifier and download the highest-quality original source audio available for that item.
- [ ] Filter by licence, preferring CC0 and CC BY, accepting CC BY-SA only if it is compatible with the release policy, and avoiding NC assets so the benchmark distribution stays permissive.
- [ ] Filter by Internet Archive metadata to target live, concert, audience, tape and soundboard captures.
- [ ] Curate roughly 300 to 500 fixed excerpts of 10 to 30 seconds, selected for real capture conditions rather than for a specific artefact.
- [ ] Record per-item provenance: Internet Archive identifier, licence, attribution, original format, and the exact excerpt bounds.
- [ ] Document the known limits of the set: unknown and uncontrolled degradations, no clean reference, and a selection bias toward what the Internet Archive happens to hold.

### IT/software engineer tasks

- [ ] Provide a crawl and download path to Internet Archive originals with retry and rate-limit handling.
- [ ] Host the curated excerpts, their provenance records and their attribution file.

### Shared deliverables

- [ ] Blind-Real curation configuration with licence and metadata filters
- [ ] 300-500 excerpt test set with per-item provenance and attribution
- [ ] documented scope statement and known limits

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

- [ ] Publish the versioned, downloadable validation/evaluation package: `openrestore-score`, metric configurations, schemas, templates, documentation, and a release archive or tagged repository revision.
- [ ] Host the research-owned scoring command for public and hidden evaluation jobs.
- [ ] Provide GPU-capable workers if selected metrics require them.
- [ ] Run `openrestore-score setup-perceptual` in the shared GPU cache to download and verify the approved CLAP, FADTK LAION Music/FMA-Pop, and Audiobox assets; manage that cache, embeddings, and reference statistics in the hosted environment.
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
| `OPENRESTORE_INPUT_MANIFEST` | `/input/degraded/index.jsonl` | read-only |
| `OPENRESTORE_INPUT_ROOT` | `/input/degraded/audio` | read-only |
| `OPENRESTORE_OUTPUT_ROOT` | `/output/audio` | write-only |
| `OPENRESTORE_OUTPUT_MANIFEST` | `/output/restoration_outputs.jsonl` | write-only |

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
  - [ ] run `openrestore-score validate-restored` before any scoring
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
