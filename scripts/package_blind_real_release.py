#!/usr/bin/env python3
"""Package Blind-Real only after every clip has passed provenance review.

The audio can ship directly rather than as an index plus a downloader only after
uploader provenance has been approved clip by clip. A test set distributed as
Internet Archive links is not a fixed test set, because items are removed or replaced --
we removed a dozen ourselves during curation. Two people "downloading the same dataset"
six months apart would then evaluate on different audio, which is how AudioSet and
MusicCaps lost reproducibility.

The downloader therefore ships as a *verification* tool instead: every clip records its
source file, that file's SHA-1 as the Archive served it, and the exact cut, so anyone can
re-derive a clip from the Archive and compare it to the one in the release.

FLAC is lossless, so a decoded clip is sample-identical to the WAV it was cut as.

    python scripts/package_blind_real_release.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from openrestor.rights import load_registry, media_key, pack_family  # noqa: E402

BUILD = REPO / "build/blind_real"

CARD = """# OpenRestor — Blind-Real release candidate

This local pack is **not approved for upload** by its creation. The laboratory/TTO
release decision remains separate from per-clip provenance approval.

Real musical recordings degraded by their own history, for evaluating audio restoration.
**No synthetic degradation is ever added to this set.**

## What is here

| | scored set | clean control |
| --- | --- | --- |
| items | {scored_items} | {clean_items} |
| excerpts | {scored_clips} | {clean_clips} |
| duration | {scored_minutes:.0f} min | {clean_minutes:.0f} min |
| distinct artists | {artist_groups} | — |

Each excerpt is 20 seconds, 44.1 kHz stereo. Items are Internet Archive uploads under CC
BY or CC0; the per-item credits are in `attribution/`.

The **clean control** set is audio a listener judged to need no restoration. It is not
scored and is not a reference for anything: it is there because a set made only of
degraded material cannot show whether a system damages audio that was already fine.

## What this set cannot measure

- **No clean reference exists**, so no similarity-to-clean metric is possible. The paired
  Diagnostic set is where fidelity to a reference is measured.
- **Input-to-output similarity must not be a primary metric.** A system that correctly
  removes hiss moves away from its input, and rewarding closeness punishes it for working.
- **There are no degradation labels.** Nothing here was measured or annotated as "noisy"
  or "band-limited"; the listening pass sorted items into degraded, clean and not-music,
  and that sort decided membership only.
- **{scored_items} items is thin.** Scores aggregate clip, then item, then dataset, so the
  effective sample size is the item count. That supports a descriptive statement about
  generalisation, not a tight comparison between two close systems.
- **The degradation is homogeneous in kind.** Mostly amateur and netlabel recordings of
  the 2000s and 2010s: {mp3_items} of {scored_items} items have an MP3 as the uploader's own
  original, and almost all sources are 44.1 kHz. There is little historic material.
- **These are not verified concerts.** Round one selected on live-capture metadata and
  round two did not require it at all. Nothing confirmed any event took place.

## Provenance and what screening does not prove

Every clip was fingerprinted against AcoustID, and matches were examined rather than acted
on automatically: for self-released and netlabel music the artist's own Creative Commons
release is catalogued in MusicBrainz like any other, so a match naming the credited artist
is expected. Items were removed when the credit named commercial rights holders, when a
recording was a mash-up of commercial masters, or when a listener recognised a commercial
release.

**A non-match is not proof that audio is free**, and a CC BY tag on Internet Archive is the
uploader's assertion, not proof they held the rights. Every item keeps its uploader, source
page, licence URL and source file so provenance can be audited after the fact.

## Modifications

{modification_notice}

## Verifying a clip against its source

`verify_clip.py` takes a clip id, fetches the source file from the Internet Archive, checks
it against the SHA-1 recorded at download time, re-cuts the same window with the same
command, and compares the decoded samples to the released audio.

## Licences

{licence_table}

No item is under BY-SA, BY-NC or BY-ND, so nothing imposes a share-alike or non-commercial
obligation on work built from this set.
"""

VERIFY = '''#!/usr/bin/env python3
"""Re-derive one released clip from the Internet Archive and compare it to the release.

    python verify_clip.py blind_real--SomeIdentifier--00
"""
import hashlib, json, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    wanted = sys.argv[1]
    rows = [json.loads(l) for l in (HERE / "blind_real_test_manifest.jsonl").open(encoding="utf-8")]
    rows += [json.loads(l) for l in (HERE / "clean_control_manifest.jsonl").open(encoding="utf-8")]
    row = next((r for r in rows if r["id"] == wanted), None)
    if row is None:
        raise SystemExit(f"{wanted} is not in either manifest")

    identifier, name = row["internet_archive_identifier"], row["source_file"]
    url = f"https://archive.org/download/{identifier}/{urllib.parse.quote(name)}"
    print(f"fetching {url}")
    source = HERE / "_verify_source"
    with urllib.request.urlopen(url, timeout=120) as response, source.open("wb") as handle:
        digest = hashlib.sha1()
        for chunk in iter(lambda: response.read(1 << 20), b""):
            digest.update(chunk)
            handle.write(chunk)
    got = digest.hexdigest()
    expected = row.get("source_sha1")
    print(f"source sha1 {got}" + (f"  expected {expected}" if expected else "  (none recorded)"))
    if expected and got != expected:
        print("!! the Archive is serving a different file than the one this clip was cut from")

    recut = HERE / "_verify_recut.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(row["start_seconds"]),
                    "-i", str(source), "-t", str(row["duration_seconds"]),
                    "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(recut)], check=True)

    def samples(path: Path) -> bytes:
        return subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                               "-f", "s16le", "-ar", "44100", "-ac", "2", "-"],
                              capture_output=True, check=True).stdout

    released = HERE / row["audio_path"]
    same = hashlib.sha256(samples(recut)).hexdigest() == hashlib.sha256(samples(released)).hexdigest()
    print("samples identical to the release" if same else
          "!! samples differ -- the source file or the decoder changed")
    for path in (source, recut):
        path.unlink(missing_ok=True)
    raise SystemExit(0 if same else 1)


if __name__ == "__main__":
    main()
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=REPO / "build/release-candidates/blind_real_approved_v0_1")
    parser.add_argument("--clips-root", type=Path, default=REPO / "build/degradations")
    parser.add_argument("--rights-register", type=Path,
                        default=REPO / "build/rights/media_registry.jsonl")
    parser.add_argument("--version", default="v0.1")
    args = parser.parse_args()

    # Fail before making a directory or copying any audio. Internet Archive's tag is
    # only an uploader assertion; it is not independent rights approval.
    registry = load_registry(args.rights_register)
    unapproved = 0
    for manifest_name in ("blind_real_test_manifest.jsonl", "clean_control_manifest.jsonl"):
        for line in (BUILD / manifest_name).open(encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            rights = registry.get(media_key("blind_real", str(row["id"])))
            if rights is None or pack_family(rights, "commercial_compatible") != "base":
                unapproved += 1
    if unapproved:
        raise SystemExit(f"Blind-Real packaging blocked: {unapproved} clips lack approved provenance")
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit("Blind-Real output must be new or empty")

    tracks: dict[tuple[str, str], str] = {}
    for name in ("tracks.jsonl", "round2_tracks.jsonl"):
        path = BUILD / name
        if path.is_file():
            for line in path.open(encoding="utf-8"):
                row = json.loads(line)
                if row.get("local_sha1"):
                    tracks[(str(row["identifier"]), str(row.get("track_name")))] = row["local_sha1"]

    args.out.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    stats: dict[str, dict] = {}

    for manifest_name, folder in (("blind_real_test_manifest.jsonl", "audio"),
                                  ("clean_control_manifest.jsonl", "clean_control")):
        rows = [json.loads(line) for line in (BUILD / manifest_name).open(encoding="utf-8") if line.strip()]
        (args.out / folder).mkdir(parents=True, exist_ok=True)
        out_rows = []
        for row in rows:
            flac = f"{folder}/{Path(row['audio_path']).stem}.flac"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y",
                            "-i", str(args.clips_root / row["audio_path"]),
                            "-c:a", "flac", "-compression_level", "8", str(args.out / flac)], check=True)
            published.append(args.out / flac)
            out = dict(row)
            out["audio_path"] = flac
            out["source_sha1"] = tracks.get((str(row["internet_archive_identifier"]),
                                             str(row.get("source_file"))))
            out_rows.append(out)
        target = args.out / manifest_name
        with target.open("w", encoding="utf-8") as handle:
            for row in sorted(out_rows, key=lambda r: str(r["id"])):
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        published.append(target)
        items = {r["internet_archive_identifier"] for r in out_rows}
        stats[folder] = {
            "clips": len(out_rows), "items": len(items),
            "minutes": sum(r["duration_seconds"] for r in out_rows) / 60,
            "licences": dict(Counter(str(r.get("license_type")) for r in out_rows).most_common()),
            "mp3_items": len({r["internet_archive_identifier"] for r in out_rows
                              if r.get("source_codec") == "mp3"}),
            "with_source_sha1": sum(1 for r in out_rows if r.get("source_sha1")),
        }
        print(f"{folder}: {stats[folder]['clips']} clips, {stats[folder]['items']} items, "
              f"{stats[folder]['with_source_sha1']} with a source checksum")

    attribution = args.out / "attribution"
    attribution.mkdir(exist_ok=True)
    for path in sorted((BUILD / "attribution").glob("*")):
        shutil.copy2(path, attribution / path.name)
        published.append(attribution / path.name)

    from write_blind_real_attribution import MODIFICATION_NOTICE  # noqa: E402

    cap = json.loads((BUILD / "artist_cap_report.json").read_text(encoding="utf-8"))
    licences = Counter()
    for folder in stats:
        licences.update(stats[folder]["licences"])
    card = CARD.format(
        scored_items=stats["audio"]["items"], scored_clips=stats["audio"]["clips"],
        scored_minutes=stats["audio"]["minutes"], clean_items=stats["clean_control"]["items"],
        clean_clips=stats["clean_control"]["clips"], clean_minutes=stats["clean_control"]["minutes"],
        artist_groups=cap["artist_groups"], mp3_items=stats["audio"]["mp3_items"],
        modification_notice=MODIFICATION_NOTICE,
        licence_table="\n".join(["| licence | clips |", "| --- | --- |"]
                                + [f"| {k} | {v} |" for k, v in licences.most_common()]),
    )
    (args.out / "DATASET_CARD.md").write_text(card, encoding="utf-8")
    (args.out / "verify_clip.py").write_text(VERIFY, encoding="utf-8")
    (args.out / "verify_clip.py").chmod(0o755)
    published += [args.out / "DATASET_CARD.md", args.out / "verify_clip.py"]

    lines = []
    for path in sorted(published):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {path.relative_to(args.out).as_posix()}\n")
    (args.out / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")

    size = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"\n{len(lines)} files checksummed, {size/1e6:.0f} MB total -> {args.out}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
