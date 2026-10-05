"""Command-line interface for the OpenRestore Phase 1 data pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

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


def _dataset_config(args: argparse.Namespace) -> dict[str, Any]:
    config = load_yaml(args.config)
    if args.source_root is not None:
        config["source_root"] = str(args.source_root)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openrestore-data")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "ingest"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=_path, required=True)
        command.add_argument("--output", type=_path, required=True)
        command.add_argument("--source-root", type=_path, help="Override the config's source_root when the dataset is mounted elsewhere")
        command.add_argument("--quiet", action="store_true")
    commands.choices["audit"].add_argument("--probe-limit", type=int, default=25)
    scan = commands.add_parser("blind-real-scan", help="Scan the IAMD catalogue for Blind-Real candidates")
    scan.add_argument("--output", type=_path, required=True)
    scan.add_argument("--shards", type=int, default=2320)
    scan.add_argument("--start", type=int, default=0)
    scan.add_argument("--workers", type=int, default=12)
    scan.add_argument("--quiet", action="store_true")

    cand = commands.add_parser("blind-real-candidates", help="Filter a scanned catalogue by licence and live-capture evidence")
    cand.add_argument("--catalogue", type=_path, required=True)
    cand.add_argument("--output", type=_path, required=True)
    cand.add_argument("--stats", type=_path)
    cand.add_argument("--allow-share-alike", action="store_true")
    cand.add_argument("--any-recording", action="store_true", help="Do not require live-capture evidence")

    freeze = commands.add_parser("blind-real-freeze", help="Deduplicate, cap, rank and freeze the Blind-Real candidate list")
    freeze.add_argument("--candidates", type=_path, required=True)
    freeze.add_argument("--output", type=_path, required=True)
    freeze.add_argument("--stats", type=_path)
    freeze.add_argument("--target", type=int, default=400)
    freeze.add_argument("--cap-per-identifier", type=int, default=2)
    freeze.add_argument("--excerpt-seconds", type=float, default=20.0)

    split = commands.add_parser("split")
    split.add_argument("--indexes", type=_path, nargs="+", required=True)
    split.add_argument("--output", type=_path, required=True)
    split.add_argument("--seed", type=int, default=20260714)
    split.add_argument("--train-fraction", type=float, default=0.90)
    split.add_argument("--validation-fraction", type=float, default=0.05)
    split.add_argument("--ariel-train-manifest", type=_path, help="Use ARIEL's exact SonicMaster train source set")
    split.add_argument("--ariel-test-manifest", type=_path, help="Use ARIEL's exact SonicMaster test source set")
    split.add_argument("--sonicmaster-split-manifest", type=_path, help="Apply the frozen original SonicMaster train/validation/test assignment")
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
    segment_command.add_argument("--clip-attempts", type=int, default=3, help="Deterministic retries with a different window when a clip is rejected")
    segment_command.add_argument("--max-pad-seconds", type=float, default=0.25, help="Top up a marginally short render with silence instead of rejecting it")
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
    progress = not getattr(args, "quiet", False)
    if args.command == "blind-real-freeze":
        import json as _json
        from .blind_real import freeze_candidate_list, select_candidates, selection_statistics
        from .core import write_jsonl as _write
        rows = read_jsonl(args.candidates)
        frozen = freeze_candidate_list(
            select_candidates(rows, args.target, args.cap_per_identifier), args.excerpt_seconds
        )
        _write(args.output, frozen)
        stats = selection_statistics(frozen)
        stats["candidates_considered"] = len(rows)
        text = _json.dumps(stats, indent=2, sort_keys=True)
        if args.stats:
            args.stats.parent.mkdir(parents=True, exist_ok=True)
            args.stats.write_text(text + "\n", encoding="utf-8")
        print(text)
        print(f"\nfroze {len(frozen)} items -> {args.output}")
    elif args.command == "blind-real-scan":
        from .blind_real import scan_catalogue
        written = scan_catalogue(args.output, args.shards, args.workers, args.start, progress=not args.quiet)
        print(f"wrote {written} catalogue rows to {args.output}")
    elif args.command == "blind-real-candidates":
        import json as _json
        from .blind_real import catalogue_statistics, filter_candidates
        rows = read_jsonl(args.catalogue)
        kept = filter_candidates(rows, args.allow_share_alike, not args.any_recording)
        from .core import write_jsonl as _write
        _write(args.output, kept)
        stats = catalogue_statistics(rows)
        stats["selected"] = len(kept)
        text = _json.dumps(stats, indent=2, sort_keys=True)
        if args.stats:
            args.stats.parent.mkdir(parents=True, exist_ok=True)
            args.stats.write_text(text + "\n", encoding="utf-8")
        print(text)
        print(f"\nselected {len(kept)} of {len(rows)} segments -> {args.output}")
    elif args.command == "audit":
        audit(_dataset_config(args), args.output, args.probe_limit, progress=progress)
    elif args.command == "ingest":
        ingest(_dataset_config(args), args.output, progress=progress)
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
            args.clip_attempts,
            args.max_pad_seconds,
            progress=progress,
        )
    elif args.command == "shard":
        write_shards(
            args.output_root, read_jsonl(args.manifest), args.shards_dir, args.shard_size, progress=progress
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
