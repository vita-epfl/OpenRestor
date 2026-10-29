# Validation indépendante IAMD — import des annotations (28 octobre 2026)

Le fichier `build/curation_reviews (2).csv` a été validé et remappé via le lock
privé `blind_id → source_key`. Les prédictions v2/v2.1 n'ont pas été révélées
et aucune décision automatique n'a été ajustée.

## Résumé des annotations

| Classe dérivée | Nombre |
| --- | ---: |
| `positive_clip_evidence` | 50 |
| `negative_clip_evidence` | 63 |
| `unresolved` | 7 |

Le classement est source-groupé, mais il décrit principalement le ou les
passages écoutés. Les champs laissés vides restent inconnus : ils ne sont pas
convertis en positifs.

| Champ | Répartition |
| --- | --- |
| Contenu | 94 musique, 25 bruit/effet, 1 ambigu |
| Qualité | 55 acceptable, 32 dégradée, 10 ambiguë, 23 vide |
| Nature | 4 enregistrement réel probable, 10 MIDI/synthétique probable, 106 vide |

Les champs `capture_quality`, `degradation_reason`, `pool_suitability` et
`source_level_label` sont restés vides dans cet export. Il est donc possible
d'évaluer la contamination et la couverture, mais pas encore de décomposer
finement les causes de dégradation.

## Signaux acoustiques descriptifs

Les médianes ci-dessous portent sur les passages extraits, pas sur les sources
entières :

| Signal | Positifs | Négatifs |
| --- | ---: | ---: |
| Bande passante (Hz) | 17 869 | 14 765 |
| Hiss proxy | 0,0048 | 0,0008 |
| Hum proxy | 1,11 | 1,27 |
| Clipping ratio | 0 | 0 |
| Dynamique (dB) | 9,64 | 8,75 |
| Noise margin (dB) | 5,05 | 4,55 |
| Silence quasi-total | 0,007 | 0,009 |

Ces recouvrements importants confirment qu'aucun seuil acoustique isolé ne
peut servir de vérité terrain. En particulier, le hiss proxy est plus élevé
chez certains positifs et le clipping médian est nul dans les deux groupes.

## Métriques modèles

AST, CLAP et Audiobox n'ont pas été recalculés sur ce lot : l'environnement
actuel ne contient pas PyTorch/Transformers/Audiobox utilisables. Les 120
annotations sont donc importées, mais aucune précision v2/v2.1 indépendante
n'est annoncée à ce stade.

Les features et annotations sont disponibles ici :

- `build/curation/iamd/evaluation/independent_v21/independent_validation_features.jsonl`
- `build/curation/iamd/evaluation/independent_v21/independent_validation_reviews.jsonl`
- `build/curation/iamd/evaluation/independent_v21/independent_validation_120_annotations_remapped.csv`

Prochaine étape : installer/rendre disponible l'environnement de probes sur un
nœud adapté, calculer AST/CLAP/Audiobox **sans modifier les locks**, puis
évaluer v2 et v2.1 sur ces annotations indépendantes. Les 7 cas ambigus doivent
rester exclus des métriques binaires.
