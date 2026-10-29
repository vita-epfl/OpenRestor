# OpenRestor Clean — candidat local metadata-only (29 octobre 2026)

Un candidat local a été reconstruit depuis le manifest fusionné et le registre
privé courant :

```bash
.venv/bin/python scripts/build_media_rights_registry.py \
  --clean-corpus-manifest build/clean_corpus/rights_registry_input.jsonl \
  --out build/rights/media_registry.jsonl \
  --summary build/rights/public_summary.json
.venv/bin/python scripts/build_publication_subset.py \
  --rights-register build/rights/media_registry.jsonl \
  --copy-into build/release-candidates/rights-v0_1-albumdb-current
bash scripts/check_initial_release_candidate.sh \
  build/release-candidates/rights-v0_1-albumdb-current
```

Le contrôle a réussi avec les invariants suivants :

- `diagnostic` : 542 829 exemples retenus par le corpus gelé, 542 829
  withheld, 0 audio empaqueté ;
- `blind_synthetic` : 25 849 exemples withheld, 0 audio empaqueté ;
- 14 RIR vérifiés dans le résumé de droits ;
- zéro identifiant privé ou URL de média dans le candidat ;
- quatre notices et les 14 checksums RIR présents ;
- `upload_approved=false` et `frozen_release_untouched=true`.

Ce candidat est un artefact local de contrôle. Il ne constitue pas une release
publique et ne contient aucun audio Clean : les 28 014 sources du manifest
fusionné restent bloquées jusqu'à la revue asset-level et l'accord de diffusion.
Le total du registre privé associé est 28 410 assets, dont 298 lignes AlbumDB
metadata-only ; seuls les 14 RIR approuvés apparaissent dans les profils.
