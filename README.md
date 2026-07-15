# OpenRestore

OpenRestore is a reproducible benchmark for musical audio restoration. This repository currently
contains the Phase 1 dataset preparation pipeline.

The pipeline uses only clean SonicMaster originals for main-track training and source-separated
SonicMaster validation/test. SDD and MUSDB18-HQ mixture audio are validation-only; FMA is not part
of this release.

Install the local package with `python -m pip install -e .`. The commands below build public data
into a directory outside the repository. Commands print progress by default; add `--quiet` for
automated runs.

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

`docs/dataset_audits.md` records the source roles and release gates. The implementation renders
canonical 30-second, 44.1 kHz, stereo PCM WAV clips; partial segments are rejected, mono is
duplicated to stereo, multichannel sources are downmixed to stereo, and silent clips fail the RMS
quality gate.
