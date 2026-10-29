"""Build two rights-derived publication profiles; never copy private shards wholesale.

Default mode is metadata-only. --copy-into creates local candidate packs containing
only approved source_ids, rebuilt Diagnostic HDF5 shards and fresh checksums. It is
not an upload command and does not imply EPFL/TTO release approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path

from .degradations.core import load_yaml
from .publication import classify_index, copy_blind_synthetic, repack_hdf5, validate_pack
from .rights import PROFILES, load_registry, public_summary

REPO = Path(__file__).resolve().parents[1]
RELEASE_NOTICE_FILES = (
    Path("THIRD_PARTY_NOTICES.md"), Path("LICENSES/Apache-2.0.txt"),
    Path("assets/degradations/v0_1/real_rirs/ATTRIBUTION.md"),
    Path("docs/degradation_assets_v0_1.sha256"),
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def family_directory(family: str) -> str:
    if family in {"base", "nc_extension"}:
        return family
    label = re.sub(r"[^a-z0-9]+", "_", family[3:].split("/licenses/")[-1].lower()).strip("_")
    return "share_alike_" + label + "_" + hashlib.sha256(family.encode()).hexdigest()[:10]


def check_nc_access(path: Path | None) -> None:
    if path is None:
        raise ValueError("NC pack requires --noncommercial-use-approval for controlled access")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("uses_effectively_noncommercial") is not True or not all(
        str(value.get(field) or "").strip() for field in
        ("approved_by", "approved_at", "approval_reference", "access_mode")
    ) or value.get("access_mode") not in {"institutional_agreement", "controlled_research_access"}:
        raise ValueError("NC access approval needs reviewer, date, reference and controlled mode")
    try:
        date.fromisoformat(value["approved_at"])
    except (TypeError, ValueError) as error:
        raise ValueError("NC access approval date must be ISO YYYY-MM-DD") from error


def media_notice(rows: list[dict], registry: dict, corpus: str) -> list[dict]:
    keys = sorted({f"{row['dataset']}:{row['source_id']}" for row in rows})
    changes = ("30-second excerpt and loudness normalization; synthetic degradation "
               "according to each index row" if corpus == "diagnostic" else
               "30-second excerpt and loudness normalization; Blind-Synthetic processing "
               "according to each index row")
    return [{"dataset": registry[key]["dataset"], "source_id": registry[key]["source_id"],
             "license_label": registry[key]["license_label"],
             "license_url": registry[key]["license_url"],
             "attribution": registry[key]["attribution"],
             "source_evidence_url": registry[key]["evidence_url"],
             "modifications": changes} for key in keys]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path,
                        default=REPO / "configs/releases/publication_policy_v0_1.yaml")
    parser.add_argument("--rights-register", type=Path,
                        default=REPO / "build/rights/media_registry.jsonl")
    parser.add_argument("--corpus", choices=("all", "diagnostic", "blind_synthetic"), default="all")
    parser.add_argument("--profile", choices=("all", *PROFILES), default="all")
    parser.add_argument("--out", type=Path, default=REPO / "build/publication/v0_1")
    parser.add_argument("--copy-into", type=Path,
                        help="Local candidate root; must be new/empty, never the frozen corpus")
    parser.add_argument("--clean-root", type=Path, default=REPO / "build/clean")
    parser.add_argument("--blind-audio-root", type=Path,
                        default=REPO / "build/blind-synthetic/audio")
    parser.add_argument("--noncommercial-use-approval", type=Path,
                        help="Private documented approval for controlled, effectively non-commercial access")
    args = parser.parse_args()

    policy = load_yaml(args.policy)
    registry = load_registry(args.rights_register)
    frozen = REPO / str(policy["frozen_release_root"])
    if args.copy_into:
        dest = args.copy_into.resolve()
        if dest == frozen.resolve() or frozen.resolve() in dest.parents:
            raise SystemExit("Candidate output cannot be inside the frozen corpus")
        if dest.exists() and any(dest.iterdir()):
            raise SystemExit("Candidate output must be new or empty")
        dest.mkdir(parents=True, exist_ok=True)
        for relative in RELEASE_NOTICE_FILES:
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, target)
        write_json(dest / "rights_summary.json", public_summary(registry.values()))

    corpora = tuple(policy["corpora"]) if args.corpus == "all" else (args.corpus,)
    profiles = PROFILES if args.profile == "all" else (args.profile,)
    for corpus in corpora:
        index = REPO / str(policy["corpora"][corpus]["index"])
        for profile in profiles:
            selected, withheld = classify_index(index, registry, profile)
            selected.setdefault("base", [])
            families = {}
            controlled_packaged = False
            for family, rows in sorted(selected.items()):
                relative = Path(corpus) / profile / family_directory(family)
                contains_nc = bool(rows) and (family == "nc_extension" or
                                             (family.startswith("sa:") and any(
                                                 registry[f"{row['dataset']}:{row['source_id']}"]["allow_commercial"] is False
                                                 for row in rows)))
                if args.copy_into:
                    if contains_nc:
                        check_nc_access(args.noncommercial_use_approval)
                        controlled_packaged = True
                    target = args.copy_into / relative
                    if corpus == "diagnostic":
                        output_rows = repack_hdf5(rows, frozen, args.clean_root, target)
                    else:
                        output_rows = copy_blind_synthetic(rows, args.blind_audio_root,
                                                           args.clean_root, target)
                    validate_pack(output_rows, registry, profile, family, target, corpus)
                    write_jsonl(target / "index.jsonl", output_rows)
                    write_jsonl(target / "MEDIA_ATTRIBUTION.jsonl",
                                media_notice(output_rows, registry, corpus))
                    if family.startswith("sa:") and output_rows:
                        first = registry[f"{output_rows[0]['dataset']}:{output_rows[0]['source_id']}"]
                        (target / "SHARE_ALIKE_NOTICE.md").write_text(
                            f"# Adapted audio: {first['license_label']}\n\n"
                            f"Exact upstream licence: {first['license_url']}\n\n"
                            "The adapted audio in this pack must retain its applicable "
                            "ShareAlike terms. See MEDIA_ATTRIBUTION.jsonl for per-source "
                            "credits and modifications. These terms do not relicense EPFL code.\n",
                            encoding="utf-8")
                    if contains_nc:
                        (target / "NONCOMMERCIAL_ACCESS_NOTICE.md").write_text(
                            "# Controlled non-commercial access only\n\n"
                            "Do not offer this pack as an unrestricted public download. "
                            "The access approval and each recipient's actual use must "
                            "satisfy the source NC terms. See MEDIA_ATTRIBUTION.jsonl "
                            "for exact licences and credits.\n", encoding="utf-8")
                else:
                    # A metadata-only run cannot expose private paths or source IDs.
                    output_rows = []
                    write_jsonl(args.out / relative / "index.jsonl", [])
                families[family] = {"eligible_examples": len(rows),
                                    "packaged_examples": len(output_rows),
                                    "packaged_shards": len({row["degraded_audio_shard"] for row in output_rows})
                                    if corpus == "diagnostic" else 0}
            report = {"corpus": corpus, "profile": profile,
                      "frozen_release_untouched": True,
                      "packaged_synthetic_audio": sum(
                          value["packaged_examples"] for value in families.values()),
                      "families": families,
                      "withheld_examples_by_dataset": dict(sorted(withheld.items())),
                      "release_notice_files": [str(path) for path in RELEASE_NOTICE_FILES],
                      "notices_copied": bool(args.copy_into),
                      "distribution_access": "controlled_noncommercial" if controlled_packaged else
                      "no_nc_packaged",
                      "upload_approved": False,
                      "note": "Local candidate only; EPFL/TTO and media-specific sign-off remain separate."}
            location = args.copy_into if args.copy_into else args.out
            write_json(location / corpus / profile / "publication_report.json", report)
            print(f"{corpus}/{profile}: {sum(v['packaged_examples'] for v in families.values())} "
                  f"packaged, {sum(withheld.values())} withheld")
    if args.copy_into:
        # A failed run leaves no completion marker, so an interrupted partial tree is
        # never mistaken for a validated handoff candidate.
        write_json(args.copy_into / "candidate_status.json",
                   {"status": "local_candidate_complete", "upload_approved": False,
                    "corpora": list(corpora), "profiles": list(profiles)})
