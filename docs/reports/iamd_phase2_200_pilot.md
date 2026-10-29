# IAMD → Archive : pilot de 200, validation aveugle

Ce pilot étend les 50 premiers `identifier` par les **150 identifiants déjà
stratifiés** dans `selection.jsonl` (`pilot_batch=expand_200`). Aucun item du
lot `full_pilot` de 550 autres n'est téléchargé ou mesuré ; aucun pipeline
d'entraînement ni manifest du benchmark n'est modifié. IAMD demeure un
catalogue. Les entrées audios sont seulement des originaux Archive
`source=original` WAV/FLAC/AIFF avec taille et SHA1 ou MD5 vérifiés ; aucun MP3
IAMD/Hugging Face, dérivé Archive ou fallback MP3 n'est admis.
Le fichier de sélection est trié par identifiant, **pas** par lot : les outils
filtrent explicitement `pilot_batch` et ne prennent jamais les 200 premières
lignes.

Le sous-lot nouveau couvre **150 identifiants uniques**, 28 collections, 139
créateurs déclarés et les dix catégories de genre-proxy de ce plan (dont 39
`unknown`, 29 `multi_genre`, 2 `classical`). Les métadonnées prévoyaient
5,22 Gio, confirmés après vérification des 150 originaux (89 WAV, 55 FLAC,
6 AIFF). La durée réellement lue est **8,81 h** nouvelles, **11,82 h** pour
les 200 ; 438 nouveaux passages d'écoute ont été extraits. La plus grande
collection, `opensource_audio`, compte 69/150 nouvelles sources ; viennent
`hifidelity_potpourri` (24) et `cratediggers` (11). Les répartitions sont
voulues diverses, pas représentatives par proportion naturelle de toutes
les sources IAMD. L'inférence de rendement global à partir de ces 200
serait abusive.
Le recoupement avec les 330 `identifier` connus de Blind-Real reste nul.

## Signaux et règle gelée

- Audiobox Aesthetics : CE/CU/PC/PQ sur la fenêtre centrale de 10 s du passage
  médian, puis les quatre axes sur les autres passages ; les valeurs couvrent
  des fenêtres, pas toute la piste.
- AST AudioSet : indices multi-étiquettes musique/parole et top labels sur
  la même fenêtre centrale ; ce ne sont pas des probabilités calibrées.
- CLAP `laion/clap-htsat-unfused`, révision
  `8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a` : similarités cosinus
  relatives à cinq familles de quatre descriptions chacune. Les familles
  opposent musique produite, musique dégradée, non-musique/parole/bruitages,
  test ou séquence synthétique rudimentaire, et **musique électronique
  légitime**. Les prompts exacts sont dans
  `scripts/iamd_phase2_clap_probe.py`. CLAP n'est ni un estimateur de qualité
  certifié ni une preuve de nature réelle/synthétique.
- Mesures acoustiques : fréquence, correspondance du format, durée,
  quasi-silence, clipping, bande passante indicative, RMS, pic, bruit de fond,
  crest factor et flatness. Métadonnées Archive/IAMD : indices de parole,
  bruitages, contexte de captation et rendus rudimentaires. `live` et
  `electronic` ne sont jamais des rejets en soi.

Sur les 150 nouvelles sources, les médianes de la fenêtre centrale sont
CE 6,44, CU 7,24, PC 5,73 et PQ 7,29 ; la médiane des **minimums** de PQ
par source sur les passages disponibles est 6,76. Ces résumés de modèles
ne sont pas des notes humaines. Les contrôles lisent zéro format contradictoire,
un original WAV à 8 kHz, 28 sources avec bande passante médiane sous 12 kHz
et six sources avec au moins un passage dépassant 0,5 % de samples écrêtés.
Ces dernières alertes ne sont pas des rejets isolés.

La règle `pilot-200-conservative-v1` propose `accept_candidate`, `review` ou
`reject_candidate`, toujours avec scores et motifs. Un cas n'est proposé au
rejet pour contenu non musical/rendu rudimentaire qu'avec plusieurs signaux
concordants ; un PQ bas ou un faible « AST Music » seul envoie en revue. Les
alertes légales restent **séparées** : `accept_candidate` n'est en aucun cas
une autorisation de réutilisation ou redistribution. Sur les 150 nouveaux,
136 licences Archive sont classées compatibles par métadonnées et 14
inconnues ; 108/150 ont une provenance plausible. Même les 108 ne sont pas
« rights-cleared ».

Les 16 avis actuels sur les 50 premières sources servent uniquement de
calibration : huit problèmes par source, huit avis positifs sur un clip
précis. Sur eux, la règle v1 propose 15 acceptations, 34 revues et un rejet ;
aucun des huit cas problématiques n'est accepté, mais seules quatre des huit
sources portant un bon clip sont proposées à l'acceptation. Ces chiffres sont
**in-sample** et ne constituent pas une estimation de performance.
CLAP seul ne sépare pas convenablement qualité et contenu sur ces exemples :
`MysticFolkAtTheNave`, jugé lointain, classe « musique produite » en tête,
alors que le bon extrait de `WSETheAll.ENOTHROYRWSEReinterpretation` place
« musique dégradée » légèrement devant. Les similarités relatives ne sont
donc jamais converties en rejet automatique isolé.
Sur les 150 nouvelles, avant toute écoute humaine, la famille CLAP en tête
est « musique produite » pour 57, « électronique légitime » pour 41,
« rendu rudimentaire » pour 25 et « musique dégradée » pour 27 ; la famille
« non-musique » n'arrive jamais première. Cela ne démontre pas l'absence de
bruitages/parole : cette famille de prompts n'est manifestement pas un bon
détecteur autonome dans cette configuration. AST et les métadonnées restent
des signaux indépendants de revue.

Prédictions gelées sur les **150 nouvelles** : 49 `accept_candidate`, 101
`review`, zéro `reject_candidate`. La charge de revue provisoire est donc
**67,3 %**, trop élevée pour prétendre déjà à une sélection largement
automatique avec revue humaine limitée. Les motifs de revue les plus
fréquents (non exclusifs) sont CLAP non positif ou contraste serré (59),
Audiobox contenu/qualité (57), cutoff suspect (27), AST musique/parole (26)
et métadonnées de contenu/captation (19). Aucun des 150 n'a été annoté
humainement au moment du verrouillage : ces chiffres ne disent rien encore
sur les faux rejets, les mauvais sons acceptés ni le rendement clean réel.
Parmi les 49 acceptations **acoustiques**, 37 ont seulement une provenance
plausible dans les métadonnées, dix une provenance non validée et deux une
licence Archive inconnue ; aucune n'est autorisée à la redistribution par ce
score.

Répartition **des propositions acoustiques**, pas du rendement humain :

| Genre-proxy | Sources nouvelles | `accept_candidate` | `review` |
| --- | ---: | ---: | ---: |
| `unknown` | 39 | 14 | 25 |
| `multi_genre` | 29 | 6 | 23 |
| `electronic_dance` | 21 | 11 | 10 |
| `ambient_experimental` | 20 | 1 | 19 |
| `rock_metal` | 15 | 7 | 8 |
| `hiphop_rap` | 8 | 3 | 5 |
| `jazz_blues` | 7 | 3 | 4 |
| `folk_acoustic` | 6 | 3 | 3 |
| `pop` | 3 | 1 | 2 |
| `classical` | 2 | 0 | 2 |

Dans les trois plus grandes collections : `opensource_audio` 29/69 proposés
à l'acceptation, `hifidelity_potpourri` 8/24, `cratediggers` 6/11. Ce ne
sont pas des taux de musique clean ; les retours aveugles doivent encore
établir les faux rejets, les faux maintiens et le rendement de chaque groupe.

Avant la revue des 150 nouveaux, le script écrit une prédiction immuable par
source dans `pilot_200_predictions_locked.jsonl` et un
`pilot_200_rules_lock.json` contenant l'empreinte SHA-256 du code de règle et
les révisions des modèles/prompts. Il refuse de régénérer silencieusement ces
prédictions si la règle change. Un CSV à colonnes plates fournit le tri et
les valeurs par source. La [fiche de choix des licences](../licensing.md)
n'est pas remplacée par ce classement acoustique.

## Protocole d'écoute et évaluation

`listening_150_blind.html` montre **un extrait médian en premier**, identique
à la fenêtre AST/CLAP ; les passages début/fin sont accessibles sous un volet.
Le classement automatique est caché pour ne pas influencer les étiquettes.
Contenu, qualité, nature et adéquation au clean pool sont saisis séparément.
L'export CSV précise si seul le clip principal, plusieurs passages ou
l'original entier ont été écoutés. Un bon clip n'est jamais transformé par le
rapport en validation de la source entière.

Après l'export du CSV, exécuter :

```bash
.venv/bin/python scripts/iamd_phase2_200_review.py \
  --reviews-csv /chemin/iamd_phase2_150_blind_reviews.csv
```

Le rapport `pilot_200_validation_report.md`/`.json` ne compte **que les 150
nouveaux** pour les faux rejets potentiels de bons clips, les clips dégradés
proposés à l'acceptation, la charge de revue et les répartitions par
genre-proxy et collection. Tant que les 150 ne sont pas annotés, il indique
explicitement `validation_complete=false` et ne donne pas de verdict de
fiabilité ni de rendement des sources entières. Les estimations par groupe
portent seulement sur les clips revus, sans extrapolation à IAMD.

Une revue partielle peut être analysée sans remplir les quatre axes :

```bash
.venv/bin/python scripts/iamd_phase2_sparse_review.py \
  --reviews-csv build/iamd_phase2_150_blind_reviews.csv
```

Le rapport `pilot_200_partial_review.md`/`.json` traite chaque champ vide comme
« non évalué », compte séparément les axes renseignés et signale les
acceptations automatiques contredites par un avis explicite. Il ne modifie ni
la règle gelée, ni les prédictions, ni le CSV original. Le rapport de
validation complète ci-dessus reste réservé à une revue complète.

## Commandes bornées utilisées

```bash
.venv/bin/python scripts/iamd_phase2_pilot.py download-expand-200 --workers 3
.venv/bin/python scripts/iamd_phase2_pilot.py measure-200
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_phase2_pilot.py pq-200
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_phase2_pilot.py aesthetics-excerpts-200
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_phase2_content_probe.py --total-sources 200
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_phase2_clap_probe.py --total-sources 200
.venv/bin/python scripts/iamd_phase2_200_review.py
```

Les résultats locaux résident sous `build/iamd_feasibility/phase2_pilot/`
et ne sont pas des assets de release. Ne pas lancer le lot de 750 sans accord
explicite après la revue aveugle.
