#!/usr/bin/env python3
"""Build an offline HTML form for a private rights-review CSV.

The page contains catalogue evidence and editable review fields. It never loads
audio, sends network requests, or grants rights. The browser can save the
edited CSV locally; the normal fail-closed CSV importer validates it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path


EDITABLE_FIELDS = (
    "decision", "reviewer", "review_date", "verified_license_label",
    "verified_license_url", "verified_attribution", "evidence_url_override",
    "allow_commercial", "allow_redistribution", "allow_derivatives",
    "share_alike", "provenance_approved", "redistribution_approved",
    "source_status_verified", "verified_source_sha256", "reason",
)
SELECT_FIELDS = {
    "decision": ("", "pending", "approved", "rejected"),
    "allow_commercial": ("", "true", "false"),
    "allow_redistribution": ("", "true", "false"),
    "allow_derivatives": ("", "true", "false"),
    "share_alike": ("", "true", "false"),
    "provenance_approved": ("", "true", "false"),
    "redistribution_approved": ("", "true", "false"),
    "source_status_verified": ("", "original_verified", "ambiguous", "rejected"),
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        if not fields or "source_key" not in fields or "decision" not in fields:
            raise ValueError("CSV must contain source_key and decision columns")
        if "audio_path" in fields:
            raise ValueError("rights-review HTML must not contain audio_path")
        rows = [dict(row) for row in reader]
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("source_key") or "")
        if not key:
            raise ValueError("every CSV row needs source_key")
        if key in seen:
            raise ValueError(f"duplicate source_key: {key}")
        seen.add(key)
    return fields, rows


def _script_json(value: object) -> str:
    # Prevent a catalogue title from closing the script element.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _link(value: str, label: str) -> str:
    if not value:
        return '<span class="muted">unknown</span>'
    return (f'<a href="{html.escape(value, quote=True)}" target="_blank" '
            f'rel="noreferrer">{html.escape(label)}</a>')


def _editor(field: str) -> str:
    safe = html.escape(field, quote=True)
    if field in SELECT_FIELDS:
        options = SELECT_FIELDS[field]
        return (f'<select data-field="{safe}">' +
                "".join(f'<option value="{html.escape(value, quote=True)}">'
                        f'{html.escape(value or "—")}</option>' for value in options) +
                "</select>")
    if field == "reason":
        return f'<textarea data-field="{safe}"></textarea>'
    return f'<input data-field="{safe}">'


def build(input_csv: Path, html_out: Path) -> dict:
    fields, rows = _read_csv(input_csv)
    digest = hashlib.sha256("\n".join(row["source_key"] for row in rows).encode()).hexdigest()
    datasets = sorted({str(row.get("dataset") or "[unknown]") for row in rows}, key=str.casefold)
    cards = []
    for row in rows:
        key = str(row["source_key"])
        safe_key = html.escape(key, quote=True)
        title = html.escape(str(row.get("title") or key))
        dataset = html.escape(str(row.get("dataset") or "[unknown]"))
        evidence = _link(str(row.get("evidence_url") or ""), "catalogue evidence")
        archive = _link(str(row.get("archive_url") or ""), "archive file")
        member = _link(str(row.get("member_url") or ""), "member")
        editors = "".join(
            f'<label>{html.escape(field)} {_editor(field)}</label>'
            for field in EDITABLE_FIELDS
        )
        cards.append(
            f'<article class="card" data-key="{safe_key}" data-dataset="{dataset}">'
            f'<h2>{title}</h2><p class="key"><code>{safe_key}</code></p>'
            f'<p><b>Dataset:</b> {dataset} · '
            f'<b>Collection:</b> {html.escape(str(row.get("collection") or "[unknown]"))}<br>'
            f'<b>Creator:</b> {html.escape(str(row.get("creator") or "[unknown]"))} · '
            f'<b>Format:</b> {html.escape(str(row.get("original_format") or "[unknown]"))}<br>'
            f'<b>Source status:</b> {html.escape(str(row.get("source_status") or "[unknown]"))} · '
            f'<b>Licence:</b> {html.escape(str(row.get("license_label") or "[unknown]"))}<br>'
            f'{evidence} · {archive} · {member}</p>'
            f'<div class="editors">{editors}</div></article>'
        )
    page = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenRestor — revue privée des droits</title>
<style>
body{font:15px system-ui,sans-serif;max-width:1250px;margin:1.5rem auto;padding:0 1rem;color:#202124}
.toolbar{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:.8rem 0;z-index:2}
button,input,select,textarea{font:inherit}button{margin:.2rem .5rem .2rem 0;padding:.35rem .6rem}
#search{width:28rem;max-width:90%}.card{border:1px solid #bbb;border-radius:8px;padding:1rem;margin:1rem 0}
.card h2{font-size:1rem;margin:.1rem 0}.key{word-break:break-all}.muted{color:#666}
.editors{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.45rem}
label{display:flex;flex-direction:column;gap:.15rem}textarea{min-height:3rem}
.card[data-hidden="true"]{display:none}a{color:#0645ad}
</style></head><body>
<h1>OpenRestor — revue privée des droits</h1>
<p>Cette page est locale. Elle ne charge aucun audio et n’accorde aucun droit. Les champs vides restent non évalués.</p>
<div class="toolbar"><input id="search" placeholder="Rechercher un identifiant, titre, créateur…">
<select id="dataset"><option value="">Tous les datasets</option>__DATASETS__</select>
<select id="decision-filter"><option value="">Toutes les décisions</option><option value="__blank__">Non renseigné</option><option>pending</option><option>approved</option><option>rejected</option></select>
<button id="export">Télécharger le CSV</button><button id="clear">Effacer les annotations locales</button>
<span id="counter"></span></div><main>__CARDS__</main>
<script>
const fields=__FIELDS__, rows=__ROWS__, editable=__EDITABLE__, storageKey='openrestor-clean-rights-__DIGEST__';
let saved={}; try{saved=JSON.parse(localStorage.getItem(storageKey)||'{}')}catch(e){saved={}}
const cards=[...document.querySelectorAll('.card')];
function value(key,field){const row=rows.find(r=>r.source_key===key)||{};return saved[key]&&saved[key][field]!==undefined?saved[key][field]:row[field]||''}
for(const card of cards){const key=card.dataset.key;for(const el of card.querySelectorAll('[data-field]')){const field=el.dataset.field;el.value=value(key,field);el.addEventListener('input',()=>{saved[key]??={};saved[key][field]=el.value;localStorage.setItem(storageKey,JSON.stringify(saved));update()})}}
function update(){const q=document.getElementById('search').value.toLowerCase();const d=document.getElementById('dataset').value;const f=document.getElementById('decision-filter').value;let visible=0,done=0;for(const card of cards){const key=card.dataset.key;const row=rows.find(r=>r.source_key===key)||{};const decision=value(key,'decision');const hay=Object.values(row).join(' ').toLowerCase()+' '+key.toLowerCase();const ok=(!q||hay.includes(q))&&(!d||card.dataset.dataset===d)&&(!f||(f==='__blank__'?!decision:decision===f));card.dataset.hidden=String(!ok);if(ok)visible++;if(decision)done++}document.getElementById('counter').textContent=visible+' affichées · '+done+' décisions'}
document.getElementById('search').oninput=update;document.getElementById('dataset').onchange=update;document.getElementById('decision-filter').onchange=update;
document.getElementById('clear').onclick=()=>{if(confirm('Effacer les annotations locales de ce lot ?')){localStorage.removeItem(storageKey);location.reload()}};
function csv(v){return '"'+String(v??'').replaceAll('"','""')+'"'}
document.getElementById('export').onclick=()=>{const out=[fields.map(csv).join(',')];for(const row of rows){const values={...row,...(saved[row.source_key]||{})};out.push(fields.map(f=>csv(values[f]||'')).join(','))}const blob=new Blob([out.join('\\r\\n')+'\\r\\n'],{type:'text/csv;charset=utf-8'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='clean_rights_review_completed.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
update();
</script></body></html>"""
    page = page.replace("__DATASETS__", "".join(
        f'<option>{html.escape(dataset)}</option>' for dataset in datasets
    ))
    page = page.replace("__CARDS__", "\n".join(cards))
    page = page.replace("__FIELDS__", _script_json(fields))
    page = page.replace("__ROWS__", _script_json(rows))
    page = page.replace("__EDITABLE__", _script_json(EDITABLE_FIELDS))
    page = page.replace("__DIGEST__", digest)
    html_out.parent.mkdir(parents=True, exist_ok=True)
    html_out.write_text(page, encoding="utf-8")
    return {"schema_version": "clean-rights-review-html-v1", "rows": len(rows),
            "datasets": datasets, "source_keys_sha256": digest,
            "audio_loaded": False, "network_requests": False,
            "permissions_changed": False, "output": str(html_out)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.input, args.out)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

