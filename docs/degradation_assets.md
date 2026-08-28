# Degradation Assets v0.1

## Purpose

Two active ARIEL/SonicMaster-parity effects require binary assets that are intentionally not stored in Git. The approved OpenRestore v0.1 bundle is installed at `assets/degradations/v0_1/`, next to the repository checkout. Its file-level checksums are tracked in `docs/degradation_assets_v0_1.sha256`.

| Effect | Asset | What it models | Required layout |
| --- | --- | --- | --- |
| `single_mic` | 20 Poliphone smartphone microphone impulse responses | The measured transfer function of a phone microphone: frequency coloration and phase response. The renderer convolves the same mono `.npy` IR with each stereo channel. It is not room reverb and it does not add environmental noise. | `assets/degradations/v0_1/microphone_irs/*.npy` |
| `single_real` | 12 real room impulse-response WAV files | Measured acoustic spaces. The renderer accepts stereo or four-channel B-format RIRs and convolves them with the clean signal. | `assets/degradations/v0_1/real_rirs/{stereo,b-formats}/*.wav` |

The v0.1 asset source bundle is the already reviewed local ARIEL asset set: `configs/smallpoli/irs` for the 20 Poliphone IRs and `configs/realrirs` for the 12 selected real RIRs. OpenRestore does not read from ARIEL at runtime.

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
4. IT runs `openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml`, then runs a small render containing `single_mic` and `single_real` before starting a release-scale job.

The binary bundle remains outside Git because it is an externally sourced release artifact. It must be versioned and retained with the degradation config, Git revision, manifests, checksums, and release logs.

## Renderer Contract

`configs/degradations/single/v0_1.yaml` points `single_mic` and `single_real` to the standard asset paths. Both selected files are deterministic for a given item seed. If the asset bundle is missing, rendering fails with an explicit `mic_ir_dir` or `real_rir_dir` error; the job must be marked failed rather than silently skipping the effect.
