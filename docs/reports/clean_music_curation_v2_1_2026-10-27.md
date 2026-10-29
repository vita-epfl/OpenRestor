# Curation clean multi-datasets — v2.1 conservatrice (27 octobre 2026)

## Décision

La v2.1 améliore nettement la fiabilité des acceptations automatiques sur les
annotations disponibles, mais elle réduit volontairement leur couverture. Elle
est adaptée à une file de candidats à vérifier, pas encore à l'alimentation
automatique du clean pool.

## Audit des erreurs v2

- `billcor-small-acts-of-love-4a8526` est une captation/production jugée dégradée
  malgré PQ 7,7–8,4, AST Music élevé et bande passante large. Son signal CLAP
  musique-versus-dégradé est faible sur les passages ; Audiobox ne mesure pas
  directement la distance micro, la réverbération ni l'intelligibilité.
- `DaVinylBoxDemo` présente une qualité plus faible et une marge CLAP dégradée
  négative sur un passage, mais restait acceptée par la v2 précédente.
- `barely_a_fleshwound` est un rendu rudimentaire : les scores acoustiques sont
  bons, mais les métadonnées `VGM`/contenu stylisé doivent bloquer l'acceptation
  automatique sans rejeter la musique électronique par défaut.

Les signaux Audiobox, AST, CLAP et no-reference sont donc complémentaires mais
non suffisants individuellement. Les proxies bruit/hum/dynamique restent des
indicateurs de revue ; leurs distributions se recouvrent trop sur la calibration.

## Correction technique importante

Le calcul no-reference précédent décimait les extraits longs avant FFT. Cela
abaissait la fréquence de Nyquist et rendait les champs `hiss_proxy` et
`bandwidth_hz` incohérents. La v2.1 utilise maintenant une fenêtre centrale
bornée à la fréquence d'échantillonnage originale. Le cache corrigé est
`build/curation/iamd/features_acoustic_v2.jsonl` ; le cache Audiobox/AST/CLAP
historique n'est pas modifié.

## Règles v2.1

Une acceptation automatique exige, sur chaque passage échantillonné :

- score v2.1 minimal de 0,82 et PQ au moins 7,0 ;
- marge CLAP musique-versus-dégradé d'au moins 0,08 ;
- absence de clipping/bande passante sévère et de signaux non musicaux consensuels ;
- absence d'indices metadata `MIDI`, `soundfont`, `tracker`, `VGM`, chiptune
  stylisé ou contexte de production nécessitant une revue.

Ces garde-fous envoient vers `manual_review` ; ils ne constituent pas des rejets
artistiques. La décision source reste distincte de la décision segment. Un fichier
partiellement dégradé peut donc produire des segments candidats, avec
`partial_source=true`, sans que la source entière soit certifiée.

## Comparaison sur les partitions déjà utilisées

| Approche | Split | Auto-accept binaires | Précision | Mauvaises acceptations | Bons rejets | Revue |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v1 historique | calibration | 6 | 66,7 % | 6,1 % des négatifs | 0,0 % | 86,5 % |
| v2 corrigée | calibration | 8 | 75,0 % | 6,1 % | 0,0 % | 77,0 % |
| **v2.1** | **calibration** | **2** | **100 %** | **0,0 %** | **0,0 %** | **89,2 %** |
| v1 historique | validation interne | 0 | non estimable | 0,0 % | 0,0 % | 88,5 % |
| v2 corrigée | validation interne | 2 | 100 % | 0,0 % | 0,0 % | 65,4 % |
| **v2.1** | **validation interne** | **0** | non estimable | **0,0 %** | **0,0 %** | **92,3 %** |

La v2.1 produit sur les 200 sources 10 `auto_accept`, 173 `manual_review` et 17
`auto_reject`. Ces nombres ne sont pas une mesure de généralisation : les 200
sources ont déjà participé au développement et la validation interne a été vue en
agrégat.

La précision v2.1 est encourageante mais fondée sur seulement deux acceptations
binaires en calibration. Elle ne justifie pas encore une publication automatique.

### Ablations des garde-fous

Sur la calibration, retirer la marge CLAP musique-versus-dégradé fait passer la
précision de 100 % (2 acceptations) à 80 % (5 acceptations) et réintroduit
`billcor-small-acts-of-love-4a8526` comme faux positif. Retirer les garde-fous
acoustiques produit le même faux positif. Le garde-fou metadata n'a pas changé
les métriques sur cette petite cohorte ; il reste utile pour les cas futurs
`MIDI`/`VGM`, mais son apport n'est pas encore démontré. Cette ablation justifie
de conserver le CLAP guard et les contrôles acoustiques, sans prétendre qu'ils
détectent toutes les captations lointaines ou réverbérantes.

## Validation indépendante préparée

Le manifeste source-disjoint de 120 identifiants est prêt :

- [manifeste indépendant](../../build/curation/iamd/independent_validation_120.jsonl)
- [template d'annotation](../../build/curation/iamd/independent_validation_120_review_template.csv)
- [rapport de stratification](../../build/curation/iamd/independent_validation_120.md)
- [ordre aveugle gelé](../../build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_order.jsonl)
- [lock de l'ordre et template blind](../../build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_order.jsonl.lock.json)

Il exclut les 200 sources du pilot et l'union des manifestes Blind-Real
(`public_test_candidates` et `resolved_originals`). Il contient les
URLs et métadonnées des originaux résolus, mais **aucun audio n'a été téléchargé**.
Les genres sont des tags IAMD bruts lorsqu'ils existent, pas une taxonomie
normalisée ; cette limite est indiquée dans le plan. Les collections et créateurs
sont plafonnés pour éviter une concentration excessive.

Après décision explicite de télécharger ce lot, les clips pourront être extraits
et l'interface existante lancée en aveugle avec `curation listen --blind`. La
politique v2.1 doit rester figée avant de révéler les annotations.

## Prédictions gelées avant annotation

Les décisions corrigées v2 et v2.1 ont été copiées sans téléchargement ni
modification du pilot, puis verrouillées par hash :

- [v2 gelée](../../build/curation/iamd/frozen/decisions_v2_frozen.jsonl) et [son lock](../../build/curation/iamd/frozen/decisions_v2_frozen.jsonl.lock.json)
- [v2.1 gelée](../../build/curation/iamd/frozen/decisions_v21_frozen.jsonl) et [son lock](../../build/curation/iamd/frozen/decisions_v21_frozen.jsonl.lock.json)

Les locks fixent le nombre de sources, le hash des features, le hash des
décisions et la version de politique. Une relance identique est acceptée ;
toute autre écriture est refusée. La page aveugle n'utilise volontairement
aucun de ces fichiers et ne révèle pas les scores.

## Artefacts et limites

- `build/curation/iamd/decisions_v21.jsonl` — décisions par passage/source.
- `build/curation/iamd/frozen/decisions_v2_frozen.jsonl` et
  `decisions_v21_frozen.jsonl` — prédictions immuables avant annotation, avec
  leurs locks hashés.
- `build/curation/iamd/v21_segment_candidates.jsonl` — 106 segments candidats,
  tous marqués acoustiques uniquement et sans approbation de redistribution.
- `build/curation/iamd/evaluation/v21/evaluation_v2.json` — comparaison v1/v2/v2.1
  sur calibration/validation interne.
- `build/curation/iamd/evaluation/v21/active_review_queue_v2.jsonl` — file active
  de clarification, incluant les 28 avis incomplets.
- `build/curation/iamd/evaluation/v21/annotation_suggestions_v2.jsonl` — 28
  suggestions non contraignantes ; les notes « distant » et « AI generated » y
  sont structurées, mais aucun label humain n'est modifié implicitement.

Les signaux de distance, réverbération et artefacts restent imparfaitement
observables sans référence propre. La prochaine décision doit dépendre de la
validation indépendante, pas d'un nouveau seuil ajusté sur ces 200 sources.

## Adjudication après écoute ciblée

Les sept corrections issues de l'écoute ciblée ont été enregistrées dans une
version définitive, avec les valeurs précédentes et la note de correction dans
un historique append-only. Les annotations indéterminées restent exclues des
métriques binaires.

| Politique | Niveau | Acceptations | Précision après correction | Revue |
| --- | --- | ---: | ---: | ---: |
| v2 | passage principal | 32 | 65,6 % [48,3–79,6] | 47,5 % |
| v2.1 | passage principal | 11 | 90,9 % [62,3–98,4] | 65,8 % |
| v2 | décision source | 15 | 73,3 % [48,0–89,1] | 66,7 % |
| v2.1 | décision source | 5 | 100,0 % [56,6–100,0] | 75,0 % |

Ces chiffres sont des diagnostics de traçabilité postérieurs à la révélation
des prédictions ; ils ne constituent pas une validation indépendante. Le niveau
« passage principal » ne certifie jamais la source entière. La v2.1 conserve un
faux accepté au niveau du passage (`TheVoyageOfTheTalisman`) ; aucun faux rejet
n'est observé après adjudication sur ce lot, avec des intervalles larges.

Les artefacts versionnés sont détaillés dans
[`clean_music_curation_independent_evaluation_2026-10-28.md`](clean_music_curation_independent_evaluation_2026-10-28.md)
et dans le manifeste
[`clean_music_curation_adjudication_manifest_2026-10-28.json`](clean_music_curation_adjudication_manifest_2026-10-28.json).
Les jugements machine directement exploitables pour les prochaines écoutes sont
exportés par source dans `pipeline_judgments_v2.jsonl` et
`pipeline_judgments_v21.jsonl` ; ils restent séparés des labels humains et des
droits.

