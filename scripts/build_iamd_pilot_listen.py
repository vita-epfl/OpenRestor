#!/usr/bin/env python3
"""Build a private IAMD pilot listening page and complete annotation template."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


ANNOTATION_FIELDS = ["segment_id", "clean_quality", "content", "instruments",
                     "use_global_eq", "use_denoising", "use_brass", "use_drums",
                     "defects", "rejection_reasons", "notes"]
CONTEXT_FIELDS = ["segment_id", "clip_path", "identifier", "name", "creator",
                  "collection", "start_s", "duration_s", "license_url"]


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            yield row


def _judgment_for_segment(segment: dict, judgments: list[dict]) -> tuple[dict | None, dict | None]:
    """Match a pilot segment to an optional common-pipeline judgment.

    The Phase 1b segment IDs are local short IDs, while the common curation
    manifest uses ``<source_key>#pN``.  The verified track hash is stable in
    both artifacts, so matching by the ``--<track_id>`` suffix avoids guessing
    from titles or creators.
    """
    track_id = str(segment.get("track_id") or "")
    passage = str(segment.get("segment_id") or "").rsplit("-", 1)[-1]
    source = next((row for row in judgments
                   if str(row.get("source_id") or "").endswith(f"--{track_id}")), None)
    if source is None:
        return None, None
    passage_row = next((row for row in source.get("segments", [])
                        if str(row.get("segment_id") or "").endswith(f"#{passage}")), None)
    return source, passage_row


def build(pilot_dir: Path, html_out: Path, csv_out: Path, judgments_path: Path | None = None) -> dict:
    segments = list(read_jsonl(pilot_dir / "segments.jsonl"))
    scores = {row["segment_id"]: row for row in read_jsonl(pilot_dir / "scores.jsonl")}
    judgments = list(read_jsonl(judgments_path)) if judgments_path else []
    if len({row.get("segment_id") for row in segments}) != len(segments):
        raise ValueError("duplicate segment_id in segments.jsonl")
    rows = []
    for segment in sorted(segments, key=lambda row: row["segment_id"]):
        score = scores.get(segment["segment_id"], {})
        rows.append({"segment": segment, "score": score})
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CONTEXT_FIELDS + ANNOTATION_FIELDS[1:])
        writer.writeheader()
        for row in rows:
            segment = row["segment"]
            writer.writerow({field: segment.get(field, "") for field in CONTEXT_FIELDS})
    cards = []
    for row in rows:
        segment, score = row["segment"], row["score"]
        sid = html.escape(str(segment["segment_id"]))
        clip = html.escape(str(segment["clip_path"]))
        source_judgment, passage_judgment = _judgment_for_segment(segment, judgments)
        machine = ""
        if source_judgment is not None:
            source_decision = html.escape(str(source_judgment.get("pipeline_decision") or "n/a"))
            source_score = html.escape(str(source_judgment.get("pipeline_clean_score") or "n/a"))
            source_reasons = html.escape(", ".join(source_judgment.get("pipeline_reasons") or []) or "-")
            passage_decision = html.escape(str((passage_judgment or {}).get("decision") or "n/a"))
            passage_score = html.escape(str((passage_judgment or {}).get("clean_score") or "n/a"))
            passage_reasons = html.escape(", ".join((passage_judgment or {}).get("reasons") or []) or "-")
            machine = (f'<aside class="machine"><b>Pipeline v2.1 (signal machine)</b> · '
                       f'source={source_decision} · score={source_score} · motifs={source_reasons}<br>'
                       f'passage={passage_decision} · score={passage_score} · motifs={passage_reasons}'
                       '</aside>')
        cards.append(f"""<article class="card" data-id="{sid}">
<h2>{sid}</h2>
<p>{html.escape(str(segment.get('creator') or ''))} · {html.escape(str(segment.get('name') or ''))} · {html.escape(str(segment.get('collection') or ''))}</p>
<audio controls preload="none" src="{clip}"></audio>
{machine}
<dl><dt>PQ</dt><dd>{score.get('audiobox_pq', 'n/a')}</dd><dt>Bandwidth</dt><dd>{score.get('bandwidth_hz', 'n/a')} Hz</dd><dt>Clipping</dt><dd>{score.get('clipped_sample_ratio', 'n/a')}</dd><dt>Noise floor</dt><dd>{score.get('noise_floor_db', 'n/a')} dB</dd></dl>
<label>Qualité <select data-field="clean_quality"><option value=""></option><option>acceptable</option><option>degraded</option><option>uncertain</option></select></label>
<label>Contenu <select data-field="content"><option value=""></option><option>recorded_instruments</option><option>synthetic</option><option>mixed</option><option>noise_experimental</option><option>other</option></select></label>
<label>Instruments <input data-field="instruments"></label>
<label>Défauts <input data-field="defects"></label>
<label>Motifs de rejet <input data-field="rejection_reasons"></label>
<label>Notes <textarea data-field="notes"></textarea></label>
</article>""")
    page = """<!doctype html><meta charset="utf-8"><title>IAMD private pilot listening</title>
<style>body{font:16px sans-serif;max-width:1100px;margin:2rem auto}.card{border:1px solid #bbb;border-radius:8px;padding:1rem;margin:1rem 0}.card audio{width:100%}.machine{background:#eef5ff;border-left:4px solid #4676b9;padding:.6rem;margin:.6rem 0;font-size:.92rem}label{display:block;margin:.5rem 0}input,textarea,select{min-width:30%;margin-left:.5rem}dl{display:flex;gap:1rem;flex-wrap:wrap}dt{font-weight:bold}dd{margin:0 1rem 0 0}</style>
<h1>IAMD Phase 1b — écoute privée</h1><p>Les métriques et le jugement pipeline sont des signaux machine, pas des labels humains. Les champs humains restent séparés.</p>
<button id="export">Exporter CSV</button><button id="clear">Effacer les annotations locales</button>
__CARDS__
<script>
const key='openrestor-iamd-phase1b-v1'; let saved={}; try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
for(const card of document.querySelectorAll('.card')){const id=card.dataset.id;for(const el of card.querySelectorAll('[data-field]')){const f=el.dataset.field;el.value=(saved[id]||{})[f]||'';el.oninput=()=>{saved[id]??={};saved[id][f]=el.value;localStorage.setItem(key,JSON.stringify(saved))}}}
document.getElementById('clear').onclick=()=>{localStorage.removeItem(key);location.reload()};
document.getElementById('export').onclick=()=>{const fields=__FIELDS__;const q=x=>'"'+String(x??'').replaceAll('"','""')+'"';const lines=[fields.map(q).join(',')];for(const card of document.querySelectorAll('.card')){const id=card.dataset.id,v=saved[id]||{};lines.push(fields.map(f=>q(f==='segment_id'?id:v[f]||'')).join(','))}const blob=new Blob([lines.join('\\r\\n')+'\\r\\n'],{type:'text/csv'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='iamd_phase1b_annotations.csv';a.click()};
</script>""".replace("__CARDS__", "\n".join(cards)).replace("__FIELDS__", json.dumps(ANNOTATION_FIELDS))
    html_out.parent.mkdir(parents=True, exist_ok=True)
    html_out.write_text(page, encoding="utf-8")
    return {"segments": len(rows), "html": str(html_out), "csv": str(csv_out), "human_labels_prefilled": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--judgments", type=Path,
                        help="Optional common-pipeline judgment JSONL to display; never fills human labels")
    args = parser.parse_args()
    print(json.dumps(build(args.pilot_dir, args.html, args.csv, args.judgments),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
