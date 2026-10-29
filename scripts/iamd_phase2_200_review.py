#!/usr/bin/env python3
"""Lock explainable 200-source IAMD triage; evaluate new sources only after blind listening.

Candidate classes are acoustic/content triage, never redistribution rights.
The first 50 may calibrate v1; the 150 new sources are a held-out listening
set. Once predictions are written they cannot be replaced by this script.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import html
import json
import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import iamd_phase2_clap_probe
from scripts.iamd_phase2_clap_probe import MODEL_REVISION, PROMPT_VERSION
from scripts.iamd_phase2_content_probe import MODEL_REVISION as AST_MODEL_REVISION
from scripts.iamd_phase2_pilot import (DEFAULT_OUT, pilot_200_rows, read_jsonl,
                                       write_json, write_jsonl)

RULE_VERSION = "pilot-200-conservative-v1"
PREDICTIONS = "pilot_200_predictions_locked.jsonl"
LOCK = "pilot_200_rules_lock.json"
CONTENT = {"music", "speech_dominant", "noise_or_sound_effect", "ambiguous"}
QUALITY = {"acceptable", "degraded", "ambiguous"}
NATURE = {"likely_real_recording", "likely_midi_or_synthetic_render", "ambiguous"}
SUITABILITY = {"suitable", "unsuitable_style", "ambiguous"}
SCOPES = {"primary_clip_only", "multiple_excerpts", "full_original"}
SOURCE_LABELS = {"", "promising", "unsuitable", "ambiguous"}


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _median(values):
    values = [float(value) for value in values if _finite(value)]
    return statistics.median(values) if values else None


def selected_excerpt(score: dict) -> dict | None:
    """Use the temporal middle excerpt scored by both AST and CLAP."""
    parts = score.get("excerpts") or []
    return parts[len(parts) // 2] if parts else None


def acoustic_features(score: dict) -> dict:
    parts = score.get("excerpts") or []
    axes = score.get("audiobox_axes") or {}
    primary = selected_excerpt(score)
    return {
        "status": score.get("status"), "format_matches": score.get("format_matches"),
        "sample_rate": score.get("sample_rate"), "duration_s": score.get("duration_s"),
        "CE": axes.get("CE"), "CU": axes.get("CU"), "PC": axes.get("PC"), "PQ": axes.get("PQ"),
        "pq_excerpt_min": min((part["audiobox_axes"]["PQ"] for part in parts
                               if _finite((part.get("audiobox_axes") or {}).get("PQ"))), default=None),
        "pq_excerpt_median": _median((part.get("audiobox_axes") or {}).get("PQ") for part in parts),
        "clipped_ratio_max": max((part.get("clipped_sample_ratio_channels", 0) for part in parts), default=None),
        "bandwidth_hz_median": _median(part.get("bandwidth_hz") for part in parts),
        "rms_dbfs_median": _median(part.get("rms_dbfs") for part in parts),
        "peak_dbfs_median": _median(part.get("peak_dbfs") for part in parts),
        "noise_floor_db_median": _median(part.get("noise_floor_db") for part in parts),
        "crest_factor_db_median": _median(part.get("crest_factor_db") for part in parts),
        "spectral_flatness_median": _median(part.get("spectral_flatness") for part in parts),
        "high_frequency_share_median": _median(part.get("high_frequency_share") for part in parts),
        "quasi_silent_excerpts": sum(part.get("near_silent_sample_ratio", 0) > .85
                                    and part.get("rms_dbfs", 0) < -30 for part in parts),
        "excerpt_count": len(parts), "primary_clip": primary.get("clip_path") if primary else None,
    }


def classify(row: dict, score: dict, ast: dict, clap: dict, metadata: dict) -> dict:
    """Conservative frozen review rule; no single model score rejects music."""
    acoustic = acoustic_features(score)
    cues = metadata.get("metadata_cues") or row.get("metadata_cues") or {}
    ast_labels = ast.get("interest_labels") or {}
    clap_groups = clap.get("group_scores") or {}
    music = ast_labels.get("Music")
    speech = ast_labels.get("Speech")
    top = clap.get("top_group")
    margin = clap.get("top_margin")
    reasons: list[str] = []
    rights = ("archive_licence_conflict" if row.get("archive_licence_category") == "contradictory"
              else "archive_licence_unknown" if row.get("archive_licence_category") != "compatible"
              else "provenance_unvalidated" if not row.get("provenance_candidate")
              else "metadata_plausible_not_rights_cleared")
    complete = (acoustic["status"] == "measured" and ast.get("status") == "scored"
                and clap.get("status") == "scored"
                and ast.get("model_revision") == AST_MODEL_REVISION
                and clap.get("model_revision") == MODEL_REVISION
                and clap.get("prompt_version") == PROMPT_VERSION
                and ast.get("clip_path") == acoustic["primary_clip"]
                and clap.get("clip_path") == acoustic["primary_clip"]
                and acoustic["excerpt_count"] >= 1
                and all(all(_finite((part.get("audiobox_axes") or {}).get(axis))
                            for axis in ("CE", "CU", "PC", "PQ"))
                        for part in score.get("excerpts") or [])
                and all(_finite(acoustic[key])
                for key in ("CE", "CU", "PC", "PQ", "pq_excerpt_min", "sample_rate"))
                and _finite(music) and _finite(speech) and _finite(margin))
    if not complete:
        reasons.append("incomplete_measurements_or_model_scores")
        label = "review"
    elif acoustic["format_matches"] is False:
        reasons.append("actual_format_mismatch")
        label = "reject_candidate"
    elif (acoustic["excerpt_count"] >= 2
          and acoustic["quasi_silent_excerpts"] == acoustic["excerpt_count"]):
        reasons.append("all_sampled_excerpts_quasi_silent")
        label = "reject_candidate"
    elif (top == "non_music" and margin >= .025 and music < .35
          and (speech > .3 or cues.get("sound_effect_cues") or cues.get("speech_cues"))):
        reasons.append("clap_ast_metadata_agree_non_music")
        label = "reject_candidate"
    elif (top == "rudimentary_synthetic" and margin >= .025
          and cues.get("synthetic_render_cues")):
        reasons.append("clap_metadata_agree_rudimentary_synthetic")
        label = "reject_candidate"
    elif (cues.get("sound_effect_cues") and music < .5 and speech > .5
          and clap_groups.get("non_music", -1) >= clap_groups.get("produced_music", 1)):
        reasons.append("metadata_ast_clap_agree_field_or_speech")
        label = "reject_candidate"
    else:
        if acoustic["sample_rate"] is not None and acoustic["sample_rate"] < 32000:
            reasons.append("low_sample_rate_review")
        if acoustic["clipped_ratio_max"] is not None and acoustic["clipped_ratio_max"] > .005:
            reasons.append("clipping_review")
        if (acoustic["bandwidth_hz_median"] is not None and acoustic["sample_rate"] >= 44100
                and acoustic["bandwidth_hz_median"] < 12000):
            reasons.append("bandwidth_cutoff_review")
        if acoustic["quasi_silent_excerpts"]:
            reasons.append("quasi_silence_review")
        if (acoustic["rms_dbfs_median"] is not None and acoustic["rms_dbfs_median"] < -30):
            reasons.append("very_low_level_review")
        if acoustic["pq_excerpt_min"] < 6.0 or acoustic["CE"] < 5 or acoustic["CU"] < 5:
            reasons.append("audiobox_quality_or_content_review")
        if acoustic["PC"] < 2.5:
            reasons.append("low_production_complexity_review")
        if any(cues.get(key) for key in ("speech_cues", "sound_effect_cues",
                                         "synthetic_render_cues", "capture_context_cues",
                                         "stylized_content_cues")):
            reasons.append("metadata_content_or_capture_review")
        if top not in {"produced_music", "legitimate_electronic_music"} or margin < .01:
            reasons.append("clap_nonpositive_or_close_contrast_review")
        if music < .5 or speech > .35:
            reasons.append("ast_music_or_speech_review")
        label = "review" if reasons else "accept_candidate"
        if not reasons:
            reasons.append("multi_signal_music_and_quality_no_review_flags")
    return {
        "identifier": row["identifier"], "pilot_batch": row["pilot_batch"],
        "sample_id": row["sample_id"], "collection": row.get("collection"),
        "creator": row.get("creator"), "genre_proxy": row.get("genre_proxy"),
        "classification": label, "reasons": reasons, "rule_version": RULE_VERSION,
        "acoustic": acoustic, "ast_music": music, "ast_speech": speech,
        "clap_top_group": top, "clap_top_margin": margin, "clap_group_scores": clap_groups,
        "metadata_cues": cues, "rights_status": rights,
        "provenance_candidate": row.get("provenance_candidate"),
        "archive_licence_category": row.get("archive_licence_category"),
        "license_url": row.get("archive_license_url"),
        "title": row.get("title"), "source_filename": row.get("name"),
        "other_clips": [part["clip_path"] for part in score.get("excerpts") or []
                        if part.get("clip_path") != acoustic["primary_clip"]],
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_locked(out: Path) -> dict:
    rows = pilot_200_rows(out)
    target = out / PREDICTIONS
    lock_path = out / LOCK
    if target.exists() or lock_path.exists():
        if not target.exists() or not lock_path.exists():
            raise ValueError("prediction lock is partial; inspect manually before proceeding")
        locked = json.loads(lock_path.read_text(encoding="utf-8"))
        if (locked.get("rules_sha256") != _hash_file(Path(__file__))
                or locked.get("clap_prompts_sha256") != _hash_file(Path(iamd_phase2_clap_probe.__file__))):
            raise ValueError("rules changed after locking predictions; validation cannot be retuned")
        predictions = list(read_jsonl(target))
        if len(predictions) != 200 or {r["identifier"] for r in predictions} != {r["identifier"] for r in rows}:
            raise ValueError("locked predictions do not match exact 200-source selection")
        return {"locked": True, "predictions": predictions, "lock": locked}
    scores = {row["identifier"]: row for row in read_jsonl(out / "scores.jsonl")}
    ast = {row["identifier"]: row for row in read_jsonl(out / "ast_content_probe.jsonl")}
    clap = {row["identifier"]: row for row in read_jsonl(out / "clap_contrastive_probe.jsonl")}
    queue = {row["identifier"]: row for row in read_jsonl(out / "metadata_review_queue.jsonl")}
    predictions = [classify(row, scores.get(row["identifier"], {}), ast.get(row["identifier"], {}),
                            clap.get(row["identifier"], {}), queue.get(row["identifier"], {}))
                   for row in rows]
    if any("incomplete_measurements_or_model_scores" in row["reasons"] for row in predictions):
        raise ValueError("all 200 sources must have complete acoustic, AST and CLAP scores before lock")
    lock = {"rule_version": RULE_VERSION, "rules_sha256": _hash_file(Path(__file__)),
            "clap_prompts_sha256": _hash_file(Path(iamd_phase2_clap_probe.__file__)),
            "ast_model_revision": AST_MODEL_REVISION,
            "clap_model_revision": MODEL_REVISION, "clap_prompt_version": PROMPT_VERSION,
            "selected_identifiers": 200, "validation_identifiers": 150,
            "note": "Frozen before new-source human labels; acoustics/content only, not legal clearance."}
    write_jsonl(target, predictions)
    write_json(lock_path, lock)
    return {"locked": False, "predictions": predictions, "lock": lock}


def write_prediction_csv(out: Path, predictions: list[dict]) -> None:
    fields = ("identifier", "pilot_batch", "classification", "reasons", "rights_status",
              "genre_proxy", "collection", "creator", "title", "primary_clip",
              "CE", "CU", "PC", "PQ", "pq_excerpt_min", "pq_excerpt_median",
              "ast_music", "ast_speech", "clap_top_group", "clap_top_margin",
              "clap_produced_music", "clap_degraded_music", "clap_non_music",
              "clap_rudimentary_synthetic", "clap_legitimate_electronic_music",
              "sample_rate", "duration_s", "clipped_ratio_max", "bandwidth_hz_median",
              "rms_dbfs_median", "archive_licence_category", "license_url",
              "provenance_candidate")
    with (out / "pilot_200_predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in predictions:
            flat = {key: row.get(key) for key in fields}
            flat["reasons"] = ";".join(row["reasons"])
            flat["primary_clip"] = row["acoustic"]["primary_clip"]
            for key in ("CE", "CU", "PC", "PQ", "pq_excerpt_min", "pq_excerpt_median",
                        "sample_rate", "duration_s", "clipped_ratio_max", "bandwidth_hz_median",
                        "rms_dbfs_median"):
                flat[key] = row["acoustic"].get(key)
            for key in ("produced_music", "degraded_music", "non_music",
                        "rudimentary_synthetic", "legitimate_electronic_music"):
                flat["clap_" + key] = row["clap_group_scores"].get(key)
            writer.writerow(flat)


def write_blind_listening(out: Path, predictions: list[dict]) -> None:
    new = [row for row in predictions if row["pilot_batch"] == "expand_200"]
    if len(new) != 150:
        raise ValueError("blind listening requires exactly 150 held-out sources")
    random.Random(20042).shuffle(new)
    cards = []
    for index, row in enumerate(new, 1):
        primary = Path(row["acoustic"]["primary_clip"])
        if not primary.is_file() or primary.parent.resolve() != (out / "clips").resolve():
            raise ValueError(f"missing primary listening clip: {row['identifier']}")
        others = []
        for path_value in row["other_clips"]:
            path = Path(path_value)
            if not path.is_file() or path.parent.resolve() != (out / "clips").resolve():
                raise ValueError(f"missing optional clip: {row['identifier']}")
            others.append(f'<audio controls preload="none" src="clips/{html.escape(path.name)}"></audio>')
        options = lambda values: ''.join(f'<option value="{html.escape(value)}">{html.escape(value)}</option>'
                                         for value in values)
        cards.append(f'''<section class="card" data-id="{html.escape(row['identifier'])}">
<h2>{index}/150 · <code>{html.escape(row['identifier'])}</code></h2>
<audio controls preload="none" src="clips/{html.escape(primary.name)}"></audio>
<details><summary>Autres extraits à écouter en cas de doute</summary>{''.join(others) or 'Aucun'}</details>
<details><summary>Métadonnées Archive (à ouvrir après écoute si besoin)</summary>
<p>{html.escape(str(row['title'] or ''))} · {html.escape(str(row['creator'] or ''))} ·
{html.escape(str(row['collection'] or ''))} · {html.escape(str(row['genre_proxy'] or ''))}</p></details>
<label>Contenu du clip<select name="content_type"><option value=""></option>{options(sorted(CONTENT))}</select></label>
<label>Qualité du clip<select name="audio_quality"><option value=""></option>{options(sorted(QUALITY))}</select></label>
<label>Nature musicale du clip<select name="source_nature"><option value=""></option>{options(sorted(NATURE))}</select></label>
<label>Adéquation au clean pool<select name="pool_suitability"><option value=""></option>{options(sorted(SUITABILITY))}</select></label>
<label>Portée de l'écoute<select name="scope">{options(('primary_clip_only','multiple_excerpts','full_original'))}</select></label>
<label>Source entière, si plusieurs passages vérifiés<select name="source_level_label"><option value=""></option>{options(('promising','unsuitable','ambiguous'))}</select></label>
<label>Notes<input name="notes" type="text"></label></section>''')
    markup = '''<!doctype html><html lang="fr"><meta charset="utf-8"><title>IAMD validation aveugle 150</title>
<style>body{font:15px system-ui,sans-serif;max-width:950px;margin:auto;padding:1rem;background:#f5f6f8}
.card{background:#fff;border:1px solid #d5dbe2;border-radius:9px;padding:1rem;margin:1rem 0}
audio{display:block;width:430px;max-width:100%;margin:.5rem 0}label{display:inline-block;margin:.5rem;min-width:220px}
select,input{display:block;width:100%;padding:.4rem}button{padding:.7rem}header{position:sticky;top:0;background:#f5f6f8;padding:.5rem}</style>
<header><h1>IAMD · 150 nouvelles sources, écoute aveugle</h1><p>Le classement automatique est caché. Une appréciation positive du premier extrait ne valide pas la source entière. Contenu, qualité, nature et adéquation au clean pool sont séparés. « likely_real_recording » inclut une production électronique aboutie ; « likely_midi_or_synthetic_render » désigne les rendus rudimentaires, pas tout synthétiseur.</p><button id="export">Exporter CSV</button> <span id="count"></span></header>'''+''.join(cards)+'''<script>
const cards=[...document.querySelectorAll('.card')], key='iamd_phase2_200_blind_v1';
let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
function update(){let n=0;for(const card of cards){const id=card.dataset.id, values=saved[id]||{};
for(const input of card.querySelectorAll('select,input')) if(values[input.name]!==undefined)input.value=values[input.name];
if(values.content_type&&values.audio_quality&&values.source_nature&&values.pool_suitability)n++}
document.getElementById('count').textContent=n+'/150 clips annotés'}
for(const card of cards)for(const input of card.querySelectorAll('select,input'))input.addEventListener('change',()=>{
const id=card.dataset.id;saved[id]??={};saved[id][input.name]=input.value;localStorage.setItem(key,JSON.stringify(saved));update()});
update();document.getElementById('export').onclick=()=>{const fields=['identifier','content_type','audio_quality','source_nature','pool_suitability','scope','source_level_label','notes'];
const quote=x=>'"'+String(x??'').replaceAll('"','""')+'"';const lines=[fields.map(quote).join(',')];
for(const card of cards){const id=card.dataset.id,v=saved[id]||{};lines.push(fields.map(k=>quote(k==='identifier'?id:v[k]??(k==='scope'?'primary_clip_only':''))).join(','))}
const blob=new Blob([lines.join('\\r\\n')+'\\r\\n'],{type:'text/csv;charset=utf-8'});
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='iamd_phase2_150_blind_reviews.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
</script></html>'''
    (out / "listening_150_blind.html").write_text(markup, encoding="utf-8")


def parse_validation(out: Path, path: Path) -> list[dict]:
    known = {row["identifier"] for row in pilot_200_rows(out) if row["pilot_batch"] == "expand_200"}
    result = []
    seen = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"identifier", "content_type", "audio_quality", "source_nature", "pool_suitability",
                    "scope", "source_level_label", "notes"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError("blind review CSV missing required fields")
        for line_number, row in enumerate(reader, 2):
            identifier = row["identifier"].strip()
            if identifier not in known or identifier in seen:
                raise ValueError(f"unknown or duplicate held-out identifier on line {line_number}")
            seen.add(identifier)
            labels = [row[key].strip() for key in ("content_type", "audio_quality", "source_nature",
                                                   "pool_suitability")]
            if not any(labels):
                continue
            if (labels[0] not in CONTENT or labels[1] not in QUALITY
                    or labels[2] not in NATURE or labels[3] not in SUITABILITY):
                raise ValueError(f"incomplete/invalid review on line {line_number}")
            scope = row["scope"].strip() or "primary_clip_only"
            source_label = row["source_level_label"].strip()
            if scope not in SCOPES or source_label not in SOURCE_LABELS:
                raise ValueError(f"invalid scope/source label on line {line_number}")
            if scope == "primary_clip_only" and source_label:
                raise ValueError(f"source-level label from only one clip on line {line_number}")
            result.append({"identifier": identifier, "content_type": labels[0],
                           "audio_quality": labels[1], "source_nature": labels[2],
                           "pool_suitability": labels[3],
                           "scope": scope, "source_level_label": source_label,
                           "notes": row["notes"].strip()})
    return result


def evaluate(out: Path, predictions: list[dict], reviews_csv: Path | None = None) -> dict:
    new = [row for row in predictions if row["pilot_batch"] == "expand_200"]
    labels = {row["identifier"]: row for row in parse_validation(out, reviews_csv)} if reviews_csv else {}
    classes = collections.Counter(row["classification"] for row in new)
    rights_by_class = collections.defaultdict(collections.Counter)
    for row in new:
        rights_by_class[row["classification"]][row["rights_status"]] += 1
    joined = [(row, labels[row["identifier"]]) for row in new if row["identifier"] in labels]
    good = [(pred, human) for pred, human in joined
            if human["content_type"] == "music" and human["audio_quality"] == "acceptable"
            and human["source_nature"] == "likely_real_recording"
            and human["pool_suitability"] == "suitable"]
    bad = [(pred, human) for pred, human in joined
           if human["content_type"] in {"speech_dominant", "noise_or_sound_effect"}
           or human["audio_quality"] == "degraded"
           or human["source_nature"] == "likely_midi_or_synthetic_render"
           or human["pool_suitability"] == "unsuitable_style"]
    groups = {}
    for field in ("genre_proxy", "collection"):
        group = collections.defaultdict(lambda: {"selected": 0, "reviewed": 0, "clip_good": 0,
                                                 "clip_bad": 0, "accept_candidate": 0})
        for row in new:
            key = str(row.get(field) or "unknown")
            group[key]["selected"] += 1
            group[key]["accept_candidate"] += row["classification"] == "accept_candidate"
        for pred, human in joined:
            key = str(pred.get(field) or "unknown")
            group[key]["reviewed"] += 1
            group[key]["clip_good"] += (pred, human) in good
            group[key]["clip_bad"] += (pred, human) in bad
        for stats in group.values():
            stats["clip_good_fraction_among_reviewed"] = (
                stats["clip_good"] / stats["reviewed"] if stats["reviewed"] else None)
        groups[field] = dict(sorted(group.items(), key=lambda pair: (-pair[1]["selected"], pair[0])))
    false_rejects = [pred["identifier"] for pred, _ in good
                     if pred["classification"] == "reject_candidate"]
    false_accepts = [pred["identifier"] for pred, _ in bad
                     if pred["classification"] == "accept_candidate"]
    degraded = [(pred, human) for pred, human in joined if human["audio_quality"] == "degraded"]
    degraded_accepted = [pred["identifier"] for pred, _ in degraded
                         if pred["classification"] == "accept_candidate"]
    data = {
        "validation_total": 150, "validation_reviewed": len(joined),
        "validation_complete": len(joined) == 150,
        "prediction_counts_new_only": dict(classes),
        "rights_status_by_acoustic_class": {key: dict(value) for key, value in rights_by_class.items()},
        "clip_good_count": len(good), "clip_bad_count": len(bad),
        "potential_false_rejects_good_clip": false_rejects,
        "potential_false_reject_rate_among_reviewed_good_clips":
            len(false_rejects) / len(good) if good else None,
        "bad_clips_auto_accepted": false_accepts,
        "bad_clip_auto_accept_rate_among_reviewed_bad_clips":
            len(false_accepts) / len(bad) if bad else None,
        "degraded_clip_count": len(degraded),
        "degraded_clips_auto_accepted": degraded_accepted,
        "degraded_clip_auto_accept_rate": len(degraded_accepted) / len(degraded) if degraded else None,
        "good_clips_sent_to_review": [pred["identifier"] for pred, _ in good
                                      if pred["classification"] == "review"],
        "source_level_promising_checked_multiple": sum(human["source_level_label"] == "promising"
                                                       and human["scope"] != "primary_clip_only"
                                                       for _, human in joined),
        "by_group": groups,
        "rights_independent": "No candidate classification clears provenance or redistribution rights.",
        "limitations": [
            "The 150 held-out identifiers are stratified, not a simple random sample of IAMD.",
            "Human labels describe the listened clip unless multiple excerpts/full original are explicitly checked.",
            "Unreviewed or ambiguous clips are never assumed clean or bad.",
            "Collection/genre fractions use only reviewed clips and are not population yield estimates.",
        ],
        "conclusion": ("Hold-out listening incomplete: no reliability/clean-yield verdict."
                       if len(joined) < 150 else
                       "Hold-out complete: inspect errors and review load before deciding GO/NO-GO; "
                       "one excerpt never certifies a whole source."),
    }
    write_json(out / "pilot_200_validation_report.json", data)
    lines = ["# IAMD · 200 sources : validation indépendante", "",
             f"Nouvelles sources : 150 ; clips annotés : {len(joined)}/150.",
             f"Prédictions gelées : {dict(classes)}.",
             f"Clips bons / problématiques parmi les annotations : {len(good)} / {len(bad)}.",
             f"Bons clips proposés au rejet : {len(data['potential_false_rejects_good_clip'])}.",
             f"Mauvais clips proposés à l'acceptation : {len(data['bad_clips_auto_accepted'])}.",
             f"Dont clips à qualité dégradée proposés à l'acceptation : {len(degraded_accepted)}.",
             f"Bons clips envoyés en revue : {len(data['good_clips_sent_to_review'])}.",
             "", data["conclusion"], "",
             "Les chiffres de clips n'établissent pas le rendement clean de sources entières ; "
             "les droits et la provenance sont contrôlés séparément."]
    (out / "pilot_200_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reviews-csv", type=Path, help="Export from blind listening HTML, never calibration labels")
    args = parser.parse_args()
    result = build_locked(args.out)
    write_prediction_csv(args.out, result["predictions"])
    write_blind_listening(args.out, result["predictions"])
    report = evaluate(args.out, result["predictions"], args.reviews_csv)
    print(json.dumps({"predictions_newly_locked": not result["locked"],
                      "classes": report["prediction_counts_new_only"],
                      "validation_reviewed": report["validation_reviewed"],
                      "listening_html": str(args.out / "listening_150_blind.html")}, indent=2))


if __name__ == "__main__":
    main()
