# SonicMaster/Jamendo Licence Audit — 2026-10-16

## Result

The official Jamendo v3 `/tracks` API was queried with `include=licenses` for all 25,000
distinct `source_id` values in `configs/datasets/sonicmaster_original_split.jsonl`. The
collection-level SonicMaster `CC BY 2.0` label is not consistent with the current per-track
records returned by Jamendo.

| Current Jamendo result | Source tracks | Diagnostic examples (21 per source) | Blind-Synthetic examples |
| --- | ---: | ---: | ---: |
| CC BY | 856 | 17,976 | 856 |
| CC BY-SA, requires a separate compatibility decision | 1,623 | 34,083 | 1,623 |
| NoDerivatives, including NC-ND | 10,356 | 217,476 | 10,356 |
| NonCommercial without ND | 3,282 | 68,922 | 3,282 |
| Returned without a licence URL | 23 | 483 | 23 |
| Licence Art Libre, not yet reviewed for this release | 4 | 84 | 4 |
| Not returned by the current Jamendo API | 8,856 | 185,976 | 8,856 |
| **Total** | **25,000** | **525,000** | **25,000** |

The strict CC BY-only candidate is therefore 856 source tracks: 17,976 Diagnostic examples
and 856 Blind-Synthetic examples. Including BY-SA would raise this to 2,479 source tracks,
but would introduce several versions and jurisdictions of ShareAlike. It is not silently
accepted by the v0.1 policy.

## Split Impact

| Split | CC BY | BY-SA | NC and/or ND | missing licence | Licence Art Libre | not returned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 805 | 1,536 | 12,790 | 21 | 4 | 8,344 |
| validation | 21 | 30 | 275 | 1 | 0 | 173 |
| test | 30 | 57 | 573 | 1 | 0 | 339 |

## Interpretation

This audit is a snapshot of what the Jamendo API reports now. It does not establish what
licence applied when SonicMaster downloaded a track, whether Jamendo retains historical
licence evidence, or whether AMAAI separately obtained sufficient rights to relicense the
underlying audio as CC BY 2.0. Those questions require written confirmation.

Until then, all SonicMaster audio remains withheld. The frozen private manifests, HDF5
shards and rendered audio remain unchanged. The derived publication indexes have been
regenerated with zero published synthetic examples so that stale indexes cannot be shipped.
If a per-track subset is eventually approved, its rows can be selected without rerendering,
but the selected HDF5 rows and clean clips must be repackaged into public-only shards; whole
mixed SonicMaster shards must not be distributed.

## Evidence

- Audit command: `scripts/audit_sonicmaster_jamendo_licenses.sh`
- Input SHA-256: `9c9c7b19b9ba5035523f4a460341b9ee0f0a0e4c6509621d3f513b91805a4f87`
- Audit time: `2026-10-16T12:41:32Z`
- Complete raw responses: 500 JSON files under
  `build/licence-audits/sonicmaster_jamendo/raw/`
- Normalized track evidence SHA-256:
  `b8bcec23daa8a8fffe641928acd0d6df098e3a068e35f605f281c709109b53d0`
- Summary SHA-256:
  `8c869e784198d247b976a1973a5d9b77c0b98dc08d654a361a0c0a2e7fef1672`
