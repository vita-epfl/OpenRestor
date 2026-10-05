#!/usr/bin/env python3
"""Drive the Blind-Synthetic render in parallel slices, then merge them.

Blind-Synthetic produces one compound example per clean clip, so it is 21 times
fewer outputs than the Diagnostic set but each costs more: a chain averages about
1.8 degradations instead of exactly one.

Slicing is safe because nothing in the output depends on an item's position. The
chain and every sampled parameter derive from the global seed and the item ID, so a
sliced run is bit-identical to a whole one.

    python scripts/render_blind_synthetic_release.py --workers 6
    python scripts/render_blind_synthetic_release.py --workers 6 --slices 48
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def slice_outputs(out_dir: Path, index: int) -> tuple[Path, Path]:
    return out_dir / f"manifest-{index:04d}.jsonl", out_dir / f"checksums-{index:04d}.jsonl"


def expected_rows(manifest: Path, index: int, count: int) -> int:
    total = sum(1 for _ in manifest.open(encoding="utf-8"))
    size = (total + count - 1) // count
    return len(range(0, total)[index * size : index * size + size])


def render_slice(
    index: int,
    slices: int,
    manifest: Path,
    clean_root: Path,
    output_root: Path,
    config: Path,
    out_dir: Path,
    log_dir: Path,
    seed: int,
) -> tuple[int, str, float]:
    started = time.monotonic()
    manifest_out, checksums_out = slice_outputs(out_dir, index)
    wanted = expected_rows(manifest, index, slices)
    if manifest_out.is_file() and sum(1 for _ in manifest_out.open(encoding="utf-8")) == wanted:
        return index, "skipped", 0.0
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "openrestore.degradations.cli", "render-blind-synthetic",
        "--manifest", str(manifest), "--clean-root", str(clean_root),
        "--output-root", str(output_root), "--config", str(config),
        "--output-manifest", str(manifest_out), "--checksums", str(checksums_out),
        "--seed", str(seed), "--slice-index", str(index), "--slice-count", str(slices), "--quiet",
    ]
    with (log_dir / f"slice-{index:04d}.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        return index, f"failed(rc={result.returncode})", elapsed
    written = sum(1 for _ in manifest_out.open(encoding="utf-8")) if manifest_out.is_file() else 0
    if written != wanted:
        return index, f"incomplete({written}/{wanted})", elapsed
    return index, "done", elapsed


def merge(out_dir: Path, slices: int, manifest_out: Path, checksums_out: Path) -> int:
    """Concatenate the slices in slice order, so the merged manifest is reproducible."""
    rows = 0
    with manifest_out.open("w", encoding="utf-8") as mf, checksums_out.open("w", encoding="utf-8") as cf:
        for index in range(slices):
            m, c = slice_outputs(out_dir, index)
            if not m.is_file():
                raise SystemExit(f"slice {index} is missing: {m}")
            for line in m.open(encoding="utf-8"):
                mf.write(line)
                rows += 1
            for line in c.open(encoding="utf-8"):
                cf.write(line)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO / "build/index.jsonl")
    parser.add_argument("--clean-root", type=Path, default=REPO / "build/clean")
    parser.add_argument("--output-root", type=Path, default=REPO / "build/blind-synthetic/audio")
    parser.add_argument("--config", type=Path, default=REPO / "configs/degradations/blind_synthetic/v0_1.yaml")
    parser.add_argument("--slice-dir", type=Path, default=REPO / "build/blind-synthetic/slices")
    parser.add_argument("--log-dir", type=Path, default=REPO / "build/blind-synthetic/logs")
    parser.add_argument("--output-manifest", type=Path, default=REPO / "build/blind-synthetic/manifest.jsonl")
    parser.add_argument("--checksums", type=Path, default=REPO / "build/blind-synthetic/checksums.jsonl")
    parser.add_argument("--slices", type=int, default=48)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--merge-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = sum(1 for _ in args.manifest.open(encoding="utf-8"))
    print(f"{total} clean clips, {args.slices} slices, {args.workers} workers", flush=True)
    if args.dry_run:
        return

    if not args.merge_only:
        counts: dict[str, int] = {}
        durations: list[float] = []
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(
                    render_slice, i, args.slices, args.manifest, args.clean_root,
                    args.output_root, args.config, args.slice_dir, args.log_dir, args.seed,
                )
                for i in range(args.slices)
            ]
            for done, future in enumerate(as_completed(futures), start=1):
                index, status, elapsed = future.result()
                counts[status] = counts.get(status, 0) + 1
                if status == "done":
                    durations.append(elapsed)
                if status not in ("done", "skipped"):
                    print(f"  !! slice {index}: {status} (see {args.log_dir}/slice-{index:04d}.log)", flush=True)
                mean = sum(durations) / len(durations) / 60 if durations else 0.0
                remaining = (len(futures) - done) * mean / max(args.workers, 1)
                print(f"[blind-synth] {done}/{len(futures)} | {counts} | mean {mean:.1f} min/slice | ~{remaining / 60:.1f} h left", flush=True)
        print(f"[blind-synth] rendered in {(time.monotonic() - started) / 3600:.2f} h: {counts}", flush=True)
        if any(k not in ("done", "skipped") for k in counts):
            raise SystemExit("some slices did not complete; see the per-slice logs")

    rows = merge(args.slice_dir, args.slices, args.output_manifest, args.checksums)
    print(f"[blind-synth] merged {rows} rows into {args.output_manifest}", flush=True)
    if rows != total:
        raise SystemExit(f"merged {rows} rows but the clean manifest has {total}")

    clean = sum(1 for line in args.output_manifest.open(encoding="utf-8") if json.loads(line)["degradation_count"] == 0)
    print(f"[blind-synth] {clean} items left clean ({100.0 * clean / max(rows, 1):.2f}%)", flush=True)


if __name__ == "__main__":
    main()
