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
    parser = argparse.ArgumentParser(prog="openrestore-score")
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
    blind_real = commands.add_parser("score-blind-real", help="No-reference scoring with clip/identifier/dataset aggregation")
    blind_real.add_argument("--manifest", type=_path, required=True, help="Blind-Real test manifest")
    blind_real.add_argument("--degraded-root", type=_path, required=True, help="Root of the Blind-Real clips")
    blind_real.add_argument("--restored-manifest", type=_path, required=True, help="restoration_outputs.jsonl")
    blind_real.add_argument("--restored-root", type=_path, help="Root for relative restored paths")
    blind_real.add_argument("--output", type=_path, required=True)
    blind_real.add_argument("--quiet", action="store_true")

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
    elif args.command == "score-blind-real":
        import json as _json
        from ..data.core import read_jsonl as _read
        from .blind_real import score_blind_real
        manifest = _read(args.manifest)
        restored: dict[str, Path] = {}
        for row in _read(args.restored_manifest):
            path = Path(str(row["restored_audio_path"]))
            if not path.is_absolute():
                path = (args.restored_root or args.restored_manifest.parent) / path
            restored[str(row["id"])] = path
        report = score_blind_real(manifest, args.degraded_root, restored, progress=not args.quiet)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"scored {report['scored_clips']}/{report['expected_clips']} clips over "
              f"{report['identifiers']} source items; complete={report['complete']}")
        if report["missing_restorations"]:
            print(f"  missing restorations: {len(report['missing_restorations'])}")
        if report["failures"]:
            print(f"  failures: {len(report['failures'])}; first: {report['failures'][0]}")
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
