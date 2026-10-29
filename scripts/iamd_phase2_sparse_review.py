#!/usr/bin/env python3
"""Summarize sparse blind listening labels against the frozen IAMD predictions.

Blank fields mean unassessed, not a positive or negative label. This tool never
changes the prediction rule, its lock, or the original review export.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path


DEFAULT_PILOT = Path("build/iamd_feasibility/phase2_pilot")
FIELDS = ("content_type", "audio_quality", "source_nature", "pool_suitability")
ALLOWED = {
    "content_type": {"music", "speech_dominant", "noise_or_sound_effect", "ambiguous"},
    "audio_quality": {"acceptable", "degraded", "ambiguous"},
    "source_nature": {"likely_real_recording", "likely_midi_or_synthetic_render", "ambiguous"},
    "pool_suitability": {"suitable", "unsuitable_style", "ambiguous"},
    "scope": {"primary_clip_only", "multiple_excerpts", "full_original"},
    "source_level_label": {"promising", "unsuitable", "ambiguous"},
}


def load_predictions(path: Path) -> dict[str, dict]:
    predictions = {}
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("pilot_batch") != "expand_200":
                continue
            identifier = row.get("identifier")
            if not identifier or identifier in predictions:
                raise ValueError(f"missing or duplicate prediction identifier on line {number}")
            predictions[identifier] = row
    if len(predictions) != 150:
        raise ValueError(f"expected 150 locked validation predictions, found {len(predictions)}")
    return predictions


def parse_reviews(path: Path, known: set[str]) -> tuple[int, list[dict]]:
    reviewed = []
    seen = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if "identifier" not in (reader.fieldnames or []):
            raise ValueError("review CSV needs an identifier column")
        for number, raw in enumerate(reader, 2):
            identifier = (raw.get("identifier") or "").strip()
            if identifier not in known or identifier in seen:
                raise ValueError(f"unknown or duplicate identifier on line {number}: {identifier!r}")
            seen.add(identifier)
            row = {field: (raw.get(field) or "").strip() for field in (*FIELDS, "scope", "source_level_label", "notes")}
            for field in (*FIELDS, "scope", "source_level_label"):
                if row[field] and row[field] not in ALLOWED[field]:
                    raise ValueError(f"invalid {field} on line {number}: {row[field]!r}")
            row["scope"] = row["scope"] or "primary_clip_only"
            if row["source_level_label"] and row["scope"] == "primary_clip_only":
                raise ValueError(f"source-level label requires multiple excerpts on line {number}")
            if any(row[field] for field in (*FIELDS, "source_level_label", "notes")):
                row["identifier"] = identifier
                reviewed.append(row)
    return len(seen), reviewed


def explicit_problem(row: dict) -> list[str]:
    reasons = []
    if row["content_type"] in {"speech_dominant", "noise_or_sound_effect"}:
        reasons.append(row["content_type"])
    if row["audio_quality"] == "degraded":
        reasons.append("degraded")
    if row["source_nature"] == "likely_midi_or_synthetic_render":
        reasons.append("likely_midi_or_synthetic_render")
    if row["pool_suitability"] == "unsuitable_style":
        reasons.append("unsuitable_style")
    return reasons


def analyze(predictions: dict[str, dict], reviewed: list[dict], csv_rows: int) -> dict:
    by_class = collections.Counter()
    by_field = {field: collections.Counter() for field in FIELDS}
    by_group = {field: collections.defaultdict(lambda: {"reviewed": 0, "explicit_problem": 0,
                                                       "problem_auto_accepted": 0})
                for field in ("collection", "genre_proxy", "creator")}
    problems = []
    auto_accepted_problems = []
    music_and_acceptable = 0
    fully_positive = 0
    for row in reviewed:
        prediction = predictions[row["identifier"]]
        candidate_class = prediction["classification"]
        by_class[candidate_class] += 1
        for field in FIELDS:
            by_field[field][row[field] or "unassessed"] += 1
        reasons = explicit_problem(row)
        if row["content_type"] == "music" and row["audio_quality"] == "acceptable":
            music_and_acceptable += 1
        if (row["content_type"] == "music" and row["audio_quality"] == "acceptable"
                and row["source_nature"] == "likely_real_recording"
                and row["pool_suitability"] == "suitable"):
            fully_positive += 1
        if reasons:
            problems.append(row["identifier"])
            if candidate_class == "accept_candidate":
                auto_accepted_problems.append({"identifier": row["identifier"], "human_reasons": reasons,
                                               "primary_clip": prediction.get("acoustic", {}).get("primary_clip"),
                                               "rights_status": prediction.get("rights_status")})
        for field in by_group:
            group = str(prediction.get(field) or "[unknown]")
            by_group[field][group]["reviewed"] += 1
            by_group[field][group]["explicit_problem"] += bool(reasons)
            by_group[field][group]["problem_auto_accepted"] += bool(reasons and candidate_class == "accept_candidate")
    return {
        "validation_total": len(predictions),
        "csv_rows": csv_rows,
        "reviewed_any_explicit_label_or_note": len(reviewed),
        "unreviewed": len(predictions) - len(reviewed),
        "candidate_class_among_reviewed": dict(by_class),
        "field_counts_among_reviewed": {field: dict(counts) for field, counts in by_field.items()},
        "music_and_acceptable_clip_evidence": music_and_acceptable,
        "fully_positive_clip_labels": fully_positive,
        "explicit_problem_count": len(problems),
        "explicit_problem_identifiers": problems,
        "explicit_problems_auto_accepted": auto_accepted_problems,
        "groups_among_reviewed": {field: dict(sorted(groups.items(),
                                                      key=lambda item: (-item[1]["reviewed"], item[0])))
                                  for field, groups in by_group.items()},
        "annotation_coverage_complete": len(reviewed) == len(predictions),
        "source_rights_cleared_by_this_report": 0,
        "interpretation": "Blank labels are unassessed. Clip labels do not validate whole sources or rights.",
    }


def write_report(data: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = data["field_counts_among_reviewed"]
    lines = [
        "# IAMD · avis d'écoute partiels (150 nouvelles sources)", "",
        f"Avis avec au moins un champ ou une note : **{data['reviewed_any_explicit_label_or_note']}/150** ; "
        f"sans avis : {data['unreviewed']}.",
        "Les champs vides restent non évalués. Les prédictions acoustiques sont gelées ; "
        "ce rapport ne change aucune règle ni décision de droits.", "",
        f"Parmi les avis : {data['candidate_class_among_reviewed']}.",
        f"Contenu : {fields['content_type']}.",
        f"Qualité : {fields['audio_quality']}.",
        f"Nature : {fields['source_nature']}.",
        f"Adéquation : {fields['pool_suitability']}.", "",
        f"Problème explicite sur au moins un axe : **{data['explicit_problem_count']}** ; "
        f"dont **{len(data['explicit_problems_auto_accepted'])}** proposés à l'acceptation automatique.",
        f"Indices conjoints `music` + `acceptable` sur un clip : {data['music_and_acceptable_clip_evidence']} ; "
        f"quatre axes positifs renseignés : {data['fully_positive_clip_labels']}.",
        "Un avis sur un clip ne valide pas la piste entière ; aucun statut juridique n'est accordé.", "",
        "## Acceptations contredites par un avis explicite", "",
        "| Identifier | Motifs humains | Extrait principal |", "| --- | --- | --- |",
    ]
    for case in data["explicit_problems_auto_accepted"]:
        lines.append(f"| `{case['identifier']}` | {', '.join(case['human_reasons'])} | `{case['primary_clip'] or ''}` |")
    if not data["explicit_problems_auto_accepted"]:
        lines.append("| — | — | — |")
    lines.extend(["", "## Groupes observés parmi les avis", "",
                  "Comptages descriptifs uniquement : le demi-lot écouté ne permet pas d'estimer le rendement IAMD.", ""])
    for field in ("collection", "genre_proxy", "creator"):
        lines.extend([f"### {field}", "", "| Groupe | Écoutés | Problèmes explicites | Problèmes auto-acceptés |",
                      "| --- | ---: | ---: | ---: |"])
        for group, stats in list(data["groups_among_reviewed"][field].items())[:15]:
            label = group.replace("|", "\\|")
            lines.append(f"| {label} | {stats['reviewed']} | {stats['explicit_problem']} | "
                         f"{stats['problem_auto_accepted']} |")
        lines.append("")
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews-csv", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--output", type=Path, default=None, help="Output prefix, without .md/.json")
    args = parser.parse_args()
    predictions = load_predictions(args.pilot_dir / "pilot_200_predictions_locked.jsonl")
    csv_rows, reviews = parse_reviews(args.reviews_csv, set(predictions))
    result = analyze(predictions, reviews, csv_rows)
    output = args.output or args.pilot_dir / "pilot_200_partial_review"
    write_report(result, output)
    print(f"Wrote {output.with_suffix('.md')} and {output.with_suffix('.json')}")


if __name__ == "__main__":
    main()
