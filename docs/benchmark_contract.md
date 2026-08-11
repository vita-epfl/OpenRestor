# OpenRestore v0.1 Benchmark Contract

## Task

A system receives one degraded 30-second musical clip and returns one restored clip with the same item ID, 44.1 kHz sample rate, stereo channel layout, and duration.

## Data

Main-track training uses clean SonicMaster originals only. SonicMaster validation/test items are source-separated. SDD and MUSDB18-HQ are validation-only. Official evaluation uses an organizer-only hidden set.

## Degradations

The v0.1 single-effect registry contains 25 deterministic, metadata-tracked effects. The canonical recipe file is configs/degradations/single/v0_1.yaml. Every output stores the recipe, seed, sampled parameters, and checksum.

## Reproducibility

A release is identified by its code commit, versioned configs, input manifest, global seed, optional asset package, output manifest, checksums, and execution environment. IT hosts these artifacts without changing their scientific content.

## Ownership

Research/audio owns the benchmark behavior and approval. IT owns secure, reproducible execution, storage, logging, monitoring, and public/private access control. The operational details are in docs/it_handoff.md.
