_Keep this file in sync with `OpenRestore_Split_Roadmap.md`._


# IT / Software Engineering GitHub Issues

Issue list derived from the IT/software-engineer tasks in `OpenRestore_Split_Roadmap.md`.

Labels are limited to:

- `feat` — new user-facing or system capability
- `chore` — internal maintenance, configuration, or operational setup that does not change external features
- `docs` — documentation or decision records
- `task` — non-coding work done outside the repo, typically in hosted infrastructure or third-party services
- `refactor` — restructuring without changing behavior

---

## Hosting environment & deployment contract

### Target hosting environment

- **Confirm target hosting platform and resource profile**
  - Labels: `task`
  - Description: Document the agreed platform (internal server, Kubernetes, GitLab runner, cloud runner, etc.) plus CPU/GPU availability, storage quotas, and expected job duration limits.
  - Acceptance: A signed-off hosting decision record exists in `docs/`.

### Deployment & CI/CD contract

- **Define deployment requirements for the pipeline package**
  - Labels: `docs`
  - Description: Specify container registry location, secrets/credential handling, environment variables, log/monitoring expectations, and backup policy.
  - Acceptance: A deployment requirements doc is reviewed by research and IT.

- **Define how CLI tools will run in hosted CI/CD and scheduled jobs**
  - Labels: `chore`
  - Description: Decide how `openrestor-*` commands are invoked in hosted CI/CD and cron/scheduled jobs, including artifact passing and failure notification.
  - Acceptance: Sample CI job definitions or scheduled-job templates are committed.

---

## Hosted dataset infrastructure

### Storage locations & access control

- **Provide hosted storage locations for dataset artifacts**
  - Labels: `task`
  - Description: Create and document public, private, release, and temporary storage buckets/directories for dataset artifacts.
  - Acceptance: Storage paths are documented and accessible to the pipeline.

- **Implement access control for private evaluation and restricted source data**
  - Labels: `task`
  - Description: Restrict access to hidden evaluation datasets and any source datasets with redistribution limits.
  - Acceptance: Access-control matrix documented; only authorized accounts/services can read private data.

- **Provide transfer/sync tooling for the dataset pipeline**
  - Labels: `feat`
  - Description: Provide tools or mounts so the research-owned dataset pipeline can read inputs from and write outputs to hosted storage.
  - Acceptance: A miniature dataset build runs end-to-end using hosted storage.

### Lifecycle management

- **Configure backups, retention, quotas, and checksums for dataset artifacts**
  - Labels: `chore`
  - Description: Apply backup schedules, retention policies, quota enforcement, and checksum verification to all hosted dataset artifacts.
  - Acceptance: Backup/retention policy documented; checksum verification runs on schedule.

- **Run research-owned dataset pipeline in hosted environment**
  - Labels: `task`
  - Description: Execute the dataset pipeline in the hosted environment and report infrastructure failures separately from scientific/pipeline failures.
  - Acceptance: A successful hosted run exists with separate infra and pipeline failure logs.

---

## Hosted degradation compute

### Batch compute

- **Provide hosted compute for the degradation command at release scale**
  - Labels: `task`
  - Description: Provision enough compute to render degraded audio for the full dataset build without changing degradation code.
  - Acceptance: A release-scale degradation job can be queued and executed.

- **Configure scheduling, retries, logs, and monitoring for degradation runs**
  - Labels: `chore`
  - Description: Set up job scheduler, retry policy, log aggregation, and monitoring/alerting for degradation jobs.
  - Acceptance: Dashboard or alert exists for degradation job health.

- **Provide parallel execution capacity for large dataset builds**
  - Labels: `task`
  - Description: Ensure the runner can scale horizontally for large builds while preserving deterministic seeds.
  - Acceptance: A multi-worker degradation build completes successfully and checksums match a single-worker run.

### Degradation artifact storage

- **Store degraded shards, manifests, checksums, and logs**
  - Labels: `task`
  - Description: Place degraded output shards, JSONL manifests, SHA-256 checksums, and run logs in agreed hosted artifact locations.
  - Acceptance: All expected artifacts are present after a degradation run.

- **Report infrastructure/quota/timeout failures separately from pipeline failures**
  - Labels: `feat`
  - Description: Distinguish infra-level failures (out of disk, timeout, preemption) from scientific failures (bad config, missing asset).
  - Acceptance: Failure classification is visible in logs and alerts.

---

## Hosted scoring & metrics infrastructure

### Scoring workers

- **Host research-owned scoring command for public and hidden evaluation**
  - Labels: `task`
  - Description: Make the scoring CLI runnable as a hosted job for both public validation/test and private organizer evaluation.
  - Acceptance: A scoring job runs against fixture data in the hosted environment.

- **Provide GPU-capable workers if selected metrics require them**
  - Labels: `task`
  - Description: Provision GPU nodes or cloud workers for embedding-based or deep metrics (CLAP, FAD, etc.) if adopted.
  - Acceptance: GPU scoring job completes successfully.

### Caching & artifact management

- **Manage caches for external metric models, embeddings, and reference statistics**
  - Labels: `feat`
  - Description: Host persistent caches for downloaded models, computed embeddings, and reference-distribution statistics.
  - Acceptance: Cache is shared across scoring runs and invalidated/versioned appropriately.

- **Store scores, reports, logs, and intermediate metric artifacts**
  - Labels: `task`
  - Description: Persist `scores.json`, per-item metric outputs, logs, and report inputs in hosted storage.
  - Acceptance: Artifacts are written to agreed paths after each scoring run.

### Report publishing

- **Publish generated reports and leaderboard-ready JSON artifacts**
  - Labels: `feat`
  - Description: Copy generated reports and leaderboard JSON files to the agreed internal or public location.
  - Acceptance: Reports and JSON are reachable via stable URL after a scoring run.

---

## Hosted baselines & leaderboard data

### Baseline artifact hosting

- **Host baseline containers, weights, restored outputs, scores, and logs**
  - Labels: `task`
  - Description: Store all baseline artifacts in agreed artifact storage.
  - Acceptance: Each baseline has a versioned storage location with container, weights, outputs, scores, and logs.

- **Configure hosted reruns of research-owned baseline commands**
  - Labels: `chore`
  - Description: Set up automated reruns of baseline commands whenever a release candidate changes.
  - Acceptance: A baseline rerun triggers and completes on a new release candidate.

- **Ensure hosted baseline reruns use exact release data, container digest, and command**
  - Labels: `feat`
  - Description: Pin data version, container image digest, and command invocation so reruns are bit-for-bit reproducible.
  - Acceptance: Rerun configuration records data hash, image digest, and command.

### Baseline result publishing

- **Publish baseline results to leaderboard site or internal review page**
  - Labels: `feat`
  - Description: Surface baseline scores on the leaderboard or an internal review page.
  - Acceptance: Baseline results appear on the site after each rerun.

---

## Secure organizer evaluation

### Evaluation sandbox

- **Host organizer evaluation command in secure container execution environment**
  - Labels: `feat`
  - Description: Deploy the local organizer evaluation command as a hosted, sandboxed service.
  - Acceptance: Evaluation command runs inside sandbox with no network/raw privilege escape.

- **Pull submitted images by digest and run with approved mounts/timeouts/limits**
  - Labels: `feat`
  - Description: Enforce image digest pinning, approved volume mounts, timeout, CPU/memory/GPU limits, and resource quotas.
  - Acceptance: A test submission runs under enforced constraints.

### Secrets & data protection

- **Manage secrets, network policy, private evaluation mounts, and output permissions**
  - Labels: `task`
  - Description: Configure credentials, network isolation, private-data mounts, and output ACLs for evaluation.
  - Acceptance: Security review passes; private evaluation audio is not accessible to submissions.

- **Store submission manifests, container digests, logs, outputs, checksums, and metrics securely**
  - Labels: `task`
  - Description: Persist all evaluation audit artifacts in secure, access-controlled storage.
  - Acceptance: All artifacts are encrypted-at-rest and access-logged.

- **Expose operational status and failure logs to organizers without exposing hidden audio**
  - Labels: `feat`
  - Description: Provide an organizer-facing status/log view that shows run health and failures without revealing evaluation audio.
  - Acceptance: Organizers can view logs/status; evaluation audio paths/content are redacted.

---

## Public release, website & leaderboard

### Release artifact publishing

- **Publish release artifact bundle to Hugging Face Datasets**
  - Labels: `task`
  - Description: Upload the research-owned public release bundle to the Hugging Face Datasets hub.
  - Acceptance: Dataset is public on Hugging Face with documented splits and checksums.

- **Publish release artifact bundle to Zenodo**
  - Labels: `task`
  - Description: Upload the release bundle to Zenodo and obtain a DOI.
  - Acceptance: Zenodo record exists with DOI and all allowed assets.

- **Publish release artifact bundle to static project website**
  - Labels: `task`
  - Description: Host downloadable release artifacts on the OpenRestore project website.
  - Acceptance: Release files are downloadable from a stable URL.

- **Store hidden evaluation artifacts in internal private storage**
  - Labels: `task`
  - Description: Keep organizer-only evaluation data and artifacts in private storage, separate from public release assets.
  - Acceptance: Private artifacts are not reachable from public release paths.

### Site & leaderboard deployment

- **Deploy static leaderboard and documentation site**
  - Labels: `feat`
  - Description: Build and deploy the static site generated by the runnable pipeline.
  - Acceptance: Website and leaderboard are live on a public URL.

- **Wire research-owned validation commands into hosted CI/CD**
  - Labels: `chore`
  - Description: Integrate release validation commands into the hosted CI/CD pipeline so releases are checked automatically.
  - Acceptance: A release candidate fails the pipeline if validation commands fail.

- **Configure mirrors, backups, storage quotas, and uptime monitoring for release assets**
  - Labels: `chore`
  - Description: Set up asset mirroring, backups, quota enforcement, and uptime monitoring for public and private release assets.
  - Acceptance: Monitoring alerts on asset unavailability; mirror and backup policies are documented.

---

## Post-v0.1 platform extensions

### Listening-test & model-registry hosting

- **Host listening-test collection tools**
  - Labels: `feat`
  - Description: Deploy the listening-test interface/protocol delivered by the research team.
  - Acceptance: Participants can complete listening tests via a hosted URL.

- **Host model and baseline artifact registries**
  - Labels: `feat`
  - Description: Provide a scalable registry for model weights, containers, and baseline artifacts as the number of baselines grows.
  - Acceptance: Registry supports versioned uploads and authenticated downloads.

### Evaluation & leaderboard enhancements

- **Improve compute scheduling for expensive hidden evaluations**
  - Labels: `chore`
  - Description: Optimize job scheduling, queueing, and resource allocation for large hidden-evaluation workloads.
  - Acceptance: Evaluation turnaround time is measured and improved.

- **Deploy richer leaderboard filtering, comparison, and version snapshots**
  - Labels: `feat`
  - Description: Add leaderboard features for filtering by track/metric, comparing submissions, and viewing version snapshots.
  - Acceptance: New leaderboard UI features are live and tested.

---

## Observability & operational readiness

### Logging & monitoring

- **Define logging and monitoring expectations for hosted pipeline**
  - Labels: `docs`
  - Description: Document log formats, retention, metrics, dashboards, and alerting expectations for all hosted components.
  - Acceptance: Monitoring runbook is reviewed and committed.

- **Implement infrastructure failure separation and operational alerting**
  - Labels: `feat`
  - Description: Ensure infra failures (disk, quota, timeout, preemption) are classified and alerted separately from pipeline errors.
  - Acceptance: Alerts include failure classification and runbook link.

- **Add uptime monitoring for public and private release assets**
  - Labels: `feat`
  - Description: Monitor availability of public website, download URLs, and private storage endpoints.
  - Acceptance: Uptime checks run at regular intervals and alert on outage.
