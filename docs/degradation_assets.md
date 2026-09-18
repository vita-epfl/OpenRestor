# Degradation Assets v0.1

## Purpose

Two active ARIEL/SonicMaster-parity effects require binary assets that are intentionally not stored in Git. The approved OpenRestore v0.1 bundle is installed at `assets/degradations/v0_1/`, next to the repository checkout. Its file-level checksums are tracked in `docs/degradation_assets_v0_1.sha256`.

| Effect | Asset | What it models | Required layout |
| --- | --- | --- | --- |
| `mic` | 20 Poliphone smartphone microphone impulse responses | The measured transfer function of a phone microphone: frequency coloration and phase response. The renderer convolves the same mono `.npy` IR with each stereo channel. It is not room reverb and it does not add environmental noise. | `assets/degradations/v0_1/microphone_irs/*.npy` |
| `reverb_real` | 12 real room impulse-response WAV files | Measured acoustic spaces. The renderer accepts stereo or four-channel B-format RIRs and convolves them with the clean signal. | `assets/degradations/v0_1/real_rirs/{stereo,b-formats}/*.wav` |

The v0.1 asset source bundle is the already reviewed local ARIEL asset set: `configs/smallpoli/irs` for the 20 Poliphone IRs and `configs/realrirs` for the 12 selected real RIRs. OpenRestore does not read from ARIEL at runtime.

## Upstream Provenance

Both asset sets originate from published third-party datasets, as documented in the SonicMaster paper (arXiv:2508.03448), which states that its Microphone function "applies one of 20 Poliphone transfer functions" and that its fourth Reverb function uses "12 selected room impulse responses from the openAIR library dataset".

| Asset set | Upstream source | Citation |
| --- | --- | --- |
| 20 microphone IRs | Poliphone smartphone recording dataset | Salvi, D., Leonzio, D. U., Giganti, A., Eutizi, C., Mandelli, S., Bestagini, P., and Tubaro, S. *Poliphone: A dataset for smartphone model identification from audio recordings.* IEEE Access, 2025. |
| 12 real RIRs | OpenAIR: Open Acoustic Impulse Response Library, University of York | Howard, D. M. and Angus, J. A. S. *Open acoustic impulse response (OpenAIR) library.* https://www.openair.hosted.york.ac.uk/ |

The installed RIR filenames match OpenAIR rooms: 1st Baptist Nashville, Elveden Hall, Falkland Tennis Court, Heslington Church, Patrick's Soundfield, Ron Cooke Hub, St Albans, and St Georges.

**The redistribution terms of these two upstream sets are not yet recorded.** The SonicMaster paper cites both sources but states no license for either. OpenAIR entries carry per-room Creative Commons terms, and the Poliphone dataset has its own release terms; both must be read and recorded here before the bundle is published or shipped to users. Until that is done, `degradation_asset_provenance_approval` in `configs/releases/private_v0_1.yaml` stays unresolved and the bundle must not be redistributed.

## Asset Release And IT Install

1. The research owner uploads the directory `assets/degradations/v0_1/` to the approved private artifact store as `openrestore-degradation-assets-v0_1.tar.gz` and records its artifact URL, license/provenance record, and archive SHA-256 in the release record.
2. IT downloads that exact approved archive into the repository root and extracts it so the paths above exist. Do not substitute an arbitrary Poliphone or OpenAIR download: changing the files changes deterministic output even with the same seed.
3. IT verifies the unpacked files from the repository root:

   ```bash
   sha256sum -c docs/degradation_assets_v0_1.sha256
   find assets/degradations/v0_1/microphone_irs -maxdepth 1 -name '*.npy' | wc -l
   find assets/degradations/v0_1/real_rirs -type f -name '*.wav' | wc -l
   ```

   The expected counts are 20 microphone IRs and 12 RIR WAV files.
4. IT runs `openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml`, then runs a small render containing `mic` and `reverb_real` before starting a release-scale job.

The binary bundle remains outside Git because it is an externally sourced release artifact. It must be versioned and retained with the degradation config, Git revision, manifests, checksums, and release logs.

## Renderer Contract

`configs/degradations/single/v0_1.yaml` points `mic` and `reverb_real` to the standard asset paths. Both selected files are deterministic for a given item seed. If the asset bundle is missing, rendering fails with an explicit `mic_ir_dir` or `real_rir_dir` error; the job must be marked failed rather than silently skipping the effect.
