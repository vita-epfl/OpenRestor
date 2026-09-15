"""Command-line interface for the OpenRestore Phase 1 data pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import load_yaml, read_jsonl
from .pipeline import (
    audit,
    combine_and_split,
    ingest,
    segment,
    verify_checksums,
    write_shards,
    write_source_statistics,
    write_statistics,
)


def _path(value: str) -> Path:
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openrestore-data")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "ingest"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=_path, required=True)
        command.add_argument("--output", type=_path, required=True)
        command.add_argument("--quiet", action="store_true")
    commands.choices["audit"].add_argument("--probe-limit", type=int, default=25)
    split = commands.add_parser("split")
    split.add_argument("--indexes", type=_path, nargs="+", required=True)
    split.add_argument("--output", type=_path, required=True)
    split.add_argument("--seed", type=int, default=20260714)
    split.add_argument("--train-fraction", type=float, default=0.90)
    split.add_argument("--validation-fraction", type=float, default=0.05)
    split.add_argument(
        "--ariel-train-manifest", type=_path, help="Use ARIEL's exact SonicMaster train source set"
    )
    split.add_argument(
        "--ariel-test-manifest", type=_path, help="Use ARIEL's exact SonicMaster test source set"
    )
    split.add_argument(
        "--sonicmaster-split-manifest",
        type=_path,
        help="Apply the frozen original SonicMaster train/validation/test assignment",
    )
    split.add_argument("--quiet", action="store_true")
    segment_command = commands.add_parser("segment")
    segment_command.add_argument("--sources", type=_path, required=True)
    segment_command.add_argument("--output-root", type=_path, required=True)
    segment_command.add_argument("--manifest", type=_path, required=True)
    segment_command.add_argument("--checksums", type=_path, required=True)
    segment_command.add_argument("--seed", type=int, default=20260714)
    segment_command.add_argument("--clips-per-source", type=int, default=1)
    segment_command.add_argument("--no-normalize", action="store_true")
    segment_command.add_argument("--min-rms", type=float, default=0.003)
    segment_command.add_argument("--quiet", action="store_true")
    shard = commands.add_parser("shard")
    shard.add_argument("--output-root", type=_path, required=True)
    shard.add_argument("--manifest", type=_path, required=True)
    shard.add_argument("--shards-dir", type=_path, required=True)
    shard.add_argument("--shard-size", type=int, default=1000)
    shard.add_argument("--quiet", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=_path, required=True)
    verify.add_argument("--checksums", type=_path, required=True)
    verify.add_argument("--quiet", action="store_true")
    source_stats = commands.add_parser("source-stats")
    source_stats.add_argument("--manifest", type=_path, required=True)
    source_stats.add_argument("--output", type=_path, required=True)
    source_stats.add_argument("--quiet", action="store_true")
    stats = commands.add_parser("stats")
    stats.add_argument("--manifest", type=_path, required=True)
    stats.add_argument("--output", type=_path, required=True)
    stats.add_argument("--quiet", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    progress = not args.quiet
    if args.command == "audit":
        audit(load_yaml(args.config), args.output, args.probe_limit, progress=progress)
    elif args.command == "ingest":
        ingest(load_yaml(args.config), args.output, progress=progress)
    elif args.command == "split":
        combine_and_split(
            args.indexes,
            args.output,
            args.seed,
            args.train_fraction,
            args.validation_fraction,
            args.ariel_train_manifest,
            args.ariel_test_manifest,
            args.sonicmaster_split_manifest,
            progress=progress,
        )
    elif args.command == "segment":
        segment(
            read_jsonl(args.sources),
            args.output_root,
            args.manifest,
            args.checksums,
            args.seed,
            args.clips_per_source,
            not args.no_normalize,
            args.min_rms,
            progress=progress,
        )
    elif args.command == "shard":
        write_shards(
            args.output_root,
            read_jsonl(args.manifest),
            args.shards_dir,
            args.shard_size,
            progress=progress,
        )
    elif args.command == "verify":
        failures = verify_checksums(args.root, args.checksums, progress=progress)
        if failures:
            raise SystemExit("Checksum failures: " + ", ".join(failures))
    elif args.command == "source-stats":
        write_source_statistics(args.manifest, args.output, progress=progress)
    elif args.command == "stats":
        write_statistics(args.manifest, args.output, progress=progress)


if __name__ == "__main__":
    main()
