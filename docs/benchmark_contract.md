# OpenRestor v0.1 Benchmark Contract

## Task

A system receives one degraded 30-second musical clip and returns one restored clip with the same item ID, 44.1 kHz sample rate, stereo channel layout, and duration.

## Data

Main-track training uses clean SonicMaster originals only.

## What of the rendered corpus may be published, and under what terms

Publishing the Diagnostic audio means redistributing the source audio in modified form, so
each source's licence governs its own partitions. Status reviewed 2026-10-16:

| source | examples | share | terms | published as audio |
| --- | --- | --- | --- | --- |
| SonicMaster clean (train/validation/test) | 525,000 | 96.7% | collection labelled CC BY 2.0; current Jamendo audit found only 856 CC BY IDs | **no, pending clarification** |
| Song Describer Dataset (transfer) | 14,805 | 2.7% | per track: 209 of 705 NoDerivatives, 301 NonCommercial, 195 unrestricted | **no** |
| MUSDB18-HQ (transfer) | 3,024 | 0.6% | academic use only, mixed CC BY-NC-SA, 100 tracks of unclear provenance | **no** |

**Both sides of a pair are governed by the same source licence.** The clean side is not
untouched source material: it is a 30-second excerpt with loudness normalisation applied
(`loudnorm I=-18 LRA=11 TP=-1.0`), so it is a derivative too, just a milder one than the
degraded side. A NoDerivatives term therefore bars publishing either side, and a
NonCommercial term bars both from a release that permits commercial use.

No Diagnostic or Blind-Synthetic audio is currently cleared for publication. The completed
Jamendo audit contradicts SonicMaster's collection label: only 856 IDs currently report CC BY,
13,638 report NC and/or ND, and 8,856 are not returned. Written clarification could establish
broader rights; otherwise a strict CC BY-only subset retains just 17,976 Diagnostic and 856
Blind-Synthetic examples and requires repackaging mixed SonicMaster shards. Both transfer sets
remain withheld and usable locally.

The frozen corpus remains unchanged. The private `build/rights/media_registry.jsonl`
records permissions and review status per `source_id`; `scripts/build_publication_subset.py`
derives both rights profiles from it. When a track is eventually approved, selected HDF5
items are reconstructed into new shards with new indexes and hashes, never copied as whole
mixed partitions. Unknown and pending rights fail closed. The initial candidate contains
zero Diagnostic and Blind-Synthetic audio; only aggregate public counts are emitted.

That is the only role the degradation tools play in distribution. They exist so users can
reproduce the degradations on their own audio, not so users have to build the datasets we
distribute. Main-track validation and in-distribution public testing use SonicMaster's supplied validation and test splits; OpenRestor does not re-split them. SDD and MUSDB18-HQ are optional local-only transfer evaluations for users who lawfully hold the upstream audio. Official evaluation uses an organizer-only hidden set.

## Degradations

The v0.1 registry contains exactly 21 deterministic, metadata-tracked degradation classes. The canonical recipe file is configs/degradations/single/v0_1.yaml. Every output stores the recipe, seed, sampled parameters, and checksum.

## Reproducibility

A release is identified by its code commit, versioned configs, clean and degraded manifests, paired public audio artifacts where redistribution permits, global seed, checksums, and execution environment. The Git commit/tag is the canonical RIR asset version; a standalone asset package is optional transport only. Every paired-audio release includes the RIR `ATTRIBUTION.md` and `docs/degradation_assets_v0_1.sha256`. The public scorer and schemas are part of the release so users can validate any inference pipeline through the same manifest-and-WAV interface. IT hosts these artifacts without changing their scientific content.

## Ownership

Research/audio owns the benchmark behavior and approval. IT owns secure, reproducible execution, storage, logging, monitoring, and public/private access control. The operational details are in docs/it_handoff.md.

## The v0.1 release keeps the former project spelling

The project was renamed from OpenRestore to OpenRestor after the v0.1 paired corpus was
rendered. Two things deliberately keep the old spelling, and neither is branding:

- `configs/releases/private_v0_1.yaml`, because its SHA-256 is recorded as
  `release_config_sha256` in the frozen plan. Editing the file at all, even a comment,
  would make the release fail its own validation.
- The `openrestore.*.v0.1` format identifiers, which are written as an attribute into each
  of the 648 HDF5 shards and into every receipt, and compared literally when a shard is
  checked.

Renaming either would invalidate 542,829 rendered examples to no benefit. The next format
revision corrects the spelling along with its version number.
