# IAMD → Archive : pilot privé Phase 2 (contenu, qualité, nature)

**Mise à jour :** le lot de 200 sources est maintenant engagé avec validation
aveugle des 150 nouvelles ; voir [le rapport de pilot 200](iamd_phase2_200_pilot.md).
Les chiffres de 50 ci-dessous décrivent le premier lot historique.

Ce pilot **ne télécharge aucun audio lors de sa préparation**, ne touche pas aux
manifests du benchmark et n'autorise aucune redistribution. IAMD reste le
catalogue ; seul un original Archive WAV/FLAC/AIFF explicitement
`source=original` peut ensuite être écouté. Les MP3 IAMD/Hugging Face et les
dérivés Archive ne sont jamais des sources clean de ce pilot.

## Plan figé

La Phase 1 donne 11 945 candidats, 11 913 items Archive résolus, 2 324
`technical_candidate`, 1 851 `provenance_candidate`. Les deux derniers termes
sont des niveaux de **métadonnées**, pas des certificats de qualité ni de droit.
Les 32 réponses Archive en échec et les 9 589 items résolus sans original strict
ne font pas partie de la population d'inférence du pilot.

Le plan offline dans `build/iamd_feasibility/phase2_pilot/` sélectionne **750
identifiants uniques** parmi ces 2 324 ; une seule piste originale par item.
Il couvre 65 collections et 601 créateurs déclarés : 459 WAV, 276 FLAC,
15 AIFF. Les métadonnées annoncent environ **50,5 h** et **29,7 Gio** pour les
750 fichiers retenus ; ces chiffres décrivent le plan, **pas** les fichiers
téléchargés. 535/750 sont aussi candidats de provenance Phase 1. Les lots
`smoke_50` et `expand_200` ont été autorisés séparément ; les 550 autres
restent non lancés.

Le tirage crée des strates « douze plus grandes collections + autres » ×
**genre-proxy**. Le genre déclaré manque pour 2 317/2 324 items techniques ;
les tags/subjects servent donc de proxy faible, avec catégories `unknown` et
`multi_genre` explicites. Dans chaque strate, les groupes de créateurs sont
tirés sans remise, puis un item par créateur ; le plan contient pour chaque
item sa probabilité d'inclusion et son poids inverse. Un créateur inconnu est
traité comme inconnu par item, pas comme un seul artiste géant. Le but est de
couvrir autant que possible collections, styles et créateurs **sans exclure
préventivement** les styles électroniques ou expérimentaux. La première
tranche de 50 couvre volontairement les dix genres-proxy et les principales
collections ; elle n'est pas représentative à elle seule pour estimer un
rendement. Seul le pilot complet permet l'estimation pondérée. Les poids sont
très inégaux (taille effective d'environ **173** pour 750 tirés) : le résultat
reste exploratoire et doit être confirmé si proche d'une décision GO/NO-GO.

Fichiers préparés :

- `plan.json` : population, coûts déclarés, strates et limites ;
- `selection.jsonl` : identifiant, fichier original, licence déclarée, URL,
  taille, durée, SHA1/MD5, collection, créateur, genre-proxy, poids, lot ;
- `metadata_review_queue.jsonl` : signaux de métadonnées à inspecter ;
- `review_template.csv` : une ligne humaine par identifiant.

La sélection est divisée en `smoke_50`, `expand_200` (150 de plus), puis
`full_pilot` (550 de plus). Les 50 puis les 150 supplémentaires ont été
lancés sur demandes distinctes ; **le lot de 750 ne se lance jamais
automatiquement**. Faire une pause après l'écoute des 200 avant d'envisager
les transferts suivants. Le fichier le plus
gros annoncé dépasse 1 Gio ; prévoir des plafonds réels d'octets et de temps
et relever les non-réponses séparément des rejets.

## Trois axes indépendants

Chaque identifiant reçoit trois annotations distinctes. Les métadonnées et
métriques servent au *ranking* de revue, jamais de vérité terrain.

| Axe | Valeurs / mesures | Décision |
| --- | --- | --- |
| `content_type` | `music`, `speech_dominant`, `noise_or_sound_effect`, `ambiguous` | Écoute humaine ; un titre « music » ne suffit pas à valider la qualité. |
| `audio_quality` | `acceptable`, `degraded`, `ambiguous` ; flags silence/quasi-silence, écrêtage excessif, cutoff suspect, PQ faible, autre | Contrôles par extraits début/milieu/fin ; aucun seuil isolé ne rejette. |
| `source_nature` | `likely_real_recording`, `likely_midi_or_synthetic_render`, `ambiguous` | Métadonnées d'abord, écoute ensuite ; jamais un seul modèle. |

Ici `likely_real_recording` signifie **production musicale authentique**, y
compris une production électronique légitime, et non « forcément captée par un
micro ». `likely_midi_or_synthetic_render` vise plutôt les rendus simples de
séquences, soundfonts, trackers, tests de tonalité, etc. Les indices `midi`,
`soundfont`, `tracker`, `sequence`, `test tone`, `sound effect` dans titre,
description, subject, collection, créateur ou nom de fichier signalent des
cas **à vérifier**. « Electronic » seul ne déclenche jamais cette étiquette.
Le premier lot de 50 n'utilisait pas CLAP ; le [pilot de 200](iamd_phase2_200_pilot.md)
l'ajoute comme signal contrastif de priorité d'écoute, jamais comme vérité
terrain. PANNs/YAMNet ne sont pas nécessaires à ce pilot.

La Phase 1 a conservé `subject` dans le cache Archive, mais pas
`description`. Le plan importe `subject` du cache. Pour compléter la revue de
métadonnées, la commande suivante est préparée : elle ne demande que les
**métadonnées des 750 items sélectionnés**, reprend après erreur et n'accède
à aucune URL audio. Elle a été exécutée sur les 750 items : **750/750 résolus**,
746 descriptions présentes, quatre absentes. Son journal se trouve dans
`metadata_enrichment.jsonl`. Les indices textuels produits sont 14 cas à
revoir côté séquence/MIDI/tracker, 36 indices de captation réelle et 24 indices
de parole/effets (catégories non exclusives et **non rejetées**) :

```bash
python3 scripts/iamd_phase2_pilot.py enrich-metadata --max-items 50
# Puis, après vérification : même commande sans --max-items.
```

Le téléchargement **autorisé et borné** des seuls `smoke_50` utilise
`download-smoke` : reprise `.part`, vérification taille et SHA1/MD5 avant
promotion, journal incrémental `download_status.jsonl`. Le contrôle local
vérifie encore taille et SHA1/MD5,
ouvre le vrai format, et mesure des passages de début/milieu/fin : fréquence
d'échantillonnage, canaux, durée, pic/RMS, quasi-silence, écrêtage, bande
passante indicative, plancher, flatness. Les passages FLAC sont rangés dans
`clips/` pour écoute. Les quatre axes Audiobox (CE/CU/PC/PQ) sont mesurés hors
ligne sur la fenêtre centrale de 10 s de l'extrait médian de chaque source ;
ce sont des indicateurs partiels, pas des scores pour toute la piste. Cutoff,
écrêtage, silence et PQ sont des
indices calibrés ensuite sur des écoutes, pas des critères définitifs par
défaut.

```bash
.venv/bin/python scripts/iamd_phase2_pilot.py download-smoke
.venv/bin/python scripts/iamd_phase2_pilot.py measure-smoke
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_phase2_pilot.py pq-smoke
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_phase2_pilot.py aesthetics-excerpts-smoke
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_phase2_content_probe.py
python3 scripts/iamd_phase2_smoke_review.py
```

La sonde AudioSet AST est facultative : elle télécharge uniquement ses poids
de modèle sous `build/metric_tools/hf_cache`, puis étiquette la même fenêtre
centrale de 10 s des extraits déjà présents. Ses scores multi-étiquettes
« Music »/« Speech » ne sont **pas des
probabilités calibrées** et ne définissent aucun seuil de rejet. Les indices
textuels `field recordings`, micro interne, capture live/rehearsal, game OST
et oscillateurs servent aussi à prioriser la revue ; une musique électronique
ou live n'est jamais rejetée pour son seul genre ou contexte.
La commande `aesthetics-excerpts-smoke` conserve les quatre axes par passage
de 24 s (fenêtre centrale de 10 s) et ajoute dans la liste d'écoute le minimum,
la médiane et le maximum de PQ, pour voir si une seule fenêtre masquait un
passage dégradé.

Le dossier privé `build/iamd_feasibility/phase2_pilot/` contient ensuite
`smoke_measurements.jsonl` (scores par source et mesures par extrait),
`listening.csv` (liste et chemins) et `listening.html` (jusqu'à trois lecteurs par
source et trois axes d'annotation indépendants). Ouvrir le HTML localement,
exporter `iamd_phase2_smoke_reviews.csv` après écoute et conserver ce fichier.
Les motifs de revue suggérés sont modifiables ; ils ne rejettent rien. Le
rapport provisoire `smoke_report.md`/`.json` donne seulement le rendement
technique observé sur 50, pas un rendement clean ni une extrapolation.
Après export des annotations, le rendement audio clean observé sur **ce lot
seul** se calcule par :

```bash
python3 scripts/iamd_phase2_smoke_review.py --reviews-csv /chemin/iamd_phase2_smoke_reviews.csv
```

Tant que les 50 lignes n'ont pas leurs trois axes, le taux clean reste non
calculé (`null`), tandis que les motifs humains déjà annotés restent visibles.

Au premier passage : **50/50 originaux vérifiés par SHA1/MD5**, 2,00 Gio et
3,01 h de durée réelle ; 31 WAV, 18 FLAC, 1 AIFF ; 148 extraits,
50/50 sondes AST et 148/148 passages avec les quatre axes Audiobox.
La piste de 48 s n'a qu'un extrait central. Le lot représente 15
collections et 48 créateurs déclarés. La médiane PQ est 7,21 sur une fenêtre
centrale de 10 s par source. Douze licences/provenances sont à revoir : sept
provenances non validées et cinq licences Archive inconnues ; les 38 restantes
ne sont **pas** une autorisation de redistribution. Les signaux non exclusifs
proposent notamment 9 cutoffs suspects et 4 cas d'écrêtage à écouter. Huit
retours négatifs par source et huit avis positifs sur **un clip nommé** ont été
conservés séparément dans `manual_feedback_partial.jsonl` ; ils ne sont pas
des annotations complètes sur les trois axes, et le clip positif ne valide
pas tous les passages de sa source. Les 34 autres sources restent sans avis
explicite. Aucun rendement « musique clean » fiable n'est donc calculé.

Sur ces huit retours, les suggestions acoustiques ou de métadonnées (hors
droits) signalent les huit pour revue, mais aussi 16 des 34 sources sans
avis explicite ; deux des huit sources ayant un clip positif portent
également une alerte acoustique. Ce n'est ni une précision mesurée ni une
règle de rejet. La comparaison détaillée des clips nommés se trouve dans
`build/iamd_feasibility/phase2_pilot/listening_feedback_calibration.md`.
Le PQ rate notamment deux captations jugées lointaines : environ 8,0 pour
Mystic Folk et 7,0 pour le piano, même après trois passages. Le seuil
« Music » de la sonde AST raterait aussi une piste chantée : 0,04 pour
HoraceIII22. Ces modèles servent à prioriser l'écoute et doivent être
calibrés sur des exemples positifs et négatifs explicitement annotés.

Le rapport pondéré du pilot complet, **non lancé**, reste accessible après
revue des 750 par :

```bash
python3 scripts/iamd_phase2_pilot.py report --reviews-csv /chemin/revue.csv
```

`report.json`/`report.md` produisent, après revue, les rejets par motif
non exclusif, les distributions des trois axes et de PQ (quantiles), les
collections et créateurs prometteurs/problématiques avec leurs effectifs,
une liste des cas ambigus à écouter, et une estimation pondérée du nombre
d'`identifier` qui passeraient les filtres audio, avec borne « ambigus
possibles ». Pas d'extrapolation si les 750 n'ont pas tous été revus et
mesurés avec PQ. Les échecs de téléchargement/lecture restent des
**non-réponses** ; ils ne doivent pas être comptés comme mauvais contenus.
Les résultats par créateur avec moins de trois pistes revues sont des pistes
de suivi, pas des conclusions ; prévoir une contre-vérification ciblée.

Même un bon rendement audio ne transforme pas `redistributable_candidate`
en autorisation de diffusion. Vérifier séparément l'identité du titulaire,
l'attribution exacte et les droits de redistribution/adaptation avant toute
release. Un verdict GO Phase 2 signifierait seulement qu'un corpus clean
généraliste **semble techniquement et qualitativement plausible** ; il ne
déclenche ni les 11 945 téléchargements ni une publication.
