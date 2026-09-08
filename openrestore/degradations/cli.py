"""Command-line interface for OpenRestore degradation rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import load_yaml
from .pipeline import list_recipes, render_degradations, validate_config, write_hdf5_shards
from .release import create_partition_plan, merge_release, render_partition, validate_clean_release, validate_release


def _path(value: str) -> Path:
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openrestore-degrade")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render")
    render.add_argument("--manifest", type=_path, required=True)
    render.add_argument("--clean-root", type=_path, required=True)
    render.add_argument("--output-root", type=_path, required=True)
    render.add_argument("--config", type=_path, required=True)
    render.add_argument("--output-manifest", type=_path, required=True)
    render.add_argument("--checksums", type=_path, required=True)
    render.add_argument("--seed", type=int, default=20260714)
    render.add_argument("--quiet", action="store_true")
    shard = commands.add_parser("shard")
    shard.add_argument("--output-root", type=_path, required=True)
    shard.add_argument("--manifest", type=_path, required=True)
    shard.add_argument("--shards-dir", type=_path, required=True)
    shard.add_argument("--output-index", type=_path, required=True)
    shard.add_argument("--shard-size", type=int, default=1000)
    shard.add_argument("--quiet", action="store_true")
    validate = commands.add_parser("validate-config")
    validate.add_argument("--config", type=_path, required=True)
    recipes = commands.add_parser("list-recipes")
    recipes.add_argument("--config", type=_path, required=True)

    clean = commands.add_parser("validate-clean-release")
    clean.add_argument("--clean-manifest", type=_path, required=True)
    clean.add_argument("--clean-root", type=_path, required=True)
    clean.add_argument("--release-config", type=_path, required=True)

    plan = commands.add_parser("plan-release")
    plan.add_argument("--clean-manifest", type=_path, required=True)
    plan.add_argument("--clean-root", type=_path, required=True)
    plan.add_argument("--release-config", type=_path, required=True)
    plan.add_argument("--output", type=_path, required=True)

    partition = commands.add_parser("render-partition")
    partition.add_argument("--plan", type=_path, required=True)
    partition.add_argument("--partition-id", required=True)
    partition.add_argument("--clean-manifest", type=_path, required=True)
    partition.add_argument("--clean-root", type=_path, required=True)
    partition.add_argument("--release-config", type=_path, required=True)
    partition.add_argument("--work-root", type=_path, required=True)
    partition.add_argument("--release-root", type=_path, required=True)

    merge = commands.add_parser("merge-release")
    merge.add_argument("--plan", type=_path, required=True)
    merge.add_argument("--release-root", type=_path, required=True)
    merge.add_argument("--output-index", type=_path, required=True)
    merge.add_argument("--receipt", type=_path, required=True)

    release = commands.add_parser("validate-release")
    release.add_argument("--plan", type=_path, required=True)
    release.add_argument("--release-root", type=_path, required=True)
    release.add_argument("--receipt", type=_path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "render":
        render_degradations(
            args.manifest,
            args.clean_root,
            args.output_root,
            args.config,
            args.output_manifest,
            args.checksums,
            args.seed,
            progress=not args.quiet,
        )
    elif args.command == "shard":
        write_hdf5_shards(
            args.output_root, args.manifest, args.shards_dir, args.output_index, args.shard_size, progress=not args.quiet
        )
    elif args.command == "validate-config":
        validate_config(load_yaml(args.config))
    elif args.command == "list-recipes":
        print(json.dumps(list_recipes(load_yaml(args.config)), indent=2, sort_keys=True))
    elif args.command == "validate-clean-release":
        print(json.dumps(validate_clean_release(args.clean_manifest, args.clean_root, args.release_config), indent=2, sort_keys=True))
    elif args.command == "plan-release":
        print(json.dumps(create_partition_plan(args.clean_manifest, args.release_config, args.output, args.clean_root), indent=2, sort_keys=True))
    elif args.command == "render-partition":
        print(json.dumps(render_partition(args.plan, args.partition_id, args.clean_manifest, args.clean_root, args.release_config, args.work_root, args.release_root), indent=2, sort_keys=True))
    elif args.command == "merge-release":
        print(json.dumps(merge_release(args.plan, args.release_root, args.output_index, args.receipt), indent=2, sort_keys=True))
    elif args.command == "validate-release":
        print(json.dumps(validate_release(args.plan, args.release_root, args.receipt), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
