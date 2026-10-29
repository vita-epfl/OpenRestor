# Dataset Audit Decisions

These records are the release gate for Phase 1. A source may be ingested locally before its
license review is complete, but its clips must not be redistributed until the decision record is
confirmed by the project owner.

These frozen benchmark roles are separate from the OpenRestor Clean v0.1 candidate. The
current Clean candidate has no approved public audio: every source still needs asset-level
provenance, exact attribution, lossless verification where claimed, and explicit redistribution
approval. A dataset-level or Zenodo record licence is evidence to investigate, not automatic
approval for the recordings. Zenodo states that it does not own uploaded content and that reuse
depends on the record's licence and scope; see the [official Zenodo permissions
FAQ](https://support.zenodo.org/help/en-gb/2-content/21-can-i-get-permission-to-use-a-specific-record).

Use `docs/templates/dataset_decision_record.md` for full per-source decisions and
`docs/templates/listening_review.md` for structured listening notes.

| Dataset | Access | OpenRestor role | License / redistribution | Quality and selection decision |
| --- | --- | --- | --- | --- |
| SonicMaster clean originals | [Hugging Face release](https://huggingface.co/datasets/amaai-lab/SonicMasterDataset); local `SonicMasterDataset/clean` mirror | Historical frozen benchmark main-track source; held-out validation and public test roles remain contract-defined | **Publication blocked pending written clarification.** The 2026-10-16 audit of all 25,000 Jamendo `source_id` values found only 856 current CC BY records, 1,623 BY-SA, 13,638 NC and/or ND, 27 missing/other licence records, and 8,856 IDs not returned. The collection-level CC BY 2.0 label cannot be treated as overriding track rights without evidence that AMAAI had authority to license the underlying recordings. See `docs/reports/sonicmaster_jamendo_licence_audit_2026-10-16.md`. | Accept only `.flac` files below `clean/`. Existing HDF5 shards, degraded examples, prompts, and split labels are excluded. Use the frozen original SonicMaster train/validation/test manifest as the authoritative source-level split; do not reassign or merge its source sets. Initial listening review found medium source quality with audible compression; acceptable for restoration use, but not as a high-quality generation reference. |
| Song Describer Dataset (SDD) | [Hugging Face release](https://huggingface.co/datasets/amaai-lab/SongDescriber); local `SDD/audio` mirror | Optional local-only transfer evaluation | **Not redistributable as a derivative.** The per-track table was obtained from Zenodo record 10072001 (`audio_licenses.txt`) and matched against all 705 tracks used here, verified 2026-10-15: **209 carry NoDerivatives**, 301 carry NonCommercial without NoDerivatives, and only 195 carry neither. The dataset-level CC BY-SA 4.0 label and the paper's "permissively licensed" wording do not describe the audio. A NoDerivatives track may not have a degraded version distributed at all. Per-track results in `build/sdd_track_licences.json`; usable locally for transfer evaluation only | Decode source MP3s to canonical WAV clips. Do not use in main-track training or public test. Initial listening review found very high source quality, suitable as a generation-grade quality reference. |
| MUSDB18-HQ | [MUSDB18 project](https://sigsep.github.io/datasets/musdb.html); local `musdb18hq` mirror | Optional local-only academic transfer evaluation | **Not redistributable.** The MUSDB18 page states that "the tracks can only be used for academic purposes" and names no licence for the collection. Per-track terms are mixed: some tracks come from MedleyDB under CC BY-NC-SA 4.0 or 3.0, and the 100 DSD100-derived tracks point back to the Mixing Secrets library for rights. Verified 2026-10-15. Usable locally for transfer evaluation; the derived degraded audio must not be published | Accept full-song mixture WAVs only. The local mirror contains mixture files, not stems; do not add stems later. Initial listening review found very good source quality, suitable as a strong transfer-evaluation reference. |
| AlbumDB | [Aalto research portal](https://research.aalto.fi/en/datasets/albumdb-a-multitrack-dataset-of-a-ten-song-album-with-stereo-and-immersive-714-masters/); [Zenodo DOI 10.5281/zenodo.19683000](https://zenodo.org/records/19683000) | Small public-research candidate; production supplement | Record metadata states CC BY 4.0; asset-level attribution, provenance and derivative scope still require confirmation | 10-song indie rock/folk album; 16-bit 44.1 kHz PCM WAV, 13–35 stems/song, stereo and 7.1.4 masters. The metadata-only probe identified 298 WAV members (about 10.73 GB uncompressed), all with ambiguous original status; two ZIP64 archives remain unresolved. Narrow genre coverage; use as a supplement, not the generalist pool. |
| Rights-cleared private concert masters (Montreux Jazz Festival candidate) | Direct authorized transfer into organizer-controlled storage; no public URL | Hidden official evaluation only | Written agreement and rights-register approval required before ingestion; never public | Keep identities, manifests, clean/degraded audio and outputs private. Use source-disjoint concerts/artists and server-side container evaluation. See `docs/hidden_evaluation.md`. |
| BBC Sound Effects, Freesound, FSD50K, MUSAN | [BBC Sound Effects](https://sound-effects.bbcrewind.co.uk/), [Freesound](https://freesound.org/), [FSD50K](https://zenodo.org/records/4060432), [MUSAN](https://www.openslr.org/17/) | Degradation material only | License and attribution reviewed per asset/source | Never use as clean musical benchmark sources. Track each selected asset in Phase 2 degradation metadata. |

FMA is intentionally not a candidate in this release: its footprint is too large for the initial
curation and audit workflow.

See `docs/licensing.md` for the Creative Commons condition matrix, software-licence plan,
Jamendo audit command and contact templates.
The dated redistribution decisions for academic-only and commercially compatible media
are in `docs/redistribution_inventory_academic.md` and
`docs/redistribution_inventory_commercial_ready.md`.
