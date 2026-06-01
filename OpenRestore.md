# OpenRestore

OpenRestore is an open, reproducible benchmark for musical audio restoration. It curates high-quality clean audio, generates controlled and organic degradation chains, evaluates restoration systems with reconstruction and perceptual metrics, and publishes datasets, baselines, reports, and a public leaderboard.

Internal application link: [CHORD-VITA application](https://docs.google.com/document/d/1jHbahFTKmkAgQGIGbRLSNHwxb-EY-tgN)

## Executive Summary

Musical audio restoration research is fragmented across denoising, dereverberation, declipping, bandwidth extension, codec repair, remastering, and general audio cleanup. OpenRestore will provide a shared benchmark for comparing restoration systems on complete musical audio clips, using deterministic degradations, high-quality source material, reproducible evaluation, and transparent metadata.

The benchmark should stay focused: one degraded mixed musical signal in, one restored signal out. Participants submit runnable containers, not restored evaluation audio. Organizers run those containers on a hidden evaluation split and publish scores on a leaderboard with an OpenRestore-train-only main track and a separate external-data track.

## What We Are Building

OpenRestore is a benchmark, not a single model. Two source collections anchor the plan: the Song Describer Dataset (SDD), a captioned collection of freely licensed music recordings, and BBC Sound Effects, a professionally produced library of sound effects and ambience. It consists of:

- A high-quality clean audio source pool centered on SDD, with BBC Sound Effects used for ambience, sound effects, and organic degradation material.
- A deterministic degradation pipeline that creates paired clean/degraded examples.
- A JSONL manifest format close to the current restoration pipeline schema.
- Public train and validation splits for development.
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
- Domains: high-quality musical material first, primarily from SDD; sound effects and ambience can support organic degradation or a separate sound-effect restoration subset.
- Clip length: support native clips up to 120 seconds, with fixed 10-second and 30-second windows for fast training, evaluation, and ablation runs.
- Sample rate: choose one canonical rate, preferably 44.1 kHz or 48 kHz stereo, with explicit conversion rules for sources that are mono or use a different rate.

### Out Of Scope

- Stem separation as the main task. The benchmark restores one degraded musical signal into one improved musical signal.
- Speech-only enhancement as a primary track. Speech can be revisited later if the project expands beyond music.
- Prompt-to-audio generation or music aesthetic scoring as a main task.
- Non-reproducible degradation steps. Every benchmark degradation should be implemented with open-source code, open assets, and recorded parameters.

### Key Decisions

- Build a single-clip musical restoration benchmark: one degraded mixed signal in, one restored signal out.
- Use SDD as the primary music source, with BBC Sound Effects reserved for high-quality ambience, sound effects, and organic degradation material.
- Keep the official evaluation split hidden, but drawn from the same documented source policy; avoid surprise-domain evaluation.
- Use container-first submissions: participants submit inference code plus weights, and organizers run restoration on the hidden evaluation split.
- Make the main leaderboard OpenRestore-train-only, with a separate external-data track for models trained on additional datasets.
- Treat AudioMD as an optional XML preservation export, not as the native JSON metadata format.
- Keep required metrics focused on one-to-one reconstruction and perceptual quality, with experimental metrics in optional reports.
- Keep all degradations open-source, reproducible, and fully specified in metadata.
- Prioritize real-world organic degradation profiles over a broad inherited list of lab-style effects.

## Dataset Strategy

OpenRestore should prioritize a small number of high-quality reference datasets over a broad pool of uneven sources. The benchmark should start from the same kind of evaluation material used by Stable Audio 3: professionally produced or carefully curated audio, long enough to evaluate musical structure, and clean enough that restoration metrics measure the degradation rather than defects in the source.

Dataset reality check: most music audio systems are trained on private scraped, licensed, or internal music collections that are not reproducible as public benchmark sources. Stable Audio is one of the few visible cases that trains and evaluates against a small set of higher-quality curated datasets. Beyond SDD and BBC Sound Effects, OpenRestore has not identified a stronger public dataset candidate for v1. The important difference is that OpenRestore creates paired clean/degraded examples from the selected source audio, so the benchmark can evaluate restoration directly instead of relying on naturally degraded recordings with unknown clean references.

Stable Audio 3 evaluates instrumental music on the Song Describer Dataset (SDD) and sound effects on the BBC Sound Effects Dataset. In that setup, SDD is filtered to instrumental, coherent, non-ambiguous prompts, producing 424 music-caption pairs. BBC Sound Effects is filtered into duration subsets up to 120 seconds, 30 seconds, 10 seconds, and 5 seconds; the paper notes that BBC is preferred over AudioCaps because its reference audio is professionally produced and full-bandwidth.

### Primary Sources

| Source | Role In OpenRestore | Why It Fits | Caveat |
| --- | --- | --- | --- |
| [Song Describer Dataset (SDD)](https://github.com/mulab-mir/song-describer-dataset) | Primary music source and main restoration benchmark material. Use the highest-quality compatible subset as the default target. | Human-written captions, freely licensed music recordings, 120-second tracks, and direct precedent in Stable Audio 3 evaluation. | Filter carefully: remove incoherent captions, ambiguous prompts, poor-quality audio, and any item whose source license is not compatible with redistribution. |
| [BBC Sound Effects](https://sound-effects.bbcrewind.co.uk/) | High-quality sound-effect and ambience source. Use for organic degradation beds, room/field ambience, transient events, and optionally a separate sound-effect restoration subset. | Professional full-bandwidth recordings, broad real-world sound coverage, and direct precedent in Stable Audio 3 evaluation. | BBC licensing is research/education/personal by default, with commercial licensing handled separately. Treat it as a research benchmark source unless the release policy confirms broader reuse. |

### Source Policy

- Do not make the benchmark a grab bag of every available audio dataset.
- Use SDD as the main musical reference set unless a specific source fails the license or quality audit.
- Use BBC Sound Effects selectively for high-quality ambience, environmental beds, and sound-effect restoration, not as a substitute for music.
- Keep broad, uneven, or weakly curated audio collections out of the default source pool unless the project later needs scale or a specific missing condition.
- If more music is needed after SDD, add it only through a second curated high-quality source with clear audio quality, metadata, and licensing. Candidate expansion sources should be evaluated one by one rather than imported wholesale; do not spend v1 scope chasing marginal datasets just to make the source list longer.

### Curation Rules

- Keep only items with clear source records, creator or dataset attribution, and redistribution terms compatible with the selected release mode.
- Prefer high-fidelity stereo recordings with full bandwidth, stable loudness, no watermarks, no obvious mastering defects, and no broken metadata.
- Preserve original long clips where possible, then derive deterministic 10-second and 30-second evaluation windows with metadata linking each window to its source clip.
- Normalize format deterministically: sample rate, channel count, loudness target, peak headroom, and file encoding.
- Split by stable grouped identifiers, not random windows, so the same source recording cannot appear across train, validation, and evaluation.

## Data Model

`index.jsonl` is the authoritative inventory. It maps stable item IDs to storage locations, source metadata, segment metadata, degradation metadata, split assignment, prompt information, and rights metadata.

Recommended storage:

- `index.jsonl` remains the authoritative manifest, but its storage URIs and optional fields depend on the selected source dataset and release mode. SDD-derived clips, BBC-derived clips, public development data, and hidden evaluation data may therefore use different physical storage backends while sharing one schema.
- Internal canonical storage: HDF5 shards, WebDataset tar shards, or plain audio plus manifests, chosen after prototyping I/O with SDD/BBC and the expected evaluation workflow.
- Public mirror: dataset card, metadata, public train/validation assets, and an export format that supports reproducible local development.
- Archival release: manifests, metadata, checksums, degradation configs, evaluation scripts, and redistributable audio covered by the selected release terms.

Do not call the project sidecar "AudioMD JSON". [AudioMD](https://www.loc.gov/standards/amdvmd/) is a Library of Congress XML technical metadata schema. OpenRestore should define its own JSON item metadata and optionally provide an AudioMD-compatible XML export for preservation partners.

### Recommended JSONL Row

OpenRestore should keep the row close to the current restoration pipeline format. Every row represents one degraded example derived from one clean source segment. This makes training, evaluation, prompt conditioning, and degradation-specific reporting straightforward.

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
    "EQ": ["airy", [12]],
    "Dynamics": [],
    "Reverb": [],
    "Amplitude": [],
    "Stereo": [],
    "Noise": [],
    "Filter": [],
    "Tape": [],
    "Composite": [],
    "Calibrated": [],
    "OrganicProfile": [],
    "Codec": [],
    "NeuralCodec": []
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

Every degradation must be deterministic from `(clean audio, recipe config, module versions, seed)`. Each output must record the applied degradation families and compact parameters in `degradation_tracking`, with full recipe/config files versioned alongside the dataset release. The v1 benchmark should move away from copying a fixed historical panel such as the 19 SonicMaster-style degradations as its main target. Those primitive families remain useful for diagnostics, but the official emphasis should be organic chains that feel like real musical damage: a track played through a room, captured by a device, compressed by a platform, clipped by gain staging, or mixed with ambience before being restored.

The current composite prototypes already point in the right direction: `crackle`, `highpass`, `hum`, `low_sr`, `noise`, `pitch_instability`, `soft_clip`, and `telephone`. OpenRestore should expand that idea into named, reproducible real-world profiles so users can evaluate themselves against conditions that resemble actual restoration work.

### Degradation Families

| Family | Examples | Implementation Notes |
| --- | --- | --- |
| Spectral and EQ | Low-pass, high-pass, shelving, peaking, band-stop, telephone band, microphone response EQ | Use SciPy filters, FIR/IIR recipes, or measured impulse responses with documented provenance. |
| Dynamics | Compression, limiting, transient softening, pumping, over-normalization | Implement with open DSP code and fixed parameter ranges. |
| Nonlinear distortion | Soft clipping, hard clipping, saturation, waveshaping, bit depth reduction | Include both mild and severe settings; store true pre/post peak levels. |
| Noise and interference | Hiss, hum, broadband noise, crowd or room ambience, clicks, crackle, dropouts | Use open-licensed noise sources; store SNR and event timing. |
| Room and acoustics | Synthetic reverb, measured room impulse responses, early reflections | Use open IRs where possible; Pyroomacoustics or equivalent for simulation. |
| Stereo and spatial | Stereo collapse, narrowing, channel imbalance, one-sided channel loss, phase issues | Include mono compatibility checks and channel correlation metrics. |
| Bandwidth and codecs | MP3, AAC, Opus, EnCodec or DAC-style neural codecs where available | Prefer FFmpeg and open codec implementations. Record codec, bitrate, sample rate, and encoder version. |
| Organic multi-step chains | Room coloration plus noise, codec plus saturation, playback-through-speaker simulation, worn-media style chains, mobile-recording style chains | Compose open-source modules into realistic sequences that resemble naturally accumulated degradation rather than isolated lab effects. |

### Real-World Degradation Inventory

The first public inventory should contain 20 named profiles. Each profile should have fixed severity bands, isolated diagnostic descriptors where possible, and at least one organic chain recipe that combines the relevant primitive modules.

| ID | Real-World Condition | Typical Components | What It Tests |
| --- | --- | --- | --- |
| `room_rir` | Reverberant room recording | Measured or simulated RIR, early reflections, late decay, wet/dry control | Dereverberation without destroying musical sustain. |
| `far_field_distance` | Distant microphone or audience recording | Distance attenuation, air absorption, reduced direct-to-reverb ratio, room tone | Restoring presence and clarity from far-field capture. |
| `off_axis_mic` | Off-axis microphone coloration | Directional mic EQ, high-frequency loss, comb filtering | Correcting microphone placement problems. |
| `consumer_mic` | Phone, laptop, or cheap recorder capture | Narrow response, AGC, self-noise, mild clipping, mono or near-mono capture | Robustness to non-studio recording devices. |
| `speaker_playback` | Playback through consumer speakers before capture | Speaker EQ, cabinet resonances, nonlinear driver saturation, room coupling | Undoing playback-chain coloration. |
| `background_ambience` | Room, street, venue, or field ambience under the music | Open ambience beds, level automation, spectral masking | Separating music from natural environmental beds. |
| `crowd_bleed` | Live audience or venue contamination | Crowd murmur, applause bursts, stage bleed, diffuse reverb | Handling concert and bootleg-style interference. |
| `broadband_noise` | Hiss, fan, tape, or general broadband noise | Colored noise mixtures, SNR targets, slow level drift | Denoising without over-smoothing music. |
| `electrical_hum` | Ground loop or electrical buzz | 50/60 Hz fundamentals, harmonic stacks, time-varying amplitude | Removing tonal interference while preserving bass. |
| `clicks_crackle` | Dust, static, vinyl, connector, or damaged-transfer crackle | Sparse clicks, dense crackle, burst events, random timing | Repairing short impulsive artifacts. |
| `dropouts_glitches` | Buffer underruns, packet loss, or bad digital transfer | Short mutes, repeats, discontinuities, zeroed blocks | Inpainting missing or discontinuous audio. |
| `gain_clipping` | Bad gain staging or overloaded input | Soft clipping, hard clipping, hidden clipping, clipped transients | Declip and reconstruct peaks. |
| `saturation_overdrive` | Preamp, tape, speaker, or analog-style overload | Waveshaping, harmonic distortion, level-dependent coloration | Removing nonlinear distortion without flattening energy. |
| `overcompression_limiter` | Excessive compression, limiting, or AGC | Low dynamic range, pumping, transient loss, loudness normalization | Restoring dynamics and transients. |
| `bandwidth_loss` | High-pass, low-pass, or poor EQ transfer | High-pass, low-pass, shelving loss, resonant notches | Recovering missing lows/highs and correcting muffling. |
| `telephone_band` | Telephone or radio-style narrowband audio | 300-3400 Hz bandpass, companding, codec/noise layer | Restoring intelligibility and bandwidth from narrowband signals. |
| `low_sample_rate` | Low sample rate capture or bad resampling | Downsampling, anti-alias variation, aliasing, upsampled output | Bandwidth extension and alias robustness. |
| `lossy_codec` | Single lossy encoding pass | MP3, AAC, Opus, bitrate ladder, encoder metadata | Removing codec artifacts and pre-echo. |
| `transcode_chain` | Repeated platform uploads or messaging-app transfers | Multiple codec generations, resampling, loudness normalization, stereo changes | Repairing accumulated distribution-platform damage. |
| `pitch_speed_instability` | Unstable playback clock, tape wow/flutter, or turntable drift | Slow wow, fast flutter, random pitch drift, timing modulation | Stabilizing pitch and timing without warping musical expression. |

### Recipe Design

- `profile`: one of the named real-world degradation profiles above, implemented as a reproducible chain with documented severity bands.
- `single`: one degradation family at a controlled severity.
- `chain`: ordered combinations of two or more degradations.
- `organic`: sampled chains intended to resemble naturally accumulated musical degradation, such as room playback, microphone capture, device compression, background ambience, mild saturation, and codec loss.
- `stress`: severe but still open and reproducible degradations for robustness testing, reported separately from the main leaderboard score.

The benchmark should report results separately by family and severity. A single global score is useful for ranking, but it must not hide which degradations a model handles poorly.

## Evaluation And Leaderboard

### Splits

- `train`: public clean and degraded pairs for model development.
- `validation`: public clean and degraded pairs for local debugging, ablations, and reproducible development reports.
- `evaluation`: hidden clean and degraded pairs used only by the organizers for official leaderboard scoring. Participants do not receive the audio or item list before evaluation.

### Leaderboard Policy

OpenRestore should be container-first and organizer-evaluated. Participants should not submit restored audio for the official leaderboard. They submit a runnable OCI/Docker container; the organizers run it on the hidden evaluation split, generate the restored audio, compute the metrics, and publish the result.

The main leaderboard should be `OpenRestore-train-only`: models may train on the public OpenRestore training split, but not on validation or evaluation audio. Submissions trained with additional datasets should be allowed only in a clearly separated `external-data` track.

The hidden evaluation split should prevent training on the exact benchmark clips, but it should not be a surprise-domain test. Prefer held-out SDD/BBC material and, if needed, additional high-quality open-licensed or project-recorded audio that follows the same documented curation rules. Secret clips are fair; secret domains are likely to create an unfair distribution shift.

Public train/validation scores can be shown as diagnostics, but official ranking should come from the hidden evaluation split.

### Local User Workflow

1. Download the public versioned dataset release and metadata.
2. Train a model using the public `train` split, or declare additional training data for the separate external-data track.
3. Tune and debug on `validation`.
4. Run the OpenRestore CLI locally on public validation examples to produce a development `scores.json`.
5. Submit an OCI/Docker container containing the inference code and either bundled weights or a declared weight-download mechanism that works when the organizers run the container.

### Organizer Evaluation

- Accept a runnable OCI/Docker container, not restored audio files as the primary submission. The container must expose a documented inference command that reads degraded audio and item metadata from an input directory and writes restored audio to an output directory.
- The submitted container must include all inference code. Model weights should either be included in the image or downloaded from a declared, versioned URL during setup/run, with checksums recorded in the submission manifest.
- Organizers run the container on the hidden `evaluation` split, generate the restored audio themselves, and compute all metrics from clean, degraded, and restored audio.
- Validate duration, sample rate, channel count, loudness bounds, file naming, item IDs, and absence of invalid samples before scoring.
- Store submission manifest, container digest, logs, metrics, output checksums, and restored outputs for audit.
- Publish `leaderboard.json` and a static leaderboard page with separate OpenRestore-train-only and external-data tracks.

## Metrics

OpenRestore should report metrics in separate families rather than collapse everything into one opaque score. The official leaderboard can still define a primary aggregate, but every submission should expose the underlying metric table by degradation family, severity, source subset, and clip duration.

### Required Metrics

| Family | Metrics | Comparison | Purpose |
| --- | --- | --- | --- |
| Pairwise reconstruction | L1, L2, SNR, SI-SDR or SI-SNR, log-spectral distance (LSD), multi-resolution STFT distance, mel-spectral distance, LTAS distance | Restored vs clean; degraded vs clean as the baseline floor | Measures whether the restored waveform/spectrum moved closer to the known clean reference. |
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

Publish baseline scores for public train/validation diagnostics and for the hidden evaluation split. In the leaderboard, these baselines should appear as fixed reference rows, not as competing teams.

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
container_image: registry.example.org/openrestore/example:1.0.0
container_digest: sha256:...
openrestore_version: 1.0.0
weights:
  mode: bundled-or-download
  uri: https://example.org/model-weights.ckpt
  sha256: ...
training_data:
  - OpenRestore train 1.0.0
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
| `training_data` | What data was used to train the model. The main leaderboard should be OpenRestore-train-only; external data belongs in a separate track. |
| `inference_command` | The exact command the organizers run inside the container. It must read degraded audio from `/input` and write restored audio to `/output`. |
| `hardware_requested` | The compute environment needed to run evaluation within a reasonable time. |
| `method_summary` | A short public explanation of the method shown beside the leaderboard entry. |

The container must be runnable without manual intervention beyond pulling the image and, if declared, downloading fixed-version weights.

## Implementation Plan

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
      organic/
      stress/
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
      tape.py
      codecs.py
      organic_profiles.py
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
| Hugging Face Datasets | Public distribution of train/validation metadata, public audio assets when licensing allows, dataset cards, and loading examples. |
| Zenodo | Frozen release archive with DOI for papers, reports, and grant deliverables. Archive the exact manifests, configs, schemas, evaluation scripts, baseline definitions, and public metadata used for a release. |
| Static website | Documentation and leaderboard generated from versioned files such as `leaderboard.json`, submission manifests, and release notes. GitLab Pages or GitHub Pages is enough. |
| Organizer private storage | Hidden evaluation audio, clean references, evaluation manifests, container logs, restored outputs, and audit checksums. These are not public, but they must be backed up and versioned internally. |

Each release should include:

- Public `index.jsonl` files for train/validation.
- Dataset card and source-license summary.
- Degradation recipes and versioned degradation code.
- Evaluation code, metric versions, and baseline definitions.
- Baseline scores on public validation and hidden evaluation.
- Leaderboard snapshot and release notes.
- Checksums for all public artifacts.

Keep optional infrastructure optional. RenkuLab, DaSCH, or other preservation platforms can be added later if a funder, partner, or archive requirement makes them useful, but they should not be required for the benchmark to run.

## Roadmap

### 1. Freeze The Benchmark Contract

- Define the task precisely: one degraded musical clip in, one restored clip out.
- Fix the split policy: public `train`, public `validation`, hidden organizer-only `evaluation`.
- Fix the leaderboard policy: container-first submissions, OpenRestore-train-only main track, separate external-data track.
- Choose canonical audio settings: sample rate, channel handling, segment lengths, loudness normalization, and output validation rules.
- Finalize the JSONL row schema around the current fields: source metadata, segment metadata, HDF5 paths, prompts, `degradation_tracking`, `hidden_clipping`, split, and rights metadata.

### 2. Build The Dataset Pipeline

- Implement SDD ingestion with quality, metadata, and license checks.
- Implement BBC Sound Effects ingestion for ambience, organic degradation material, and optional sound-effect restoration subsets.
- Segment long sources into deterministic 10-second and 30-second windows while preserving links to the original source recording.
- Build HDF5 shards and portable `index.jsonl` manifests with release-relative paths.
- Generate public train/validation splits and a hidden evaluation split from source-level groups.
- Produce dataset statistics: duration, source dataset, degradation family, prompt coverage, license status, sample rate, channels, and segment length.

### 3. Implement Degradations And Tracking

- Implement the 20 real-world degradation profiles first, starting from the existing composite prototypes: `crackle`, `highpass`, `hum`, `low_sr`, `noise`, `pitch_instability`, `soft_clip`, and `telephone`.
- Implement the primitive modules needed by those profiles: RIR/reverb, distance and microphone response, EQ/filtering, noise and ambience mixing, hum, crackle/clicks, clipping/saturation, compression/limiting, sample-rate loss, codec loss, dropouts/glitches, and pitch/speed instability.
- Store compact per-item metadata in `degradation_tracking` and keep full recipe/config files versioned with the release.
- Create isolated recipes only for diagnosis and AAE validation; keep the main v1 benchmark focused on organic multi-step profiles that resemble real restoration cases.
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

- Publish public train/validation metadata and redistributable audio assets where licensing allows.
- Publish degradation configs, schemas, evaluation code, metric versions, baseline code, and baseline scores.
- Archive the release on Zenodo with a DOI.
- Publish the documentation and static leaderboard site.
- Open the submission process with clear instructions and example containers.

### 8. Extend Carefully

- Add listening tests once objective metrics and baselines are stable.
- Add stronger generative-audio baselines, such as audio-to-audio diffusion, Schrodinger-bridge, flow-matching, or foundation-model restorers, when licenses and training assumptions are clear.
- Add specialized tracks only when needed: remastering, bandwidth extension, codec repair, device-capture restoration, or sound-effect restoration.
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
- ACE-Step: <https://arxiv.org/abs/2506.00045>
- ACE-Step 1.5: <https://arxiv.org/abs/2602.00744>
- Hugging Face Dataset Cards: <https://huggingface.co/docs/hub/datasets-cards>
- Zenodo DOI versioning: <https://zenodo.org/help/versioning>
- GitLab Pages: <https://docs.gitlab.com/ee/user/project/pages/>
- GitHub Pages: <https://docs.github.com/en/pages>
