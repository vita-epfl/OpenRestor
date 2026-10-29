# Pilote IAMD — passage dans la curation commune (29 octobre 2026)

Ce rapport documente uniquement les quatre fichiers IAMD déjà téléchargés et
vérifiés par checksum dans le pilote Phase 1b. Aucun nouveau fichier audio n'a
été téléchargé et aucun benchmark n'a été modifié.

## Reproductibilité

Le manifeste d'entrée est
`build/iamd_feasibility/phase1b/curation_manifest.jsonl`. Les commandes ont été
exécutées dans l'environnement local du dépôt :

```bash
.venv/bin/python -m openrestor.curation.cli extract \
  --manifest build/iamd_feasibility/phase1b/curation_manifest.jsonl \
  --clips-dir build/iamd_feasibility/phase1b/common_curation/clips \
  --out build/iamd_feasibility/phase1b/common_curation/features.jsonl \
  --segment-seconds 24
.venv/bin/python -m openrestor.curation.cli enrich-acoustics \
  --features build/iamd_feasibility/phase1b/common_curation/features.jsonl \
  --out build/iamd_feasibility/phase1b/common_curation/features_acoustic.jsonl
build/metric_tools/audiobox_cpu_venv/bin/python -m openrestor.curation.cli probe \
  --features build/iamd_feasibility/phase1b/common_curation/features_acoustic.jsonl \
  --out build/iamd_feasibility/phase1b/common_curation/features_probed.jsonl \
  --models ast,clap,aesthetics --cache-dir build/metric_tools/hf_cache
.venv/bin/python -m openrestor.curation.cli score \
  --features build/iamd_feasibility/phase1b/common_curation/features_probed.jsonl \
  --out build/iamd_feasibility/phase1b/common_curation/decisions_v21.jsonl \
  --policy v21 --config configs/curation/clean_music_v21.yaml
.venv/bin/python -m openrestor.curation.cli export-judgments \
  --features build/iamd_feasibility/phase1b/common_curation/features_probed.jsonl \
  --decisions build/iamd_feasibility/phase1b/common_curation/decisions_v21.jsonl \
  --out build/iamd_feasibility/phase1b/common_curation/pipeline_judgments_v21.jsonl
```

Les modèles AST, CLAP et Audiobox ont été réutilisés depuis le cache existant.
Les probes ont produit les scores des 12 passages sans erreur de modèle.

## Résultat

| Source | PQ médian | Bande passante médiane | Clipping maximal | Score v2.1 | Décision | Motifs principaux |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `AdamLaMottePictureInaFrame` | 7,98 | 11,9 kHz | 0,00121 | 0,7877 | `manual_review` | désaccord entre passages ; garde CLAP de captation dégradée |
| `RevolutionVoidBiomythos_ambientsoundscapemix_` | 7,89 | 8,5 kHz | 0 | 0,6283 | `manual_review` | bande passante ; désaccord entre passages |
| `ahp007` | 5,98 | 21,8 kHz | 0 | 0,4845 | `manual_review` | garde souffle ; PQ faible ; garde CLAP |
| `digitalminimum_dm001` | 7,33 | 19,7 kHz | 0 | 0,6511 | `manual_review` | indices metadata de rendu synthétique/stylisé |

Le scoreur a donc produit **4 `manual_review`, 0 `auto_accept`, 0
`auto_reject`**. C'est le comportement attendu d'un lot sans décision humaine
et avec des signaux contradictoires : aucun audio n'est promu automatiquement.
Le fichier `digitalminimum_dm001` contient le terme `midi` dans ses métadonnées ;
il est placé en revue, pas rejeté automatiquement, afin de ne pas éliminer la
musique électronique légitime sur un indice textuel unique.

## Droits et portée

Les quatre lignes restent `redistributable_candidate=false`,
`provenance_approved=false` et `review_status=pilot_pending_asset_review`.
Une décision acoustique, même positive, ne constitue pas une autorisation de
redistribution. Les extraits ne certifient pas non plus l'intégralité de leur
source.

Les résultats sont un contrôle technique sur quatre fichiers, pas une
estimation du rendement IAMD ni un motif pour lancer les 56 téléchargements
restants du pilote.

La page privée d'écoute a été régénérée avec ces jugements visibles par passage
(`build/iamd_feasibility/phase1b/listen.html`). Le CSV
`annotation_template_complete.csv` contient toujours uniquement des champs
humains vides : l'affichage machine ne préremplit aucune annotation.
