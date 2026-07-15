# Dataset Audit Decisions

These records are the release gate for Phase 1. A source may be ingested locally before its
license review is complete, but its clips must not be redistributed until the decision record is
confirmed by the project owner.

Use `docs/templates/dataset_decision_record.md` for full per-source decisions and
`docs/templates/listening_review.md` for structured listening notes.

| Dataset | Access | OpenRestore role | License / redistribution | Quality and selection decision |
| --- | --- | --- | --- | --- |
| SonicMaster clean originals | [Hugging Face release](https://huggingface.co/datasets/amaai-lab/SonicMasterDataset); local `SonicMasterDataset/clean` mirror | Main-track training; held-out validation and public test | Verify the upstream release terms before redistributing derived clips | Accept only `.flac` files below `clean/`. Existing HDF5 shards, degraded examples, prompts, and split labels are excluded. Split by source recording with a seeded hash. Initial listening review found medium source quality with audible compression; acceptable for restoration use, but not as a high-quality generation reference. |
| Song Describer Dataset (SDD) | [Hugging Face release](https://huggingface.co/datasets/amaai-lab/SongDescriber); local `SDD/audio` mirror | Validation only | Verify the upstream release terms before redistributing derived clips | Decode source MP3s to canonical WAV clips. Do not use in main-track training or public test. |
| MUSDB18-HQ | [MUSDB18 project](https://sigsep.github.io/datasets/musdb.html); local `musdb18hq` mirror | Validation only | CC BY-NC-SA 4.0; verify local distribution and derived-clip release conditions | Accept full-song mixture WAVs only. The local mirror contains mixture files, not stems; do not add stems later. |
| Secret custom music dataset | Organizer-controlled storage; no public URL | Hidden official evaluation only | Record internally before use; never public | Keep manifests and audio private. It must meet the same 44.1 kHz, 30-second, source-separated policy. |
| BBC Sound Effects, Freesound, FSD50K, MUSAN | [BBC Sound Effects](https://sound-effects.bbcrewind.co.uk/), [Freesound](https://freesound.org/), [FSD50K](https://zenodo.org/records/4060432), [MUSAN](https://www.openslr.org/17/) | Degradation material only | License and attribution reviewed per asset/source | Never use as clean musical benchmark sources. Track each selected asset in Phase 2 degradation metadata. |

FMA is intentionally not a candidate in this release: its footprint is too large for the initial
curation and audit workflow.
