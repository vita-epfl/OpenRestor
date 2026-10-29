# Degradation Assets v0.1

## Purpose

One active effect requires binary assets. The approved OpenRestor v0.1 bundle is tracked in Git at `assets/degradations/v0_1/`, so the repository tag and commit identify the canonical asset version. Its file-level checksums are tracked independently in `docs/degradation_assets_v0_1.sha256`.

| Effect | Asset | What it models | Required layout |
| --- | --- | --- | --- |
| `reverb_real` | 14 real room impulse-response WAV files from five rooms | Measured acoustic spaces. The renderer accepts stereo or four-channel B-format RIRs and convolves them with the clean signal. | `assets/degradations/v0_1/real_rirs/{stereo,b-formats}/*.wav` |

The v0.1 asset bundle is downloaded directly from OpenAIR at `https://webfiles.york.ac.uk/OPENAIR/IRs/`. It no longer derives from the ARIEL asset set, and OpenRestor does not read from ARIEL at runtime.

## Upstream Provenance

The RIRs originate from OpenAIR, the library the SonicMaster paper also draws on for its fourth Reverb function. OpenRestor selects its own subset on licence grounds rather than reusing SonicMaster's twelve.

| Asset set | Upstream source | Citation |
| --- | --- | --- |
| 14 real RIRs | OpenAIR: Open Acoustic Impulse Response Library, University of York | Howard, D. M. and Angus, J. A. S. *Open acoustic impulse response (OpenAIR) library.* https://www.openair.hosted.york.ac.uk/ |

The installed RIR filenames match five OpenAIR rooms: 1st Baptist Nashville, Hoffmann Lime Kiln, Saint Lawrence Church at Molenbeek-Wersbeek, Spokane Woman's Club, and St Georges Episcopal Church.

### Recorded Terms

**The bundle contains only OpenAIR recordings whose stated terms permit commercial use and redistribution.** OpenAIR licenses each recording separately, so the library-wide "CC BY 4.0" label used by third-party dataset catalogues does not hold. Terms were read from each room's "License for this content" field as captured by the Internet Archive, because the OpenAIR web pages are suspended; the audio itself remains available at `https://webfiles.york.ac.uk/OPENAIR/IRs/`.

| Room | Files | Stated license | Attribution |
| --- | --- | --- | --- |
| 1st Baptist Nashville | 3 stereo | Public Domain | not required |
| Hoffmann Lime Kiln, Langcliffe | 6 B-format | Public Domain | not required |
| Saint Lawrence Church, Molenbeek-Wersbeek | 1 stereo | Public Domain | not required |
| St Georges Episcopal Church | 3 stereo | Public Domain | not required |
| Spokane Woman's Club | 1 stereo | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | **`www.openairlib.net` and James Cadwallader** |

Fourteen files across five rooms. Per-file credits are in `assets/degradations/v0_1/real_rirs/ATTRIBUTION.md`, which any release distributing these files, or audio rendered through them, must carry.

Nothing in the bundle is non-commercial or no-derivatives, and nothing carries a share-alike obligation, so no clause propagates to the rendered corpus.

### Confirmed By The OpenAIR Maintainers

Damian Murphy of the University of York AudioLab confirmed by email, in October 2026, the terms of the 25 rooms whose web pages were unreachable. **The standard current OpenAIR licence is CC BY-SA 4.0**, and he confirmed it applies to 23 of them:

air-museum, arthur-sykes-rymer-auditorium-university-york, cliffords-tower, forest-scale-model, genesis-6-studio-live-room-drum-set, hendrix-hall, holy-trinity-church, house-of-commons-auralizations, jack-lyons-concert-hall-university-york, koli-national-park-winter, maes-howe, newgrange, r1-nuclear-reactor-hall, ron-cooke-hub-university-york, shrine-and-parish-church-all-saints-north-street, spring-lane-building-university-york, st-andrews-church, st-margarets-church-ncem-5-piece-band-spatial-measurements, st-marys-abbey-reconstruction, st-pauls-cathedral, virtual-membranes, wheldrake-wood, york-minster.

He was able to state this because a member of his team or one of their students made each measurement. Two rooms stay unresolved: **tvisongur-sound-sculpture-iceland-model** and **usina-del-arte-symphony-hall** were measured by people outside his team; contributors had to accept the CC BY-SA terms to publish on OpenAIR, but the entries are old and he would not confirm their provenance. They are therefore treated as unknown.

This resolves the gap recorded earlier and settles the provenance of `ron-cooke-hub-university-york`, the source of the two unidentified files in the retired bundle.

**It does not change the v0.1 bundle.** These 23 rooms are CC BY-SA, and the bundle deliberately admits only Public Domain and CC BY so that no share-alike obligation propagates to the rendered corpus. More decisively, the Diagnostic release is already rendered: changing the RIR set now would invalidate 542,829 paired examples, because which RIR a seed selects depends on the installed bundle. This is information for a future version, not a change to make to this one.

If a later release accepts CC BY-SA, the confirmation widens the usable pool from 22 rooms to roughly 45, and the additions are the musically valuable ones: York Minster, St Paul's Cathedral, the Jack Lyons Concert Hall, Maes Howe, Newgrange, Holy Trinity Church and St Andrew's Church.

### Rooms Deliberately Excluded

A survey of 75 archived OpenAIR room pages found 22 rooms with permissive terms, of which 19 have stereo or B-format files the renderer can read. The bundle takes only the five Public Domain and CC BY rooms. The 14 remaining permissive rooms are Attribution Share Alike: usable commercially, but share-alike would propagate to the rendered `reverb_real` audio, and nothing else in the benchmark imposes such a clause. They are available to revisit if the release policy ever accepts share-alike.

Also excluded regardless of licence: rooms whose only files are mono or 5.1, which the renderer rejects; `st-patricks-patrington-model` and `waveguide-web-example-audio`, which are simulations rather than measurements and would defeat the purpose of a measured-RIR class; and `slinky-ir`, which is a spring rather than a space.

The earlier bundle, which mixed Public Domain, Share Alike, Non-commercial Share Alike and No Derivatives files plus two files of unresolved provenance, was retired to `build/retired-assets/openair_real_rirs_v0_1_mixed_licences/`.

### Retired: The Poliphone Microphone IRs

v0.1 originally rendered a `mic` class by convolving with 20 Poliphone smartphone impulse responses (Salvi et al., IEEE Access 2025), released for non-commercial research only. That single dependency would have forced the whole benchmark non-commercial, so the class was replaced by `smartphone_capture`, which reproduces the degradation parametrically from code alone.

Poliphone has been removed from the project: the asset bundle, the checksum manifest, the `microphone_response` primitive and the ARIEL `mic` effect are all gone. OpenAIR is the only remaining asset dependency, but the per-room terms recorded above show it is not uniformly permissive, so `degradation_asset_provenance_approval` still turns on which `reverb_real` files are retained.

Measured microphone impulse responses are still worth adding later as a separate class rather than as a substitute, on the model of `reverb_real` beside the simulated reverb classes. Any such set must permit commercial use and redistribution.

## Asset Release And IT Install

1. The release record identifies the exact Git tag and commit containing `assets/degradations/v0_1/`. Do not substitute an arbitrary OpenAIR download: changing the files changes deterministic output even with the same seed.
2. IT checks out that revision and verifies the files from the repository root:

   ```bash
   sha256sum -c docs/degradation_assets_v0_1.sha256
   find assets/degradations/v0_1/real_rirs -type f -name '*.wav' | wc -l
   ```

   The expected count is 14 RIR WAV files.
3. IT runs `openrestor-degrade validate-config --config configs/degradations/single/v0_1.yaml`, then runs a small render containing `reverb_real` before starting a release-scale job.

Every release that distributes the RIRs or audio rendered through them must include both `assets/degradations/v0_1/real_rirs/ATTRIBUTION.md` and `docs/degradation_assets_v0_1.sha256`. The Git revision, degradation config, manifests, checksums and release logs remain part of the release record.

Some artifact stores require one downloadable archive. That is an optional transport copy, not the canonical source. Create it only when the hosting workflow requires it:

```bash
scripts/package_degradation_assets.sh
```

This writes `build/release_assets/openrestor-degradation-assets-v0_1.tar.gz` and its archive SHA-256. The tarball is simply the 14 Git-tracked WAVs plus `ATTRIBUTION.md`, `THIRD_PARTY_NOTICES.md`, the provenance document and checksum manifest; it is not another dataset and does not change the renderer.

## Renderer Contract

`configs/degradations/single/v0_1.yaml` points `reverb_real` to the standard asset path. The selected file is deterministic for a given item seed. If the asset bundle is missing, rendering fails with an explicit `real_rir_dir` error; the job must be marked failed rather than silently skipping the effect.
