# OpenRestore

OpenRestore is a reproducible benchmark for musical audio restoration. This repository currently contains the Phase 1 dataset preparation pipeline and the Phase 2 local degradation renderer.

The pipeline uses only clean SonicMaster originals for main-track training and SonicMaster’s supplied validation/test splits. SDD and MUSDB18-HQ mixture audio are separate public transfer/local-evaluation sets; FMA is not part of this release.

Install the local package with `python -m pip install -e .`. Commands print progress by default; add `--quiet` for automated runs.

Start with the [OpenRestore Guide](docs/openrestor_guide.md) for the public artifacts, dataset roles, local validation workflow, degradation pipeline, and submission contract. The released validation and public-test packages include OpenRestore-rendered degraded counterparts and manifests where source redistribution permits; use the public scorer rather than reimplementing the metrics.

## Repository Context

This repository pins Node.js 20 for Repomix via `.nvmrc`, `.node-version`,
and the `package.json` Volta setting. If your shell does not auto-select Node
20, run Repomix through the repository script:

```bash
npm run repomix
```

## Dataset Preparation

```bash
openrestor-data audit --config configs/datasets/sonicmaster_clean.yaml --output build/audits/sonicmaster_clean.json
openrestor-data ingest --config configs/datasets/sonicmaster_clean.yaml --output build/indexes/sonicmaster.jsonl
openrestor-data ingest --config configs/datasets/sdd_transfer.yaml --output build/indexes/sdd.jsonl
openrestor-data ingest --config configs/datasets/musdb18_hq_transfer.yaml --output build/indexes/musdb18_hq.jsonl
openrestor-data split --indexes build/indexes/sonicmaster.jsonl build/indexes/sdd.jsonl build/indexes/musdb18_hq.jsonl --output build/sources.jsonl
openrestor-data source-stats --manifest build/sources.jsonl --output build/source_statistics.json
openrestor-data segment --sources build/sources.jsonl --output-root /path/to/openrestor-clips --manifest build/index.jsonl --checksums build/checksums.jsonl
openrestor-data shard --output-root /path/to/openrestor-clips --manifest build/index.jsonl --shards-dir build/shards
openrestor-data verify --root /path/to/openrestor-clips --checksums build/checksums.jsonl
openrestor-data stats --manifest build/index.jsonl --output build/statistics.json
```

## Degradation Pipeline

The active benchmark registry has exactly 24 canonical degradation classes. Validate and inspect it with:

```bash
openrestor-degrade validate-config --config configs/degradations/single/v0_1.yaml
openrestor-degrade list-recipes --config configs/degradations/single/v0_1.yaml
openrestor-degrade shard --output-root build/degraded --manifest build/degraded/manifest.jsonl --shards-dir build/release/shards --output-index build/release/index.jsonl --shard-size 960

# Private production release: validate clean clips, then create the frozen job plan.
openrestor-degrade plan-release --clean-manifest build/clean/manifest.jsonl --clean-root build/clean/audio --release-config configs/releases/private_v0_1.yaml --output build/private-releases/openrestor-paired-v0.1/plan.json

# Metrics and local restored-output validation
openrestor-score validate-restored --degraded-manifest build/degraded/manifest.jsonl --restored-manifest build/restored/restoration_outputs.jsonl
openrestor-score score --degraded-manifest build/degraded/manifest.jsonl --degraded-root build/degraded --clean-root build/clean --restored-manifest build/restored/restoration_outputs.jsonl --config configs/evaluation/metrics.yaml --output-dir build/scores
```

For the scoring contracts, perceptual-cache setup, and artifact meanings, read [the Phase 3 scoring guide](docs/phase_3_scoring.md). The versioned task and ownership contract is [docs/benchmark_contract.md](docs/benchmark_contract.md). The required microphone and real-RIR artifact layout is [docs/degradation_assets.md](docs/degradation_assets.md).

`docs/dataset_audits.md` records source roles and release gates. The dataset implementation renders canonical 30-second, 44.1 kHz, stereo PCM WAV clips; partial segments are rejected, mono is duplicated to stereo, multichannel sources are downmixed to stereo, and silent clips fail the RMS quality gate.

## Perceptual Metrics

The optional GPU pack is documented in [Phase 3 scoring](docs/phase_3_scoring.md). Install it with `python -m pip install -e '.[perceptual]'`, run `openrestor-score setup-perceptual` once to populate a verified model cache, then use `openrestor-score perceptual` for the separate learned-metric report.
