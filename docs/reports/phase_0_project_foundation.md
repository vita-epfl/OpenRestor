# Phase 0 Report: Project Contracts And Repository Skeleton

## Status

Implemented. Phase 0 establishes the repository shape, installation contract, JSON schemas, validation CLI, CI check, container starting point, and ownership boundaries needed before larger data or evaluation releases are hosted.

## Purpose

This phase prevents the benchmark from becoming a collection of incompatible scripts. It defines the stable places where the dataset pipeline, degradation pipeline, metrics, evaluation, submissions, and leaderboard work will live. It also gives IT a minimal, testable artifact to host without asking them to invent audio-research behavior.

## Implementation Map

| Path | Responsibility |
| --- | --- |
| pyproject.toml | Python package metadata, runtime dependencies, and installed CLI entry points. |
| openrestore/__init__.py | Root package namespace. |
| openrestore/data/ | Reserved and implemented home of the Phase 1 dataset pipeline. |
| openrestore/degradations/ | Reserved and implemented home of the Phase 2 renderer. |
| openrestore/metrics/ | Reserved namespace for later objective metrics. |
| openrestore/evaluation/ | Reserved namespace for later evaluation orchestration. |
| openrestore/submissions/ | Reserved namespace for submission handling. |
| openrestore/leaderboard/ | Reserved namespace for leaderboard publication logic. |
| openrestore/validation/core.py | Draft 2020-12 JSON Schema validator for JSON and JSONL artifacts. |
| openrestore/validation/cli.py | Installed openrestore-validate command. |
| schemas/*.schema.json | Initial contracts for index, degradation tracking, submissions, scores, and leaderboard entries. |
| .github/workflows/ci.yml | Python 3.11 install, unit tests, degradation-config validation, and schema-fixture validation. |
| docker/Dockerfile | Minimal Python 3.11 and FFmpeg runtime image definition. |
| docker/README.md, scripts/README.md, site/README.md | Deployment, automation, and future site boundaries. |
| docs/benchmark_contract.md | Cross-phase artifact and schema contract. |
| tests/test_schemas.py, tests/fixtures/index.json | Small validated schema fixture. |

## Structure

The repository is a Python package named openrestore. Each benchmark concern has its own namespace so future implementations can share validation and contracts without becoming tightly coupled.

The current schemas are deliberately lightweight. They validate document structure and required fields; they do not yet enforce every future scientific policy. openrestore-validate accepts JSON and JSONL, loads the selected schema from schemas/, and reports invalid records before an artifact is used by another phase.

The installed command surface currently includes:

    openrestore-validate index --input tests/fixtures/index.json
    openrestore-degrade validate-config --config configs/degradations/single/v0_1.yaml

The second command belongs to Phase 2 but proves the package and entry-point pattern is usable in CI and deployment environments.

## Verification In Place

CI uses Python 3.11, installs the package with pip install -e ., runs the unit suite, validates the active degradation configuration, and validates the tiny index fixture. The local test suite covers schema validation in addition to the Phase 1 and Phase 2 behavior tests.

## Current Limits

- The Dockerfile is a runtime starting point, not a published image, deployment specification, or scheduler integration.
- Metrics, evaluation, submissions, and leaderboard packages are boundaries only. Their operational behavior is not implemented.
- Schema files are initial contracts and will need controlled versioning as Phase 2 releases and later evaluation outputs are frozen.
- There is no secrets, identity, artifact registry, or environment configuration system in the repository.

## Next Steps For IT

This is the Phase 0 IT checklist from the roadmap:

- [ ] Confirm the target hosting environment for the runnable pipeline: internal server, Kubernetes, GitLab runner, cloud runner, or another agreed platform.
- [ ] Confirm CPU/GPU availability, storage quotas, and expected job-duration limits.
- [ ] Define deployment requirements: container registry location, secrets and credential handling, environment variables, logs and monitoring expectations, and backup policy.
- [ ] Define how IT will run the delivered command-line tools in hosted CI/CD and scheduled jobs.

### Handoff Details

The delivered starting points are docker/Dockerfile, .github/workflows/ci.yml, pyproject.toml, and the installed commands. IT should publish a pinned runtime image, keep credentials in the hosting platform secret store, and preserve CI logs and build artifacts for auditability. Deployment-specific settings should be external configuration or approved environment variables, not edits to artifact schemas or audio behavior.

## Next Steps For Research

- Version schema changes explicitly and keep old readers available for already released artifacts.
- Expand the benchmark contract only when a producing phase and consuming phase agree on the new field.
- Keep the package boundaries intact as later phases gain real implementations.
