# OpenRestor

OpenRestor is a reproducible benchmark for musical audio restoration. This repository currently contains the Phase 1 dataset preparation pipeline and the Phase 2 local degradation renderer.

The repository contains the frozen benchmark pipeline and the separate OpenRestor Clean
multi-dataset curation workflow. SonicMaster remains the historical main-track source in
the benchmark contract, but its audio is currently withheld from redistribution pending
track-level rights clarification. The Clean v0.1 candidate is metadata-only until each
source has verified provenance, lossless status, curation results, and redistribution
approval. SDD and MUSDB18-HQ remain local-only transfer-evaluation sets for users who
lawfully hold the upstream data; their audio is not redistributed.

Use Python 3.11 or newer. For a fresh local environment, create and activate a virtual
environment before installing the package:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python --version
command -v ffmpeg ffprobe
```

If Python 3.12 is not installed, `uv venv --python 3.12 --seed .venv` can create the
environment and download a compatible interpreter. Both `ffmpeg` and `ffprobe` must be on
`PATH` for the data pipeline and tests; activating the environment also exposes copies
installed in `.venv/bin`. Commands print progress by default; add `--quiet` for automated
runs.

If importing `pyroomacoustics` fails with a missing `GLIBCXX` version after moving the
environment between machines, rebuild that package with the local C++ compiler:
`python -m pip install --force-reinstall --no-deps --no-binary pyroomacoustics 'pyroomacoustics==0.9.0'`.

Start with the [OpenRestor Guide](docs/openrestor_guide.md) for the public artifacts, dataset roles, local validation workflow, degradation pipeline, and submission contract. The released validation and public-test packages include OpenRestor-rendered degraded counterparts and manifests where source redistribution permits; use the public scorer rather than reimplementing the metrics.

## Licensing Status

The proposed licence for EPFL-owned OpenRestor code and original manifests is the EPFL
Source Code Academic License, subject to laboratory and TTO approval. The SonicMaster
degradation adaptation retains its upstream Apache-2.0 permissions. No project licence
relicenses benchmark audio. Dataset and asset decisions, including the completed
SonicMaster/Jamendo per-track audit and its unresolved publication gate, are documented in
[the licensing guide](docs/licensing.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
The two redistribution scenarios have separate inventories:
[academic non-commercial](docs/redistribution_inventory_academic.md) and
[academic with commercially compatible media](docs/redistribution_inventory_commercial_ready.md).

## Repository Context

This repository pins Node.js 24 for Repomix via `.nvmrc`, `.node-version`,
and the `package.json` Volta setting, and pins Repomix 1.18.1 in the repository
script. If your shell does not auto-select Node 24, activate the local toolchain
installed under the ignored `.venv` directory first. The local wrapper avoids a network
download and writes the ignored snapshot at the repository root:

```bash
source .venv/bin/activate
repomix --style xml --output repomix-output.xml .
```

## Dataset Preparation

```bash
openrestor-data audit --config configs/datasets/sonicmaster_clean.yaml --output build/audits/sonicmaster_clean.json
openrestor-data ingest --config configs/datasets/sonicmaster_clean.yaml --output build/indexes/sonicmaster.jsonl
openrestor-data split --indexes build/indexes/sonicmaster.jsonl --sonicmaster-split-manifest configs/datasets/sonicmaster_original_split.jsonl --output build/sources.jsonl
openrestor-data source-stats --manifest build/sources.jsonl --output build/source_statistics.json
openrestor-data segment --sources build/sources.jsonl --output-root /path/to/openrestor-clips --manifest build/index.jsonl --checksums build/checksums.jsonl
openrestor-data shard --output-root /path/to/openrestor-clips --manifest build/index.jsonl --shards-dir build/shards
openrestor-data verify --root /path/to/openrestor-clips --checksums build/checksums.jsonl
openrestor-data stats --manifest build/index.jsonl --output build/statistics.json
```

SDD and MUSDB18-HQ never enter the canonical public build. Lawful source holders can create
explicitly local-only diagnostic packs with
`scripts/build_optional_local_transfer_pack.sh`; see
[Optional Local Data Packs](docs/optional_local_data.md).

## Degradation Pipeline

The active benchmark registry has exactly 21 canonical degradation classes. Validate and inspect it with:

```bash
openrestor-degrade validate-config --config configs/degradations/single/v0_1.yaml
openrestor-degrade list-recipes --config configs/degradations/single/v0_1.yaml
openrestor-degrade shard --output-root build/degraded --manifest build/degraded/manifest.jsonl --shards-dir build/release/shards --output-index build/release/index.jsonl --shard-size 840

# Private production release: validate clean clips, then create the frozen job plan.
openrestor-degrade plan-release --clean-manifest build/clean/manifest.jsonl --clean-root build/clean/audio --release-config configs/releases/private_v0_1.yaml --output build/private-releases/openrestor-paired-v0.1/plan.json

# Metrics and local restored-output validation
openrestor-score validate-restored --degraded-manifest build/degraded/manifest.jsonl --restored-manifest build/restored/restoration_outputs.jsonl
openrestor-score score --degraded-manifest build/degraded/manifest.jsonl --degraded-root build/degraded --clean-root build/clean --restored-manifest build/restored/restoration_outputs.jsonl --config configs/evaluation/metrics.yaml --output-dir build/scores
```

For the scoring contracts, perceptual-cache setup, and artifact meanings, read [the Phase 3 scoring guide](docs/phase_3_scoring.md). The versioned task and ownership contract is [docs/benchmark_contract.md](docs/benchmark_contract.md). The required microphone and real-RIR artifact layout is [docs/degradation_assets.md](docs/degradation_assets.md). Rights and isolation requirements for the organizer-only set are in [docs/hidden_evaluation.md](docs/hidden_evaluation.md).

`docs/dataset_audits.md` records source roles and release gates. The dataset implementation renders canonical 30-second, 44.1 kHz, stereo PCM WAV clips; partial segments are rejected, mono is duplicated to stereo, multichannel sources are downmixed to stereo, and silent clips fail the RMS quality gate.

## Perceptual Metrics

The optional GPU pack is documented in [Phase 3 scoring](docs/phase_3_scoring.md). Install it with `python -m pip install -e '.[perceptual]'`, run `openrestor-score setup-perceptual` once to populate a verified model cache, then use `openrestor-score perceptual` for the separate learned-metric report.
