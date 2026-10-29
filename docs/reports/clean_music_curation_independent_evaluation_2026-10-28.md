# Évaluation indépendante v2/v2.1 — IAMD (28 octobre 2026)

Les probes ont été exécutées dans l'environnement existant
`build/metric_tools/audiobox_cpu_venv` avec le cache de modèles déjà approuvé.
Les modèles AST, CLAP, les prompts contrastifs et les seuils n'ont pas été
modifiés. Les 340 passages des 120 sources ont été calculés sans erreur.

La relecture des 200 sources du pilot reproduit les décisions gelées à 200/200
pour v2 et 200/200 pour v2.1. Les 7 annotations `unresolved` du lot indépendant
sont exclues de tous les dénominateurs binaires.

## Métrique au niveau du passage annoté

Les labels portent sur le passage principal. C'est la mesure la plus directe,
mais elle ne certifie pas la source complète.

| Politique | Acceptations binaires | Précision | Mauvais acceptés | Bons rejetés | Revue (120) |
| --- | ---: | ---: | ---: | ---: | ---: |
| v2 | 32 | 59,4 % [42,3–74,5] | 20,6 % [12,5–32,2] | 8,0 % [3,2–18,8] | 47,5 % |
| v2.1 | 11 | 72,7 % [43,4–90,3] | 4,8 % [1,6–13,1] | 8,0 % [3,2–18,8] | 65,8 % |

La v2.1 réduit donc fortement les mauvaises acceptations, avec un intervalle
large dû aux 11 acceptations seulement. Les bons rejets ne progressent pas sur
ce lot.

## Contrôle avec décision source

Cette seconde table applique la décision agrégée de la source au label du
passage principal uniquement. Elle mesure une cohérence conservatrice ; elle
ne constitue pas une validation de la source entière.

| Politique | Acceptations binaires | Précision du passage | Mauvais acceptés | Bons rejetés | Revue (120) |
| --- | ---: | ---: | ---: | ---: | ---: |
| v2 | 15 | 66,7 % [41,7–84,8] | 7,9 % [3,4–17,3] | 6,0 % [2,1–16,2] | 66,7 % |
| v2.1 | 5 | 80,0 % [37,6–96,4] | 1,6 % [0,3–8,5] | 6,0 % [2,1–16,2] | 75,0 % |

Une source `auto_accept` ne devra donc pas être intégrée au clean pool sans
contrôle de tous les passages et vérification indépendante des droits.

## Erreurs principales v2.1 avant réécoute ciblée

- faux positifs au niveau du passage : `80ssynthpop`, `AJazzConstruct`,
  `TheVoyageOfTheTalisman` ;
- faux positifs dans le contrôle source : `80ssynthpop` ;
- bons passages rejetés : `7-impromptus-piano-eye-filmmuseum`, `AeolianDrift`,
  `ER34struggle`, `TheSleepingMoth`.

## Adjudication après écoute ciblée

Une écoute manuelle des cas signalés a été réalisée après le gel et la
révélation des prédictions. Elle ne constitue donc pas une validation
indépendante et ne remplace pas les métriques ci-dessus.

- `80ssynthpop` est finalement jugé acceptable : le faible niveau de gain
  masquait une bonne qualité, mais l'audio est exploitable après écoute à un
  niveau adapté.
- `7-impromptus-piano-eye-filmmuseum`, `AeolianDrift` et `TheSleepingMoth`
  sont correctement rejetés (coloration/bande passante, qualité insuffisante
  et clipping respectivement).
- `AJazzConstruct` est une bonne production avec une trompette distante ; la
  `manual_review` reste la décision appropriée, plutôt qu'un rejet automatique.
- `ER34struggle` est effectivement très mauvais.
- `TheVoyageOfTheTalisman` est effectivement très mauvais ; sa revue humaine a
  évité une acceptation automatique de la source.

Sur ces cas ciblés, la décision source v2.1 est correcte dans les deux sens :
le seul faux positif source apparent (`80ssynthpop`) disparaît après écoute et
les trois rejets apparemment « bons » sont confirmés. Ce constat est
post-hoc et ne doit pas être présenté comme une précision indépendante.

Le détail structuré de cette adjudication est dans
`build/curation/iamd/evaluation/independent_v21/error_review/post_listening_adjudication.json`.

## Recalcul sur le ground truth définitif

Les sept corrections explicites ont été appliquées dans une nouvelle version
d'annotations. Les annotations et métriques brutes restent conservées pour la
traçabilité ; les résultats ci-dessous sont postérieurs à la révélation des
prédictions et ne constituent donc pas une validation indépendante.

| Politique | Niveau | Acceptations | Précision | Mauvais acceptés | Bons rejetés | Revue |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v2 | passage principal | 32 | 65,6 % [48,3–79,6] | 16,9 % [9,7–27,8] | 0,0 % [0,0–7,4] | 47,5 % |
| v2.1 | passage principal | 11 | 90,9 % [62,3–98,4] | 1,5 % [0,3–8,2] | 0,0 % [0,0–7,4] | 65,8 % |
| v2 | décision source | 15 | 73,3 % [48,0–89,1] | 6,2 % [2,4–14,8] | 0,0 % [0,0–7,4] | 66,7 % |
| v2.1 | décision source | 5 | 100,0 % [56,6–100,0] | 0,0 % [0,0–5,6] | 0,0 % [0,0–7,4] | 75,0 % |

Les intervalles sont Wilson à 95 %. Le résultat v2.1 au niveau source est
prometteur mais repose sur seulement cinq acceptations et sur un ground truth
corrigé après écoute des erreurs : il ne justifie pas à lui seul la suppression
de la revue humaine.

Les erreurs résiduelles après adjudication sont maintenant explicites :

- v2, passage principal : 11 mauvais acceptés — `01-gean-bittencourt-mancha-azul`,
  `71-mirando-el-firmamento`, `ATMPKThoughtCloud`, `GalacticOrbit`,
  `GjestarHybridBlackOutGjestarReWork`, `JonahDempcyAutumninNewYork_jazzstandard_`,
  `ReggaePlaygroundSelectaBobFigurante_CasadaMusicaReggaeFest_0`, `SRS05312`,
  `SimonSlator_TheLake`, `TheVoyageOfTheTalisman` et
  `ThisIsNotAConspiracyTheory` ; aucun bon rejet.
- v2, décision source : 4 mauvais acceptés — `01-gean-bittencourt-mancha-azul`,
  `71-mirando-el-firmamento`, `SimonSlator_TheLake` et
  `TheVoyageOfTheTalisman` ; aucun bon rejet.
- v2.1, passage principal : un seul mauvais accepté,
  `TheVoyageOfTheTalisman` ; aucun bon rejet.
- v2.1, décision source : aucun mauvais accepté ni bon rejet parmi les 120
  sources annotées (les 7 avis `unresolved` restent exclus).

Ces listes proviennent directement de
`evaluation_corrected/independent_evaluation.json`, et non d'une
réinterprétation du tableau du rapport.

La version définitive, son historique et son verrou sont :

- `build/curation/iamd/evaluation/independent_v21/independent_validation_reviews_definitive_v2.jsonl` ;
- `build/curation/iamd/evaluation/independent_v21/error_review/annotation_history.jsonl` ;
- `build/curation/iamd/evaluation/independent_v21/independent_validation_reviews_definitive_v2.jsonl.lock.json`.

Le manifeste versionné de cette chaîne (chemins, hashes, corrections et erreurs
résiduelles) est
[`clean_music_curation_adjudication_manifest_2026-10-28.json`](clean_music_curation_adjudication_manifest_2026-10-28.json).

Pour les prochaines évaluations, les exports
`pipeline_judgments_v2.jsonl` et `pipeline_judgments_v21.jsonl` donnent
directement, par source, la décision de la pipeline, le score, les motifs, les
décisions par passage et le statut des droits. Ils ne remplacent pas l'écoute
humaine, mais fournissent le jugement machine et ses éléments explicatifs avant
toute interprétation manuelle.

Pour produire ces jugements sur un nouveau lot, utiliser la commande
`export-judgments` avec les features et les décisions v2/v2.1 gelées ; fournir
le fichier d'annotations uniquement après l'écoute si l'on souhaite juxtaposer
le jugement humain. Les exports doivent être conservés avec le même identifiant
de lot que les métriques.

## Conclusion

La v2.1 est préférable à v2 pour limiter la contamination des acceptations,
mais elle ne permet pas encore une sélection automatique suffisamment couverte
pour constituer seule un clean pool de grande taille. Un rendement observé sur
ce lot est de 5 sources `auto_accept` au niveau source, avec 75 % de revue ;
l'écoute ciblée ne révèle pas de contamination sur les erreurs source
examinées, mais cet échantillon est trop petit et post-hoc pour justifier une
nouvelle estimation de généralisation. Les faux rejets apparents examinés sont
justifiés, tandis que les cas de musique bonne mais imparfaite doivent rester
en `manual_review`.

Les décisions, features, reviews et métriques détaillées sont dans
`build/curation/iamd/evaluation/independent_v21/`.
