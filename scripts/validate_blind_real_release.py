#!/usr/bin/env python3
"""Check every invariant the Blind-Real release claims, and fail if one is broken.

This exists because each of these was broken at some point during curation, and each
time the symptom was a plausible-looking number rather than an error: 45 items admitted
because nothing had rejected them, two excerpts of one song presented as two excerpts,
a copyright screen reporting zero matches because it had failed 195 times. A claim that
is only asserted in prose gets asserted again after it stops being true.

    python scripts/validate_blind_real_release.py
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "build/blind_real"

ALLOWED_LICENCES = {"CC0", "BY"}
FORBIDDEN_IN_URL = ("by-sa", "by-nc", "by-nd", "nc-", "-nd", "sa/")
EXPECTED_SECONDS = 20.0
EXPECTED_RATE = 44100
EXPECTED_CHANNELS = 2


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def probe(path: Path) -> tuple[float, int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=sample_rate,channels:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    stream = (data.get("streams") or [{}])[0]
    return (float(data["format"]["duration"]), int(stream["sample_rate"]), int(stream["channels"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored", type=Path, default=BUILD / "blind_real_test_manifest.jsonl")
    parser.add_argument("--clean", type=Path, default=BUILD / "clean_control_manifest.jsonl")
    parser.add_argument("--rejections", type=Path, default=BUILD / "rejected_identifiers.tsv")
    parser.add_argument("--clips-root", type=Path, default=REPO / "build/degradations")
    parser.add_argument("--audio-sample", type=int, default=0,
                        help="Probe only N clips per set (0 probes all of them)")
    args = parser.parse_args()

    scored, clean = read(args.scored), read(args.clean)
    failures: list[str] = []
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(message)

    rejections: dict[str, str] = {}
    for line in args.rejections.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "\t" in line:
            key, reason = line.split("\t", 1)
            rejections[key.strip()] = reason.strip()

    # The sets must not overlap, and neither may contain anything rejected. A clean
    # control is excluded from scoring, so finding one in the scored set would silently
    # put audio that needs no restoration into the measurement.
    scored_items = {r["internet_archive_identifier"] for r in scored}
    clean_items = {r["internet_archive_identifier"] for r in clean}
    check(not (scored_items & clean_items),
          f"{len(scored_items & clean_items)} identifiers are in both the scored and clean sets: "
          f"{sorted(scored_items & clean_items)[:3]}")
    hard = {key for key, reason in rejections.items()
            if not reason.startswith(("clean_control", "not_degraded_enough", "not_yet_listened"))}
    check(not (scored_items & hard),
          f"{len(scored_items & hard)} rejected identifiers are in the scored set: "
          f"{sorted(scored_items & hard)[:3]}")
    staged = {key for key, reason in rejections.items() if reason.startswith("not_yet_listened")}
    check(not (scored_items & staged),
          f"{len(scored_items & staged)} unlistened identifiers are in the scored set")

    # Every scored item needs a recorded verdict. Being left over is not a verdict.
    listened: set[str] = set()
    for path in sorted(BUILD.glob("*verdicts*.csv")):
        for record in csv.DictReader(path.read_text(encoding="utf-8").splitlines()):
            clip = (record.get("clip_id") or "").strip()
            if clip.startswith("blind_real--"):
                listened.add(clip.split("--")[1])
    presented = BUILD / "blind_real_test_manifest.jsonl.pre_artist_cap"
    if presented.is_file():
        listened |= {r["internet_archive_identifier"] for r in read(presented)}
    check(scored_items <= listened,
          f"{len(scored_items - listened)} scored items have no recorded verdict: "
          f"{sorted(scored_items - listened)[:3]}")

    for name, rows in (("scored", scored), ("clean", clean)):
        ids = Counter(r["id"] for r in rows)
        check(all(n == 1 for n in ids.values()),
              f"{name}: duplicate clip ids {[i for i, n in ids.items() if n > 1][:3]}")

        # Two excerpts of one item must come from two different source tracks. Two windows
        # of the same song sound alike however far apart they are cut, so this is what
        # makes a second excerpt worth anything.
        tracks = defaultdict(list)
        for row in rows:
            tracks[row["internet_archive_identifier"]].append(row.get("source_file"))
        shared = [i for i, files in tracks.items() if len(files) > 1 and len(set(files)) != len(files)]
        check(not shared, f"{name}: {len(shared)} items draw two excerpts from one track: {shared[:3]}")

        per_item = Counter(r["internet_archive_identifier"] for r in rows)
        check(max(per_item.values(), default=0) <= 2,
              f"{name}: an item contributes more than two clips")

        for row in rows:
            licence = str(row.get("license_type") or "")
            if licence not in ALLOWED_LICENCES:
                failures.append(f"{name}: {row['id']} has licence {licence!r}")
            url = str(row.get("license_url") or "").lower()
            if any(bad in url for bad in FORBIDDEN_IN_URL):
                failures.append(f"{name}: {row['id']} licence url is restrictive: {url}")
            for field in ("attribution", "license_url", "title", "internet_archive_metadata"):
                if not str(row.get(field) or "").strip():
                    failures.append(f"{name}: {row['id']} is missing {field}")
            if str(row.get("normalization")) != "none":
                failures.append(f"{name}: {row['id']} claims normalization "
                                f"{row.get('normalization')!r}; Blind-Real is never normalised")
        checks += 4 * len(rows)

        sample = rows if not args.audio_sample else rows[: args.audio_sample]
        missing = [r["id"] for r in rows if not (args.clips_root / r["audio_path"]).is_file()]
        check(not missing, f"{name}: {len(missing)} clip files are missing: {missing[:3]}")
        for row in sample:
            path = args.clips_root / row["audio_path"]
            if not path.is_file():
                continue
            seconds, rate, channels = probe(path)
            if abs(seconds - EXPECTED_SECONDS) > 0.05 or rate != EXPECTED_RATE or channels != EXPECTED_CHANNELS:
                failures.append(f"{name}: {row['id']} is {seconds:.2f}s {rate}Hz {channels}ch, "
                                f"expected {EXPECTED_SECONDS}s {EXPECTED_RATE}Hz {EXPECTED_CHANNELS}ch")
            checks += 1

        print(f"{name:<7} {len(rows):>4} clips / {len(set(r['internet_archive_identifier'] for r in rows)):>3} items"
              f"   licences {dict(Counter(str(r.get('license_type')) for r in rows))}"
              f"   probed {len(sample)}")

    print(f"\n{checks} checks, {len(failures)} failures")
    for failure in failures[:20]:
        print(f"  !! {failure}")
    if failures:
        sys.exit(1)
    print("every invariant holds")


if __name__ == "__main__":
    main()
