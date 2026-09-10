Usage
=====

OpenRestore ships four command-line entry points, each generated from an
``argparse`` parser in the corresponding subpackage's ``cli`` module. The
subcommands and flags below are read directly from those sources.

``openrestore-data``
--------------------

Phase 1 data pipeline. The command takes one subcommand:

``audit``
    Probe a corpus described by a YAML config before ingest.
    ``--config`` (required), ``--output`` (required), ``--probe-limit`` (default 25), ``--quiet``.

``ingest``
    Ingest a corpus described by a YAML config.
    ``--config`` (required), ``--output`` (required), ``--quiet``.

``split``
    Split indexes into train/validation/test partitions.
    ``--indexes`` (one or more, required), ``--output`` (required),
    ``--seed`` (default 20260714), ``--train-fraction`` (default 0.90),
    ``--validation-fraction`` (default 0.05), ``--quiet``.

``segment``
    Segment sources into clips and write a manifest plus checksums.
    ``--sources`` (required), ``--output-root`` (required), ``--manifest`` (required),
    ``--checksums`` (required), ``--seed`` (default 20260714),
    ``--clips-per-source`` (default 1), ``--no-normalize``, ``--min-rms`` (default 0.003),
    ``--quiet``.

``shard``
    Write a manifest into shards.
    ``--output-root`` (required), ``--manifest`` (required), ``--shards-dir`` (required),
    ``--shard-size`` (default 1000), ``--quiet``.

``verify``
    Verify file checksums against a checksums file.
    ``--root`` (required), ``--checksums`` (required), ``--quiet``.

``source-stats``
    Write per-source statistics from a manifest.
    ``--manifest`` (required), ``--output`` (required), ``--quiet``.

``stats``
    Write corpus statistics from a manifest.
    ``--manifest`` (required), ``--output`` (required), ``--quiet``.

``openrestore-degrade``
-----------------------

Apply degradations to a clean corpus. The command takes one subcommand:

``render``
    Render degraded audio from a clean manifest.
    ``--manifest`` (required), ``--clean-root`` (required), ``--output-root`` (required),
    ``--config`` (required), ``--output-manifest`` (required), ``--checksums`` (required),
    ``--seed`` (default 20260714), ``--quiet``.

``shard``
    Write a degraded manifest into shards and an HDF5 output index.
    ``--output-root`` (required), ``--manifest`` (required), ``--shards-dir`` (required),
    ``--output-index`` (required), ``--shard-size`` (default 1000), ``--quiet``.

``validate-config``
    Validate a degradations config.
    ``--config`` (required).

``list-recipes``
    List available degradation recipes.
    ``--config`` (required).

``openrestore-score``
---------------------

Local scoring and restoration validation. The command takes one subcommand:

``validate-restored``
    Validate a restored manifest against a degraded manifest.
    ``--degraded-manifest`` (required), ``--restored-manifest`` (required), ``--restored-root``.

``score``
    Compute quality scores between degraded, clean, and restored audio.
    ``--degraded-manifest`` (required), ``--degraded-root`` (required),
    ``--clean-root`` (required), ``--restored-manifest`` (required),
    ``--config`` (required), ``--output-dir`` (required), ``--submission-id``.

``perceptual``
    Run perceptual scoring (e.g. on a GPU).
    ``--degraded-manifest`` (required), ``--degraded-root`` (required),
    ``--clean-root`` (required), ``--restored-manifest`` (required),
    ``--config`` (required), ``--output-dir`` (required), ``--cache-dir``,
    ``--device`` (default "cuda"), ``--submission-id``.

``setup-perceptual``
    Prepare a cache for perceptual scoring.
    ``--config`` (required), ``--cache-dir``.

``no-restoration``
    Baseline that passes the degraded audio through unchanged.
    ``--degraded-manifest`` (required), ``--degraded-root`` (required),
    ``--output-root`` (required), ``--output-manifest`` (required).

``openrestore-validate``
------------------------

Validate OpenRestore JSON and JSONL artifacts. Takes a positional ``kind``
(one of ``index``, ``degradation_tracking``, ``submission_manifest``,
``restoration_outputs``, ``restoration_metadata``, ``scores``,
``leaderboard_entry``) and ``--input`` (required), then reports the number of
documents validated against the corresponding ``.schema.json``.
