# Adjudication après écoute ciblée — IAMD v2.1 (28 octobre 2026)

Cette note complète l'évaluation indépendante sans modifier les annotations
brutes, les prédictions figées ou les métriques indépendantes. Elle est
postérieure à la révélation des erreurs et ne constitue donc pas une nouvelle
validation indépendante.

## Décision source

Les quatre cas écoutés sont reclassés ainsi :

| Source | Décision v2.1 | Verdict après écoute |
| --- | --- | --- |
| `80ssynthpop` | `auto_accept` | Acceptable ; le niveau de gain initial masquait la bonne qualité. |
| `7-impromptus-piano-eye-filmmuseum` | `auto_reject` | Rejet valide ; coloration/limitation de bande passante audible. |
| `AeolianDrift` | `auto_reject` | Rejet valide ; égaliseur et qualité insuffisante. |
| `TheSleepingMoth` | `auto_reject` | Rejet valide ; clipping important. |

Ainsi, le seul faux positif apparent au niveau source (`80ssynthpop`) n'en est
pas un après écoute. Sur ces 4 cas ciblés, la décision source v2.1 est correcte
dans les deux sens. Cela reste un constat post-hoc, pas une estimation de
généralisation.

## Diagnostic des passages centraux

- `AJazzConstruct` : musique de bonne qualité, mais trompette distante ; la
  revue humaine est préférable à un rejet automatique.
- `ER34struggle` : très mauvaise qualité ; le rejet est justifié.
- `TheVoyageOfTheTalisman` : très mauvaise qualité ; la revue humaine a évité
  une acceptation automatique de la source.

Le diagnostic passage passe donc de trois mauvais acceptés à un seul cas réel,
`TheVoyageOfTheTalisman`. Les quatre bons rejets apparents sont confirmés comme
des rejets justifiés.

## Conséquence pratique

La v2.1 est suffisamment conservatrice pour que les `auto_accept` source soient
prometteurs, mais l'échantillon ne permet pas encore de supprimer la revue
humaine. `AJazzConstruct` illustre le cas à conserver en `manual_review` : bonne
musique, défaut local de prise de son, et pas de règle binaire fiable.

Les détails structurés sont dans
`build/curation/iamd/evaluation/independent_v21/error_review/post_listening_adjudication.json`.
