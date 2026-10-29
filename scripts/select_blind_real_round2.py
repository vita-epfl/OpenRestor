#!/usr/bin/env python3
"""Select a second round of Blind-Real candidates, without the live-capture proxy.

Round one required high-confidence live metadata. That proxy cost 98% of the permissive
pool -- 131 identifiers out of 9,759 music items -- and still admitted 27 recordings a
listener judged to need no restoration. "Live" was never the requirement; "degraded by
its own history" is, and no metadata field states it.

Nothing automatic replaces the proxy, which this round accepts rather than works around:
the format fields are empty (sample_rate on 7 of 12,405 items, channels on none) and the
no-reference descriptors separate a listener's keep and too-clean verdicts at chance
(AUC 0.35-0.56). Listening stays the arbiter. Selection's only job is to spend it well:
drop what is reliably predictable -- non-music collections, uncredible licences,
ambient and noise aesthetics -- and spread the rest across collections and artists.

    python scripts/select_blind_real_round2.py --target 200
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openrestor.data.blind_real import (
    filter_candidates,
    freeze_candidate_list,
    live_evidence,
    looks_ambient_or_noise,
    looks_non_music_filename,
    primary_collection,
    select_diverse_candidates,
    stream_jsonl,
)

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "build/blind_real"

# Spoken word, sermons, podcasts and social media clips are not music, and audio_religion
# is dominated by sermons rather than performance. Round one excluded only the field
# recording and spoken word collections because the live filter kept the rest out anyway.
EXTRA_EXCLUDED = ("podcasts", "podcasts_miscellaneous", "folksoundomy_podfic",
                  "audio_religion", "audio_sermons", "social-media-video",
                  "spinal_implant_screws_collection")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=BUILD / "iamd_catalogue.jsonl")
    parser.add_argument("--output", type=Path, default=BUILD / "round2_candidates.jsonl")
    parser.add_argument("--frozen", type=Path, default=BUILD / "round2_frozen.jsonl",
                        help="The same selection in the frozen item shape the clip extractor reads")
    parser.add_argument("--target", type=int, default=200, help="Identifiers to select")
    parser.add_argument("--clips-per-identifier", type=int, default=2)
    parser.add_argument("--cap-per-artist", type=int, default=3)
    args = parser.parse_args()

    # Everything round one touched is off limits: already in the set, already rejected,
    # or already listened to. The second pass must not spend listening on a repeat.
    used: set[str] = set()
    for name in ("blind_real_test_manifest.jsonl", "blind_real_test_manifest.jsonl.pre_artist_cap",
                 "clean_control_manifest.jsonl", "public_test_candidates.jsonl"):
        path = BUILD / name
        if path.is_file():
            for row in stream_jsonl(path):
                used.add(str(row.get("internet_archive_identifier") or row.get("identifier")))
    rejections = BUILD / "rejected_identifiers.tsv"
    if rejections.is_file():
        for line in rejections.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "\t" in line:
                used.add(line.split("\t", 1)[0].split("--")[1] if line.startswith("blind_real--") else line.split("\t", 1)[0])
    print(f"{len(used)} identifiers already used in round one")

    counts = Counter()
    pool: list[dict] = []
    for row in stream_jsonl(args.catalogue):
        counts["scanned"] += 1
        if not filter_candidates([row], require_live=False):
            counts["licence or collection"] += 1
            continue
        collection = str(row.get("collection") or "").lower()
        if any(name in collection for name in EXTRA_EXCLUDED):
            counts["non-music collection"] += 1
            continue
        if looks_ambient_or_noise(row):
            counts["ambient or noise aesthetic"] += 1
            continue
        if str(row.get("audio_type") or "").startswith(("Spoken", "Sounds")):
            counts["declared non-music"] += 1
            continue
        if looks_non_music_filename(str(row.get("segment_path") or "")):
            counts["non-music filename"] += 1
            continue
        if str(row.get("identifier")) in used:
            counts["already used"] += 1
            continue
        counts["eligible"] += 1
        pool.append(row)

    print("\nfunnel:")
    for key in ("scanned", "licence or collection", "non-music collection",
                "ambient or noise aesthetic", "declared non-music", "non-music filename",
                "already used", "eligible"):
        print(f"   {counts[key]:>9}  {key}")
    print(f"\n{len({str(r.get('identifier')) for r in pool})} eligible identifiers")

    selected = select_diverse_candidates(
        pool, target=args.target * args.clips_per_identifier,
        cap_per_identifier=args.clips_per_identifier, cap_per_artist=args.cap_per_artist,
    )
    identifiers = {str(row["identifier"]) for row in selected}
    print(f"selected {len(identifiers)} identifiers, {len(selected)} segment rows")
    print("\nby collection:")
    for collection, n in Counter(primary_collection(r) for r in selected).most_common(15):
        print(f"   {n:>4}  {collection}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(selected, key=lambda r: (str(r["identifier"]), str(r.get("key"))))
    with args.output.open("w", encoding="utf-8") as handle:
        for row in ordered:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    # Live evidence is still recorded, now as a description rather than a filter: some of
    # these items will be live and some will not, and the manifest should say which
    # without that deciding anything. Round-two ids start after round one's so the two
    # rounds can be concatenated without collision.
    frozen = freeze_candidate_list([{**row, "live_evidence": live_evidence(row)} for row in ordered])
    for row, source in zip(frozen, ordered):
        row["selection"]["round"] = 2
        row["selection"]["live_required"] = False
        row["selection"]["primary_collection"] = source.get("primary_collection")
    with args.frozen.open("w", encoding="utf-8") as handle:
        for row in frozen:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"\ncandidates -> {args.output}\nfrozen     -> {args.frozen}")


if __name__ == "__main__":
    main()
