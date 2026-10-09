#!/usr/bin/env python3
"""Build the Blind-Real curation QA package.

This is dataset curation, not a subjective listening study and not a model
evaluation. The only question being answered is which items belong in the set.

First pass is one clip per Internet Archive identifier. The second clip of an item is
staged but not presented, because asking for both doubles the listening for no gain on
items whose first clip settles the matter; it is there for items marked uncertain.

Audio QA and provenance QA are kept strictly apart. A clip can be a perfect live
recording whose licence is not trustworthy, and the two verdicts must not be collapsed:
an AcoustID non-match is not proof the audio is free, and a CC BY tag on Internet
Archive is not proof the uploader held the rights.

    python scripts/build_blind_real_qa.py
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

REJECT_REASONS = [
    "not_live", "commercial_release", "dj_mix_or_compilation",
    "non_music_or_speech_dominant", "not_degraded_enough", "unusable_audio", "uncertain",
]
QUALITY_LABELS = ["clean_live", "moderately_degraded", "strongly_degraded"]

CSV_FIELDS = [
    # Decisions, to be filled in.
    "audio_verdict", "reject_reason", "quality_label", "provenance_verdict", "note",
    # Identity and provenance, kept for audit.
    "clip_id", "identifier", "clip_index", "title", "artist", "collection",
    "license_type", "license_url", "confidence_tier", "live_trigger",
    "source_file", "source_format", "source_codec", "source_sample_rate",
    "excerpt_start_s", "excerpt_end_s", "source_duration_s",
    "acoustid_score", "acoustid_match", "archive_url",
]


def live_trigger(row: dict[str, Any]) -> str:
    """The field or phrase that made this item look like a live capture."""
    evidence = row.get("live_evidence") or {}
    if evidence.get("structured_fields"):
        fields = ", ".join(evidence["structured_fields"])
        venue = _text(row.get("venue"))
        return f"field {fields}" + (f" = {venue}" if venue else "")
    if evidence.get("strong_phrases"):
        return "phrase " + ", ".join(evidence["strong_phrases"][:3])
    if evidence.get("keyword_hits"):
        return "keyword " + ", ".join(evidence["keyword_hits"][:3])
    return "none"


def build_rows(manifest: list[dict[str, Any]], screen: dict[str, dict[str, Any]]) -> tuple[list, dict]:
    by_identifier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest:
        by_identifier[row["internet_archive_identifier"]].append(row)
    for clips in by_identifier.values():
        clips.sort(key=lambda r: r["clip_index"])

    first_pass, second_pass = [], {}
    for identifier in sorted(by_identifier):
        clips = by_identifier[identifier]
        first_pass.append(clips[0])
        if len(clips) > 1:
            second_pass[identifier] = clips[1]
    return first_pass, second_pass


def _text(value: Any) -> str:
    """Flatten a field that the Archive may return as a list, a number or nothing."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value if v not in (None, ""))
    return str(value)


def sheet_row(row: dict[str, Any], screen: dict[str, dict[str, Any]], audio_name: str) -> dict[str, Any]:
    artists = _text(row.get("attribution"))
    hit = screen.get(row["internet_archive_identifier"], {})
    match = (hit.get("matches") or [{}])[0] if hit.get("commercial_match") else {}
    return {
        "audio_verdict": "", "reject_reason": "", "quality_label": "",
        "provenance_verdict": "", "note": "",
        "clip_id": row["id"], "identifier": row["internet_archive_identifier"],
        "clip_index": row["clip_index"], "title": _text(row.get("title")),
        "artist": artists, "collection": _text(row.get("collection")),
        "license_type": _text(row.get("license_type")), "license_url": _text(row.get("license_url")),
        "confidence_tier": _text(row.get("confidence_tier")), "live_trigger": live_trigger(row),
        "source_file": _text(row.get("source_file")), "source_format": _text(row.get("source_format")),
        "source_codec": _text(row.get("source_codec")), "source_sample_rate": _text(row.get("source_sample_rate")),
        "excerpt_start_s": round(float(row.get("start_seconds", 0)), 1),
        "excerpt_end_s": round(float(row.get("start_seconds", 0)) + float(row.get("duration_seconds", 0)), 1),
        "source_duration_s": round(float(row.get("source_duration_seconds", 0)), 1),
        "acoustid_score": hit.get("score", ""),
        "acoustid_match": f"{match.get('artists')} / {match.get('title')}" if match else "",
        "archive_url": f"https://archive.org/details/{row['internet_archive_identifier']}",
        "_audio": audio_name,
    }


def page(rows: list[dict[str, Any]], second: dict[str, str]) -> str:
    cards = []
    for n, r in enumerate(rows, start=1):
        follow = second.get(r["identifier"])
        acoustid = (
            f'<span class="flag">AcoustID {r["acoustid_score"]} &rarr; {html.escape(str(r["acoustid_match"]))}</span>'
            if r["acoustid_match"] else
            f'<span class="muted">AcoustID: no match (score {r["acoustid_score"]}) &mdash; not proof of free rights</span>'
        )
        cards.append(f"""
<article class="card" data-clip="{html.escape(r['clip_id'])}">
  <header>
    <span class="num">{n}/{len(rows)}</span>
    <h2>{html.escape(r['title'] or r['identifier'])}</h2>
  </header>
  <audio controls preload="none" src="audio/{html.escape(r['_audio'])}"></audio>
  <dl>
    <dt>identifier</dt><dd><a href="{html.escape(r['archive_url'])}" target="_blank" rel="noopener">{html.escape(r['identifier'])}</a></dd>
    <dt>artist</dt><dd>{html.escape(r['artist']) or '<span class="muted">unknown</span>'}</dd>
    <dt>collection</dt><dd>{html.escape(r['collection'])}</dd>
    <dt>licence</dt><dd>{html.escape(r['license_type'])} &middot; <span class="muted">a tag is not proof of rights</span></dd>
    <dt>live evidence</dt><dd><b>{html.escape(r['confidence_tier'])}</b> &mdash; {html.escape(r['live_trigger'])}</dd>
    <dt>source file</dt><dd>{html.escape(r['source_file'])} <span class="muted">({html.escape(str(r['source_codec']))}, {html.escape(str(r['source_sample_rate']))} Hz)</span></dd>
    <dt>excerpt</dt><dd>{r['excerpt_start_s']}s &ndash; {r['excerpt_end_s']}s of {r['source_duration_s']}s</dd>
    <dt>fingerprint</dt><dd>{acoustid}</dd>
  </dl>
  <div class="qa">
    <fieldset>
      <legend>1. Audio QA &mdash; real live capture? degraded enough? usable?</legend>
      <label><input type="radio" name="a_{n}" value="keep"> keep</label>
      <label><input type="radio" name="a_{n}" value="reject"> reject</label>
      <label><input type="radio" name="a_{n}" value="uncertain"> uncertain</label>
      <select name="r_{n}"><option value="">reject reason&hellip;</option>{''.join(f'<option>{x}</option>' for x in REJECT_REASONS)}</select>
      <select name="q_{n}"><option value="">coarse quality (optional)&hellip;</option>{''.join(f'<option>{x}</option>' for x in QUALITY_LABELS)}</select>
    </fieldset>
    <fieldset>
      <legend>2. Provenance QA &mdash; is the licence trustworthy enough to distribute?</legend>
      <label><input type="radio" name="p_{n}" value="keep"> trustworthy</label>
      <label><input type="radio" name="p_{n}" value="reject"> not trustworthy</label>
      <label><input type="radio" name="p_{n}" value="uncertain"> uncertain</label>
    </fieldset>
    <input type="text" name="n_{n}" placeholder="note (optional)">
    {f'<details><summary>second excerpt of this item &mdash; only if the first is uncertain</summary><audio controls preload="none" src="audio_pass2/{html.escape(follow)}"></audio></details>' if follow else '<p class="muted">no second excerpt for this item</p>'}
  </div>
</article>""")

    return f"""<title>Blind-Real curation QA</title>
<style>
  :root {{ --ink:#1a1a1a; --dim:#6b6b6b; --line:#e2e2e2; --accent:#1f5f8b; --warn:#9c3b1b; }}
  body {{ max-width: 54rem; margin: 0 auto; padding: 1.5rem; color: var(--ink); line-height: 1.5; }}
  h1 {{ font-size: 1.5rem; margin-bottom: .25rem; }}
  .intro {{ background:#f6f7f8; border-left:3px solid var(--accent); padding:.75rem 1rem; margin-bottom:1.5rem; }}
  .intro p {{ margin:.4rem 0; }}
  .card {{ border:1px solid var(--line); border-radius:6px; padding:1rem; margin-bottom:1.25rem; }}
  .card header {{ display:flex; gap:.6rem; align-items:baseline; }}
  .card h2 {{ font-size:1.05rem; margin:0 0 .5rem; }}
  .num {{ color:var(--dim); font-variant-numeric:tabular-nums; font-size:.85rem; }}
  audio {{ width:100%; margin:.5rem 0; }}
  dl {{ display:grid; grid-template-columns:9rem 1fr; gap:.15rem .75rem; font-size:.88rem; margin:.5rem 0; }}
  dt {{ color:var(--dim); }}
  dd {{ margin:0; overflow-wrap:anywhere; }}
  .muted {{ color:var(--dim); }}
  .flag {{ color:var(--warn); font-weight:600; }}
  fieldset {{ border:1px solid var(--line); border-radius:4px; margin:.5rem 0; padding:.5rem .75rem; }}
  legend {{ font-size:.82rem; color:var(--dim); padding:0 .3rem; }}
  .qa label {{ margin-right:.9rem; font-size:.9rem; }}
  .qa select, .qa input[type=text] {{ font-size:.85rem; padding:.2rem; margin-top:.3rem; }}
  .qa input[type=text] {{ width:100%; }}
  .bar {{ position:sticky; top:0; background:#fff; border-bottom:1px solid var(--line); padding:.6rem 0; margin-bottom:1rem; display:flex; gap:.75rem; align-items:center; z-index:5; }}
  button {{ font-size:.9rem; padding:.4rem .8rem; cursor:pointer; }}
  #count {{ color:var(--dim); font-size:.85rem; }}
  details {{ margin-top:.5rem; font-size:.88rem; }}
  @media (max-width:640px) {{ dl {{ grid-template-columns:1fr; }} dt {{ margin-top:.4rem; }} }}
</style>
<h1>Blind-Real curation QA</h1>
<div class="intro">
  <p><b>This is dataset curation, not a listening study and not a model evaluation.</b> The only question is which items belong in the set.</p>
  <p>One excerpt per source item. A second excerpt is staged under each card but only worth opening when the first leaves you uncertain.</p>
  <p>Bad audio quality is <b>not</b> a reason to reject &mdash; degraded recordings are the point. Reject speech, non-music, commercial releases and unusable audio.</p>
  <p>The two fieldsets are deliberately separate: a perfect live recording can have an untrustworthy licence. <b>An AcoustID non-match is not proof the audio is free, and a CC BY tag is not proof the uploader held the rights.</b></p>
</div>
<div class="bar">
  <button id="save">Download verdicts CSV</button>
  <span id="count"></span>
</div>
{''.join(cards)}
<script>
const N = {len(rows)};
const CLIPS = {json.dumps([r['clip_id'] for r in rows])};
const KEY = 'blind-real-qa';
function state() {{
  const out = {{}};
  for (let i = 1; i <= N; i++) {{
    const get = (p) => {{ const el = document.querySelector(`[name="${{p}}_${{i}}"]:checked`) || document.querySelector(`[name="${{p}}_${{i}}"]`); return el ? el.value : ''; }};
    const radio = (p) => {{ const el = document.querySelector(`[name="${{p}}_${{i}}"]:checked`); return el ? el.value : ''; }};
    out[CLIPS[i-1]] = {{ audio_verdict: radio('a'), reject_reason: get('r'), quality_label: get('q'), provenance_verdict: radio('p'), note: get('n') }};
  }}
  return out;
}}
function refresh() {{
  const s = state();
  const done = Object.values(s).filter(v => v.audio_verdict).length;
  document.getElementById('count').textContent = `${{done}} / ${{N}} decided`;
  try {{ localStorage.setItem(KEY, JSON.stringify(s)); }} catch (e) {{}}
}}
try {{
  const saved = JSON.parse(localStorage.getItem(KEY) || '{{}}');
  CLIPS.forEach((clip, idx) => {{
    const v = saved[clip]; if (!v) return; const i = idx + 1;
    if (v.audio_verdict) {{ const el = document.querySelector(`[name="a_${{i}}"][value="${{v.audio_verdict}}"]`); if (el) el.checked = true; }}
    if (v.provenance_verdict) {{ const el = document.querySelector(`[name="p_${{i}}"][value="${{v.provenance_verdict}}"]`); if (el) el.checked = true; }}
    ['r','q','n'].forEach((p, k) => {{ const el = document.querySelector(`[name="${{p}}_${{i}}"]`); if (el) el.value = [v.reject_reason, v.quality_label, v.note][k] || ''; }});
  }});
}} catch (e) {{}}
document.addEventListener('change', refresh);
document.addEventListener('input', refresh);
document.getElementById('save').addEventListener('click', () => {{
  const s = state();
  const head = ['clip_id','audio_verdict','reject_reason','quality_label','provenance_verdict','note'];
  const esc = (v) => `"${{String(v == null ? '' : v).replace(/"/g, '""')}}"`;
  const lines = [head.join(',')];
  CLIPS.forEach(clip => {{ const v = s[clip] || {{}}; lines.push([clip, v.audio_verdict, v.reject_reason, v.quality_label, v.provenance_verdict, v.note].map(esc).join(',')); }});
  const blob = new Blob([lines.join('\\n')], {{type: 'text/csv'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'blind_real_verdicts.csv';
  document.body.appendChild(a); a.click(); a.remove();
}});
refresh();
</script>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO / "build/blind_real/blind_real_test_manifest.jsonl")
    parser.add_argument("--clips-root", type=Path, default=REPO / "build/blind_real/clips")
    parser.add_argument("--screen", type=Path, default=REPO / "build/blind_real/acoustid_screen.jsonl")
    parser.add_argument("--output", type=Path, default=REPO / "build/blind_real/qa_pass1")
    parser.add_argument("--flac", action="store_true", help="Encode the staged audio as FLAC")
    args = parser.parse_args()

    manifest = [json.loads(line) for line in args.manifest.open(encoding="utf-8")]
    screen: dict[str, dict[str, Any]] = {}
    if args.screen.is_file():
        for line in args.screen.open(encoding="utf-8"):
            row = json.loads(line)
            # Keep the strongest signal per identifier.
            previous = screen.get(row["identifier"])
            if previous is None or (row.get("score") or 0) > (previous.get("score") or 0):
                screen[row["identifier"]] = row

    first, second = build_rows(manifest, screen)
    if args.output.exists():
        shutil.rmtree(args.output)
    (args.output / "audio").mkdir(parents=True)
    (args.output / "audio_pass2").mkdir(parents=True)

    sheet, second_names = [], {}
    for row in first:
        name = f"{row['id']}.wav"
        shutil.copy2(args.clips_root / row["audio_path"], args.output / "audio" / name)
        sheet.append(sheet_row(row, screen, name))
    for identifier, row in second.items():
        name = f"{row['id']}.wav"
        shutil.copy2(args.clips_root / row["audio_path"], args.output / "audio_pass2" / name)
        second_names[identifier] = name

    if args.flac:
        for directory in ("audio", "audio_pass2"):
            for wav in sorted((args.output / directory).glob("*.wav")):
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav),
                                "-c:a", "flac", "-compression_level", "8", str(wav.with_suffix(".flac"))], check=True)
                wav.unlink()
        for entry in sheet:
            entry["_audio"] = str(Path(entry["_audio"]).with_suffix(".flac"))
        second_names = {k: str(Path(v).with_suffix(".flac")) for k, v in second_names.items()}

    with (args.output / "verdicts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for entry in sheet:
            writer.writerow({k: v for k, v in entry.items() if k in CSV_FIELDS})

    (args.output / "index.html").write_text(page(sheet, second_names), encoding="utf-8")
    (args.output / "provenance.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in manifest), encoding="utf-8")

    flagged = sum(1 for e in sheet if e["acoustid_match"])
    print(f"{len(sheet)} items in pass 1, {len(second_names)} second excerpts staged")
    print(f"{flagged} carry an AcoustID commercial match")
    print(f"open {args.output / 'index.html'} in a browser, or annotate {args.output / 'verdicts.csv'}")


if __name__ == "__main__":
    main()
