# Phase 1 Report: Dataset Audit, Ingestion, And Splitting

## Status

Implemented and verified locally. Phase 1 turns declared source datasets into a reproducible clean-audio corpus with stable splits, canonical clips, manifests, checksums, and archive shards.

## Purpose

Phase 1 owns the clean side of the benchmark. Its output is the reference material consumed by the in-progress degradation pipeline in Phase 2 and, later, restoration evaluation. Source audio is inspected before it is copied, every generated clip is tied to its original source, and manifests retain the information required to reproduce a build.

## Dataset Allocation

This is the Phase 1 implementation of the dataset strategy defined in `OpenRestor.md`. Every benchmark item is a clean 30-second music clip and an OpenRestor-generated degraded counterpart; naturally degraded SonicMaster pairs are not reused.

| Dataset | OpenRestor use | Explicit exclusions |
| --- | --- | --- |
| SonicMaster clean originals | Historical default main-track source in the frozen benchmark contract; its audio is currently withheld from redistribution pending track-level rights clarification. Source-separated held-out items remain the contract's validation/public-test roles when lawfully available to the organizer. | Do not use SonicMaster degraded pairs as benchmark or leaderboard data. Do not treat the local mirror as a public Clean v0.1 release. |
| Song Describer Dataset (SDD) | Separately reported local-only transfer evaluation, for transfer to curated captioned music. | Never redistribute or use for main-track training or the in-distribution public test. |
| MUSDB18-HQ mixture audio | Separately reported local-only academic transfer evaluation, as a real mixed-music robustness check. | Never redistribute or use for main-track training, the in-distribution public test, or stems. |
| Rights-cleared private concert masters | Organizer-only hidden official evaluation; Montreux Jazz Festival archives are a candidate pending written permission and contamination review. | Never release publicly or expose to participants. |
| BBC Sound Effects, Freesound, FSD50K, MUSAN | Optional source material for Phase 2 organic degradation layers. | Never use as clean benchmark music. |

Any other training data belongs to the external-data track unless the benchmark contract is explicitly revised. FMA is not a Phase 1 benchmark source.

## Implementation Map

| Path | Responsibility |
| --- | --- |
| openrestor/data/core.py | Shared data structures, JSONL/YAML I/O, ARIEL-manifest and optional hash-fallback splitting, SHA-256, FFprobe metadata inspection, and source discovery. |
| openrestor/data/pipeline.py | Dataset ingestion, split assignment, 30-second clip rendering, quality checks, manifests, checksums, shard creation, verification, and statistics. |
| openrestor/data/cli.py | openrestor-data command-line interface. |
| configs/datasets/*.yaml | Source declarations, roles, local roots, licensing reminders, and minimum source duration. |
| configs/datasets/pipeline.yaml | Global split, segmentation, audio-canonicalization, and loudness-normalization policy. |
| tests/test_data_pipeline.py | Generated WAV fixture and end-to-end pipeline tests. |
| docs/dataset_audits.md | Dataset suitability, role, and provenance decisions. |
| docs/listening_reviews/ | Human listening-review records for declared datasets. |

## Structure And Flow

1. openrestor-data audit discovers supported audio files and records source duration, sample rate, channels, and basic metadata.
2. openrestor-data ingest writes a source-level index.jsonl. Each record has a stable item_id, source path, source metadata, source checksum, and assigned split.
3. openrestor-data split assigns SonicMaster-derived items with a deterministic SHA-256-based fraction of the source identifier. This prevents order-dependent split changes.
4. openrestor-data segment chooses valid source regions and calls FFmpeg to render canonical clips: 30 seconds, 44.1 kHz, stereo PCM WAV, loudness-normalized to the policy in pipeline.yaml.
5. The segment stage measures RMS and true-peak proxies, rejects silence and invalid output, and writes the clean output manifest plus a checksum JSONL file.
6. openrestor-data shard groups finished WAVs and their manifest records into TAR archives for transfer or later conversion to another storage format.
7. openrestor-data verify, source-stats, and stats validate artifact integrity and report corpus composition.

The current on-disk contract is WAV plus JSONL. A clean manifest row is the join point for later phases and retains item_id, split, source provenance, clean path, audio properties, and checksum data.

## Primary Commands

Run the following sequence for an auditable canonical build. The commands use the current
`openrestor-data` interface; replace `build/` paths with the release workspace used by IT.
Add `--source-root` to `audit` and `ingest` when SonicMaster is mounted somewhere other than
the path recorded in the config. SDD and MUSDB18-HQ are deliberately absent from this build.

```bash
# 1. Inspect candidate source trees and write auditable source summaries.
openrestor-data audit --config configs/datasets/sonicmaster_clean.yaml --output build/audits/sonicmaster_clean.json

# 2. Index approved source files with media metadata and source checksums.
openrestor-data ingest --config configs/datasets/sonicmaster_clean.yaml --output build/indexes/sonicmaster.jsonl

# 3. Apply the authoritative frozen SonicMaster split.
#    Omitting --sonicmaster-split-manifest falls back to the legacy seeded-hash split.
openrestor-data split --indexes build/indexes/sonicmaster.jsonl --output build/sources.jsonl --sonicmaster-split-manifest configs/datasets/sonicmaster_original_split.jsonl

# 4. Render canonical clean clips and write their manifest and checksums.
openrestor-data segment --sources build/sources.jsonl --output-root build/clean --manifest build/index.jsonl --checksums build/checksums.jsonl

# 5. Package canonical WAVs into portable TAR shards, then verify every checksum.
openrestor-data shard --output-root build/clean --manifest build/index.jsonl --shards-dir build/shards
openrestor-data verify --root build/clean --checksums build/checksums.jsonl

# 6. Report source and rendered-corpus composition for release review.
openrestor-data source-stats --manifest build/sources.jsonl --output build/source_statistics.json
openrestor-data stats --manifest build/index.jsonl --output build/statistics.json
```

- `audit` discovers supported audio files below a configured source root and records a bounded media-quality sample. It is the first check that the expected local dataset is present and plausible.
- `ingest` writes one JSONL source row per eligible file, including source path, source ID, duration, sample rate, channel count, split role, and SHA-256. It does not render or modify audio.
- `audit` and `ingest` accept `--source-root` to override the config's `source_root` when the same dataset is mounted at a different path on a given machine. The committed configs stay unchanged.
- `split` applies the authoritative frozen original SonicMaster manifest, with ARIEL and
  seeded-hash modes retained only for legacy reproduction. It rejects split leakage.
- `segment` selects deterministic 30-second windows, invokes FFmpeg to produce 44.1 kHz stereo PCM WAV, applies the configured loudness normalization, rejects invalid or silent clips, and writes the clean manifest plus checksums.
- `shard` packages the rendered WAVs and manifest records into fixed-size TAR archives for transfer or hosted storage. The canonical WAV/JSONL contract remains unchanged.
- `verify` recomputes each rendered WAV checksum and fails on missing or altered files.
- `source-stats` and `stats` summarize, respectively, the source index and finished clean manifest for release auditing.

Users who independently and lawfully hold SDD or MUSDB18-HQ may build isolated local
diagnostic packs with `scripts/build_optional_local_transfer_pack.sh`; see
`docs/optional_local_data.md`. Those packs must not be combined with the canonical corpus,
published, or used for the official leaderboard score.

## Verification In Place

tests/test_data_pipeline.py creates a small synthetic 31-second stereo WAV and verifies ingestion, deterministic splitting, canonical segmentation, checksum creation, TAR sharding, verification, and statistics. CI runs this test suite using Python 3.11.

## Current Limits

- Shards are TAR archives today, not the HDF5 storage format mentioned in early roadmap material.
- Source roots are local filesystem paths. Remote object storage, access control, backups, and retention are deployment responsibilities.
- The pipeline does not yet publish a versioned corpus release or an immutable build identifier.

## Next Steps For IT

This is the Phase 1 IT checklist from the roadmap:

- [ ] Provide hosted storage locations for public, private, release, and temporary dataset artifacts.
- [ ] Implement access control for private evaluation data and restricted source datasets.
- [ ] Provide transfer/sync tooling so the research-owned dataset pipeline can read inputs and write outputs in hosted storage.
- [ ] Configure backups, retention, quotas, and checksums for hosted dataset artifacts.
- [ ] Run the research-owned dataset pipeline in the hosted environment and report infrastructure failures separately from pipeline failures.

### Handoff Details

Use read-only source mounts and a separate write location for generated artifacts. Retain the input configuration, Git revision, command log, index.jsonl, clean manifest, and checksum file with every production build. IT may use TAR, object storage, or HDF5 as the storage backend, but must preserve the WAV/JSONL manifest contract consumed by later phases.

## Next Steps For Research

- Finalize source-license and redistribution records for each declared dataset.
- Freeze the first clean-corpus version after a listening review and manifest audit.
- Define public versus hidden evaluation membership before any participant-facing release.
