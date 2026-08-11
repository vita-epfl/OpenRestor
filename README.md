# OpenRestore

OpenRestore is a reproducible benchmark for musical audio restoration. This repository currently contains the Phase 1 dataset preparation pipeline and the Phase 2 local degradation renderer.

The pipeline uses only clean SonicMaster originals for main-track training and source-separated SonicMaster validation/test. SDD and MUSDB18-HQ mixture audio are validation-only; FMA is not part of this release.

Install the local package with `python -m pip install -e .`. Commands print progress by default; add `--quiet` for automated runs.

## Dataset Preparation

```bash
openrestore-data audit --config configs/datasets/sonicmaster_clean.yaml --output build/audits/sonicmaster_clean.json
openrestore-data ingest --config configs/datasets/sonicmaster_clean.yaml --output build/indexes/sonicmaster.jsonl
openrestore-data ingest --config configs/datasets/sdd_validation.yaml --output build/indexes/sdd.jsonl
openrestore-data ingest --config configs/datasets/musdb18_hq_validation.yaml --output build/indexes/musdb18_hq.jsonl
openrestore-data split --indexes build/indexes/sonicmaster.jsonl build/indexes/sdd.jsonl build/indexes/musdb18_hq.jsonl --output build/sources.jsonl
openrestore-data source-stats --manifest build/sources.jsonl --output build/source_statistics.json
openrestore-data segment --sources build/sources.jsonl --output-root /path/to/openrestore-clips --manifest build/index.jsonl --checksums build/checksums.jsonl
openrestore-data shard --output-root /path/to/openrestore-clips --manifest build/index.jsonl --shards-dir build/shards
openrestore-data verify --root /path/to/openrestore-clips --checksums build/checksums.jsonl
openrestore-data stats --manifest build/index.jsonl --output build/statistics.json
```

## Degradation Pipeline

The active single-effect registry has 25 degradations. Validate and inspect it with:

```bash
openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml
openrestore-degrade list-recipes --config configs/degradations/single/v0_1.yaml
```

For the exact render contract, storage layout, optional-asset handling, acceptance checks, and IT responsibilities, read [the IT handoff](docs/it_handoff.md). The versioned task and ownership contract is [docs/benchmark_contract.md](docs/benchmark_contract.md).

`docs/dataset_audits.md` records source roles and release gates. The dataset implementation renders canonical 30-second, 44.1 kHz, stereo PCM WAV clips; partial segments are rejected, mono is duplicated to stereo, multichannel sources are downmixed to stereo, and silent clips fail the RMS quality gate.
