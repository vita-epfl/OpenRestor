#!/usr/bin/env python3
"""Resolve ChoraleBricks Zenodo metadata without downloading record files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from scripts.resolve_zenodo_metadata import fetch_record, summarize_record


def summarize(payload: dict) -> dict:
    """Backward-compatible wrapper for the original ChoraleBricks resolver."""
    return summarize_record(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", default="15081740",
                        help="Zenodo concept record or published record ID")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(fetch_record(args.record))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    print(f"Resolved Zenodo metadata for record {result['record_id']}: {args.out}")


if __name__ == "__main__":
    main()
