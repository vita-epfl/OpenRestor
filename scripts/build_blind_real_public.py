#!/usr/bin/env python3
"""Build the Blind-Real Public manifest from the frozen candidates and downloads.

This exists because the manifest used to be produced by hand, which made the one set in
the benchmark that cannot be regenerated from a seed also the one set with no recorded
recipe. Everything upstream of here is already frozen on disk: the candidate selection,
the per-track downloads, the AcoustID screen and the rejection list. This script turns
those into the manifest, and applies the two curation rules that act on the whole set:

1. **Rejections** -- identifiers or single clips removed by the AcoustID screen or by the
   listening pass.
2. **A cap per artist.** Source-disjointness by Internet Archive identifier does not stop
   one act dominating: before the cap, Daniel Romano's Outfit held 14 of 113 items across
   three spellings of the credit (two of them the same concert uploaded twice), and
   Ambient Samurai held 14 more. A test set where one microphone is 13% of the score
   measures that microphone.

    python scripts/build_blind_real_public.py
    python scripts/build_blind_real_public.py --cap 3 --dry-run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openrestore.data.blind_real import cap_items_per_artist, load_rejections
from openrestore.data.blind_real_clips import clip_statistics, extract_clips

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "build/blind_real"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, nargs="+",
                        default=[BUILD / "public_test_candidates.jsonl"])
    # tracks.jsonl, not downloaded.jsonl: the latter holds one file per item, which caps
    # every item at a single excerpt. Two excerpts of one item have to come from two
    # different tracks, since two windows of the same song sound alike however far apart
    # they are cut.
    parser.add_argument("--downloaded", type=Path, nargs="+", default=[BUILD / "tracks.jsonl"])
    parser.add_argument("--rejections", type=Path, default=BUILD / "rejected_identifiers.tsv")
    parser.add_argument("--originals", type=Path, nargs="+", default=[BUILD / "tracks"],
                        help="One download root per --downloaded file, in the same order")
    parser.add_argument("--output-root", type=Path, default=REPO / "build/degradations")
    parser.add_argument("--manifest", type=Path, default=BUILD / "blind_real_test_manifest.jsonl")
    parser.add_argument("--cap", type=int, default=3,
                        help="Maximum identifiers per artist group (0 disables the cap)")
    parser.add_argument("--clips-per-identifier", type=int, default=2)
    parser.add_argument("--excerpt-seconds", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what the cap would do without cutting or writing")
    args = parser.parse_args()

    candidates: list[dict[str, Any]] = []
    for path in args.candidates:
        candidates += read_jsonl(path)
    if len(args.originals) != len(args.downloaded):
        raise SystemExit("--originals needs one download root per --downloaded file")
    # Each round downloaded into its own root, so paths are rewritten relative to the
    # repository and the extractor is given a single root. Rounds then merge into one
    # manifest, which is what the set is: the rounds are a build detail, not a split.
    downloaded = []
    for path, root in zip(args.downloaded, args.originals):
        for row in read_jsonl(path):
            if row.get("local_path"):
                row["local_path"] = str((root / str(row["local_path"])).resolve().relative_to(REPO))
            downloaded.append(row)
    rejections = load_rejections(args.rejections) if args.rejections.is_file() else {}
    tracks_per_item = len({row["identifier"] for row in downloaded if row.get("local_path")})
    print(f"{len(candidates)} candidate rows, {len(downloaded)} downloaded tracks over "
          f"{tracks_per_item} identifiers, {len(rejections)} rejection keys")
    if len(downloaded) <= tracks_per_item and args.clips_per_identifier > 1:
        raise SystemExit(
            f"{args.downloaded} holds one track per identifier, so no item can yield "
            f"{args.clips_per_identifier} distinct excerpts. Pass the per-track download "
            f"list (build/blind_real/tracks.jsonl) instead."
        )

    if args.dry_run and args.manifest.is_file():
        # The cap is the only rule that needs the whole set, so it can be previewed
        # against the existing manifest without re-cutting a single excerpt.
        rows = read_jsonl(args.manifest)
    else:
        rows = extract_clips(
            downloaded, candidates, REPO, args.output_root,
            excerpt_seconds=args.excerpt_seconds,
            clips_per_identifier=args.clips_per_identifier,
            rejections=rejections,
        )

    report: dict[str, Any] = {}
    if args.cap > 0:
        rows, report = cap_items_per_artist(rows, cap=args.cap)
        print(f"artist cap {args.cap}: {report['identifiers_before']} -> "
              f"{report['identifiers_after']} items, "
              f"{report['clips_before']} -> {report['clips_after']} clips "
              f"across {report['artist_groups']} artist groups")
        for group in report["largest_groups"]:
            print(f"    {group['identifiers']:>3} items before the cap  {group['artist_group'][:60]}")

    stats = clip_statistics(rows)
    print("\n" + json.dumps(stats, indent=2))

    if args.dry_run:
        print("\ndry run: nothing written")
        return

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    (BUILD / "artist_cap_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (BUILD / "clip_statistics.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"\nmanifest -> {args.manifest}")


if __name__ == "__main__":
    main()
