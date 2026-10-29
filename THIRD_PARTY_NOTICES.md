# Third-Party Material Notices

This file records third-party material used or referenced by OpenRestor. It does not grant a
licence to that material and does not replace its source-specific attribution.

## SonicMaster/ARIEL software adaptation

`openrestor/degradations/ariel_effects.py` adapts the degradation implementations in
[SonicMaster `dataset_scripts`](https://github.com/AMAAI-Lab/SonicMaster/tree/main/dataset_scripts),
released by AMAAI Lab under [Apache License 2.0](https://github.com/AMAAI-Lab/SonicMaster/blob/main/LICENSE).
It ports effects to channel-last audio, adds deterministic parameter tracking, preview
controls and OpenRestor-specific RIR handling. The upstream Apache-2.0 permissions and
required attribution must be preserved; a copy of that licence is in
`LICENSES/Apache-2.0.txt`. The exact code boundary and any upstream copyright
headers still require review before a software release.

## OpenAIR Room Impulse Responses

The 14 files under `assets/degradations/v0_1/real_rirs/` come from the Open Acoustic
Impulse Response Library (OpenAIR), Audiolab, University of York. Four rooms are marked
Public Domain by their archived OpenAIR pages. The Spokane Woman's Club recording is
licensed under Creative Commons Attribution 3.0 and must be credited to OpenAIR
(`www.openairlib.net`) and James Cadwallader.

The complete per-file notice, source links and modification statement are in
`assets/degradations/v0_1/real_rirs/ATTRIBUTION.md`. File hashes are in
`docs/degradation_assets_v0_1.sha256`.

## Benchmark Audio Sources

- SonicMaster/Jamendo: the API audit found track-level terms that contradict the collection-level label;
  no derived audio is cleared pending written clarification or approval of a filtered subset.
- Song Describer Dataset and MUSDB18-HQ: used locally for transfer evaluation; their source
  or derived audio is not included in the public OpenRestor release.
- Blind-Real Public: CC0 and CC BY material is distributed only with its generated per-item
  attribution and provenance records.

The proposed EPFL academic licence would apply only to components whose relevant rights
EPFL holds. It would not replace SonicMaster's Apache-2.0 grant or relicense third-party
audio, datasets, model weights or other material.
