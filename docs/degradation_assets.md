# Degradation Assets v0.1

## Purpose

One active effect requires binary assets that are intentionally not stored in Git. The approved OpenRestore v0.1 bundle is installed at `assets/degradations/v0_1/`, next to the repository checkout. Its file-level checksums are tracked in `docs/degradation_assets_v0_1.sha256`.

| Effect | Asset | What it models | Required layout |
| --- | --- | --- | --- |
| `reverb_real` | 12 real room impulse-response WAV files | Measured acoustic spaces. The renderer accepts stereo or four-channel B-format RIRs and convolves them with the clean signal. | `assets/degradations/v0_1/real_rirs/{stereo,b-formats}/*.wav` |

The v0.1 asset source bundle is the already reviewed local ARIEL asset set: `configs/realrirs` for the 12 selected real RIRs. OpenRestore does not read from ARIEL at runtime.

## Upstream Provenance

The RIRs originate from a published third-party dataset, as documented in the SonicMaster paper (arXiv:2508.03448), whose fourth Reverb function uses "12 selected room impulse responses from the openAIR library dataset".

| Asset set | Upstream source | Citation |
| --- | --- | --- |
| 12 real RIRs | OpenAIR: Open Acoustic Impulse Response Library, University of York | Howard, D. M. and Angus, J. A. S. *Open acoustic impulse response (OpenAIR) library.* https://www.openair.hosted.york.ac.uk/ |

The installed RIR filenames match OpenAIR rooms: 1st Baptist Nashville, Elveden Hall, Falkland Tennis Court, Heslington Church, Patrick's Soundfield, Ron Cooke Hub, St Albans, and St Georges.

### Recorded Terms

| Asset set | Terms | Commercial use |
| --- | --- | --- |
| 12 OpenAIR RIRs | Creative Commons. The AHRC grant record for AH/J013838/1 states the library "has been licensed to three audio software companies under a Creative Commons License and included in their commercial releases" (Ableton Live 9, Presonus Studio One, Reason Studios), and third-party dataset indexes list OpenAIR as CC BY 4.0. | Permitted, with attribution |

Both openair.hosted.york.ac.uk and openairlib.net were unreachable when this was written, so per-room confirmation for the 12 selected files needs the Internet Archive or direct contact with the University of York.

### Retired: The Poliphone Microphone IRs

v0.1 originally rendered a `mic` class by convolving with 20 Poliphone smartphone impulse responses (Salvi et al., IEEE Access 2025), released for non-commercial research only. That single dependency would have forced the whole benchmark non-commercial, so the class was replaced by `smartphone_capture`, which reproduces the degradation parametrically from code alone.

Poliphone has been removed from the project: the asset bundle, the checksum manifest, the `microphone_response` primitive and the ARIEL `mic` effect are all gone. OpenAIR is the only remaining asset dependency and its terms permit commercial use, so `degradation_asset_provenance_approval` has no blocking obstacle left.

Measured microphone impulse responses are still worth adding later as a separate class rather than as a substitute, on the model of `reverb_real` beside the simulated reverb classes. Any such set must permit commercial use and redistribution.

## Asset Release And IT Install

1. The research owner uploads the directory `assets/degradations/v0_1/` to the approved private artifact store as `openrestore-degradation-assets-v0_1.tar.gz` and records its artifact URL, license/provenance record, and archive SHA-256 in the release record.
2. IT downloads that exact approved archive into the repository root and extracts it so the paths above exist. Do not substitute an arbitrary OpenAIR download: changing the files changes deterministic output even with the same seed.
3. IT verifies the unpacked files from the repository root:

   ```bash
   sha256sum -c docs/degradation_assets_v0_1.sha256
   find assets/degradations/v0_1/real_rirs -type f -name '*.wav' | wc -l
   ```

   The expected count is 12 RIR WAV files.
4. IT runs `openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml`, then runs a small render containing `reverb_real` before starting a release-scale job.

The binary bundle remains outside Git because it is an externally sourced release artifact. It must be versioned and retained with the degradation config, Git revision, manifests, checksums, and release logs.

## Renderer Contract

`configs/degradations/single/v0_1.yaml` points `reverb_real` to the standard asset path. The selected file is deterministic for a given item seed. If the asset bundle is missing, rendering fails with an explicit `real_rir_dir` error; the job must be marked failed rather than silently skipping the effect.
