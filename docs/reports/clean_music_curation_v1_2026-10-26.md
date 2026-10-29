# Curation clean multi-datasets — état de la v1 (26 octobre 2026)

## Verdict

La pipeline locale est opérationnelle et réutilisable, mais **le tri automatique
fiable n'est pas encore démontré**. Le manifest produit aujourd'hui est un
ensemble de candidats acoustiques, pas un clean pool prêt à intégrer ou à
redistribuer. Aucun seuil n'a été ajusté sur la validation interne ; les
mesures de celle-ci sont trop peu nombreuses pour certifier les acceptations.
Pas de téléchargement massif ni de modification des benchmarks/datasets gelés.

## Données, séparation, portée des labels

- 200 originaux lossless du pilot IAMD déjà locaux ; 586 passages, chacun avec
  Audiobox Aesthetics, AST et CLAP. Les modèles additionnels ont été exécutés
  **offline** sur les passages qui en manquaient, sans erreur de probe.
- Les 150 sources de l'extension ont un CSV : 100 avec retour humain explicite,
  dont 28 bons clips (`music` + `acceptable` sans contradiction), 44 indices
  négatifs et 28 avis incomplets/ambigus. Les 50 autres sont **non annotées**,
  jamais des positifs par défaut. Les retours antérieurs sur le premier lot de
  50 restent hors de cette évaluation chiffrée.
- Split source-groupé figé : 74 calibration (22 positifs, 33 négatifs, 19
  incomplets), 26 validation interne (6, 11, 9) et 50 validation prospective
  encore aveugle. Les annotations disponibles concernent le plus souvent le
  passage central, pas le fichier entier.
- Les 100 étiquettes avaient déjà été consultées en agrégat avant le gel de ce
  split : la « validation interne » n'est donc **pas une preuve indépendante
  forte**. La vraie vérification prospective reste les 50 sources non annotées.

## Ce qui discrimine — calibration uniquement

Le meilleur signal univarié est PC (AUC 0,815), puis PQ (0,766), CU (0,747),
CE (0,742) et la bande passante (0,697). Ces AUC sont descriptives sur 22
positifs et 33 négatifs, sans intervalle de confiance et sans valeur de seuil
universelle. Les distributions se chevauchent largement : PC médian 6,32
contre 4,61 ; PQ 7,64 contre 6,75. AST Music (AUC 0,525) et les marges CLAP
musique/non-musique (0,565) et musique/rendu rudimentaire (0,457) ne séparent
pas bien ces cas difficiles. La présence de voix, de texture bruitée ou de
sons électroniques ne prouve pas une mauvaise référence musicale.

Les mesures de clipping et bande passante renseignent la qualité technique,
mais pas le caractère « vraie production musicale ». Les proxies de souffle,
hum, dynamique et roll-off sont calculés par l'extracteur générique ; le cache
historique IAMD n'a pas ces colonnes, donc ils n'ont pas été utilisés pour
calibrer cette évaluation. Leur interprétation exige de distinguer intention
artistique et défaut de capture.

## Comparaison des approches

| Approche | Split | Acceptés parmi labels binaires | Bons / mauvais parmi eux | Bons rejetés | Revue humaine |
| --- | --- | ---: | ---: | ---: | ---: |
| Règle pilot figée | calibration | 15 | 10 / 5 | 0 / 22 | 66,2 % |
| v1 multi-passages | calibration | 6 | 4 / 2 | 0 / 22 | 86,5 % |
| Logistique L2 diagnostique | calibration | 2 | 2 / 0 | 0 / 22 | 85,1 % |
| Règle pilot figée | validation interne | 5 | 4 / 1 | 0 / 6 | 65,4 % |
| v1 multi-passages | validation interne | **0** | non estimable | 0 / 6 | 88,5 % |
| Logistique L2 diagnostique | validation interne | **0** | non estimable | 0 / 6 | 92,3 % |

La v1 accepte aussi 3 avis incomplets en calibration et 3 en validation. Ces
cas ne sont pas inclus dans les dénominateurs de précision ; ils doivent être
réécoutés. La précision apparente de 4/6 en calibration a un intervalle de
Wilson 95 % d'environ **30–90 %**. Le 0/6 rejet de bons clips ne démontre pas
une faible perte : presque tous les cas sont envoyés en revue. La petite
régression logistique, entraînée sur 55 labels binaires et 9 features centrales,
n'est qu'un diagnostic ; aucun réentraînement lourd ni déploiement comme gate.

Le sweep du seuil de score, effectué **seulement sur calibration**, montre le
coût du compromis : à 0,65, 10 acceptations étiquetées dont 3 mauvaises et
78,4 % de revue ; à 0,78 (v1), 6 dont 2 mauvaises et 86,5 % de revue ; à 0,90,
2 dont 0 mauvaises mais 95,9 % de revue. Ce dernier point n'est pas une
preuve de précision : l'échantillon est minuscule et le seuil n'a pas été
retenu comme nouvelle règle.

Sur les 200 sources, la règle inchangée émet 25 `auto_accept`, 174
`manual_review` et 1 `auto_reject`. Les 25 acceptations ne sont **pas** 25
sources validées : 7 appartiennent aux 50 sources prospectives non annotées et
6 au premier lot de 50 non inclus dans cette évaluation chiffrée. La validation interne
ne contient aucune acceptation avec label binaire ; on ne peut pas estimer la
précision hors calibration. Le taux d'automatisation actuel est donc trop bas
pour atteindre le critère « peu de revue humaine ».

Les deux faux acceptés v1 de calibration illustrent la limite : un beat jugé
rudimentaire et une piste jugée dégradée ont pourtant de bons scores PC/PQ,
AST Music et CLAP musique. Les erreurs restantes sont dans `opensource_audio`
(2 faux acceptés sur 35 sources de calibration de cette collection) ; cela
ne permet **pas** de condamner la collection entière. Les groupes genre/créateur
sont trop petits pour mesurer des performances stables ; le JSON détaille
chaque groupe et type de contenu. Les faux acceptés de l'ancienne règle
comprenaient trois rendus rudimentaires et deux dégradés en calibration.

## Architecture et garde-fous

`openrestor/curation` lit des manifestes locaux communs à IAMD/AlbumDB/MUSDB,
extrait les passages et features avec cache/reprise, applique des probes offline
et une règle explicable par passage puis par source. Le manque d'un modèle
entraîne `manual_review`; un seul PQ/AST faible ne rejette pas une piste.
L'interface HTML d'écoute peut être aveugle et exporter des annotations sparse.
Le score ne dépend jamais de `rights` ; un candidat acoustique conserve
`redistribution_approved=false`. Il faut encore une validation juridique et
une vérification de la source avant tout clean pool public.

Artefacts locaux :

- `build/curation/iamd/features_probed.jsonl` — 200 sources / 586 passages ;
- `build/curation/iamd/decisions_v1.jsonl` — décisions et motifs ;
- `build/curation/iamd/evaluation/evaluation.md` et `evaluation.json` — chiffres,
  Wilson, détails par genre/collection/créateur et type de contenu ;
- `build/curation/iamd/evaluation/split_locked.jsonl` — split figé par source ;
- `build/curation/iamd/evaluation/active_review_queue.jsonl` — 28 avis
  incomplets à clarifier ;
- `build/curation/iamd/evaluation/prospective_blind_listen.html` — page pour
  annoter les 50 sources tenues à l'écart ;
- `build/curation/iamd/acoustic_candidates_v1.jsonl` — 75 clips de 25 sources,
  **candidats acoustiques seulement**, non approuvés côté droits.

## Prochaine décision, sans surajustement

Écouter à l'aveugle les 50 sources prospectives : passage central de chacune,
plus tous les passages des 7 sources proposées en `auto_accept` (et des cas
discordants). Enregistrer explicitement la portée du jugement. Ne modifier ni
les seuils ni les prompts en fonction de ce lot avant de rapporter sa précision
et les faux rejets. Si l'estimation reste incertaine, compléter les 28 avis
ambigus pour enrichir la calibration, puis collecter **un nouveau** jeu
indépendant stratifié par genre/collection et enrichi en contradictions entre
signaux. À ce stade, privilégier une file de revue humaine ciblée et ne pas
intégrer automatiquement les 25 sources au clean pool.

## Résultat prospectif des 50 écoutes (27 octobre 2026)

Le CSV `build/curation_reviews.csv` contient 50 sources uniques. Il a été
évalué après gel de `decisions_v1.jsonl`, sans retoucher les seuils : 21 clips
positifs, 28 négatifs et 1 avis incomplet. La règle v1 produit 7
`auto_accept` et 43 `manual_review`.

Sur les 6 acceptations ayant une étiquette binaire, les 6 sont bonnes :
précision observée 100 %, intervalle de Wilson 95 % **61,0–100 %**. Aucun
audio négatif n'est accepté (0/28 ; borne haute Wilson **12,1 %**). Aucun bon
clip n'est automatiquement rejeté (borne haute Wilson **15,5 %**). Un des 7
`auto_accept` a un avis incomplet et ne doit pas être compté comme positif.

La correction de l'écoute pour `JenniferGreerAtTheNaveMay32008` classe finalement
la source `music` et `acceptable`, en accord avec les scores Audiobox/AST/CLAP
(score source 0,900). Ce n'est donc plus un faux positif. Le cas incomplet
`in-this-world-full-of-attraction` est noté « AI generated » dans les notes,
mais `source_nature` n'a pas été renseigné : les notes ne doivent pas être
transformées automatiquement en étiquette, donc il reste en revue.

Par collection, `opensource_audio` donne 5 acceptations dont aucune mauvaise
(9 bonnes, 11 mauvaises au total) ; `hifidelity_potpourri` donne 2 acceptations
dont 1 mauvaise (5 bonnes, 6 mauvaises). Par genre, les acceptations sont
concentrées sur rock/métal (2), hip-hop (1), pop (1), multi-genre (1) et
inconnu (2). Les groupes restent trop petits pour en déduire des performances
par genre ou créateur.

### Décision technique

Le résultat est meilleur que la calibration et que le pilot précédent pour la
contamination observée, mais **86 % des sources nécessitent encore une revue**.
La prochaine priorité est donc la stratégie de sélection et l'enrichissement
des labels, avant d'ajouter un modèle complexe :

1. conserver le score acoustique multi-passage et le rejet consensuel de
   non-musique ;
2. ajouter un drapeau explicite `source_nature`/`provenance` pour les notes
   comme « AI generated », au lieu de les laisser non structurées ;
3. créer une catégorie de revue « qualité dégradée malgré contenu musical » et
   collecter davantage de cas contradictoires Audiobox élevé + écoute dégradée ;
4. améliorer les features de capture (distance, souffle/hum, cutoff,
   multi-passage) et ne tester un petit modèle supervisé qu'après davantage
   d'annotations ;
5. ne pas abaisser les seuils pour augmenter le rendement : la validation donne
   actuellement zéro faux rejet observé, mais avec une borne haute non
   négligeable et un volume trop faible.

Le rapport machine complet, avec intervalles, erreurs par genre/collection/
créateur et la liste exacte des erreurs, est dans
`build/curation/iamd/evaluation/prospective_evaluation.json` et `.md`.
