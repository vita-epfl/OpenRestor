#!/usr/bin/env python3
"""Write the attribution files the Blind-Real licences require.

CC BY asks for three things when the material is redistributed: credit to the creator as
designated, a link to the licence, and an indication that the material was modified. The
first two come from the manifest, which carries them for every clip. The third is this
project's doing and is stated once here rather than per clip: every excerpt is a 20-second
cut, resampled to 44.1 kHz stereo, and deliberately *not* loudness-normalised.

CC0 items need no attribution. They are listed anyway, because a reader cannot audit
provenance for only part of a set.

    python scripts/write_blind_real_attribution.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "build/blind_real"

MODIFICATION_NOTICE = """All audio in this set is modified from its source. Each excerpt is a
20-second cut from a longer recording, taken at a deterministic offset recorded per clip,
resampled to 44.1 kHz stereo for format uniformity, and encoded as 16-bit PCM. Excerpts are
deliberately **not** loudness-normalised: level problems are part of a recording's history and
normalising would repair one of the things a restoration system is meant to handle. No synthetic
degradation is ever added. The source file, its checksum, the excerpt bounds and the source
sample rate, channel count and codec are recorded for every clip in the manifest."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", type=Path, nargs="+", default=[
        BUILD / "blind_real_test_manifest.jsonl", BUILD / "clean_control_manifest.jsonl"])
    parser.add_argument("--out-dir", type=Path, default=BUILD / "attribution")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for manifest in args.manifests:
        rows = [json.loads(line) for line in manifest.open(encoding="utf-8") if line.strip()]
        items: dict[str, dict] = {}
        clips_per_item: Counter[str] = Counter()
        for row in rows:
            items.setdefault(row["internet_archive_identifier"], row)
            clips_per_item[row["internet_archive_identifier"]] += 1

        stem = manifest.stem.replace("_manifest", "")
        csv_path = args.out_dir / f"{stem}_attribution.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["internet_archive_identifier", "title", "creator", "licence",
                             "licence_url", "source_url", "clips_in_set", "source_file"])
            for identifier in sorted(items):
                row = items[identifier]
                writer.writerow([
                    identifier, row.get("title") or "", row.get("attribution") or "",
                    row.get("license_type") or "", row.get("license_url") or "",
                    f"https://archive.org/details/{identifier}",
                    clips_per_item[identifier], row.get("source_file") or "",
                ])

        licences = Counter(str(row.get("license_type")) for row in rows)
        md = [f"# Attribution — {stem}", "",
              f"{len(rows)} excerpts from {len(items)} Internet Archive items.", "",
              "| licence | clips |", "| --- | --- |"]
        md += [f"| {name} | {count} |" for name, count in licences.most_common()]
        md += ["", "## Modifications", "", MODIFICATION_NOTICE, "",
               "## Credits", "",
               "Each item is credited as its Internet Archive metadata designates, which for some "
               "items is an uploader address rather than an artist name; the source page is linked "
               "so the designation can be checked. The full table is in "
               f"`{csv_path.name}`.", ""]
        for identifier in sorted(items):
            row = items[identifier]
            md.append(f"- **{row.get('title') or identifier}** — {row.get('attribution') or 'uncredited'} "
                      f"— [{row.get('license_type')}]({row.get('license_url')}) — "
                      f"[source](https://archive.org/details/{identifier})")
        (args.out_dir / f"{stem}_ATTRIBUTION.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"{len(items):>4} items, {len(rows):>4} clips -> {csv_path.name} and "
              f"{stem}_ATTRIBUTION.md  {dict(licences)}")


if __name__ == "__main__":
    main()
