# Phase 1 Report: Dataset Audit, Ingestion, And Splitting

## Status

Implemented and verified locally. Phase 1 turns declared source datasets into a reproducible clean-audio corpus with stable splits, canonical clips, manifests, checksums, and archive shards.

## Purpose

Phase 1 owns the clean side of the benchmark. Its output is the reference material consumed by the in-progress degradation pipeline in Phase 2 and, later, restoration evaluation. Source audio is inspected before it is copied, every generated clip is tied to its original source, and manifests retain the information required to reproduce a build.

## Dataset Allocation

This is the Phase 1 implementation of the dataset strategy defined in `OpenRestore.md`. Every benchmark item is a clean 30-second music clip and an OpenRestore-generated degraded counterpart; naturally degraded SonicMaster pairs are not reused.

| Dataset | OpenRestore use | Explicit exclusions |
| --- | --- | --- |
| SonicMaster clean originals | The only default main-track training source. Source-separated held-out items also supply in-distribution validation and the public test split. | Do not use SonicMaster degraded pairs as benchmark or leaderboard data. |
| Song Describer Dataset (SDD) | Separately reported public transfer/local evaluation, for transfer to curated captioned music. | Never use for main-track training or the in-distribution public test. |
| MUSDB18-HQ mixture audio | Separately reported public transfer/local evaluation, as a real mixed-music robustness check. | Never use for main-track training, the in-distribution public test, or stems. |
| Secret custom music dataset | Organizer-only hidden official evaluation. | Never release publicly or expose to participants. |
| BBC Sound Effects, Freesound, FSD50K, MUSAN | Optional source material for Phase 2 organic degradation layers. | Never use as clean benchmark music. |

Any other training data belongs to the external-data track unless the benchmark contract is explicitly revised. FMA is not a Phase 1 benchmark source.

## Implementation Map

| Path | Responsibility |
| --- | --- |
| openrestore/data/core.py | Shared data structures, JSONL/YAML I/O, stable hash splitting, SHA-256, FFprobe metadata inspection, and source discovery. |
| openrestore/data/pipeline.py | Dataset ingestion, split assignment, 30-second clip rendering, quality checks, manifests, checksums, shard creation, verification, and statistics. |
| openrestore/data/cli.py | openrestore-data command-line interface. |
| configs/datasets/*.yaml | Source declarations, roles, local roots, licensing reminders, and minimum source duration. |
| configs/datasets/pipeline.yaml | Global split, segmentation, audio-canonicalization, and loudness-normalization policy. |
| tests/test_data_pipeline.py | Generated WAV fixture and end-to-end pipeline tests. |
| docs/dataset_audits.md | Dataset suitability, role, and provenance decisions. |
| docs/listening_reviews/ | Human listening-review records for declared datasets. |

## Structure And Flow

1. openrestore-data audit discovers supported audio files and records source duration, sample rate, channels, and basic metadata.
2. openrestore-data ingest writes a source-level index.jsonl. Each record has a stable item_id, source path, source metadata, source checksum, and assigned split.
3. openrestore-data split assigns SonicMaster-derived items with a deterministic SHA-256-based fraction of the source identifier. This prevents order-dependent split changes.
4. openrestore-data segment chooses valid source regions and calls FFmpeg to render canonical clips: 30 seconds, 44.1 kHz, stereo PCM WAV, loudness-normalized to the policy in pipeline.yaml.
5. The segment stage measures RMS and true-peak proxies, rejects silence and invalid output, and writes the clean output manifest plus a checksum JSONL file.
6. openrestore-data shard groups finished WAVs and their manifest records into TAR archives for transfer or later conversion to another storage format.
7. openrestore-data verify, source-stats, and stats validate artifact integrity and report corpus composition.

The current on-disk contract is WAV plus JSONL. A clean manifest row is the join point for later phases and retains item_id, split, source provenance, clean path, audio properties, and checksum data.

## Primary Commands

Run the following sequence for an auditable local build. The commands use the current `openrestore-data` interface; replace `build/` paths with the release workspace used by IT.

```bash
# 1. Inspect candidate source trees and write auditable source summaries.
openrestore-data audit --config configs/datasets/sonicmaster_clean.yaml --output build/audits/sonicmaster_clean.json
openrestore-data audit --config configs/datasets/sdd_transfer.yaml --output build/audits/sdd.json
openrestore-data audit --config configs/datasets/musdb18_hq_transfer.yaml --output build/audits/musdb18_hq.json

# 2. Index approved source files with media metadata and source checksums.
openrestore-data ingest --config configs/datasets/sonicmaster_clean.yaml --output build/indexes/sonicmaster.jsonl
openrestore-data ingest --config configs/datasets/sdd_transfer.yaml --output build/indexes/sdd.jsonl
openrestore-data ingest --config configs/datasets/musdb18_hq_transfer.yaml --output build/indexes/musdb18_hq.jsonl

# 3. Deterministically split SonicMaster and combine the fixed public transfer-evaluation sources.
openrestore-data split --indexes build/indexes/sonicmaster.jsonl build/indexes/sdd.jsonl build/indexes/musdb18_hq.jsonl --output build/sources.jsonl

# 4. Render canonical clean clips and write their manifest and checksums.
openrestore-data segment --sources build/sources.jsonl --output-root build/clean --manifest build/index.jsonl --checksums build/checksums.jsonl

# 5. Package canonical WAVs into portable TAR shards, then verify every checksum.
openrestore-data shard --output-root build/clean --manifest build/index.jsonl --shards-dir build/shards
openrestore-data verify --root build/clean --checksums build/checksums.jsonl

# 6. Report source and rendered-corpus composition for release review.
openrestore-data source-stats --manifest build/sources.jsonl --output build/source_statistics.json
openrestore-data stats --manifest build/index.jsonl --output build/statistics.json
```

- `audit` discovers supported audio files below a configured source root and records a bounded media-quality sample. It is the first check that the expected local dataset is present and plausible.
- `ingest` writes one JSONL source row per eligible file, including source path, source ID, duration, sample rate, channel count, split role, and SHA-256. It does not render or modify audio.
- `split` applies the fixed seeded split to SonicMaster source IDs, then combines it with SDD and MUSDB18-HQ, which remain fixed `transfer` sources by policy. It rejects split leakage.
- `segment` selects deterministic 30-second windows, invokes FFmpeg to produce 44.1 kHz stereo PCM WAV, applies the configured loudness normalization, rejects invalid or silent clips, and writes the clean manifest plus checksums.
- `shard` packages the rendered WAVs and manifest records into fixed-size TAR archives for transfer or hosted storage. The canonical WAV/JSONL contract remains unchanged.
- `verify` recomputes each rendered WAV checksum and fails on missing or altered files.
- `source-stats` and `stats` summarize, respectively, the source index and finished clean manifest for release auditing.

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
