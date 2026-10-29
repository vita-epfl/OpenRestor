#!/usr/bin/env python3
"""Apply a Blind-Real QA pass: turn verdicts into rejections and report the outcome.

Takes the CSV the QA page downloads, or the annotated verdicts.csv, and produces the
lists the curation decision needs: kept, rejected with reason, uncertain, the coarse
quality distribution, and the final counts.

The two verdict columns stay separate throughout. An item is dropped if *either* its
audio or its provenance fails, but the reports say which, because the remedies differ:
bad audio means the item is wrong for the task, while a recognised commercial release
means it may be fine audio we are not allowed to ship.

The provenance column records one narrow judgement only -- "I recognise this as a
commercial release" -- because that is the only provenance question listening can settle.
Whether an uploader held the rights is desk research, carried alongside each verdict in
the uploader columns and kept for audit; it is never inferred from a listener's answer.

    python scripts/apply_blind_real_verdicts.py --verdicts ~/Downloads/blind_real_verdicts.csv
    python scripts/apply_blind_real_verdicts.py --verdicts ... --write-rejections
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
# "reject" on the provenance column means the listener recognised a commercial release,
# so it maps to that reason rather than a vague "provenance" bucket.
PROVENANCE_REJECT_REASON = "commercial_release"

# The listening form sorts three ways instead of keeping or rejecting. "clean" is not a
# rejection: such an item leaves the scored set but enters the clean control set, because
# a recording that needs no restoration is what shows whether a system damages audio that
# was already fine. The legacy keep/reject vocabulary is still read so the first pass,
# which used it, stays reproducible from its own CSV.
# The marker the build looks for to route an item to the clean control manifest rather
# than discard it. It must stay in sync with build_blind_real_public.py.
CLEAN_CONTROL_REASON = "clean_control"

# An undecided item must not drift into the set by default. It is held out under this
# reason until its second excerpt settles the matter, which is what the staged second
# clip of every item is for. Deleting the line readmits it.
PENDING_REASON = "uncertain_pending_second_excerpt"

SORT_TO_OUTCOME = {
    "degraded": "scored", "keep": "scored",
    "clean": "clean_control", "not_degraded_enough": "clean_control",
    "not_music": "rejected", "unusable": "rejected", "reject": "rejected",
    "uncertain": "uncertain", "": "scored",
}


def read_verdicts(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            clip = (row.get("clip_id") or "").strip()
            if clip:
                out[clip] = {k: (v or "").strip() for k, v in row.items()}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verdicts", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=REPO / "build/blind_real/blind_real_test_manifest.jsonl")
    parser.add_argument("--rejections", type=Path, default=REPO / "build/blind_real/rejected_identifiers.tsv")
    parser.add_argument("--report", type=Path, default=REPO / "build/blind_real/qa_report.json")
    parser.add_argument("--write-rejections", action="store_true",
                        help="Append the new rejections to the rejection list")
    args = parser.parse_args()

    manifest = [json.loads(line) for line in args.manifest.open(encoding="utf-8")]
    by_clip = {row["id"]: row for row in manifest}
    clips_per_item: dict[str, list[str]] = defaultdict(list)
    for row in manifest:
        clips_per_item[row["internet_archive_identifier"]].append(row["id"])

    verdicts = read_verdicts(args.verdicts)
    unknown = sorted(set(verdicts) - set(by_clip))

    kept, rejected, uncertain, clean_control = [], [], [], []
    reasons, quality = Counter(), Counter()
    for clip, verdict in verdicts.items():
        row = by_clip.get(clip)
        if row is None:
            continue
        audio = verdict.get("audio_verdict", "").lower()
        provenance = verdict.get("provenance_verdict", "").lower()
        note = verdict.get("sort_note") or verdict.get("reject_reason") or ""
        outcome = SORT_TO_OUTCOME.get(audio, "uncertain")
        if note:
            quality[note] += 1
        entry = {
            "clip_id": clip, "identifier": row["internet_archive_identifier"],
            "audio_verdict": audio or "degraded", "provenance_verdict": provenance or "keep",
            "sort_note": note, "outcome": outcome,
            "note": verdict.get("note", ""),
            "uploader": verdict.get("uploader", ""),
            "uploader_artist_count": verdict.get("uploader_artist_count", ""),
        }
        # A recognised commercial release overrides the sort: it cannot be distributed
        # whichever bucket it would otherwise have landed in.
        if provenance == "reject":
            entry["outcome"] = outcome = "rejected"
            entry["rejected_on"] = "provenance"
            reasons[PROVENANCE_REJECT_REASON] += 1
        elif outcome == "rejected":
            entry["rejected_on"] = "audio"
            reasons[note or audio or "unspecified"] += 1
        if outcome == "uncertain" or provenance == "uncertain":
            uncertain.append(entry)
        elif outcome == "rejected":
            rejected.append(entry)
        elif outcome == "clean_control":
            clean_control.append(entry)
        else:
            kept.append(entry)

    # A verdict on the first clip of an item decides the item, since pass one presents
    # one clip per source and the rest of the item shares its provenance.
    rejected_items = {e["identifier"]: e for e in rejected}
    rejected_items.update({e["identifier"]: e for e in clean_control})
    rejected_items.update({e["identifier"]: e for e in uncertain})
    uncertain_items = {e["identifier"] for e in uncertain}
    surviving_items = [i for i in sorted(clips_per_item) if i not in rejected_items]
    surviving_clips = [c for i in surviving_items for c in clips_per_item[i]]

    report = {
        "verdicts_read": len(verdicts),
        "unknown_clip_ids": unknown,
        "pass1_kept": len(kept),
        "pass1_rejected": len(rejected),
        "pass1_uncertain": len(uncertain),
        "pass1_clean_control": len(clean_control),
        "clean_control": clean_control,
        "clean_control_identifiers": sorted({e["identifier"] for e in clean_control}),
        "rejected_by_reason": dict(reasons.most_common()),
        "rejected_on": dict(Counter(e["rejected_on"] for e in rejected).most_common()),
        "quality_distribution": dict(quality.most_common()),
        "uncertain_identifiers": sorted(uncertain_items),
        "final_identifiers": len(surviving_items),
        "final_clips": len(surviving_clips),
        "kept": kept,
        "rejected": rejected,
        "uncertain": uncertain,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"verdicts read            {len(verdicts)}")
    if unknown:
        print(f"  !! {len(unknown)} clip ids not in the manifest, first: {unknown[0]}")
    print(f"sorted: {len(kept)} degraded / {len(clean_control)} clean control / "
          f"{len(rejected)} rejected / {len(uncertain)} uncertain")
    if reasons:
        print("rejected by reason:")
        for reason, count in reasons.most_common():
            print(f"   {count:>4}  {reason}")
    if report["rejected_on"]:
        print(f"rejected on: {report['rejected_on']}")
    if quality:
        print("what was heard (descriptive only, never a degradation label):")
        for label, count in quality.most_common():
            print(f"   {count:>4}  {label}")
    print(f"\nfinal: {len(surviving_items)} identifiers, {len(surviving_clips)} clips")
    if uncertain_items:
        print(f"{len(uncertain_items)} identifiers need their second excerpt listened to")
    print(f"report -> {args.report}")

    if args.write_rejections and (rejected or clean_control or uncertain):
        existing = args.rejections.read_text(encoding="utf-8") if args.rejections.is_file() else ""
        lines = ["\n# --- QA listening pass -----------------------------------------------------------\n"]
        for entry in rejected:
            why = entry["sort_note"] or (
                PROVENANCE_REJECT_REASON if entry.get("rejected_on") == "provenance"
                else entry["audio_verdict"] or "unspecified")
            note = f"; {entry['note']}" if entry["note"] else ""
            lines.append(f"{entry['identifier']}\t{why} ({entry.get('rejected_on', 'audio')}){note}\n")
        if uncertain:
            lines.append(f"\n# Undecided on the first excerpt: held out until the second one is heard.\n")
            for entry in uncertain:
                note = f"; {entry['note']}" if entry["note"] else ""
                lines.append(f"{entry['identifier']}\t{PENDING_REASON}{note}\n")
        if clean_control:
            # Clean items leave the scored set but are not rejected: the reason is marked
            # so the build can route them to the clean control manifest instead of
            # dropping them. Without this they stayed in the scored set, because nothing
            # was ever written for them.
            lines.append("\n# Needed no restoration: excluded from the scored set, kept as clean controls.\n")
            for entry in clean_control:
                note = f"; {entry['note']}" if entry["note"] else ""
                lines.append(f"{entry['identifier']}\t{CLEAN_CONTROL_REASON}{note}\n")
        args.rejections.write_text(existing + "".join(lines), encoding="utf-8")
        print(f"appended {len(rejected)} rejections, {len(clean_control)} clean controls and "
              f"{len(uncertain)} held pending -> {args.rejections}")


if __name__ == "__main__":
    main()
