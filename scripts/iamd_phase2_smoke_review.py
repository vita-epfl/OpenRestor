#!/usr/bin/env python3
"""Create private listening and annotation files for the 50-item IAMD smoke pilot."""

from __future__ import annotations

import argparse
import collections
import csv
import html
import json
import math
import statistics
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.iamd_phase2_pilot import (DEFAULT_OUT, parse_reviews, read_jsonl, smoke_rows,
                                       write_json, write_jsonl)  # noqa: E402


def median(values):
    numbers = [float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(value)]
    return statistics.median(numbers) if numbers else None


def percentile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    left = math.floor(position)
    right = math.ceil(position)
    return sorted_values[left] + (sorted_values[right] - sorted_values[left]) * (position - left)


def rights_status(row: dict) -> str:
    if row["archive_licence_category"] == "contradictory":
        return "archive_licence_conflict"
    if row["archive_licence_category"] != "compatible":
        return "archive_licence_unknown"
    if not row["provenance_candidate"]:
        return "provenance_unvalidated"
    return "metadata_plausible_not_rights_cleared"


def metrics(score: dict) -> dict:
    excerpts = score.get("excerpts") or []
    excerpt_pq = [part["audiobox_axes"]["PQ"] for part in excerpts
                  if isinstance((part.get("audiobox_axes") or {}).get("PQ"), (int, float))]
    return {"audiobox_pq": score.get("audiobox_pq"),
            "audiobox_ce": score.get("audiobox_axes", {}).get("CE"),
            "audiobox_cu": score.get("audiobox_axes", {}).get("CU"),
            "audiobox_pc": score.get("audiobox_axes", {}).get("PC"),
            "audiobox_pq_excerpt_min": min(excerpt_pq) if excerpt_pq else None,
            "audiobox_pq_excerpt_median": median(excerpt_pq),
            "audiobox_pq_excerpt_max": max(excerpt_pq) if excerpt_pq else None,
            "sample_rate": score.get("sample_rate"),
            "detected_format": score.get("detected_format"),
            "format_matches": score.get("format_matches"),
            "duration_s": score.get("duration_s"),
            "near_silent_sample_ratio": median(part.get("near_silent_sample_ratio") for part in excerpts),
            "clipped_sample_ratio_channels": median(part.get("clipped_sample_ratio_channels") for part in excerpts),
            "bandwidth_hz": median(part.get("bandwidth_hz") for part in excerpts),
            "rms_dbfs": median(part.get("rms_dbfs") for part in excerpts),
            "peak_dbfs": median(part.get("peak_dbfs") for part in excerpts),
            "noise_floor_db": median(part.get("noise_floor_db") for part in excerpts),
            "crest_factor_db": median(part.get("crest_factor_db") for part in excerpts),
            "spectral_flatness": median(part.get("spectral_flatness") for part in excerpts),
            "high_frequency_share": median(part.get("high_frequency_share") for part in excerpts),
            "excerpt_count": len(excerpts)}


def suggestions(row: dict, queue: dict, score: dict, pq_cutoff: float | None) -> list[str]:
    result = []
    cues = queue.get("metadata_cues") or {}
    if cues.get("speech_cues"):
        result.append("metadata_speech_cue_review")
    if cues.get("sound_effect_cues"):
        result.append("metadata_sound_effect_cue_review")
    if cues.get("synthetic_render_cues"):
        result.append("metadata_midi_sequence_cue_review")
    if cues.get("capture_context_cues"):
        result.append("metadata_capture_context_review")
    if cues.get("stylized_content_cues"):
        result.append("metadata_stylized_content_review")
    if rights_status(row) != "metadata_plausible_not_rights_cleared":
        result.append("rights_or_provenance_review")
    if score.get("status") != "measured":
        if score.get("status") not in (None, "original_not_present"):
            result.append("measurement_failed_review")
        return result
    m = metrics(score)
    if m["format_matches"] is False:
        result.append("actual_format_mismatch")
    if m["sample_rate"] is not None and m["sample_rate"] < 32000:
        result.append("low_sample_rate_review")
    if (m["near_silent_sample_ratio"] is not None and m["rms_dbfs"] is not None
            and m["near_silent_sample_ratio"] > .85 and m["rms_dbfs"] < -30):
        result.append("quasi_silence_review")
    if m["clipped_sample_ratio_channels"] is not None and m["clipped_sample_ratio_channels"] > .005:
        result.append("clipping_review")
    if (m["bandwidth_hz"] is not None and m["sample_rate"] is not None
            and m["sample_rate"] >= 44100 and m["bandwidth_hz"] < 12000):
        result.append("bandwidth_cutoff_review")
    if pq_cutoff is not None and m["audiobox_pq"] is not None and m["audiobox_pq"] <= pq_cutoff:
        result.append("pq_bottom_quintile_review")
    return result


def smoke_rows_with_scores(out: Path) -> tuple[list[dict], dict]:
    selected = smoke_rows(out)
    scores_path = out / "scores.jsonl"
    scores = {row["identifier"]: row for row in read_jsonl(scores_path)} if scores_path.exists() else {}
    queue = {row["identifier"]: row for row in read_jsonl(out / "metadata_review_queue.jsonl")}
    status_path = out / "download_status.jsonl"
    downloads = {row["identifier"]: row for row in read_jsonl(status_path)} if status_path.exists() else {}
    probe_path = out / "ast_content_probe.jsonl"
    probes = {row["identifier"]: row for row in read_jsonl(probe_path)} if probe_path.exists() else {}
    feedback_path = out / "manual_feedback_partial.jsonl"
    feedback = {row["identifier"]: row for row in read_jsonl(feedback_path)} if feedback_path.exists() else {}
    pq_values = sorted(float(scores[row["identifier"]]["audiobox_pq"]) for row in selected
                       if row["identifier"] in scores and scores[row["identifier"]].get("audiobox_status") == "measured"
                       and isinstance(scores[row["identifier"]].get("audiobox_pq"), (int, float)))
    # A relative bottom-quintile marker is meaningful only after every source has PQ.
    pq_cutoff = pq_values[math.ceil(.2 * len(pq_values)) - 1] if len(pq_values) == 50 else None
    output = []
    for row in selected:
        score = scores.get(row["identifier"], {})
        q = queue.get(row["identifier"], {})
        parts = score.get("excerpts") or []
        output.append({"identifier": row["identifier"], "title": row["title"], "creator": row["creator"],
                       "collection": row["collection"], "genre_proxy": row["genre_proxy"],
                       "source_filename": row["name"], "source_format_declared": row["format"],
                       "source_path": row["local_original_path"], "archive_file_url": row["archive_file_url"],
                       "source_status": row["source"], "source_sha1": row.get("sha1"),
                       "source_md5": row.get("md5"), "source_size_bytes": row["size_bytes_metadata"],
                       "license_url": row["archive_license_url"],
                       "archive_licence_category": row["archive_licence_category"],
                       "provenance_candidate": row["provenance_candidate"],
                       "redistributable_candidate_metadata_only": row["redistributable_candidate"],
                       "rights_status": rights_status(row),
                       "download_status": downloads.get(row["identifier"], {}).get("status", "not_attempted"),
                       "measurement_status": score.get("status", "not_measured"),
                       "content_probe": probes.get(row["identifier"]),
                       "partial_user_feedback": feedback.get(row["identifier"]),
                       "metadata_cues": q.get("metadata_cues") or {},
                       "source_nature_metadata_hint": q.get("source_nature_metadata_hint"),
                       "content_metadata_hint": q.get("content_metadata_hint"),
                       "metrics": metrics(score),
                       "audiobox_pq_method": score.get("audiobox_pq_method"),
                       "excerpt_measurements": parts,
                       "excerpts": [{"path": part["clip_path"], "start_s": part["start_s"],
                                     "duration_s": part["duration_s"], "audiobox_pq": part.get("audiobox_pq")}
                                    for part in parts],
                       "suggested_reasons": suggestions(row, q, score, pq_cutoff)})
    return output, {"pq_bottom_quintile_cutoff": pq_cutoff, "pq_values": pq_values}


def write_csv(out: Path, rows: list[dict]) -> None:
    fields = ("identifier", "title", "creator", "collection", "genre_proxy", "source_format_declared",
              "source_filename", "source_path", "source_status", "source_sha1", "source_md5",
              "source_size_bytes", "archive_file_url", "license_url", "archive_licence_category",
              "provenance_candidate", "redistributable_candidate_metadata_only", "rights_status",
              "download_status", "measurement_status", "audiobox_ce", "audiobox_cu",
              "audiobox_pc", "audiobox_pq", "audiobox_pq_excerpt_min",
              "audiobox_pq_excerpt_median", "audiobox_pq_excerpt_max", "sample_rate", "duration_s",
              "near_silent_sample_ratio", "clipped_sample_ratio_channels", "bandwidth_hz",
              "ast_music_score", "ast_speech_score", "ast_top_labels",
              "user_observation", "provisional_content_type", "provisional_audio_quality", "pool_suitability",
              "suggested_reasons", "excerpt_1", "excerpt_2", "excerpt_3")
    with (out / "listening.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {key: row.get(key) for key in fields}
            flat.update({key: row["metrics"].get(key) for key in row["metrics"] if key in fields})
            probe = row.get("content_probe") or {}
            if probe.get("status") == "scored":
                flat["ast_music_score"] = probe.get("interest_labels", {}).get("Music")
                flat["ast_speech_score"] = probe.get("interest_labels", {}).get("Speech")
                flat["ast_top_labels"] = ";".join(label["label"] for label in probe.get("top_labels", [])[:5])
            for field in ("user_observation", "provisional_content_type", "provisional_audio_quality", "pool_suitability"):
                flat[field] = (row.get("partial_user_feedback") or {}).get(field)
            flat["suggested_reasons"] = ";".join(row["suggested_reasons"])
            for index, part in enumerate(row["excerpts"][:3], 1):
                flat[f"excerpt_{index}"] = part["path"]
            writer.writerow(flat)


def write_html(out: Path, rows: list[dict]) -> None:
    esc = lambda value: html.escape(str(value if value is not None else ""), quote=True)
    cards = []
    for row in rows:
        clips = []
        for index, part in enumerate(row["excerpts"], 1):
            relative = Path(part["path"]).relative_to(out).as_posix()
            clips.append(f'<div class="clip">Extrait {index} · {part["start_s"]:.0f} s'
                         f'<audio controls preload="none" src="{esc(relative)}"></audio></div>')
        m = row["metrics"]
        score_text = ' · '.join(f'{axis} {m[key]:.2f}' for axis, key in
                                (("CE", "audiobox_ce"), ("CU", "audiobox_cu"),
                                 ("PC", "audiobox_pc"), ("PQ", "audiobox_pq"))
                                if m[key] is not None) or "Audiobox en attente"
        score_text += f' · {m["sample_rate"] or "?"} Hz · cutoff proxy {m["bandwidth_hz"]:.0f} Hz' if m["bandwidth_hz"] is not None else ""
        score_text += f' · clipping {100*m["clipped_sample_ratio_channels"]:.2f} %' if m["clipped_sample_ratio_channels"] is not None else ""
        if m["audiobox_pq_excerpt_min"] is not None:
            score_text += (f' · PQ extraits {m["audiobox_pq_excerpt_min"]:.2f}/'
                           f'{m["audiobox_pq_excerpt_median"]:.2f}/'
                           f'{m["audiobox_pq_excerpt_max"]:.2f} (min/méd/max)')
        probe = row.get("content_probe") or {}
        if probe.get("status") == "scored":
            interest = probe.get("interest_labels") or {}
            if interest.get("Music") is not None:
                score_text += f' · AST Music {interest["Music"]:.2f}'
            if interest.get("Speech") is not None:
                score_text += f' · AST Speech {interest["Speech"]:.2f}'
        probe_text = ('AST (indices non calibrés) : ' + ', '.join(
            f'{part["label"]} {part["score"]:.2f}' for part in probe.get("top_labels", [])[:3])
            if probe.get("status") == "scored" else 'AST non mesuré')
        feedback_text = (f'<p class="feedback">Retour partiel : {esc(row["partial_user_feedback"].get("user_observation"))}</p>'
                         if row.get("partial_user_feedback") else '')
        license_value = row["license_url"]
        license_link = (f'<a href="{esc(license_value)}">licence déclarée</a>'
                        if isinstance(license_value, str) and urllib.parse.urlparse(license_value).scheme in {"https", "http"}
                        else esc(license_value or "licence non documentée"))
        archive_details_url = "https://archive.org/details/" + urllib.parse.quote(row["identifier"], safe="")
        options = lambda values: '<option value="">À qualifier</option>' + ''.join(
            f'<option value="{esc(value)}">{esc(value)}</option>' for value in values)
        cards.append(f'''<article class="card" data-id="{esc(row["identifier"])}">
<h2>{esc(row["creator"])} — {esc(row["title"] or row["identifier"])}</h2>
<p class="small"><code>{esc(row["identifier"])}</code> · {esc(row["collection"])} · {esc(row["genre_proxy"])} · {esc(row["source_format_declared"])}</p>
<p class="small">{esc(score_text)} · <a href="{esc(archive_details_url)}">fiche Archive</a> · {license_link}</p>
<p class="small">{esc(probe_text)}</p>
{feedback_text}
<p class="rights">Droits : {esc(row["rights_status"])} · Mesure : {esc(row["measurement_status"])}</p>
<p>À vérifier (propositions seulement) : <strong>{esc('; '.join(row["suggested_reasons"]) or 'aucun signal simple')}</strong></p>
<div class="clips">{''.join(clips) or '<em>Extraits indisponibles</em>'}</div>
<div class="axes"><label>Contenu<select data-field="content_type">{options(('music','speech_dominant','noise_or_sound_effect','ambiguous'))}</select></label>
<label>Qualité<select data-field="audio_quality">{options(('acceptable','degraded','ambiguous'))}</select></label>
<label>Nature<select data-field="source_nature">{options(('likely_real_recording','likely_midi_or_synthetic_render','ambiguous'))}</select></label></div>
<label>Flags qualité, séparés par ;<input data-field="quality_flags" placeholder="silence_or_quasi_silence;excessive_clipping;..." /></label>
<label>Motifs suggérés, modifiables<input data-field="proposed_reasons" value="{esc(';'.join(row['suggested_reasons']))}" /></label>
<label>Autre défaut<input data-field="other_quality_issue" /></label>
<label>Notes<input data-field="notes" /></label>
</article>''')
    markup = '''<!doctype html><html lang="fr"><meta charset="utf-8"><title>IAMD Phase 2 — écoute 50</title>
<style>body{font:15px system-ui,sans-serif;max-width:1100px;margin:auto;padding:1rem;background:#f5f6f8;color:#1e252b}
.card{background:white;border:1px solid #dce1e5;border-radius:12px;margin:1rem 0;padding:1rem}h2{font-size:1.1rem;margin:.2rem 0}
.small{font-size:.85rem;color:#52606b}.rights{color:#8a3f00}.feedback{color:#123c64;background:#eef6ff;padding:.5rem}.clips,.axes{display:flex;flex-wrap:wrap;gap:.7rem;margin:1rem 0}
.clip{min-width:240px}audio{display:block;width:290px;max-width:100%}label{display:block;flex:1;min-width:200px;font-size:.86rem}
input,select{box-sizing:border-box;display:block;width:100%;padding:.45rem;margin:.3rem 0 .8rem;border:1px solid #aab4be;border-radius:5px}
button{padding:.7rem 1rem;cursor:pointer}header{position:sticky;top:0;background:#f5f6f8;padding:.7rem 0;border-bottom:1px solid #ccd}
</style><header><h1>IAMD — 50 originaux à qualifier</h1><p>Trois axes indépendants. Les indices automatiques ne rejettent rien.
Le navigateur peut garder les réponses localement ; exporte régulièrement le CSV pour les conserver.</p>
<label>Nom de la personne qui annote<input id="reviewer" placeholder="Nom / initiales"></label>
<button id="export">Exporter les annotations CSV</button> <span id="count"></span></header><main>'''
    markup += "\n".join(cards)
    markup += '''</main><script>
const fields=['content_type','audio_quality','source_nature','quality_flags','proposed_reasons','other_quality_issue','notes'];
const cards=[...document.querySelectorAll('.card')];
let saved={};try{saved=JSON.parse(localStorage.getItem('iamd_phase2_smoke_reviews')||'{}');}catch(error){}
for(const card of cards){const id=card.dataset.id;for(const field of fields){const el=card.querySelector('[data-field="'+field+'"]');
if(saved[id]&&Object.hasOwn(saved[id],field))el.value=saved[id][field];el.addEventListener('input',()=>{saved[id]??={};saved[id][field]=el.value;
try{localStorage.setItem('iamd_phase2_smoke_reviews',JSON.stringify(saved));}catch(error){}update();});}}
function update(){let n=cards.filter(c=>['content_type','audio_quality','source_nature'].every(f=>c.querySelector('[data-field="'+f+'"]')?.value)).length;
document.getElementById('count').textContent=n+'/'+cards.length+' annotations complètes';}update();
function cell(value){return '"'+String(value??'').replaceAll('"','""')+'"';}
document.getElementById('export').onclick=()=>{const reviewer=document.getElementById('reviewer').value.trim();
const header=['identifier','content_type','audio_quality','source_nature','quality_flags','proposed_reasons','other_quality_issue','reviewer','review_date','notes'];
const lines=[header.map(cell).join(',')];let partial=0;
for(const card of cards){const id=card.dataset.id;const r=Object.fromEntries(fields.map(f=>[f,card.querySelector('[data-field="'+f+'"]').value.trim()]));
const axes=['content_type','audio_quality','source_nature'];if(axes.some(f=>r[f])&&!axes.every(f=>r[f])){partial++;continue;}
if(!axes.every(f=>r[f]))continue;const record={identifier:id,...r,reviewer,review_date:new Date().toISOString().slice(0,10)};
lines.push(header.map(f=>cell(record[f])).join(','));}
if(partial)alert(partial+' annotations partielles ignorées : compléter les trois axes.');
const blob=new Blob(['\\ufeff'+lines.join('\\r\\n')+'\\r\\n'],{type:'text/csv;charset=utf-8'});
const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='iamd_phase2_smoke_reviews.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
</script></html>'''
    (out / "listening.html").write_text(markup, encoding="utf-8")


def build(out: Path, reviews_csv: Path | None = None) -> dict:
    rows, pq = smoke_rows_with_scores(out)
    reviews = parse_reviews(out, reviews_csv) if reviews_csv else {}
    for row in rows:
        row["human_review"] = reviews.get(row["identifier"])
    write_jsonl(out / "smoke_measurements.jsonl", rows)
    write_csv(out, rows)
    write_html(out, rows)
    downloads = collections.Counter(row["download_status"] for row in rows)
    measured = [row for row in rows if row["measurement_status"] == "measured"]
    reasons = collections.Counter(reason for row in rows for reason in row["suggested_reasons"])
    rights = collections.Counter(row["rights_status"] for row in rows)
    reviewed = [row for row in rows if row["human_review"]]
    definite_clean = [row for row in reviewed
                      if row["human_review"]["content_type"] == "music"
                      and row["human_review"]["audio_quality"] == "acceptable"
                      and row["human_review"]["source_nature"] == "likely_real_recording"
                      and row["metrics"]["format_matches"] is True]
    human_reasons = collections.Counter()
    edited_review_reasons = collections.Counter()
    for row in reviewed:
        review = row["human_review"]
        for field, good in (("content_type", "music"), ("audio_quality", "acceptable"),
                            ("source_nature", "likely_real_recording")):
            if review[field] != good:
                human_reasons[f"{field}:{review[field]}"] += 1
        for flag in review["quality_flags"]:
            human_reasons[f"quality_flag:{flag}"] += 1
        for reason in (review.get("proposed_reasons") or "").split(";"):
            if reason.strip():
                edited_review_reasons[reason.strip()] += 1
    by_collection = collections.defaultdict(lambda: {"sources": 0, "sources_with_review_signals": 0,
                                                       "signal_count": 0, "human_reviewed": 0,
                                                       "human_not_definite_clean": 0})
    by_creator = collections.defaultdict(lambda: {"sources": 0, "sources_with_review_signals": 0,
                                                    "signal_count": 0, "human_reviewed": 0,
                                                    "human_not_definite_clean": 0})
    definite_clean_ids = {row["identifier"] for row in definite_clean}
    for row in rows:
        audio_reasons = [reason for reason in row["suggested_reasons"] if reason != "rights_or_provenance_review"]
        for counter, key in ((by_collection, row["collection"]), (by_creator, row["creator"])):
            counter[key]["sources"] += 1
            counter[key]["sources_with_review_signals"] += bool(audio_reasons)
            counter[key]["signal_count"] += len(audio_reasons)
            if row["human_review"]:
                counter[key]["human_reviewed"] += 1
                counter[key]["human_not_definite_clean"] += row["identifier"] not in definite_clean_ids
    collection_priorities = sorted(({"collection": name, **stats} for name, stats in by_collection.items()
                                    if stats["sources"] >= 2),
                                   key=lambda item: (-item["sources_with_review_signals"] / item["sources"],
                                                     -item["sources"], item["collection"]))
    creator_leads = sorted(({"creator": name, **stats} for name, stats in by_creator.items()
                            if stats["sources_with_review_signals"]),
                           key=lambda item: (-item["signal_count"], item["creator"]))
    pq_values = pq["pq_values"]
    probe_scored = [row for row in rows if (row.get("content_probe") or {}).get("status") == "scored"]
    excerpts_scored = sum(bool(part.get("audiobox_axes")) for row in rows for part in row["excerpt_measurements"])
    axis_values = {axis: sorted(row["metrics"][f"audiobox_{axis.lower()}"] for row in rows
                                if row["metrics"][f"audiobox_{axis.lower()}"] is not None)
                   for axis in ("CE", "CU", "PC", "PQ")}
    summary = {"selected": 50, "verified_originals": downloads["verified"],
               "verified_original_bytes": sum(row["source_size_bytes"] for row in rows
                                              if row["download_status"] == "verified"),
               "download_statuses": dict(downloads), "measured_sources": len(measured),
               "excerpt_count": sum(len(row["excerpts"]) for row in rows),
               "excerpts_with_all_audiobox_axes": excerpts_scored,
               "measured_duration_hours": sum(row["metrics"]["duration_s"] or 0 for row in measured) / 3600,
               "original_formats": dict(collections.Counter(row["source_format_declared"] for row in rows)),
               "sample_rates_hz": dict(collections.Counter(row["metrics"]["sample_rate"] for row in measured)),
               "unique_collections": len({row["collection"] for row in rows}),
               "unique_creators": len({row["creator"] for row in rows}),
               "sources_with_pq": len(pq_values),
               "sources_with_ast_content_probe": len(probe_scored),
               "sources_with_partial_user_feedback": sum(bool(row.get("partial_user_feedback")) for row in rows),
               "audiobox_axes_distribution": {
                   axis: {"count": len(values), "min": min(values) if values else None,
                          "median": median(values), "max": max(values) if values else None}
                   for axis, values in axis_values.items()},
               "pq_distribution": {"min": min(pq_values) if pq_values else None,
                                   "p10": percentile(pq_values, .1), "p25": percentile(pq_values, .25),
                                   "median": median(pq_values), "p75": percentile(pq_values, .75),
                                   "p90": percentile(pq_values, .9),
                                   "max": max(pq_values) if pq_values else None,
                                   "bottom_quintile_cutoff": pq["pq_bottom_quintile_cutoff"]},
               "rights_statuses": dict(rights),
               "suggested_review_reasons_nonexclusive": dict(reasons),
               "suggested_review_rates_nonexclusive": {key: value / 50 for key, value in reasons.items()},
               "human_reviews_complete": len(reviewed),
               "human_definite_clean_count": len(definite_clean),
               "human_rejection_or_ambiguity_reasons_nonexclusive": dict(human_reasons),
               "human_edited_review_reasons_nonexclusive": dict(edited_review_reasons),
               "collection_review_priorities_min_2_sources": collection_priorities,
               "collection_human_review_min_2_sources": sorted(
                   ({"collection": name, **stats} for name, stats in by_collection.items()
                    if stats["sources"] >= 2 and stats["human_reviewed"]),
                   key=lambda item: (-item["human_not_definite_clean"] / item["human_reviewed"],
                                     -item["human_reviewed"], item["collection"])),
               "creator_human_review_min_2_sources": sorted(
                   ({"creator": name, **stats} for name, stats in by_creator.items()
                    if stats["sources"] >= 2 and stats["human_reviewed"]),
                   key=lambda item: (-item["human_not_definite_clean"] / item["human_reviewed"],
                                     -item["human_reviewed"], item["creator"])),
               "creator_review_leads_not_patterns": creator_leads,
               "observed_technical_yield": downloads["verified"] / 50,
               "observed_audio_clean_yield": (len(definite_clean) / 50
                                              if len(reviewed) == len(measured) == len(pq_values) == downloads["verified"] == 50
                                              else None),
               "conclusion": "Descriptive for this 50-item lot only; no extrapolation to 200, 750 or the full IAMD pool.",
               "limitations": ["Suggestions are not rejections or ground truth.",
                               "One chosen original per identifier; other tracks are not checked.",
                               "Music, audio quality and source nature require separate listening labels.",
                               "Rights/provenance are distinct from acoustic quality.",
                               "Most creators occur only once in this smoke lot; no creator-level pattern can be inferred."]}
    write_json(out / "smoke_report.json", summary)
    lines = ["# IAMD Phase 2 — premier lot de 50", "",
             f"Originaux vérifiés : **{downloads['verified']}/50** ; sources mesurées : **{len(measured)}/50** ; PQ : **{len(pq_values)}/50**.",
             f"Sonde de contenu AudioSet (AST) : **{len(probe_scored)}/50** ; scores multi-étiquettes non calibrés, sans rejet automatique.",
             f"Audiobox sur les passages d'écoute : **{excerpts_scored}/{summary['excerpt_count']}**.",
             f"Volume téléchargé et vérifié : **{summary['verified_original_bytes']/1024**3:.2f} Gio** ; "
             f"durée réelle lue : **{summary['measured_duration_hours']:.2f} h**. "
             f"Formats : {summary['original_formats']}. "
             f"Diversité du lot : {summary['unique_collections']} collections, {summary['unique_creators']} créateurs déclarés.",
             f"Extraits d'écoute : **{summary['excerpt_count']}** (trois par source sauf piste trop courte).",
             "Rendement technique observé : " + f"{100*summary['observed_technical_yield']:.0f} % des fichiers sélectionnés. "
             "Ce n'est pas un rendement de musique clean.",
             (f"Rendement audio clean observé sur ce lot : **{len(definite_clean)}/50** après 50/50 annotations."
              if summary["observed_audio_clean_yield"] is not None else
              f"**Rendement audio clean non calculé** : {len(reviewed)}/50 annotations, "
              f"{len(measured)}/50 mesures, {len(pq_values)}/50 PQ, {downloads['verified']}/50 originaux vérifiés."),
             "Aucune extrapolation à 200, 750 ou 11 945.", "",
             "## À écouter et annoter", "",
             "Ouvrir `listening.html` dans un navigateur (fichiers locaux), choisir séparément contenu, qualité et nature, "
             "puis exporter le CSV. `listening.csv` et `smoke_measurements.jsonl` donnent les chemins et toutes les mesures.", "",
             "## Droits et indices", "",
             f"Statuts droits/provenance : {dict(rights)}. Aucune source n'est approuvée pour redistribution par ce pilot.",
             f"Propositions de revue, non exclusives : {dict(reasons)}.",
             f"Motifs humains observés, non exclusifs : {dict(human_reasons)}.",
             f"Motifs suggérés corrigés dans le CSV : {dict(edited_review_reasons)}.",
             f"PQ (min / p10 / médiane / p90 / max) : {summary['pq_distribution']['min']} / "
             f"{summary['pq_distribution']['p10']} / {summary['pq_distribution']['median']} / "
             f"{summary['pq_distribution']['p90']} / {summary['pq_distribution']['max']}.",
             f"Audiobox quatre axes (médianes CE/CU/PC/PQ) : "
             f"{[summary['audiobox_axes_distribution'][axis]['median'] for axis in ('CE','CU','PC','PQ')]}.",
             "Les seuils simples et le quintile PQ servent à prioriser l'écoute, pas à rejeter automatiquement.", "",
             "## Collections et créateurs", "",
             "Collections comptant au moins deux sources, classées par proportion d'indices à revoir :"]
    lines += [f"- {entry['collection']} : {entry['sources_with_review_signals']}/{entry['sources']} avec indice(s)."
              for entry in collection_priorities[:12]]
    if reviewed:
        lines += ["", "Après annotation humaine :"]
        lines += [f"- {entry['collection']} : {entry['human_not_definite_clean']}/{entry['human_reviewed']} "
                  "non retenus comme clean certain (effectif très faible)."
                  for entry in summary["collection_human_review_min_2_sources"][:12]]
    lines += ["", "Les créateurs n'ont presque jamais plusieurs sources dans ce premier lot : `smoke_report.json` "
              "donne des cas individuels à revoir, pas un classement fiable de créateurs.", ""]
    (out / "smoke_report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reviews-csv", type=Path)
    args = parser.parse_args()
    summary = build(args.out, args.reviews_csv)
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in {"creator_review_leads_not_patterns", "collection_review_priorities_min_2_sources"}},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
