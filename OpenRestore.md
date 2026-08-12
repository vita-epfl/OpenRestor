# OpenRestore

OpenRestore is an open, reproducible benchmark for musical audio restoration. It curates high-quality clean audio, generates controlled single degradations, evaluates restoration systems with reconstruction and perceptual metrics, and publishes datasets, baselines, reports, and a public leaderboard.

Internal application link: [CHORD-VITA application](https://docs.google.com/document/d/1jHbahFTKmkAgQGIGbRLSNHwxb-EY-tgN)

## Executive Summary

Musical audio restoration research is fragmented across denoising, dereverberation, declipping, bandwidth extension, codec repair, remastering, and general audio cleanup. OpenRestore will provide a shared benchmark for comparing restoration systems on complete musical audio clips, using deterministic degradations, high-quality source material, reproducible evaluation, and transparent metadata.

The benchmark should stay focused: one degraded mixed musical signal in, one restored signal out. Participants submit runnable containers, not restored evaluation audio. Organizers run those containers on a hidden evaluation split and publish scores on a leaderboard with an approved-training-pool main track and a separate external-data track.

## What We Are Building

OpenRestore is a benchmark, not a single model. The main training source should be the clean original audio from SonicMaster Dataset only. Validation should cover held-out SonicMaster clean audio, SDD (Song Describer Dataset), and MUSDB18-HQ mixture audio. The public test source should be held-out SonicMaster clean audio, while the official hidden evaluation set should come from a separate secret custom dataset that is not publicly released. Sound datasets can support degradations, but they are not benchmark music sources. It consists of:

- A SonicMaster-clean training source, held-out SonicMaster public test source, and validation sources spanning SonicMaster, SDD, and MUSDB18-HQ mixture audio.
- A deterministic degradation pipeline that creates paired clean/degraded examples.
- A JSONL manifest format close to the current restoration pipeline schema.
- Public train, validation, and test splits for development and diagnostics.
- A hidden organizer-only evaluation split for official leaderboard scoring.
- A container-based submission workflow.
- Metrics covering reconstruction, perceptual quality, embedding similarity, distributional quality, and degradation-specific AAE diagnostics.
- Baselines that make leaderboard scores interpretable.
- A lightweight release process with public artifacts, DOI snapshots, and a static leaderboard.

## Benchmark Contract

### Task

OpenRestore should focus on clip-level musical audio restoration across any musical domain:

- Input: one degraded musical audio clip, usually a full mixed signal rather than separated stems.
- Output: one restored audio clip with the same duration, sample rate, and channel count.
- Ground truth: the clean source clip used to create the degradation.
- Domains: high-quality music only. Sound-effect datasets are not benchmark sources; they may only be used as optional degradation/noise material.
- Clip length: each dataset item is a clean 30-second music clip paired with one or more degraded 30-second versions.
- Sample rate: 44.1 kHz.

### Key Decisions

- Build a single-clip musical restoration benchmark: one degraded mixed signal in, one restored signal out.
- Use SonicMaster clean originals only for training; use held-out SonicMaster, SDD, and MUSDB18-HQ mixture audio for validation; use held-out SonicMaster clean audio for the public test split.
- Keep the official evaluation split hidden and organizer-only, using a separate secret custom dataset curated under the same documented source policy; avoid surprise-domain evaluation.
- Use container-first submissions: participants submit inference code plus weights, and organizers run restoration on the hidden evaluation split.
- Make the main leaderboard use only the approved OpenRestore training source: SonicMaster clean originals; keep a separate external-data track for anything else.
- Treat AudioMD as an optional XML preservation export, not as the native JSON metadata format.
- Keep required metrics focused on one-to-one reconstruction and perceptual quality, with experimental metrics in optional reports.
- Keep all degradations open-source, reproducible, and fully specified in metadata.
- Prioritize a small SonicMaster-adjacent primitive degradation set over a broad inherited list of lab-style effects or real-world profiles.

## Dataset Strategy

OpenRestore should prioritize high-quality music datasets over broad pools of uneven audio. The benchmark item is always a paired example: a clean 30-second music clip and one or more degraded 30-second versions generated from it. Sound-effect datasets should not define the benchmark source distribution.

Dataset reality check: most music audio systems are trained on private scraped, licensed, or internal music collections that are not reproducible as public benchmark sources. Stable Audio is one of the few visible cases that trains and evaluates against a small set of higher-quality curated datasets. OpenRestore should use SonicMaster clean originals as the only default training source because it provides the most useful public scale for v1. The important difference is that OpenRestore creates paired clean/degraded examples from the selected source audio, so the benchmark can evaluate restoration directly instead of relying on naturally degraded recordings with unknown clean references.

Stable Audio 3 evaluates instrumental music on the Song Describer Dataset (SDD). OpenRestore should keep SDD as a validation source because it provides curated music recordings with human-written captions and 120-second source tracks from which deterministic 30-second validation windows can be derived. MUSDB18-HQ mixture audio should also be used as a small validation source for real mixed-music sanity checks.

### Benchmark Datasets

| Role | Decision | Rationale |
| --- | --- | --- |
| Training pool | Use only the clean original audio from SonicMaster Dataset as the default approved training source, if it passes license and quality checks. Do not use SonicMaster's degraded pairs as benchmark or leaderboard data. | SonicMaster clean originals provide the main public training scale for v1, while OpenRestore generates its own real-world degradations on top. Excluding SonicMaster's degraded pairs prevents the benchmark from inheriting their degradation design. |
| Validation splits | Use held-out SonicMaster clean audio, SDD, and MUSDB18-HQ mixture audio for validation. Do not use SDD or MUSDB18-HQ for training in the main track. | SonicMaster validation measures in-distribution behavior, SDD checks transfer to the curated captioned music source used by Stable Audio, and MUSDB18-HQ provides a small real mixed-music sanity check. |
| Public test split | Use held-out SonicMaster clean audio for the public test split. | The public test should match the default training source while remaining source-separated from training and validation items. |
| Hidden evaluation split | Use a separate secret custom dataset that is not publicly released. | A private organizer-only evaluation set prevents leakage of official leaderboard audio while the public train, validation, and test splits remain reproducible from documented sources. |

### Degradation Material Sources

| Role | Decision | Rationale |
| --- | --- | --- |
| Organic degradation material | Use sound datasets only as source material for degradation layers, not as clean benchmark audio. | BBC Sound Effects, Freesound, FSD50K, and MUSAN can provide ambience, noise, interference, or environmental beds for organic degradation chains that are mixed into clean music clips. |

The OpenRestore main-track training source is SonicMaster clean originals only. We split SonicMaster clean originals by source recording into training, validation, and public test subsets, then generate clean 30-second music clips and degraded 30-second versions for each split. Validation also includes SDD and MUSDB18-HQ mixture audio to test transfer beyond SonicMaster. Official leaderboard scoring uses a separate secret custom evaluation dataset that is not publicly released. SonicMaster's degraded pairs are not reused as benchmark or leaderboard data, and MUSDB18-HQ stems are not used as benchmark items in the main track. Degradation-source datasets are used only to synthesize degraded audio and are not part of the clean benchmark distribution. Any other training source belongs in the separate external-data track unless we explicitly revise the benchmark contract.

### Source Policy

- Do not make the benchmark a grab bag of every available audio dataset.
- Use SonicMaster clean originals as the only default main-track training source unless a specific license or quality audit blocks that role.
- Use a separate secret custom dataset for the organizer-only hidden evaluation split.
- Use held-out SonicMaster clean audio, SDD, and MUSDB18-HQ mixture audio for validation. Use held-out SonicMaster clean audio for the public test split. Do not train main-track models on SDD or MUSDB18-HQ.
- Do not reuse SonicMaster's degraded set as benchmark or leaderboard data.
- Use sound datasets only for degradation material, not as benchmark source music.
- Put any training source outside the approved pool in the external-data track.

### Curation Rules

- Keep only items with clear source records, creator or dataset attribution, and redistribution terms compatible with the selected release mode.
- Prefer high-fidelity stereo recordings with full bandwidth, stable loudness, no watermarks, no obvious mastering defects, and no broken metadata.
- Preserve original long clips where possible, then derive deterministic 30-second windows with metadata linking each window to its source clip.
- Normalize format deterministically: sample rate, channel count, loudness target, peak headroom, and file encoding.
- Split by stable grouped identifiers, not random windows, so the same source recording cannot appear across train, validation, and evaluation.

### License And Quality Audit

Every candidate source should pass a documented audit before it enters either the public benchmark source pool, the approved training pool, or the degradation-material pool. The audit should produce a versioned decision record with dataset name, version, access URL, review date, reviewer, intended role in OpenRestore, and final status: `accepted`, `accepted with filtering`, `internal-only`, or `rejected`.

#### License Audit

- Record the exact governing terms: dataset card, repository license, source-site terms, per-track terms, and any separate attribution requirements.
- Verify whether OpenRestore may download, transform, store, redistribute, and publicly mirror the audio, metadata, and derived degraded versions.
- Distinguish clearly between rights for internal organizer use, public benchmark release, and participant redistribution. A dataset may be acceptable for internal hidden evaluation yet not for public hosting.
- Check whether commercial use, model training, sublicensing, or public competition use is restricted.
- Check whether attribution must be preserved per item, per collection, or in a dataset-level notice.
- Reject sources with ambiguous provenance, contradictory license signals, or terms that cannot support the dataset's intended OpenRestore role.
- If only part of a dataset is usable, mark it `accepted with filtering` and define the exact inclusion rule in code and metadata.

#### Quality Audit

- Confirm that the source audio is real recorded music for benchmark/training roles, not synthesized, MIDI-rendered, or obviously AI-generated audio unless a later track explicitly allows that material.
- Check technical format: sample rate, bandwidth, codec history, mono/stereo layout, clipping, truncation, corrupted files, and gross metadata errors.
- Screen for audible defects in the clean source: watermarks, heavy codec artifacts, severe background noise, intrusive room coloration, distortion, dropouts, or non-musical contamination that would make the source unsuitable as clean reference audio.
- For mixed-music sources, verify task fit: the audio should behave like a real full mix. For MUSDB18-HQ, only the `mixture` track can be used, and only for validation unless the benchmark contract is revised; stems are excluded from the main track.
- For SonicMaster, verify that only the clean original audio is ingested into the approved training, validation, and public test splits; its degraded pairs must remain excluded from benchmark and leaderboard data.
- Run a small structured listening review on sampled items from each candidate dataset and document common failure modes and estimated reject rates.
- Run lightweight automated checks where possible: duration bounds, silence ratio, clipped-sample ratio, loudness distribution, channel consistency, checksum validity, and duplicate or near-duplicate detection against existing OpenRestore sources.
- If a dataset passes only after filtering, freeze the filtering rules in code so future releases reproduce the same inclusion logic.

#### Audit Outcome Rules

- `accepted`: the dataset can be used for its declared role without additional content filtering beyond routine preprocessing.
- `accepted with filtering`: the dataset is usable only after explicit item-level or subset-level exclusions that are recorded in code and manifests.
- `internal-only`: the dataset may be used for organizer-side hidden evaluation or internal experiments, but not redistributed in the public benchmark release.
- `rejected`: the dataset is excluded because its license, provenance, audio quality, or task fit is incompatible with OpenRestore.

## Data Model

`index.jsonl` is the authoritative inventory. It maps stable item IDs to storage locations, source metadata, segment metadata, degradation metadata, split assignment, prompt information, and rights metadata.

Recommended storage:

- `index.jsonl` remains the authoritative manifest, but its storage URIs and optional fields depend on the selected source dataset and release mode. SonicMaster-derived train/validation/public test clips, SDD validation clips, MUSDB18-HQ validation clips, and secret evaluation clips may therefore use different physical storage backends while sharing one schema.
- Internal canonical storage: HDF5 shards, WebDataset tar shards, or plain audio plus manifests, chosen after prototyping I/O with SDD and the expected evaluation workflow.
- Public mirror: dataset card, metadata, public train/validation/test assets, and an export format that supports reproducible local development.
- Archival release: manifests, metadata, checksums, degradation configs, evaluation scripts, and redistributable audio covered by the selected release terms.

Do not call the project sidecar "AudioMD JSON". [AudioMD](https://www.loc.gov/standards/amdvmd/) is a Library of Congress XML technical metadata schema. OpenRestore should define its own JSON item metadata and optionally provide an AudioMD-compatible XML export for preservation partners.

### Recommended JSONL Row

OpenRestore should keep the row close to the current restoration pipeline format. Every row represents one degraded 30-second example derived from one clean 30-second music segment. This makes training, evaluation, prompt conditioning, and degradation-specific reporting straightforward.

```json
{
  "name": "song_or_source_seg0002.wav",
  "id": "sample_0000001_song_or_source_seg0002_airy",
  "source_id": "song_or_source",
  "source_path": "sources/song_or_source.wav",
  "source_relative_path": "song_or_source.wav",
  "source_duration_sec": 241.1857,

  "segment_index": 2,
  "segment_start_sec": 60.0,
  "segment_end_sec": 90.0,
  "segment_duration_sec": 30.0,
  "duration": 30.0,
  "clip_start": 60.0,
  "clip_end": 90.0,
  "is_partial_segment": false,

  "sample_rate": 44100,
  "original_sample_rate": 44100,
  "source_channels": 2,
  "output_channels": 2,
  "original_length": 10636288,

  "clean_audio_path": "train_clean_30s/shard_0000.h5::/sample_0000001_song_or_source_seg0002",
  "clean_audio_dataset": "sample_0000001_song_or_source_seg0002",
  "clean_audio_shard": "train_clean_30s/shard_0000.h5",
  "clean_audio_index": 1,

  "degraded_audio_path": "train_degraded/airy/shard_0000.h5::/sample_00001_sample_0000001_song_or_source_seg0002_deg1",
  "degraded_audio_dataset": "sample_00001_sample_0000001_song_or_source_seg0002_deg1",
  "degraded_audio_shard": "train_degraded/airy/shard_0000.h5",

  "prompt": "Lift the top end for a more open character.",
  "alt_prompt": "Enhance the sense of space in the highs.",

  "degradation_tracking": {
    "eq_coloration": ["airy_lack_high_frequencies", {"high_shelf_hz": 12000, "gain_db": -6.0}],
    "dynamics": [],
    "reverb_room": [],
    "gain_level": [],
    "clipping_distortion": [],
    "stereo_spatial": [],
    "bandwidth_filtering": [],
    "noise_interference": [],
    "device_mic_response": [],
    "codec_resampling": [],
    "severity": "medium"
  },

  "hidden_clipping": [false, 0],
  "split": "train",
  "source_dataset": "song-describer-dataset",
  "license_spdx": "...",
  "attribution": "..."
}
```

### Field Groups

| Group | Fields | Purpose |
| --- | --- | --- |
| Identity | `id`, `name`, `source_id`, `source_dataset`, `split` | Stable identifiers for indexing, grouping, splitting, and reporting. |
| Source | `source_path`, `source_relative_path`, `source_duration_sec` | Links each segment back to the original full recording. |
| Segment | `segment_index`, `segment_start_sec`, `segment_end_sec`, `segment_duration_sec`, `clip_start`, `clip_end`, `is_partial_segment` | Makes fixed-window training and evaluation reproducible. |
| Audio format | `sample_rate`, `original_sample_rate`, `source_channels`, `output_channels`, `original_length` | Ensures the model output can be validated against the expected format. |
| Clean storage | `clean_audio_path`, `clean_audio_dataset`, `clean_audio_shard`, `clean_audio_index` | Points to the clean reference audio in the HDF5 shard. |
| Degraded storage | `degraded_audio_path`, `degraded_audio_dataset`, `degraded_audio_shard` | Points to the degraded input audio in the HDF5 shard. |
| Prompting | `prompt`, `alt_prompt` | Supports prompt-conditioned restoration and prompt-quality analysis. |
| Degradation metadata | `degradation_tracking`, `hidden_clipping` | Records which degradation families were applied and their compact parameters. |
| Rights | `license_spdx`, `attribution` | Keeps public release metadata connected to source rights. |

For public releases, avoid machine-specific absolute paths such as `/work/vita/...` in the canonical manifest. Store release-relative paths instead, and let local tooling resolve those paths against a dataset root. Internal manifests may keep absolute paths during generation, but exported manifests should be portable.

`degradation_tracking` is also the bridge to metric reporting: each non-empty family determines which degradation-specific metrics and AAE measurements should be computed for that item.

## Degradation Pipeline

### Degradation Taxonomy

OpenRestore v0.1 is effect-first: every single-degradation recipe names the audible degradation directly. The high-level group is retained only for organization, filtering, and reporting. Each effect samples deterministic random parameters from the ARIEL implementation; `ariel_random` is not a three-level preset.

#### v0.1 Degradation Set

| ID | Group | What the degradation does | Origin | Why it matters | Status | Benchmark role |
| --- | --- | --- | --- | --- | --- | --- |
| `comp` | Dynamics | Applies strong feed-forward compression with randomized threshold, ratio, attack, release, and makeup gain. | ARIEL implementation of SonicMaster's `comp` effect. | Represents flattened dynamics, reduced contrast, and over-compressed material. | Baseline parity | Single-effect |
| `punch` | Dynamics | Detects and attenuates transient peaks while preserving the rest of the signal. | ARIEL implementation of SonicMaster's `punch` effect. | Covers mixes that have lost impact because attacks are softened or suppressed. | Baseline parity | Single-effect |
| `xband` | EQ | Applies a randomized multi-band peaking EQ curve across the spectrum. | ARIEL implementation of SonicMaster's `xband` effect. | Produces broad, irregular tonal imbalance rather than a single shelf or cutoff. | Baseline parity | Single-effect |
| `mic` | EQ | Convolves the signal with one microphone transfer function. | SonicMaster's Poliphone microphone approach, using ARIEL-compatible `.npy` transfer functions. | Captures the spectral fingerprint of a real recording device. | Baseline parity | Single-effect |
| `bright` | EQ | Cuts the high shelf around 6 kHz, making the result insufficiently bright. | ARIEL implementation of SonicMaster's `bright` effect. | Models dull high frequencies and reduced presence. | Baseline parity | Single-effect |
| `dark` | EQ | Boosts the high shelf around 6 kHz, reducing audible darkness. | ARIEL implementation of SonicMaster's `dark` effect. | Adds excessive top-end energy that restoration models must identify and control. | Baseline parity | Single-effect |
| `airy` | EQ | Cuts the high shelf around 10 kHz. | ARIEL implementation of SonicMaster's `airy` effect. | Represents missing air and reduced openness in the extreme high frequencies. | Baseline parity | Single-effect |
| `boom` | EQ | Cuts the low shelf around 120 Hz. | ARIEL implementation of SonicMaster's `boom` effect. | Covers low-end imbalance and loss of weight in bass and kick content. | Baseline parity | Single-effect |
| `clarity` | EQ | Applies a low-pass filter around 4 kHz with randomized order. | ARIEL implementation of SonicMaster's `clarity` effect. | Models a clear, common loss of definition and intelligibility. | Baseline parity | Single-effect |
| `mud` | EQ | Isolates the 200-500 Hz region through a Chebyshev band-pass response. | ARIEL implementation of SonicMaster's `mud` effect. | Targets congested low-mid coloration that masks detail. | Baseline parity | Single-effect |
| `warm` | EQ | Cuts the low shelf around 400 Hz. | ARIEL implementation of SonicMaster's `warm` effect. | Covers insufficient warmth and thin lower-mid content. | Baseline parity | Single-effect |
| `vocal` | EQ | Applies a 350-3500 Hz Chebyshev band-stop response. | ARIEL implementation of SonicMaster's `vocal` effect. | Simulates recessed vocal and midrange content in a full mix. | Baseline parity | Single-effect |
| `small` | Reverb | Convolves audio with a randomized small Pyroomacoustics room. | SonicMaster small-room simulation, ported from ARIEL. | Represents close-room reflections and short acoustic coloration. | Baseline parity | Single-effect |
| `big` | Reverb | Convolves audio with a randomized large Pyroomacoustics room. | SonicMaster big-room simulation, ported from ARIEL. | Covers longer, more spacious room coloration and decay. | Baseline parity | Single-effect |
| `mix` | Reverb | Simulates a room with mixed absorptive and reflective wall materials. | SonicMaster mixed-room simulation, ported from ARIEL. | Adds frequency-dependent room coloration closer to varied real spaces. | Baseline parity | Single-effect |
| `real` | Reverb | Convolves audio with a selected stereo or B-format room impulse response. | SonicMaster openAIR-style real-RIR approach, ported from ARIEL. | Supplies real acoustic responses that complement simulated rooms. | Baseline parity | Single-effect |
| `stereo` | Stereo | Sums the left and right channels and duplicates the combined signal to both outputs. | ARIEL implementation of SonicMaster's `stereo` effect. | Tests restoration from collapsed stereo information. | Baseline parity | Single-effect |
| `clip` | Amplitude | Normalizes, amplifies by a sampled amount, then hard-clips the waveform. | ARIEL implementation of SonicMaster's `clip` effect. | Represents overload distortion and lost peak detail. | Baseline parity | Single-effect |
| `volume` | Amplitude | Normalizes then attenuates audio using one of ARIEL's low-volume multipliers. | ARIEL implementation of SonicMaster's `volume` effect. | Covers severe gain mismatch; it remains listed for parity with ARIEL, even if later evaluation decides it duplicates an existing volume task. | Baseline parity | Single-effect |
| `noise` | Noise | Adds colored broadband noise at a controlled SNR. | OpenRestore addition; ARIEL already contains calibrated white, pink, and brown noise helpers. | Covers persistent recording noise that is absent from the SonicMaster parity set. | OpenRestore addition - implemented | Listening review |
| `hum` | Noise | Adds 50 or 60 Hz electrical hum with decaying harmonics. | OpenRestore addition; ARIEL already contains a hum helper. | A recognizable real-world electrical fault with clear diagnostic behavior. | OpenRestore addition - implemented | Listening review |
| `codec` | Codec | Encodes and decodes through a lossy codec such as MP3, AAC, or Opus. | OpenRestore addition; ARIEL and OpenRestore have codec helpers. | Distribution and platform transcodes are common in music restoration inputs. | OpenRestore addition - implemented | Listening review |
| `bandwidth` | Filtering | Applies telephone, low-pass, high-pass, or low-sample-rate bandwidth loss. | OpenRestore addition; ARIEL has telephone and high-pass helpers. | Separates capture or transmission bandwidth loss from the broader SonicMaster EQ effects. | OpenRestore addition - implemented | Listening review |
| `distant_mic_capture` | Capture | Simulates a microphone recording several metres from the source: reduced direct-to-reverberant ratio, distance-related high-frequency loss, and optional low room noise. | OpenRestore addition, using a physically constrained Pyroomacoustics source/microphone geometry. | Covers acoustic distance as a capture problem, not merely reverb added to a close recording. | OpenRestore addition - implemented | Listening review |

#### Asset Requirements

The `mic` effect needs ARIEL-compatible microphone transfer functions in `parameters.mic_ir_dir`. The `real` effect needs compatible RIR WAV files in `parameters.real_rir_dir`. The remaining 22 effects run without external assets. Simulated room effects use the local `pyroomacoustics` dependency.

#### Recipe Inventory

Each recipe contains one named degradation from the table above. Every active effect is rendered explicitly; the runner never samples an effect choice or combines effects. Randomness is limited to the parameters of that selected effect.

Do not use mild, medium, and strong as separate recipe IDs. Intensity remains random within the effect's ARIEL range, with the item-level seed and every sampled value stored in metadata.

## Evaluation And Leaderboard

### Splits

- `train`: public clean and degraded pairs for model development.
- `validation`: public clean and degraded pairs for local debugging and ablations.
- `test`: public clean and degraded pairs for reproducible diagnostic reports before official submission.
- `evaluation`: hidden clean and degraded pairs used only by the organizers for official leaderboard scoring. Participants do not receive the audio or item list before evaluation.

### Leaderboard Policy

OpenRestore should be container-first and organizer-evaluated. Participants should not submit restored audio for the official leaderboard. They submit a runnable OCI/Docker container; the organizers run it on the hidden evaluation split, generate the restored audio, compute the metrics, and publish the result.

The main leaderboard should use only the approved OpenRestore training source: SonicMaster clean originals. Models must not train on validation, test, or evaluation audio, including SDD validation or MUSDB18-HQ validation audio. Submissions trained with any other datasets should be allowed only in a clearly separated `external-data` track.

The hidden evaluation split should prevent training on the exact benchmark clips, but it should not be a surprise-domain test. Prefer a secret custom dataset made of high-quality open-licensed or project-recorded music that follows the same documented curation rules as the public benchmark. Secret clips are fair; secret domains are likely to create an unfair distribution shift.

Public train/validation/test scores can be shown as diagnostics, but official ranking should come from the hidden evaluation split.

### Local User Workflow

1. Download the public versioned dataset release and metadata.
2. Train a model using the approved main-track training source: SonicMaster clean originals only. Declare any other training data, including SDD or MUSDB18-HQ, for the separate external-data track.
3. Tune and debug on `validation`, then optionally run a final public diagnostic check on `test`.
4. Run the OpenRestore CLI locally on public validation examples to produce a development `scores.json`.
5. Submit an OCI/Docker container containing the inference code and either bundled weights or a declared weight-download mechanism that works when the organizers run the container.

### Organizer Evaluation

- Accept a runnable OCI/Docker container, not restored audio files as the primary submission. The container must expose a documented inference command that reads degraded audio and item metadata from an input directory and writes restored audio to an output directory.
- The submitted container must include all inference code. Model weights should either be included in the image or downloaded from a declared, versioned URL during setup/run, with checksums recorded in the submission manifest.
- Organizers run the container on the hidden `evaluation` split, generate the restored audio themselves, and compute all metrics from clean, degraded, and restored audio.
- Validate duration, sample rate, channel count, loudness bounds, file naming, item IDs, and absence of invalid samples before scoring.
- Store submission manifest, container digest, logs, metrics, output checksums, and restored outputs for audit.
- Publish `leaderboard.json` and a static leaderboard page with separate approved-training-pool and external-data tracks.

## Metrics

OpenRestore should report metrics in separate families rather than collapse everything into one opaque score. The official leaderboard can still define a primary aggregate, but every submission should expose the underlying metric table by degradation family, severity, source subset, and clip duration.

### Required Metrics

| Family | Metrics | Comparison | Purpose |
| --- | --- | --- | --- |
| Pairwise reconstruction | L1, L2, SNR, SI-SDR, SI-SNR, log-spectral distance (LSD), multi-resolution STFT distance, mel-spectral distance, LTAS distance | Restored vs clean; degraded vs clean as the baseline floor | Measures whether the restored waveform/spectrum moved closer to the known clean reference. |
| Structural similarity | SSIM on log-mel or magnitude spectrograms; optional KL divergence between normalized spectral or embedding distributions | Restored vs clean; degraded vs clean | Captures spectro-temporal structure and distributional mismatch that simple L1/L2 may miss. |
| Embedding similarity | CLAP audio embedding cosine similarity; optional CLAP audio-text consistency when captions are available | Restored vs clean, and restored vs source caption for SDD items | Checks whether restored audio remains semantically close to the target audio/content. |
| Distributional audio quality | FAD restored vs clean; FAD-LAION restored vs clean; FAD-LAION restored vs FMA-Pop | Dataset-level only | Measures whether restored outputs match the clean evaluation distribution and whether they remain close to a broad high-quality music reference distribution. |
| Aesthetic/perceptual quality | Meta Audiobox Aesthetics CE, CU, PC, PQ; optional Zimtohrli or ViSQOL if practical | Restored absolute score, clean absolute score, and restored-clean gap | Estimates perceived content enjoyment, usefulness, production complexity, production quality, and general perceptual quality. |
| Degradation diagnostics | Average Absolute Error (AAE) by degradation family | Restored vs clean, and improvement over degraded | Measures whether the specific known artifact was actually removed, not just whether generic quality improved. |
| Operations | Runtime, hardware class, model size, failure rate, invalid output rate | Submission-level | Keeps the leaderboard reproducible and operationally honest. |

FAD variants should be explicit:

- `FAD-clean`: restored outputs compared against the clean evaluation references.
- `FAD-LAION-clean`: same comparison, but using LAION-CLAP or another explicitly named FADTK embedding backend.
- `FAD-LAION-FMA-Pop`: restored outputs compared against the FMA-Pop reference statistics distributed by FADTK. This is not a reconstruction metric; it is a broad music-quality/distribution sanity check.

### Degradation-Specific Diagnostics And AAE

AAE means `Average Absolute Error`, following the SonicMaster paper. The idea is to measure, for a degradation family, how far the restored audio remains from the clean reference in a targeted diagnostic space. Because OpenRestore generates degradations with known families and parameters, AAE can be reported only where the diagnostic descriptor is meaningful and validated.

For a degradation family `d`, define a descriptor `D_d(audio)` that returns a measurable artifact-related vector or scalar. Then report:

```text
AAE_d(restored) = mean(abs(D_d(restored) - D_d(clean)))
AAE_d(degraded) = mean(abs(D_d(degraded) - D_d(clean)))
AAE_reduction_d = 1 - AAE_d(restored) / max(AAE_d(degraded), epsilon)
```

This gives two useful views: the residual average absolute error after restoration, and the percentage improvement over the degraded input. AAE should only be official for degradation families where the descriptor is validated and stable.

Initial AAE descriptors:

| Degradation | Descriptor | Example AAE |
| --- | --- | --- |
| EQ / coloration | LTAS curve, band-energy ratios, spectral centroid/rolloff | L1/L2 distance between restored and clean LTAS or band-energy vectors. |
| Bandwidth loss | Estimated cutoff frequency, high-frequency energy ratio, spectral rolloff | Absolute cutoff error and high-band energy error relative to clean. |
| Noise / ambience | Residual noise floor, segmental SNR, known-noise residual when synthetic noise is mixed from a stored source | Residual noise estimate or residual injected-noise energy after restoration. |
| Clipping / saturation | Flat-top detector, clipped-sample ratio, crest factor, harmonic distortion proxy | Difference between restored and clean clipped-sample ratio or crest factor. |
| Dynamics | Loudness range, crest factor, peak-to-loudness ratio, short-term loudness variance | Distance between restored and clean dynamics descriptors. |
| Reverb / room | RT60 or decay-slope estimate, direct-to-reverberant ratio proxy, early/late energy ratio | Difference between restored and clean room/acoustic descriptors. |
| Stereo / spatial | Inter-channel correlation, mid/side energy ratio, channel balance, phase coherence | Distance between restored and clean stereo descriptors. |
| Codec / transmission | Band energy discontinuities, pre-echo proxy, modulation artifacts, codec-classifier confidence if validated | Residual codec-artifact descriptor error. Treat as experimental until the estimator is robust. |

SonicMaster reports degradation-specific behavior with AAE for its degradation groups instead of relying only on a single global score. OpenRestore should follow that principle, but keep the implementation transparent: each AAE descriptor must be open-source, versioned, tested on controlled degradations, and reported separately from perceptual metrics.

### Optional Metrics

- Additional psychoacoustic or learned perceptual metrics if they are available through open implementations.
- Subjective listening tests using pairwise A/B, MUSHRA-style panels, or expert ratings.
- SongEval or music-aesthetic metrics for a future generated-music or mastering track, not for the main restoration leaderboard.

## Baselines

Baselines are reference restoration systems that the OpenRestore team runs and publishes. They are not the final goal of the project. They make the leaderboard understandable by showing what happens when we do nothing, what simple audio processing can already fix, and what a small learned model can achieve.

OpenRestore should publish each baseline as runnable code or a runnable container, with its restored outputs and scores. This lets participants check that their local evaluation setup matches the official one.

| Baseline | What It Does | Why We Need It |
| --- | --- | --- |
| No-restoration baseline | Copies the degraded input directly to the output. No model, no processing. | This is the minimum reference point. A useful restoration model should improve over the degraded input, not make it worse. |
| Simple DSP baseline | Applies a few transparent signal-processing methods, for example denoising, declipping, basic EQ correction, simple dereverberation, or bandwidth repair when the degradation family is known. | This shows what can be fixed without machine learning. If a neural model cannot beat simple DSP on a degradation, that is important to know. |
| Small learned baseline | Trains a compact open model only on the public OpenRestore training split. | This gives a realistic first neural reference without relying on massive external datasets. It helps participants understand the expected difficulty of the benchmark. |

Later, OpenRestore can add stronger reference models aligned with current generative-audio research: audio-to-audio diffusion and Schrodinger-bridge restorers such as A2SB, latent diffusion or diffusion-transformer audio models, flow-matching or rectified-flow audio models, foundation audio models with inpainting or audio-to-audio conditioning, and specialist generative restorers for declipping, dereverberation, bandwidth extension, and codec artifact reduction. These should be added only when their licenses, training data, task assumptions, and inference requirements are clear.

Publish baseline scores for public train/validation/test diagnostics and for the hidden evaluation split. In the leaderboard, these baselines should appear as fixed reference rows, not as competing teams.

## Submission Manifest

A submission manifest is the instruction sheet for a submitted model container. It tells the organizers what the model is, who submitted it, how to run it, where the weights are, and what data was used for training.

This matters because OpenRestore should not ask participants to restore the hidden evaluation audio themselves. Participants submit a runnable OCI/Docker container. The organizers run that container on the hidden evaluation split, generate the restored audio, compute the metrics, and publish the score.

The manifest should be a small YAML or JSON file submitted with the container:

```yaml
submission_id: team-model-version
model_name: ExampleRestorer
authors:
  - name: ...
contact: ...
code_url: ...
code_commit: ...
container_image: registry.example.org/openrestore/example:<release>
container_digest: sha256:...
openrestore_release: <release>
weights:
  mode: bundled-or-download
  uri: https://example.org/model-weights.ckpt
  sha256: ...
training_data:
  - OpenRestore train <release>
  - external data, declared with licenses if entering the external-data track
inference_command: >
  python -m openrestore_infer --input /input --metadata /input/index.jsonl --output /output
hardware_requested:
  accelerator: none
  max_runtime_minutes: 120
method_summary: >
  Short public description of the method.
```

Important fields:

| Field | Meaning |
| --- | --- |
| `container_image` and `container_digest` | The exact Docker/OCI image the organizers will run. The digest prevents the image from silently changing. |
| `weights` | Whether the model weights are inside the image or downloaded at runtime. If downloaded, the URL and checksum must be fixed. |
| `training_data` | What data was used to train the model. The main leaderboard uses the approved training pool; any other data belongs in a separate external-data track. |
| `inference_command` | The exact command the organizers run inside the container. It must read degraded audio from `/input` and write restored audio to `/output`. |
| `hardware_requested` | The compute environment needed to run evaluation within a reasonable time. |
| `method_summary` | A short public explanation of the method shown beside the leaderboard entry. |

The container must be runnable without manual intervention beyond pulling the image and, if declared, downloading fixed-version weights.

## Implementation Plan

### Submissions And Leaderboard Modules

In the implementation roadmap, `openrestore/submissions` and `openrestore/leaderboard` are not
model code. They are the benchmark contract around participant evaluation and public reporting.

`openrestore/submissions` should define how participants package a restoration system for official
evaluation. A submission is a runnable OCI/Docker container plus a manifest, not a folder of
restored hidden-evaluation audio. This module should own the submission manifest parser and
validator, the container interface specification, training-data declarations, weight URI/checksum
rules, hardware/runtime declarations, and invalid-submission checks. Its job is to answer: can the
organizers run this system reproducibly on the hidden evaluation split, and does it belong in the
main track or the external-data track?

`openrestore/leaderboard` should define how evaluated submissions become public results. It should
take versioned score files, submission metadata, baseline rows, and benchmark release metadata, then
produce a stable `leaderboard.json` and a static public table. This module should own score
aggregation, main-track versus external-data ranking, per-degradation-family summaries, validation
of leaderboard entries, release snapshots, and static rendering. Its job is to answer: how are
systems compared, ranked, and published after the organizers have run evaluation?

These modules depend on the lower-level pipeline in this order: `data` builds the public and hidden
evaluation manifests, `degradations` creates paired inputs, `metrics` scores restored outputs,
`evaluation` runs containers and validates outputs, `submissions` validates participant metadata,
and `leaderboard` publishes the resulting scores.

### Repository Layout

The repository should separate public benchmark code from generated data. Audio shards, model weights, hidden evaluation files, and restored outputs should live in release/storage locations, not directly in the Git repository.

```text
openrestore/
  README.md
  OpenRestore.md
  pyproject.toml

  configs/
    datasets/
      sdd.yaml
      bbc_sound_effects.yaml
    degradations/
      single/
    evaluation/
      metrics.yaml
      leaderboard.yaml
    containers/
      submission_interface.yaml

  schemas/
    index.schema.json
    degradation_tracking.schema.json
    submission_manifest.schema.json
    scores.schema.json
    leaderboard.schema.json

  openrestore/
    data/
      ingest_sdd.py
      ingest_bbc.py
      segment.py
      shards.py
      validate_index.py
    degradations/
      eq.py
      dynamics.py
      reverb.py
      amplitude.py
      stereo.py
      noise.py
      filters.py
      codec_resampling.py
      recipes.py
      tracking.py
    metrics/
      reconstruction.py
      fad.py
      clap.py
      audiobox_aesthetics.py
      aae.py
      aggregation.py
    evaluation/
      run_container.py
      run_inference.py
      score_outputs.py
      validate_outputs.py
      report.py
    submissions/
      manifest.py
      container_spec.py
    leaderboard/
      build.py
      render.py

  baselines/
    no_restoration/
    simple_dsp/
    small_learned/

  scripts/
    build_public_release.py
    build_hidden_evaluation.py
    run_degradations.py
    evaluate_submission.py
    build_leaderboard.py

  docker/
    evaluator/
    baseline_no_restoration/
    baseline_simple_dsp/
    baseline_small_learned/

  site/
    docs/
    leaderboard/
    static/

  examples/
    index_row.json
    submission_manifest.yaml
    local_evaluation.sh

  tests/
    data/
    degradations/
    metrics/
    evaluation/
    schemas/
```

Generated or external artifacts should be excluded from Git and referenced through manifests:

```text
data/
  public/
    train/
    validation/
  private/
    evaluation/
  releases/
outputs/
  submissions/
  baselines/
weights/
```

### CI And Quality Gates

- Validate `index.jsonl` and submission manifests against JSON Schema.
- Verify that every referenced storage key exists.
- Decode a sample of clean and degraded audio from every shard.
- Recompute checksums for release candidates.
- Regenerate a fixed miniature dataset and compare checksums within the same pipeline version.
- Run unit tests for degradation modules and metric aggregation.
- Rebuild the static leaderboard from `leaderboard.json`.
- Generate release statistics: duration by split, domain, source dataset, license, degradation family, and severity.

## Release And Sustainability Plan

OpenRestore should use a lightweight release process that is easy to maintain. The goal is not to build a complex archival infrastructure; the goal is to make each public release reproducible, citable, and easy to download.

Core release layers:

| Layer | Use |
| --- | --- |
| Git repository | Canonical source for code, degradation configs, schemas, evaluation scripts, baseline code, documentation, and leaderboard generation. |
| Hugging Face Datasets | Public distribution of train/validation/test metadata, public audio assets when licensing allows, dataset cards, and loading examples. |
| Zenodo | Frozen release archive with DOI for papers, reports, and grant deliverables. Archive the exact manifests, configs, schemas, evaluation scripts, baseline definitions, and public metadata used for a release. |
| Static website | Documentation and leaderboard generated from versioned files such as `leaderboard.json`, submission manifests, and release notes. GitLab Pages or GitHub Pages is enough. |
| Organizer private storage | Hidden evaluation audio, clean references, evaluation manifests, container logs, restored outputs, and audit checksums. These are not public, but they must be backed up and versioned internally. |

Each release should include:

- Public `index.jsonl` files for train/validation/test.
- Dataset card and source-license summary.
- Degradation recipes and versioned degradation code.
- Evaluation code, metric versions, and baseline definitions.
- Baseline scores on public validation/test and hidden evaluation.
- Leaderboard snapshot and release notes.
- Checksums for all public artifacts.

Keep optional infrastructure optional. RenkuLab, DaSCH, or other preservation platforms can be added later if a funder, partner, or archive requirement makes them useful, but they should not be required for the benchmark to run.

## Roadmap

### 1. Freeze The Benchmark Contract

- Define the task precisely: one degraded musical clip in, one restored clip out.
- Fix the split policy: public `train`, public `validation`, public `test`, hidden organizer-only `evaluation`.
- Fix the leaderboard policy: container-first submissions, approved-training-pool main track, separate external-data track.
- Choose canonical audio settings: sample rate, channel handling, segment lengths, loudness normalization, and output validation rules.
- Finalize the JSONL row schema around the current fields: source metadata, segment metadata, HDF5 paths, prompts, `degradation_tracking`, `hidden_clipping`, split, and rights metadata.

### 2. Build The Dataset Pipeline

- Implement ingestion of SonicMaster clean originals as the only default training source if its license and quality checks pass. Do not ingest SonicMaster's degraded set as benchmark or leaderboard data.
- Split SonicMaster clean originals by source recording into public train, validation, and public test subsets.
- Implement SDD and MUSDB18-HQ mixture ingestion for validation only, and do not use MUSDB18-HQ stems as benchmark items in the main track.
- Define and curate a separate secret custom evaluation dataset for organizer-only scoring.
- Implement optional sound-dataset ingestion only for organic degradation material such as ambience, noise, or interference.
- Segment long music sources into deterministic 30-second windows while preserving links to the original source recording.
- Build HDF5 shards and portable `index.jsonl` manifests with release-relative paths.
- Generate the public train/validation/test splits from SonicMaster source-level groups, plus separate SDD and MUSDB18-HQ validation manifests.
- Generate the hidden evaluation split from the secret custom dataset.
- Produce dataset statistics: duration, source dataset, degradation family, prompt coverage, license status, sample rate, channels, and segment length.

### 3. Implement Degradations And Tracking

- Implement the v0.1 primitive degradations first: `eq_coloration`, `dynamics`, `reverb_room`, `gain_level`, `clipping_distortion`, `stereo_spatial`, `bandwidth_filtering`, `noise_interference`, `device_mic_response`, and `codec_resampling`.
- Keep first-release modules close to SonicMaster: EQ/filtering, dynamics, reverb, gain, clipping/saturation, stereo, microphone/device response, noise/hum/ambience, bandwidth loss, and conventional codec/resampling loss.
- Store compact per-item metadata in `degradation_tracking` and keep full recipe/config files versioned with the release.
- Use one explicitly selected degradation per output in v0.1. Do not sample effect choices or combine effects; sample only the selected effects parameters.
- Validate each degradation on a small fixed fixture set so outputs are reproducible across releases.

### 4. Implement Metrics And Reports

- Implement pairwise reconstruction metrics: L1, L2, SNR, SI-SDR/SI-SNR, LSD, STFT, mel distance, and LTAS distance.
- Implement perceptual and embedding metrics: CLAP similarity, FAD, FAD-LAION, FAD-LAION-FMA-Pop, and Meta Audiobox Aesthetics CE/CU/PC/PQ.
- Implement structural/distributional metrics: SSIM and KL where appropriate.
- Implement AAE diagnostics by degradation family, following the SonicMaster principle of degradation-specific reporting.
- Build a report generator that aggregates metrics by degradation family, severity, source subset, prompt type, and clip duration.

### 5. Build Baselines

- Add the no-restoration baseline and publish its scores.
- Add the simple DSP baseline and publish its scores by degradation family.
- Train or adapt a small learned baseline using only the public OpenRestore training split.
- Package baselines as runnable code or containers so users can reproduce the scores.
- Use baseline results to sanity-check metrics, degradation recipes, and leaderboard aggregation.

### 6. Build Container Evaluation

- Define the submission container interface: input directory, metadata path, output directory, inference command, and expected audio format.
- Implement submission manifest validation, including container digest, training-data declaration, weight URL/checksum, and hardware request.
- Implement organizer-side evaluation: pull container, prepare hidden evaluation input, run inference, validate outputs, compute metrics, store logs/checksums.
- Add safeguards for timeouts, invalid files, missing outputs, sample-rate mismatches, and unstable weight downloads.

### 7. Publish The First Release

- Publish public train/validation/test metadata and redistributable audio assets where licensing allows.
- Publish degradation configs, schemas, evaluation code, metric versions, baseline code, and baseline scores.
- Archive the release on Zenodo with a DOI.
- Publish the documentation and static leaderboard site.
- Open the submission process with clear instructions and example containers.

### 8. Extend Carefully

- Add listening tests once objective metrics and baselines are stable.
- Add stronger generative-audio baselines, such as audio-to-audio diffusion, Schrodinger-bridge, flow-matching, or foundation-model restorers, when licenses and training assumptions are clear.
- Add specialized music tracks only when needed: remastering, bandwidth extension, codec repair, or device-capture restoration.
- Publish periodic benchmark reports with frozen leaderboard snapshots.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Dataset licensing ambiguity | Maintain a source-license table and filter the default release to the selected open licenses. |
| Metrics disagree with human perception | Use multiple metric families, publish per-degradation breakdowns, and add listening tests before making strong perceptual claims. |
| Closed tooling harms reproducibility | Core degradations and metrics must use open-source implementations, open assets, and versioned parameters. |
| Storage and bandwidth cost | Use shards, compression where appropriate, mirrors, checksums, and staged releases. |
| Leaderboard gaming | Require runnable containers, training-data disclosure, container digests, fixed weight checksums, output validation, audit logs, and per-family reporting. |

## Positioning And Related Work

OpenRestore should learn from related benchmarks without duplicating them.

| Project | What It Contributes | Implication For OpenRestore |
| --- | --- | --- |
| [Music Source Restoration / RawStems](https://arxiv.org/abs/2505.21827) | Defines music source restoration as recovery of unprocessed sources from degraded or professionally processed mixtures; introduces RawStems annotations. | Use its degradation families, instrument grouping, and evaluation ideas as references, while keeping OpenRestore focused on one input signal and one restored output. |
| [MSRBench](https://arxiv.org/abs/2510.10995) and [MSR Challenge](https://msrchallenge.com/) | Provides a benchmark for music source restoration with raw-processed pairs and real-world degradations; challenge reports use metrics such as Multi-Mel-SNR, Zimtohrli, and FAD-CLAP. | Treat as the closest music-restoration benchmark. OpenRestore should be simpler: single musical clip in, restored musical clip out. |
| [SonicMaster](https://arxiv.org/abs/2508.03448) and [SonicMaster Dataset](https://huggingface.co/datasets/amaai-lab/SonicMasterDataset) | Trains an all-in-one music restoration and mastering model using paired degraded/high-quality music generated with degradation groups such as equalization, dynamics, reverb, amplitude, and stereo. | Use its taxonomy, prompt-conditioned restoration framing, and AAE-style degradation diagnostics as starting points, while keeping OpenRestore recipes transparent and reproducible. |
| [Audio Degradation Toolbox](https://qmro.qmul.ac.uk/xmlui/handle/123456789/6061) | Provides an early open toolbox for controlled music degradations, including chained degradations intended to mimic real-world conditions. | Directly supports deterministic modules plus organic multi-step chains. Reimplement or modernize concepts in Python rather than depending on the original Matlab stack. |
| [ODAQ: Open Dataset of Audio Quality](https://arxiv.org/abs/2401.00197) and [expanded ODAQ](https://arxiv.org/abs/2504.00742) | Provides open audio stimuli with expert and later expanded listener quality ratings across controlled processing classes. | Useful for validating perceptual metrics and for designing listening-test protocols; not a restoration benchmark by itself. |
| [A2SB](https://arxiv.org/abs/2501.11311) | A high-resolution music restoration model for 44.1 kHz bandwidth extension and audio inpainting. | Important baseline family for bandwidth loss, missing segments, and long-audio restoration behavior. |
| [Apollo](https://arxiv.org/abs/2409.08514) and [Stochastic Restoration GAN](https://arxiv.org/abs/2207.01667) | Focus on restoring heavily compressed musical audio and codec artifacts. | Useful references for the codec-loss track, especially where reconstruction and perceptual quality may disagree. |
| [AudioSR](https://arxiv.org/abs/2309.07314), [FlashSR](https://arxiv.org/abs/2501.10807), and [UniverSR](https://arxiv.org/abs/2510.00771) | Versatile audio super-resolution systems that target music, speech, and sound effects across low sample rates. | Useful baseline candidates for bandwidth-extension degradations, though OpenRestore should report music-specific results separately. |
| [Smule Renaissance Small / Extreme Degradation Bench](https://arxiv.org/abs/2510.21659) | Introduces an efficient vocal restoration model and a benchmark of singing and speech recordings captured under severe multi-degradation conditions. | Relevant for organic degradation design and singing/vocal subsets, while OpenRestore remains broader than vocals. |
| [Microsoft DNS Challenge](https://github.com/microsoft/DNS-Challenge) | Mature challenge infrastructure for speech enhancement, with datasets, baselines, and subjective evaluation protocols. | Borrow challenge mechanics, submission discipline, and subjective-test thinking. Speech restoration can be a later track. |
| [Clarity Challenge](https://claritychallenge.org/) | Hearing-aid enhancement challenges with structured train/dev/eval splits and perceptual/intelligibility metrics. | Borrow split discipline and clear task definitions, especially if OpenRestore adds speech or hearing-aid tracks. |
| [Stable Audio 3](https://arxiv.org/abs/2605.17991), [ACE-Step](https://arxiv.org/abs/2506.00045), [ACE-Step 1.5](https://arxiv.org/abs/2602.00744) | Modern open or partially open music/audio generation and editing systems. | Useful for source selection, evaluation precedent, and future baselines, but not part of the core restoration benchmark. |

## References

- FAIR Principles: <https://www.go-fair.org/fair-principles>
- Swiss Open Research Data: <https://www.swissuniversities.ch/en/topics/open-science/open-research-data>
- AudioMD and VideoMD, Library of Congress: <https://www.loc.gov/standards/amdvmd/>
- Music Source Restoration / RawStems: <https://arxiv.org/abs/2505.21827>
- MSRBench: <https://arxiv.org/abs/2510.10995>
- MSR Challenge: <https://msrchallenge.com/>
- SonicMaster: <https://arxiv.org/abs/2508.03448>
- SonicMaster Dataset: <https://huggingface.co/datasets/amaai-lab/SonicMasterDataset>
- Audio Degradation Toolbox: <https://qmro.qmul.ac.uk/xmlui/handle/123456789/6061>
- ODAQ: <https://arxiv.org/abs/2401.00197>
- Expanding and Analyzing ODAQ: <https://arxiv.org/abs/2504.00742>
- A2SB: <https://arxiv.org/abs/2501.11311>
- AudioX: <https://arxiv.org/abs/2503.10522>
- MeanAudio: <https://arxiv.org/abs/2508.06098>
- Apollo: <https://arxiv.org/abs/2409.08514>
- Stochastic Restoration of Heavily Compressed Musical Audio: <https://arxiv.org/abs/2207.01667>
- AudioSR: <https://arxiv.org/abs/2309.07314>
- FlashSR: <https://arxiv.org/abs/2501.10807>
- UniverSR: <https://arxiv.org/abs/2510.00771>
- Smule Renaissance Small / Extreme Degradation Bench: <https://arxiv.org/abs/2510.21659>
- Extreme Degradation Bench dataset: <https://huggingface.co/datasets/smulelabs/ExtremeDegradationBench>
- Microsoft DNS Challenge: <https://github.com/microsoft/DNS-Challenge>
- Clarity Challenge: <https://claritychallenge.org/>
- Frechet Audio Distance: <https://arxiv.org/abs/1812.08466>
- FADTK: <https://arxiv.org/abs/2311.01616>
- LAION-CLAP: <https://github.com/LAION-AI/CLAP>
- CLAP / Language-Audio Pretraining: <https://arxiv.org/abs/2206.04769>
- Meta Audiobox Aesthetics: <https://arxiv.org/abs/2502.05139>
- SSIM: <https://ieeexplore.ieee.org/document/1284395>
- Kullback-Leibler divergence: <https://doi.org/10.1214/aoms/1177729694>
- MUSHRA listening test recommendation ITU-R BS.1534: <https://www.itu.int/rec/R-REC-BS.1534>
- Zimtohrli: <https://arxiv.org/abs/2509.26133>
- Stable Audio 3: <https://arxiv.org/abs/2605.17991>
- Song Describer Dataset: <https://github.com/mulab-mir/song-describer-dataset>
- Song Describer Dataset paper: <https://arxiv.org/abs/2311.10057>
- BBC Sound Effects: <https://sound-effects.bbcrewind.co.uk/>
- BBC Sound Effects licensing: <https://sound-effects.bbcrewind.co.uk/licensing>
- Free Music Archive dataset: <https://github.com/mdeff/fma>
- FMA dataset paper: <https://arxiv.org/abs/1612.01840>
- Freesound datasets: <https://labs.freesound.org/datasets/>
- FSD50K: <https://fsannotator.upf.edu/fsd/release/FSD50K/>
- MUSAN: <https://www.openslr.org/17/>
- ACE-Step: <https://arxiv.org/abs/2506.00045>
- ACE-Step 1.5: <https://arxiv.org/abs/2602.00744>
- Hugging Face Dataset Cards: <https://huggingface.co/docs/hub/datasets-cards>
- Zenodo DOI versioning: <https://zenodo.org/help/versioning>
- GitLab Pages: <https://docs.gitlab.com/ee/user/project/pages/>
- GitHub Pages: <https://docs.github.com/en/pages>
