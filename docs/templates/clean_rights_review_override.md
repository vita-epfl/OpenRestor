# Revue privée des droits Clean

Ce formulaire est destiné au registre privé uniquement. Une licence affichée
dans un catalogue, un score acoustique ou un fichier téléchargé ne constitue
pas une approbation. Ne remplir une ligne qu'après vérification de l'asset
exact (`media_key`) et de sa provenance.

## Champs requis pour une approbation

Le fichier d'override est un JSONL privé, une ligne par asset. Les champs
minimaux d'une ligne approuvée sont :

```json
{
  "media_key": "dataset:source_id",
  "review_status": "approved",
  "reviewer": "nom ou équipe",
  "license_label": "CC BY 4.0",
  "license_url": "https://creativecommons.org/licenses/by/4.0/",
  "attribution": "crédit exact exigé par la licence",
  "evidence_url": "URL ou référence du document vérifié",
  "evidence_date": "2026-10-29",
  "allow_commercial": true,
  "allow_redistribution": true,
  "allow_derivatives": true,
  "share_alike": false,
  "provenance_approved": true,
  "redistribution_approved": true,
  "source_status": "original_verified",
  "source_sha256": "sha256 du fichier original vérifié"
}
```

Pour un refus explicite, utiliser `"review_status": "rejected"` et conserver
la raison dans `"provenance_note"`. Pour une information incomplète, garder
`"review_status": "pending"` et les permissions à `null`. `null` ne signifie
jamais « autorisé ».

Les valeurs `allow_*` doivent correspondre à l'URL exacte de la licence. Une
licence `NC` ne peut pas avoir `allow_commercial: true` ; une licence `ND` ne
peut pas avoir `allow_derivatives: true`. Les licences `BY-SA` sont exportées
dans une famille de pack séparée et ne doivent pas être mélangées avec le pack
principal.

## Régénération locale après revue

Conserver le JSONL hors du dépôt. Pour un manifest Clean multi-dataset,
appliquer d'abord les overrides au manifest : cette étape met à jour les droits
utilisés par les profils et conserve l'historique par source.

```bash
.venv/bin/python scripts/apply_clean_rights_overrides.py \
  --manifest build/clean_corpus/no_benchmark_overlap_manifest.jsonl \
  --overrides /chemin/prive/clean_rights_overrides.jsonl \
  --out build/clean_corpus/no_benchmark_overlap_manifest_reviewed.jsonl \
  --report build/clean_corpus/no_benchmark_overlap_manifest_reviewed_report.json

.venv/bin/python scripts/build_media_rights_registry.py \
  --clean-corpus-manifest build/clean_corpus/no_benchmark_overlap_manifest_reviewed.jsonl \
  --out build/rights/media_registry.jsonl \
  --summary build/rights/public_summary.json

.venv/bin/python scripts/filter_clean_manifest_profiles.py \
  --input build/clean_corpus/no_benchmark_overlap_manifest_reviewed.jsonl \
  --out-dir build/clean_corpus/reviewed_rights_profiles \
  --require-technical

.venv/bin/python scripts/audit_clean_release_readiness.py \
  --manifest build/clean_corpus/no_benchmark_overlap_manifest_reviewed.jsonl \
  --profiles-dir build/clean_corpus/reviewed_rights_profiles \
  --out build/clean_corpus/reviewed_release_readiness.json
```

`--review-overrides` de `build_media_rights_registry.py` reste disponible pour
les workflows historiques de publication, mais il ne remplace pas l'étape
`apply_clean_rights_overrides.py` lorsqu'un profil est calculé directement à
partir d'un manifest Clean.

Un verdict `GO` mécanique ne remplace ni l'accord TTO/EPFL, ni la vérification
scientifique de la curation. Ne publier aucun audio tant que le registre et la
provenance de chaque asset ne sont pas approuvés.
