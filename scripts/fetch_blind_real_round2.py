#!/usr/bin/env python3
"""Resolve, download and copyright-screen the round-two Blind-Real candidates.

Same pipeline as round one, driven from the round-two candidate list: resolve each
Internet Archive identifier to the best original file the uploader posted, fetch two
distinct tracks per item so the two excerpts cannot be the same song, then fingerprint
one track per item against AcoustID.

The AcoustID key is read from ACOUSTID_API_KEY rather than stored here. A non-match is
not evidence that a recording is free -- it only means no fingerprint was found -- so the
screen removes matches and claims nothing about the rest.

    ACOUSTID_API_KEY=... python scripts/fetch_blind_real_round2.py
    python scripts/fetch_blind_real_round2.py --skip-screen
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openrestore.data.blind_real import (
    download_distinct_tracks,
    resolve_originals,
    resolve_summary,
    screen_for_commercial_release,
    stream_jsonl,
)

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "build/blind_real"

# IAMD names each segment "<original stem>_<track>_<segment>.mp3", so the stem names the
# file IAMD itself chose to segment. Preferring it is what stops a non-music file in the
# same item outranking the music.
_SEGMENT_SUFFIX = re.compile(r"_\d+_\d{4,}$")


def segmented_stems(rows: list[dict]) -> dict[str, list[str]]:
    stems: dict[str, set[str]] = {}
    for row in rows:
        path = str(row.get("segment_path") or "")
        if not path:
            continue
        stem = _SEGMENT_SUFFIX.sub("", Path(path).stem)
        if stem:
            stems.setdefault(str(row["identifier"]), set()).add(stem)
    return {k: sorted(v) for k, v in stems.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=BUILD / "round2_candidates.jsonl")
    parser.add_argument("--resolved", type=Path, default=BUILD / "round2_resolved.jsonl")
    parser.add_argument("--tracks", type=Path, default=BUILD / "round2_tracks.jsonl")
    parser.add_argument("--screen", type=Path, default=BUILD / "round2_acoustid.jsonl")
    parser.add_argument("--destination", type=Path, default=BUILD / "round2_tracks")
    parser.add_argument("--tracks-per-item", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--skip-screen", action="store_true")
    args = parser.parse_args()

    candidates = list(stream_jsonl(args.candidates))
    identifiers = list(dict.fromkeys(str(row["identifier"]) for row in candidates))
    print(f"{len(identifiers)} identifiers to resolve", flush=True)

    if args.resolved.is_file():
        resolved = list(stream_jsonl(args.resolved))
        print(f"reusing {len(resolved)} resolved rows", flush=True)
    else:
        resolved = resolve_originals(identifiers, workers=6, segmented_stems=segmented_stems(candidates))
        with args.resolved.open("w", encoding="utf-8") as handle:
            for row in resolved:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps(resolve_summary(resolved), indent=1), flush=True)

    if args.tracks.is_file():
        tracks = list(stream_jsonl(args.tracks))
        print(f"reusing {len(tracks)} downloaded track rows", flush=True)
    else:
        tracks = download_distinct_tracks(resolved, args.destination,
                                          tracks_per_item=args.tracks_per_item, workers=args.workers)
        with args.tracks.open("w", encoding="utf-8") as handle:
            for row in tracks:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    ok = [row for row in tracks if row.get("local_path")]
    print(f"{len(ok)} tracks downloaded over "
          f"{len({r['identifier'] for r in ok})} identifiers", flush=True)
    print("download status:", dict(Counter(str(r.get("download_status")) for r in tracks).most_common()), flush=True)

    if args.skip_screen:
        return
    key = os.environ.get("ACOUSTID_API_KEY")
    if not key:
        raise SystemExit("set ACOUSTID_API_KEY to run the copyright screen, or pass --skip-screen")

    # One track per identifier is enough: the screen is about the release, not the take.
    first: dict[str, Path] = {}
    for row in sorted(ok, key=lambda r: (str(r["identifier"]), int(r.get("track_index", 0)))):
        first.setdefault(str(row["identifier"]), args.destination / str(row["local_path"]))
    screened = screen_for_commercial_release(sorted(first.items()), key)
    with args.screen.open("w", encoding="utf-8") as handle:
        for row in screened:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    hits = [row for row in screened if row.get("commercial_match")]
    print(f"\n{len(hits)} of {len(screened)} identifiers match a commercial release", flush=True)
    for row in hits:
        match = (row.get("matches") or [{}])[0]
        print(f"   {row['identifier'][:44]:<46} {row.get('score'):.2f}  "
              f"{str(match.get('artists'))[:40]} - {str(match.get('title'))[:40]}", flush=True)
    print(f"screen -> {args.screen}")


if __name__ == "__main__":
    main()
