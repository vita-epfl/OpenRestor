# Curation clean multi-datasets — v2 ciblée (27 octobre 2026)

## Résultat en une phrase

La v2 augmente fortement la couverture automatique sur la cohorte annotée, surtout
en acceptation et en rejet, mais la qualité des acceptations reste insuffisamment
établie pour alimenter un clean pool sans revue. La principale limite observée est
un faux positif « audio dégradé » (`billcor-small-acts-of-love-4a8526`) qui obtient
des scores acoustiques et Audiobox élevés : les métriques seules ne suffisent pas.

## Périmètre et séparation

- 200 sources IAMD et 586 passages déjà locaux ; aucun téléchargement ni modification
  de benchmark n'a été effectué.
- Les 150 sources de l'extension restent séparées par `source_key` : 74 calibration,
  26 validation interne, 50 prospectives. Les 50 prospectives et leurs annotations
  ne servent pas au réglage v2.
- Les 28 avis incomplets restent inconnus et ne sont jamais comptés comme positifs.
- Les droits et la provenance restent dans `rights` et ne participent pas au score
  acoustique. Un `auto_accept` n'est donc pas une autorisation de redistribution.

L'apparente contradiction entre « 6/6 acceptations correctes » et le faux positif
`hifidelity_potpourri` vient de partitions différentes. Les 6/6 concernent les 50
prospectives, évaluées avec la v1 gelée, après correction de l'écoute de
`JenniferGreerAtTheNaveMay32008`. Le faux positif historique et les deux faux
acceptés de calibration (`POWERInspiredRichHomieQuanTypeBeat.` et
`billcor-small-acts-of-love-4a8526`) appartiennent à la cohorte de calibration, pas
à cette mesure prospective.

## Changements implémentés

1. `enrich-acoustics` recalcule sur les clips locaux des descripteurs bornés et
   reprisables : roll-off 95 %, variabilité inter-trames, marge bruit/signal et
   fraction de bande passante, en plus des descripteurs historiques. Le cache v1
   n'est pas écrasé.
2. La politique `clean-music-v2` agrège tous les passages. Les signaux Audiobox,
   AST, CLAP et qualité technique restent explicables ; les indices MIDI/test tone,
   `type beat` et contexte de production envoient en revue sans bannir la musique
   électronique, ambient ou live.
3. Les proxies de noise floor et de variabilité temporelle sont conservés pour
   l'analyse, mais ne sont pas des veto : sur la calibration disponible, leurs
   distributions se recouvrent trop entre positifs et négatifs.
4. Les annotations acceptent désormais `capture_quality`, `degradation_reason` et
   `provenance`, indépendamment de `content_type`, `audio_quality` et
   `source_nature`. La file `active_review_queue_v2.jsonl` priorise les 28 avis
   incomplets, les désaccords inter-passages et les scores proches de la frontière.

## Comparaison quantitative

| Approche | Split | Revue | Acceptations binaires | Précision accept. | Mauvaises acceptations | Bons rejets |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v1 | calibration | 86,5 % | 6 | 66,7 % | 6,1 % des négatifs | 0,0 % |
| v2 avec enrichissement | calibration | **73,0 %** | 11 | **81,8 %** | 6,1 % des négatifs | 0,0 % |
| v2 sans enrichissement | calibration | 68,9 % | 10 | 70,0 % | 9,1 % des négatifs | 4,5 % |
| v1 | validation interne | 88,5 % | 0 | non estimable | 0,0 % | 0,0 % |
| v2 avec enrichissement | validation interne | **61,5 %** | 3 | 66,7 % | 9,1 % des négatifs | 0,0 % |

Sur les 200 sources, v2 produit 51 `auto_accept`, 137 `manual_review` et 12
`auto_reject` ; ces chiffres incluent les sources non annotées et ne constituent
pas une précision. La v1 produisait 25 `auto_accept`, 174 `manual_review` et 1
`auto_reject` sur le même ensemble. La couverture augmente donc nettement, mais
la validation interne expose déjà un mauvais accept (`DaVinylBoxDemo`) et la
calibration deux mauvais acceptés (`barely_a_fleshwound` et
`billcor-small-acts-of-love-4a8526`). Les intervalles de Wilson et les clés exactes
sont dans `build/curation/iamd/evaluation/v2/evaluation_v2.json`.

La v2 sans enrichissement accepte presque autant et rejette davantage certains
cas, tandis qu'elle rejette un bon clip (`JossbergWhenIDream`). L'enrichissement
apporte donc un garde-fou utile sur des cas techniques sévères, mais les nouveaux
proxies ne justifient pas à eux seuls un seuil de qualité ou une acceptation.

## Erreurs et limites

- Audiobox, AST et CLAP identifient bien une partie des non-musiques et des cas très
  faibles, mais ils peuvent donner un score élevé à une production rudimentaire ou
  à une captation dégradée.
- `type beat` est maintenant un motif de revue, pas un rejet automatique.
- Le bruit, la dynamique et le roll-off peuvent refléter un choix artistique ou un
  passage musical dense ; aucun de ces signaux ne doit être un veto isolé.
- Les 100 annotations disponibles ont été vues en agrégat avant le gel du split :
  la validation interne n'est pas une validation indépendante forte.
- Aucune généralisation à AlbumDB, MUSDB ou à une redistribution publique n'est
  démontrée.

## Recommandation

**Ne pas intégrer automatiquement les 51 acceptations au clean pool.** La v2 est
utile pour réduire la file de revue et rejeter des cas manifestement inutilisables,
mais un rendement automatique réellement sûr n'est pas encore démontré. Pour la
prochaine itération, clarifier les 28 avis incomplets puis annoter un nouveau lot
indépendant, stratifié par genre/collection/créateur et enrichi en cas
`Audiobox élevé + écoute dégradée`. Une politique à seuil très conservateur peut
viser une précision d'acceptation proche de 100 % sur la calibration, au prix d'une
couverture faible ; il faut mesurer ce compromis sur ce nouveau lot avant tout
changement de corpus ou de licence.

## Artefacts

- `build/curation/iamd/features_acoustic_v2.jsonl` — cache enrichi local, 200 sources.
- `build/curation/iamd/decisions_v2.jsonl` — décisions, segments, motifs et droits séparés.
- `build/curation/iamd/evaluation/v2/evaluation_v2.{json,md}` — comparaison et ablation.
- `build/curation/iamd/evaluation/v2/active_review_queue_v2.jsonl` — file d'active learning.

