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
import csv
import json
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openrestor.data.blind_real import cap_items_per_artist, load_rejections
from openrestor.data.blind_real_clips import clip_statistics, extract_clips

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
    parser.add_argument("--listened", type=Path, nargs="*", default=None,
                        help="Records of what has been listened to: verdict CSVs and the "
                             "manifests earlier passes presented. Defaults to every "
                             "*verdicts*.csv in the build directory plus the round-one "
                             "package")
    parser.add_argument("--allow-unlistened", action="store_true",
                        help="Admit items with no recorded verdict. Only for a deliberately "
                             "unaudited build")
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
        rows = all_rows = read_jsonl(args.manifest)
    else:
        rows = extract_clips(
            downloaded, candidates, REPO, args.output_root,
            excerpt_seconds=args.excerpt_seconds,
            clips_per_identifier=args.clips_per_identifier,
            rejections=rejections,
        )
        # Cut the clean controls too: they are excluded from the scored set, not from the
        # build, and a manifest entry with no audio behind it would be useless.
        clean_only = {key: reason for key, reason in rejections.items()
                      if not str(reason).startswith(("clean_control", "not_degraded_enough"))}
        all_rows = extract_clips(
            downloaded, candidates, REPO, args.output_root,
            excerpt_seconds=args.excerpt_seconds,
            clips_per_identifier=args.clips_per_identifier,
            rejections=clean_only, progress=False,
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

    # Every item in the scored set must have been decided by someone. Twice now a batch
    # entered the set simply because nothing had rejected it: candidates are downloaded in
    # bounded rounds, and whatever is left over is not evidence of quality. Silence is not
    # a verdict, so the build refuses rather than quietly shipping unheard audio.
    listened_paths = args.listened
    if listened_paths is None:
        listened_paths = sorted(BUILD.glob("*verdicts*.csv")) + [
            BUILD / "blind_real_test_manifest.jsonl.pre_artist_cap"]
    listened: set[str] = set()
    for path in listened_paths:
        if not Path(path).is_file():
            continue
        text = Path(path).read_text(encoding="utf-8")
        if str(path).endswith(".csv"):
            for record in csv.DictReader(text.splitlines()):
                clip = (record.get("clip_id") or "").strip()
                if clip.startswith("blind_real--"):
                    listened.add(clip.split("--")[1])
        else:
            for line in text.splitlines():
                if line.strip():
                    listened.add(str(json.loads(line).get("internet_archive_identifier")))
    unheard = sorted({str(row["internet_archive_identifier"]) for row in rows} - listened)
    if unheard and not args.allow_unlistened:
        raise SystemExit(
            f"{len(unheard)} items in the scored set have no recorded verdict, for example "
            f"{unheard[:3]}. Add them to a listening pass, or mark them in "
            f"{args.rejections.name} as not_yet_listened. Pass --allow-unlistened to override."
        )
    if unheard:
        print(f"!! admitting {len(unheard)} items with no recorded verdict")

    stats = clip_statistics(rows)
    print("\n" + json.dumps(stats, indent=2))

    if args.dry_run:
        print("\ndry run: nothing written")
        return

    # Items marked as clean controls are excluded from the scored set but written to
    # their own manifest, because a set with no clean material cannot show whether a
    # system damages audio that was already fine.
    clean_keys = {key for key, reason in rejections.items()
                  if str(reason).startswith(("clean_control", "not_degraded_enough"))}
    if clean_keys and not args.dry_run:
        controls = [row for row in all_rows
                    if str(row["internet_archive_identifier"]) in clean_keys or str(row["id"]) in clean_keys]
        for row in controls:
            row["blind_real_role"] = "clean_control_not_scored"
            row["excluded_reason"] = rejections.get(str(row["internet_archive_identifier"])) \
                or rejections.get(str(row["id"]))
        with (BUILD / "clean_control_manifest.jsonl").open("w", encoding="utf-8") as handle:
            for row in sorted(controls, key=lambda r: str(r["id"])):
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        print(f"clean controls: {len({r['internet_archive_identifier'] for r in controls})} items, "
              f"{len(controls)} clips -> {BUILD / 'clean_control_manifest.jsonl'}")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    (BUILD / "artist_cap_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (BUILD / "clip_statistics.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"\nmanifest -> {args.manifest}")


if __name__ == "__main__":
    main()
