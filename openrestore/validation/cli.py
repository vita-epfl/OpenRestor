"""CLI for validating OpenRestore JSON and JSONL artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import validate_file


def main() -> None:
    parser = argparse.ArgumentParser(prog="openrestore-validate")
    parser.add_argument("kind", choices=["index", "degradation_tracking", "submission_manifest", "restored_outputs", "scores", "leaderboard_entry"])
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    count = validate_file(args.kind, args.input)
    print(f"Validated {count} document(s) against {args.kind}.schema.json")


if __name__ == "__main__":
    main()
