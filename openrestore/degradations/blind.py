"""Blind-Synthetic track: compound degradations with an unknown chain.

The Diagnostic track applies exactly one degradation per item so a failure is
attributable to one cause. This track does the opposite on purpose: a random
number of degradations, of random types, in a random order, so a system has to
work without being told what went wrong. Clean targets are kept, so evaluation
stays quantitative, and some items get no degradation at all, which is how
over-restoration becomes measurable.

Operation definitions and parameter ranges are not redeclared here. They are read
from the Diagnostic registry, so an intensity means the same thing in both tracks
and is defined in exactly one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .core import load_yaml, read_audio, read_jsonl, sha256_file, stable_seed, write_audio, write_jsonl
from .pipeline import CANONICAL_SAMPLE_RATE, _compact_params, apply_recipe, validate_config

# A constant recipe id keeps operation seeds a function of (global seed, item, index)
# only, so the sampled parameters do not shift when the sampled chain changes.
BLIND_RECIPE_ID = "blind_synthetic"

# Fields that reveal what was done to an item. Withheld from the public test split.
REVEALING_FIELDS = (
    "degradation_chain",
    "degradation_count",
    "degradation_params",
    "degradation_tracking",
    "degradation_seed",
)


def load_blind_config(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the blind config and the Diagnostic recipes it draws its operations from."""
    config = load_yaml(path)
    source = config.get("source_recipe_config")
    if not source:
        raise ValueError("A blind-synthetic config must name source_recipe_config")
    recipes_config = load_yaml(Path(source))
    validate_config(recipes_config)
    recipes = {recipe["id"]: recipe for recipe in recipes_config["recipes"]}

    weights = config.get("degradation_count", {}).get("weights")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("A blind-synthetic config must define degradation_count.weights")
    counts = {int(k): float(v) for k, v in weights.items()}
    if any(c < 0 for c in counts) or any(w < 0 for w in counts.values()):
        raise ValueError("degradation_count.weights must map non-negative counts to non-negative weights")
    if sum(counts.values()) <= 0:
        raise ValueError("degradation_count.weights must not sum to zero")
    if max(counts) > len(recipes):
        raise ValueError(f"degradation_count.weights asks for more degradations than the {len(recipes)} available classes")
    config["_counts"] = counts

    for group, members in (config.get("exclusive_groups") or {}).items():
        unknown = sorted(set(members) - set(recipes))
        if unknown:
            raise ValueError(f"exclusive_groups.{group} names unknown classes: {unknown}")
    for pair in config.get("incompatible_pairs") or []:
        if len(pair) != 2:
            raise ValueError(f"incompatible_pairs entries must have exactly two classes: {pair}")
        unknown = sorted(set(pair) - set(recipes))
        if unknown:
            raise ValueError(f"incompatible_pairs names unknown classes: {unknown}")
    return config, recipes


def _conflicts(candidate: str, chosen: list[str], config: dict[str, Any]) -> bool:
    """Reject a candidate that is physically absurd or redundant beside what is chosen."""
    for members in (config.get("exclusive_groups") or {}).values():
        if candidate in members and any(other in members for other in chosen):
            return True
    for first, second in config.get("incompatible_pairs") or []:
        if (candidate == first and second in chosen) or (candidate == second and first in chosen):
            return True
    return False


def sample_chain(
    item_id: str, global_seed: int, config: dict[str, Any], recipes: dict[str, dict[str, Any]]
) -> list[str]:
    """Pick a deterministic, compatible, ordered chain of class IDs for one item.

    An empty chain is a legitimate outcome: it leaves the item clean, which is what
    makes over-restoration measurable.
    """
    rng = np.random.default_rng(stable_seed(global_seed, item_id, BLIND_RECIPE_ID))
    counts = config["_counts"]
    options = sorted(counts)
    weights = np.array([counts[c] for c in options], dtype=float)
    target = int(rng.choice(options, p=weights / weights.sum()))

    chosen: list[str] = []
    pool = sorted(recipes)
    rng.shuffle(pool)
    for candidate in pool:
        if len(chosen) >= target:
            break
        if not _conflicts(candidate, chosen, config):
            chosen.append(candidate)
    rng.shuffle(chosen)  # the application order is itself random
    return chosen


def _chain_recipe(chain: list[str], recipes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": BLIND_RECIPE_ID,
        "severity": "blind_random",
        "operations": [recipes[class_id]["operations"][0] for class_id in chain],
    }


def render_blind_synthetic(
    manifest: Path,
    clean_root: Path,
    output_root: Path,
    config_path: Path,
    output_manifest: Path,
    checksums: Path,
    seed: int,
    progress: bool = False,
    progress_interval: int = 50,
) -> list[dict[str, Any]]:
    """Render one compound example per clean item, recording the whole ordered chain."""
    config, recipes = load_blind_config(config_path)
    clean_rows = read_jsonl(manifest)
    output_rows: list[dict[str, Any]] = []
    checksum_rows: list[dict[str, str]] = []
    clean_count = 0
    for index, clean_row in enumerate(clean_rows, start=1):
        clean_path = clean_root / clean_row["clean_path"]
        audio, sample_rate = read_audio(clean_path)
        if sample_rate != CANONICAL_SAMPLE_RATE:
            raise ValueError(f"Expected {CANONICAL_SAMPLE_RATE} Hz input: {clean_path}")
        chain = sample_chain(clean_row["id"], seed, config, recipes)
        recipe = _chain_recipe(chain, recipes)
        degraded, operation_params = apply_recipe(audio, sample_rate, clean_row["id"], recipe, seed)
        if not chain:
            clean_count += 1
        degraded_id = f"{clean_row['id']}--{BLIND_RECIPE_ID}"
        relative_path = Path(clean_row["split"]) / clean_row["dataset"] / f"{degraded_id}.wav"
        write_audio(output_root / relative_path, degraded, sample_rate)
        digest = sha256_file(output_root / relative_path)
        output_rows.append(
            {
                **clean_row,
                "id": degraded_id,
                "clean_id": clean_row["id"],
                "degraded_path": relative_path.as_posix(),
                "degradation_recipe_id": BLIND_RECIPE_ID,
                "severity": "blind_random",
                "degradation_seed": stable_seed(seed, clean_row["id"], BLIND_RECIPE_ID),
                "degradation_count": len(chain),
                "degradation_chain": chain,
                "degradation_tracking": {
                    "recipe_id": BLIND_RECIPE_ID,
                    "chain": chain,
                    "operations": [
                        {
                            "primitive": op["primitive"],
                            "variant": op.get("variant"),
                            "seed": op["seed"],
                            "summary": _compact_params(op["parameters"]),
                        }
                        for op in operation_params
                    ],
                },
                "degradation_params": operation_params,
                "degraded_audio_sha256": digest,
            }
        )
        checksum_rows.append({"path": relative_path.as_posix(), "sha256": digest})
        if progress and (index == 1 or index % progress_interval == 0 or index == len(clean_rows)):
            print(f"[blind] {index}/{len(clean_rows)} rendered, {clean_count} left clean", flush=True)
    write_jsonl(output_manifest, output_rows)
    write_jsonl(checksums, checksum_rows)
    if progress:
        share = 100.0 * clean_count / max(len(output_rows), 1)
        print(f"[blind] wrote {len(output_rows)} rows to {output_manifest} ({clean_count} clean, {share:.1f}%)", flush=True)
    return output_rows


# The clean reference. Published with the test split by design, so the track stays
# quantitatively scorable, but an inference-time manifest should not carry it.
CLEAN_REFERENCE_FIELDS = ("clean_path", "audio_sha256", "quality", "start_seconds")


def withhold_degradation_metadata(
    rows: list[dict[str, Any]], withhold_clean: bool = False
) -> list[dict[str, Any]]:
    """Strip the fields that reveal what was done to an item.

    The item keeps its ID, its degraded path and its audio properties, so it can be
    restored and scored; it loses any statement of the chain. With withhold_clean, it
    also loses the clean reference, which is what an inference-time manifest should
    look like: the clean targets stay published for scoring, just not handed to the
    model alongside its input.
    """
    drop = set(REVEALING_FIELDS)
    if withhold_clean:
        drop |= set(CLEAN_REFERENCE_FIELDS)
    return [{k: v for k, v in row.items() if k not in drop} for row in rows]


def chain_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise the realised chain distribution, to check sampling did what was asked."""
    from collections import Counter

    counts = Counter(len(row.get("degradation_chain", [])) for row in rows)
    classes: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for row in rows:
        chain = row.get("degradation_chain", [])
        classes.update(chain)
        for i, first in enumerate(chain):
            for second in chain[i + 1 :]:
                pairs[tuple(sorted((first, second)))] += 1
    total = max(len(rows), 1)
    return {
        "items": len(rows),
        "clean_items": counts.get(0, 0),
        "clean_share": round(counts.get(0, 0) / total, 4),
        "count_distribution": {str(k): counts[k] for k in sorted(counts)},
        "class_frequency": dict(sorted(classes.items())),
        "most_common_pairs": [{"pair": list(p), "count": c} for p, c in pairs.most_common(10)],
    }
