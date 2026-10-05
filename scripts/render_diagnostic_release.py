#!/usr/bin/env python3
"""Drive the 648 Diagnostic partitions locally, with a bounded worker pool.

Each partition is an independent unit of work, so this is embarrassingly parallel.
The driver is idempotent: a partition whose shard already reads back with the
expected row count is skipped, so an interrupted run resumes instead of restarting.

This is the local counterpart to submitting one Run:ai job per partition. It exists
because 648 jobs on a shared cluster and 648 subprocesses on one machine want the
same bookkeeping, and the bookkeeping is the part worth getting right.

    python scripts/render_diagnostic_release.py --workers 8
    python scripts/render_diagnostic_release.py --workers 8 --clean-staging
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def partition_ids(plan: Path) -> list[tuple[str, int]]:
    data = json.loads(plan.read_text(encoding="utf-8"))
    return [(p["id"], int(p["expected_outputs"])) for p in data["partitions"]]


def shard_is_complete(release_root: Path, partition_id: str, expected: int) -> bool:
    """A partition counts as done only if its shard opens and holds every row."""
    shards = sorted((release_root / "shards" / partition_id).glob("*.h5"))
    if not shards:
        return False
    try:
        import h5py

        total = 0
        for shard in shards:
            with h5py.File(shard, "r") as handle:
                total += handle["audio"].shape[0]
        return total == expected
    except Exception:
        return False


def render_one(
    partition_id: str,
    expected: int,
    plan: Path,
    clean_manifest: Path,
    clean_root: Path,
    release_config: Path,
    work_root: Path,
    release_root: Path,
    log_dir: Path,
    clean_staging: bool,
) -> tuple[str, str, float]:
    started = time.monotonic()
    if shard_is_complete(release_root, partition_id, expected):
        return partition_id, "skipped", 0.0
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{partition_id}.log"
    command = [
        sys.executable, "-m", "openrestore.degradations.cli", "render-partition",
        "--plan", str(plan), "--partition-id", partition_id,
        "--clean-manifest", str(clean_manifest), "--clean-root", str(clean_root),
        "--release-config", str(release_config),
        "--work-root", str(work_root), "--release-root", str(release_root),
    ]
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        return partition_id, f"failed(rc={result.returncode})", elapsed
    if not shard_is_complete(release_root, partition_id, expected):
        # The common cause is the renderer being killed mid-packaging, which leaves a
        # truncated shard and an empty log. Report it rather than counting a success.
        return partition_id, "incomplete-shard", elapsed
    if clean_staging:
        shutil.rmtree(work_root / partition_id, ignore_errors=True)
    return partition_id, "done", elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=REPO / "build/private-releases/openrestore-paired-v0.1/plan.json")
    parser.add_argument("--clean-manifest", type=Path, default=REPO / "build/index.jsonl")
    parser.add_argument("--clean-root", type=Path, default=REPO / "build/clean")
    parser.add_argument("--release-config", type=Path, default=REPO / "configs/releases/private_v0_1.yaml")
    parser.add_argument("--work-root", type=Path, default=REPO / "build/degradation-staging")
    parser.add_argument("--release-root", type=Path, default=REPO / "build/private-releases/openrestore-paired-v0.1")
    parser.add_argument("--log-dir", type=Path, default=REPO / "build/partition-logs")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, help="Render only the first N outstanding partitions")
    parser.add_argument("--clean-staging", action="store_true", help="Delete a partition's WAV staging once its shard validates")
    parser.add_argument("--dry-run", action="store_true", help="Report what is outstanding and exit")
    args = parser.parse_args()

    partitions = partition_ids(args.plan)
    outstanding = [(pid, n) for pid, n in partitions if not shard_is_complete(args.release_root, pid, n)]
    if args.limit is not None:
        outstanding = outstanding[: args.limit]
    print(f"{len(partitions)} partitions in the plan, {len(outstanding)} outstanding, {args.workers} workers", flush=True)
    if args.dry_run:
        for pid, n in outstanding[:5]:
            print(f"  would render {pid} ({n} outputs)")
        if len(outstanding) > 5:
            print(f"  ... and {len(outstanding) - 5} more")
        return

    counts: dict[str, int] = {}
    durations: list[float] = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(
                render_one, pid, n, args.plan, args.clean_manifest, args.clean_root,
                args.release_config, args.work_root, args.release_root, args.log_dir,
                args.clean_staging,
            )
            for pid, n in outstanding
        ]
        for done, future in enumerate(as_completed(futures), start=1):
            pid, status, elapsed = future.result()
            counts[status] = counts.get(status, 0) + 1
            if status == "done":
                durations.append(elapsed)
            if status not in ("done", "skipped"):
                print(f"  !! {pid}: {status}  (see {args.log_dir / (pid + '.log')})", flush=True)
            if done % 5 == 0 or done == len(futures):
                mean = sum(durations) / len(durations) / 60 if durations else 0.0
                remaining = (len(futures) - done) * mean / max(args.workers, 1)
                print(
                    f"[release] {done}/{len(futures)} | {counts} | mean {mean:.1f} min/partition "
                    f"| ~{remaining / 60:.1f} h left",
                    flush=True,
                )
    print(f"[release] finished in {(time.monotonic() - started) / 3600:.2f} h: {counts}", flush=True)
    if any(k not in ("done", "skipped") for k in counts):
        raise SystemExit("some partitions did not complete; see the per-partition logs")


if __name__ == "__main__":
    main()
