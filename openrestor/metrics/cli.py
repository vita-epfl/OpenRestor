"""Command-line interface for local OpenRestore scoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .perceptual import perceptual_score, setup_perceptual
from .pipeline import no_restoration, score, validate_restored_manifest


def _path(value: str) -> Path:
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openrestor-score")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-restored")
    validate.add_argument("--degraded-manifest", type=_path, required=True)
    validate.add_argument("--restored-manifest", type=_path, required=True)
    validate.add_argument("--restored-root", type=_path)
    scoring = commands.add_parser("score")
    scoring.add_argument("--degraded-manifest", type=_path, required=True)
    scoring.add_argument("--degraded-root", type=_path, required=True)
    scoring.add_argument("--clean-root", type=_path, required=True)
    scoring.add_argument("--restored-manifest", type=_path, required=True)
    scoring.add_argument("--config", type=_path, required=True)
    scoring.add_argument("--output-dir", type=_path, required=True)
    scoring.add_argument("--submission-id", type=str)
    perceptual = commands.add_parser("perceptual")
    for name in (
        "degraded-manifest",
        "degraded-root",
        "clean-root",
        "restored-manifest",
        "config",
        "output-dir",
    ):
        perceptual.add_argument(f"--{name}", type=_path, required=True)
    perceptual.add_argument("--cache-dir", type=_path)
    perceptual.add_argument("--device", type=str, default="cuda")
    perceptual.add_argument("--submission-id", type=str)
    setup = commands.add_parser("setup-perceptual")
    setup.add_argument("--config", type=_path, required=True)
    setup.add_argument("--cache-dir", type=_path)
    baseline = commands.add_parser("no-restoration")
    baseline.add_argument("--degraded-manifest", type=_path, required=True)
    baseline.add_argument("--degraded-root", type=_path, required=True)
    baseline.add_argument("--output-root", type=_path, required=True)
    baseline.add_argument("--output-manifest", type=_path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "validate-restored":
        rows, failures = validate_restored_manifest(
            args.degraded_manifest, args.restored_manifest, args.restored_root
        )
        print(
            json.dumps({"valid_items": len(rows), "failures": failures}, indent=2, sort_keys=True)
        )
        if failures:
            raise SystemExit(1)
    elif args.command == "score":
        score(
            args.degraded_manifest,
            args.degraded_root,
            args.clean_root,
            args.restored_manifest,
            args.config,
            args.output_dir,
            args.submission_id,
        )
    elif args.command == "perceptual":
        perceptual_score(
            args.degraded_manifest,
            args.degraded_root,
            args.clean_root,
            args.restored_manifest,
            args.config,
            args.output_dir,
            args.cache_dir,
            args.device,
            args.submission_id,
        )
    elif args.command == "setup-perceptual":
        setup_perceptual(args.config, args.cache_dir)
    else:
        no_restoration(
            args.degraded_manifest, args.degraded_root, args.output_root, args.output_manifest
        )


if __name__ == "__main__":
    main()
