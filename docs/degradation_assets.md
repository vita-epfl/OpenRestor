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

**OpenAIR licenses each recording separately, and three of our twelve files forbid commercial use.** The library-wide "CC BY 4.0" label that circulates in third-party dataset catalogues is wrong. The authoritative per-room statements were recovered from the Internet Archive, because openairlib.net and openair.hosted.york.ac.uk are both suspended; each room page carries a "License for this content:" field.

| File | OpenAIR room | Declared license | Commercial | Derivatives |
| --- | --- | --- | --- | --- |
| `stereo/1st_baptist_nashville_far_close.wav` | 1st Baptist Nashville | Public Domain | yes | yes |
| `stereo/st_georges_medium.wav` | St Georges Episcopal Church | Public Domain | yes | yes |
| `b-formats/heslington_impulseresponseheslingtonchurch-003.wav` | Heslington Church | Attribution Share Alike | yes | share-alike |
| `b-formats/heslington_impulseresponseheslingtonchurch-007.wav` | Heslington Church | Attribution Share Alike | yes | share-alike |
| `b-formats/patrick_soundfield_s1r1.wav` | St Patrick's Church, Patrington | Attribution Share Alike | yes | share-alike |
| `b-formats/patrick_soundfield_s3r3.wav` | St Patrick's Church, Patrington | Attribution Share Alike | yes | share-alike |
| `b-formats/stalbans_b_wxyz.wav` | Lady Chapel, St Albans Cathedral | Attribution Share Alike | yes | share-alike |
| `b-formats/falkland_tennis_court_b_format.wav` | Falkland Palace Royal Tennis Court | Attribution **Non-commercial** Share Alike | **no** | share-alike |
| `stereo/elveden_1a_marble_hall.wav` | Elveden Hall, Suffolk | Attribution **Non-commercial No Derivatives** | **no** | **no** |
| `stereo/elveden_4a_hats_cloaks_visitors.wav` | Elveden Hall, Suffolk | Attribution **Non-commercial No Derivatives** | **no** | **no** |
| `b-formats/roncooke_sssr.wav` | Ron Cooke Hub (unconfirmed) | **unknown** | ? | ? |
| `b-formats/roncooke_tsfr.wav` | Ron Cooke Hub (unconfirmed) | **unknown** | ? | ? |

Two further notes. The site's generic Terms and Conditions reserve all rights and forbid republication and commercial use, but they open with "Unless otherwise stated", and the per-room license fields are that statement, so the table above governs. And no Ron Cooke Hub page exists anywhere in the Internet Archive's capture of the site, so those two files may postdate the last snapshot or come from elsewhere entirely; their provenance is unresolved.

The No Derivatives condition on the two Elveden files is the hardest of the three blocks: rendering music through an impulse response produces a derivative of it, which ND forbids outright regardless of whether the result is sold.

Consequences for `reverb_real`, in increasing order of cost:

1. Keep the 7 unambiguously commercial-friendly files (2 Public Domain, 5 Attribution Share Alike) and drop the other 5. The released degraded audio for this class would carry a share-alike obligation, which nothing else in the benchmark does.
2. Keep only the 2 Public Domain files. No obligation at all, but only two rooms of variety.
3. Drop `reverb_real` and ship 20 classes with no asset dependency at all, as was done for the `mic` class.

Any of the first two changes which file a given seed selects, since `_real_rir` indexes a sorted listing, so they must be settled before release-scale rendering starts. `ariel_effects.py` also samples `rir_index` over `integer(0, 11)`, which assumes twelve files and would need adjusting.

### Retired: The Poliphone Microphone IRs

v0.1 originally rendered a `mic` class by convolving with 20 Poliphone smartphone impulse responses (Salvi et al., IEEE Access 2025), released for non-commercial research only. That single dependency would have forced the whole benchmark non-commercial, so the class was replaced by `smartphone_capture`, which reproduces the degradation parametrically from code alone.

Poliphone has been removed from the project: the asset bundle, the checksum manifest, the `microphone_response` primitive and the ARIEL `mic` effect are all gone. OpenAIR is the only remaining asset dependency, but the per-room terms recorded above show it is not uniformly permissive, so `degradation_asset_provenance_approval` still turns on which `reverb_real` files are retained.

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
