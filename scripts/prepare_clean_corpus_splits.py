#!/usr/bin/env python3
"""Deduplicate a clean-corpus manifest and assign deterministic group splits.

This is a metadata-only gate.  It never opens, copies, downloads, or modifies
audio.  Exact duplicate content is grouped by an existing checksum when one
is available. Sources from the same creator or explicitly identified album are
kept in one split by default to reduce artist/album leakage; otherwise they
fall back to source-level groups.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
from pathlib import Path

from openrestor.validation.core import validate_clean_manifest


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {path}:{number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"manifest row is not an object at {path}:{number}")
            yield row


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                      for row in rows), encoding="utf-8")
    os.replace(temporary, path)


def source_key(row: dict) -> str:
    dataset = str(row.get("dataset") or "").strip()
    source_id = str(row.get("source_id") or row.get("identifier") or "").strip()
    if not dataset or not source_id:
        raise ValueError("each manifest row needs dataset and source_id/identifier")
    return f"{dataset}:{source_id}"


def metadata_value(row: dict, *names: str):
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for name in names:
        for candidate in (row.get(name), metadata.get(name)):
            if candidate not in (None, "", [], {}):
                return candidate
    return None


def normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def content_key(row: dict, key: str) -> tuple[str, bool]:
    """Return an exact-content key and whether it is backed by a checksum."""
    for field in ("source_sha256", "original_sha256", "sha256", "audio_sha256", "checksum"):
        value = row.get(field)
        if value not in (None, ""):
            normalized = normalize_text(value)
            return f"checksum:{normalized}", True
    return f"source:{key}", False


def creator_key(row: dict, key: str) -> tuple[str, bool]:
    value = metadata_value(row, "creator", "artist", "artist_name", "composer")
    if value is None:
        return f"source:{key}", False
    if isinstance(value, (list, tuple)):
        value = ";".join(str(item) for item in value)
    normalized = normalize_text(value)
    return (f"creator:{normalized}", True) if normalized else (f"source:{key}", False)


def album_key(row: dict) -> tuple[str | None, str | None]:
    """Use an evidenced album identity, never dataset authors as performers.

    AlbumDB record 19683001 is a single ten-song album. Its asset rows have no
    creator, so source-level grouping would put stems/masters of the same songs
    in different splits. Other Zenodo records are not assumed to be albums.
    """
    explicit = metadata_value(row, "album_group_id")
    if explicit is not None and normalize_text(explicit):
        return f"album:{normalize_text(row.get('dataset'))}:{normalize_text(explicit)}", "explicit_album"
    if row.get("dataset") == "albumdb" and str(metadata_value(row, "zenodo_record_id")) == "19683001":
        return "album:albumdb:19683001", "album_record"
    return None, None


def candidate_rank(row: dict, key: str) -> tuple:
    """Prefer the most usable row without turning rights into an implicit grant."""
    lossless = str(row.get("lossless_status") or "") in {"clean_lossless", "lossless_container_unverified"}
    return (
        0 if row.get("redistributable_candidate") is True else 1,
        0 if row.get("provenance_candidate") is True else 1,
        0 if row.get("technical_candidate") is True else 1,
        0 if lossless else 1,
        key,
    )


def stable_bucket(value: str, seed: int) -> float:
    digest = hashlib.sha256(f"openrestor-clean-split-v1|{seed}|{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def assign_split(group: str, seed: int, validation_ratio: float, test_ratio: float) -> str:
    bucket = stable_bucket(group, seed)
    if bucket < test_ratio:
        return "test"
    if bucket < test_ratio + validation_ratio:
        return "validation"
    return "train"


def prepare(rows: list[dict], seed: int = 20261029, validation_ratio: float = 0.15,
            test_ratio: float = 0.15, group_creators: bool = True) -> tuple[list[dict], list[dict], dict]:
    if validation_ratio < 0 or test_ratio < 0 or validation_ratio + test_ratio >= 1:
        raise ValueError("validation/test ratios must be non-negative and sum to less than 1")
    keyed = []
    seen_sources: set[str] = set()
    for row in rows:
        key = source_key(row)
        if key in seen_sources:
            raise ValueError(f"duplicate source key: {key}")
        seen_sources.add(key)
        ckey, has_checksum = content_key(row, key)
        cgroup, has_creator = creator_key(row, key) if group_creators else (f"source:{key}", False)
        agroup, album_basis = album_key(row) if group_creators else (None, None)
        gkey = agroup or cgroup
        grouping_basis = album_basis or ("creator" if has_creator else "source")
        keyed.append({"row": row, "source_key": key, "content_key": ckey,
                      "has_checksum": has_checksum, "group_key": gkey,
                      "creator_key": cgroup, "album_key": agroup,
                      "has_group_identity": bool(agroup) or has_creator,
                      "grouping_basis": grouping_basis, "has_creator": has_creator})
    # A checksum duplicate can connect two credited creators. Group the full
    # connected component, including their other recordings, before assigning
    # a split. Grouping each checksum bucket independently leaks those songs.
    parent = list(range(len(keyed)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = root(left), root(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    first_content: dict[str, int] = {}
    first_creator: dict[str, int] = {}
    first_album: dict[str, int] = {}
    for index, item in enumerate(keyed):
        if item["has_checksum"]:
            previous = first_content.setdefault(item["content_key"], index)
            union(index, previous)
        if group_creators and item["has_creator"]:
            previous = first_creator.setdefault(item["creator_key"], index)
            union(index, previous)
        if group_creators and item["album_key"]:
            previous = first_album.setdefault(item["album_key"], index)
            union(index, previous)
    components: dict[int, list[dict]] = collections.defaultdict(list)
    for index, item in enumerate(keyed):
        components[root(index)].append(item)
    component_group: dict[str, str] = {}
    cross_creator_components = 0
    for members in components.values():
        creators = sorted({item["creator_key"] for item in members if item["has_creator"]})
        identities = sorted(set(creators) | {item["album_key"] for item in members if item["album_key"]})
        if len(creators) > 1:
            cross_creator_components += 1
        if len(identities) == 1:
            group = identities[0]
        elif len(members) == 1:
            group = members[0]["group_key"]
        else:
            connected = sorted(set(identities) |
                               {item["content_key"] for item in members if item["has_checksum"]})
            group = "connected:" + hashlib.sha256("\n".join(connected).encode()).hexdigest()[:20]
        for item in members:
            component_group[item["source_key"]] = group
    by_content: dict[str, list[dict]] = collections.defaultdict(list)
    for item in keyed:
        by_content[item["content_key"]].append(item)
    chosen = []
    source_map = []
    for content, members in sorted(by_content.items()):
        members.sort(key=lambda item: candidate_rank(item["row"], item["source_key"]))
        representative = members[0]
        merged_group = component_group[representative["source_key"]]
        split = assign_split(merged_group, seed, validation_ratio, test_ratio)
        representative_row = dict(representative["row"])
        representative_row.update({
            "source_key": representative["source_key"],
            "dedup_group_id": content,
            "duplicate_source_keys": sorted(item["source_key"] for item in members),
            "split_group_key": merged_group,
            "split": split,
            "dedup_representative": True,
        })
        chosen.append(representative_row)
        for item in members:
            source_map.append({"source_key": item["source_key"], "dedup_group_id": content,
                               "dedup_representative": item is representative,
                               "has_content_checksum": item["has_checksum"],
                               "creator_group_key": item["creator_key"],
                               "album_group_key": item["album_key"],
                               "group_identity_key": item["group_key"],
                               "has_creator": item["has_creator"],
                               "has_group_identity": item["has_group_identity"],
                               "grouping_basis": item["grouping_basis"],
                               "split_group_key": merged_group, "split": split})
    chosen.sort(key=lambda row: row["source_key"])
    source_map.sort(key=lambda row: row["source_key"])
    split_creators = collections.defaultdict(set)
    split_genres = collections.defaultdict(collections.Counter)
    for row in chosen:
        split_creators[row["split"]].add(row.get("split_group_key"))
        genre = metadata_value(row, "genre", "genres", "tags")
        if isinstance(genre, list):
            genres = [normalize_text(value) for value in genre if value not in (None, "")]
        else:
            genres = [normalize_text(genre)] if genre not in (None, "") else ["[unknown]"]
        for value in genres or ["[unknown]"]:
            split_genres[row["split"]][value] += 1
    groups_by_split = collections.defaultdict(set)
    for row in source_map:
        groups_by_split[row["split"]].add(row["split_group_key"])
    overlap = {left: sorted(groups_by_split[left] & groups_by_split[right])
               for left, right in (("train", "validation"), ("train", "test"), ("validation", "test"))}
    report = {
        "schema_version": "clean-corpus-split-audit-v1",
        "input_sources": len(rows),
        "deduplicated_sources": len(chosen),
        "exact_duplicate_groups": sum(len(members) > 1 for members in by_content.values()),
        "duplicate_rows_removed": len(rows) - len(chosen),
        "connected_split_groups": len(components),
        "cross_creator_connected_groups": cross_creator_components,
        "sources_without_content_checksum": sum(not item["has_checksum"] for item in keyed),
        "sources_without_creator": sum(not item["has_creator"] for item in keyed),
        "sources_without_group_identity": sum(not item["has_group_identity"] for item in keyed),
        "sources_grouped_by_album": sum(bool(item["album_key"]) for item in keyed),
        "seed": seed,
        "group_by_creator": group_creators,
        "ratios": {"validation": validation_ratio, "test": test_ratio,
                   "train": 1 - validation_ratio - test_ratio},
        "source_counts_by_split": dict(collections.Counter(row["split"] for row in chosen)),
        "group_counts_by_split": {split: len(groups) for split, groups in sorted(groups_by_split.items())},
        "genre_counts_by_split": {split: dict(sorted(counter.items()))
                                  for split, counter in sorted(split_genres.items())},
        "split_group_overlap": overlap,
        "split_disjoint": not any(overlap.values()),
        "rights_not_inferred": True,
        "audio_accessed": False,
    }
    return chosen, source_map, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--deduplicated-out", type=Path, required=True)
    parser.add_argument("--split-out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--no-creator-grouping", action="store_true")
    args = parser.parse_args()
    rows = [row for path in args.input for row in read_jsonl(path)]
    chosen, source_map, report = prepare(rows, seed=args.seed,
                                         validation_ratio=args.validation_ratio,
                                         test_ratio=args.test_ratio,
                                         group_creators=not args.no_creator_grouping)
    write_jsonl(args.deduplicated_out, chosen)
    validate_clean_manifest(args.deduplicated_out)
    write_jsonl(args.split_out, source_map)
    report["deduplicated_manifest_schema_validated"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Prepared {len(chosen)} deduplicated sources from {len(rows)} rows; report {args.report}")


if __name__ == "__main__":
    main()
