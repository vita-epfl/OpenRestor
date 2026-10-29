# Curation de musique clean — v1 locale

Cette pipeline classe des **candidats acoustiques**, sans autoriser leur emploi
ou redistribution. Les droits restent dans `rights` et ne participent jamais au
score. Elle ne télécharge aucun audio et ne modifie aucun benchmark gelé.

## Entrée commune aux datasets

Un manifest JSONL contient une ligne par source locale, par exemple :

```json
{"dataset":"albumdb","source_id":"album-123/track-4","audio_path":"/chemin/local/track.flac","metadata":{"title":"Titre","creator":"Artiste","genre":"rock","collection":"AlbumDB"},"rights":{"status":"unreviewed","license_url":null}}
```

`dataset` et `source_id` identifient le groupe de passages. Les formats acceptés
sont WAV, FLAC et AIFF détectés dans le fichier même, pas dans son extension.
Les MP3/réencodages ne sont pas importés comme clean lossless. AlbumDB, MUSDB,
IAMD, etc. utilisent le même format d'entrée, mais leur disponibilité locale et
leurs droits doivent être établis séparément.

```bash
.venv/bin/python -m openrestor.curation.cli extract \
  --manifest build/curation/local_sources.jsonl \
  --clips-dir build/curation/clips \
  --out build/curation/features.jsonl

build/metric_tools/audiobox_cpu_venv/bin/python -m openrestor.curation.cli probe \
  --features build/curation/features.jsonl \
  --out build/curation/features_probed.jsonl \
  --models ast,clap,aesthetics

.venv/bin/python -m openrestor.curation.cli score \
  --features build/curation/features_probed.jsonl \
  --config configs/curation/clean_music_v1.yaml \
  --out build/curation/decisions.jsonl

.venv/bin/python -m openrestor.curation.cli export \
  --features build/curation/features_probed.jsonl \
  --decisions build/curation/decisions.jsonl \
  --out build/curation/acoustic_candidates.jsonl
```

`extract` lit trois passages de 24 s vers le début, milieu et fin lorsque la
durée le permet. Les clips et features utilisent un cache lié à la taille et à
la date de modification du fichier ; `probe` reprend les scores manquants et
force les modèles en mode offline. AST, CLAP et Audiobox doivent déjà être
installés et mis en cache. Une erreur de modèle reste visible dans
`probe_errors` et déclenche `manual_review`, jamais un faux score zéro.
Les indices textuels MIDI, soundfont, podcast, bruitage, etc. sont extraits des
métadonnées si `metadata_cues` n'est pas fourni ; « electronic », « ambient »
et « live » ne sont pas des motifs de rejet.

Les mesures de souffle/hum, dynamique et roll-off sont des **indicateurs**.
Elles ne peuvent pas à elles seules distinguer une texture intentionnelle
d'une dégradation. Les seuils de v1 se concentrent sur l'accord de plusieurs
signaux et restent configurables. `auto_reject` demande quasi-silence ou accord
AST + CLAP sur l'absence de musique ; un PQ faible isolé ne suffit pas.
`auto_accept` demande l'accord des passages échantillonnés, mais n'affirme pas
que le fichier entier est propre : l'évaluation actuelle n'en démontre pas
encore la précision. Le manifest exporté porte toujours
`acoustic_candidate_only=true` et `redistribution_approved=false`.

## Annotation et séparation des groupes

```bash
.venv/bin/python -m openrestor.curation.cli listen \
  --features build/curation/features_probed.jsonl \
  --blind \
  --out build/curation/listen.html

.venv/bin/python -m openrestor.curation.cli import-reviews \
  --features build/curation/features_probed.jsonl \
  --csv build/curation/curation_reviews.csv \
  --out build/curation/review_import.jsonl
```

La page garde les choix localement dans le navigateur et exporte un CSV ; `--blind`
cache les noms/métadonnées visibles, mélange l'ordre de façon reproductible et
n'affiche jamais les prédictions. Les champs sont facultatifs. Une
case vide signifie inconnu, pas « bon ». `scope` vaut par défaut
`primary_clip_only`; choisir `all_sampled_passages` seulement après avoir
écouté tous les passages. Les annotations d'extrait ne valident pas une source
entière. L'import accepte les CSV partiels et conserve motifs/notes ; les
valeurs hors vocabulaire et `source_key` inconnus échouent explicitement.

Pour le pilot IAMD, `import-iamd` réutilise les 200 sources et mesures déjà
calculées. `evaluate-iamd` verrouille le split par `source_id` dans
`split_locked.jsonl`, garde les 50 sources non annotées en prospectif, compare
la règle figée précédente, v1 et une petite régression logistique diagnostique
entraînée uniquement sur la calibration. Cette dernière n'est ni un gate de
release ni un modèle validé. Le rapport du pilot est
[`clean_music_curation_v1_2026-10-26.md`](reports/clean_music_curation_v1_2026-10-26.md).

Après l'écoute prospective, évaluer le CSV sans retoucher les seuils :

```bash
.venv/bin/python -m openrestor.curation.cli evaluate-prospective \
  --features build/curation/iamd/features_probed.jsonl \
  --decisions build/curation/iamd/decisions_v1.jsonl \
  --reviews-csv build/curation_reviews.csv \
  --locked-split build/curation/iamd/evaluation/split_locked.jsonl \
  --out-dir build/curation/iamd/evaluation
```

Cette commande sépare les 50 sources prospectives des 50 sources IAMD hors
cohorte, et produit `prospective_evaluation.md`/`.json`.

Avant un clean pool automatique, il faut écouter et étiqueter à l'aveugle les
50 sources prospectives, puis mesurer les taux d'erreur **sans retoucher la
règle sur ce jeu**. Les 28 avis incomplets peuvent être complétés en parallèle
pour améliorer la calibration, mais pas comptés comme positifs implicites.

## v2.1 conservatrice et validation indépendante

La v2.1 corrige le calcul des descripteurs no-reference (fenêtre centrée à la
fréquence d'origine, sans décimation aliasante) et ajoute des garde-fous
conservateurs PQ/CLAP/contenu. Ils empêchent une `auto_accept` mais ne rejettent
pas automatiquement la musique électronique, ambient ou live :

```bash
.venv/bin/python -m openrestor.curation.cli enrich-acoustics \
  --features build/curation/iamd/features_probed.jsonl \
  --out build/curation/iamd/features_acoustic_v2.jsonl
.venv/bin/python -m openrestor.curation.cli score \
  --features build/curation/iamd/features_acoustic_v2.jsonl \
  --out build/curation/iamd/decisions_v21.jsonl \
  --policy v21 --config configs/curation/clean_music_v21.yaml
```

Avant toute nouvelle annotation, les décisions utilisées pour l'analyse sont
gelées avec les hashes des features, de la configuration et du fichier de
décisions. Ne pas modifier ces fichiers gelés ; une modification nécessite un
nouveau suffixe/version :

```bash
.venv/bin/python -m openrestor.curation.cli freeze-predictions \
  --features build/curation/iamd/features_acoustic_v2.jsonl \
  --decisions build/curation/iamd/decisions_v2_corrected.jsonl \
  --policy v2 --label corrected-acoustic-v2 \
  --out build/curation/iamd/frozen/decisions_v2_frozen.jsonl
.venv/bin/python -m openrestor.curation.cli freeze-predictions \
  --features build/curation/iamd/features_acoustic_v2.jsonl \
  --decisions build/curation/iamd/decisions_v21.jsonl \
  --policy v21 --label conservative-v2.1 \
  --out build/curation/iamd/frozen/decisions_v21_frozen.jsonl
```

Chaque fichier possède un `.lock.json`. Le verrou est reproductible et refuse
un écrasement avec un autre contenu ; il indique aussi que la révélation des
prédictions est bloquée pendant l'annotation.

Les passages acceptés dans une source mixte peuvent être exportés pour écoute
avec `export-segments`; ils restent `partial_source=true`, acoustiques seulement
et sans approbation de redistribution. Le rapport détaillé est
[`clean_music_curation_v2_1_2026-10-27.md`](reports/clean_music_curation_v2_1_2026-10-27.md).

Le manifeste indépendant de 120 sources est préparé sans audio :

```bash
.venv/bin/python -m openrestor.curation.cli prepare-independent-validation \
  --items build/iamd_feasibility/items.jsonl \
  --catalog build/iamd_feasibility/candidates.jsonl \
  --files build/iamd_feasibility/files.jsonl \
  --exclude-features build/curation/iamd/features_probed.jsonl \
  --blind-real-manifest build/blind_real/public_test_candidates.jsonl \
  --blind-real-manifest build/blind_real/resolved_originals.jsonl \
  --out build/curation/iamd/independent_validation_120.jsonl --target 120
```

Ne pas révéler les labels ni ajuster v2.1 après le gel de ce manifeste. Après une
éventuelle acquisition explicite des audios et extraction locale des clips,
figer d'abord l'ordre opaque :

```bash
.venv/bin/python -m openrestor.curation.cli prepare-blind-listen \
  --manifest build/curation/iamd/independent_validation_120.jsonl \
  --out build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_order.jsonl
```

Cette commande crée aussi un template CSV contenant seulement `blind_id` et un
lock privé qui conserve la correspondance `blind_id`/`source_key`. Quand les
features et clips locaux du lot seront disponibles, générer l'écoute sans
`--decisions` et sans `--show-predictions` :

```bash
.venv/bin/python -m openrestor.curation.cli listen \
  --features build/curation/iamd/independent_validation_features.jsonl \
  --order-file build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_order.jsonl \
  --blind --out build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_listen.html
```

La page n'affiche ni identifiant, ni métadonnée, ni prédiction ; son export porte
des `blind_id` opaques. Elle ne doit être lancée qu'après présence des clips
locaux, et ne déclenche aucun téléchargement.

Après export du CSV, remapper les `blind_id` avec l'ordre privé puis importer les
reviews. L'évaluation indépendante sépare les métriques du passage principal
(portée réelle des annotations) du contrôle de la décision source :

```bash
.venv/bin/python -m openrestor.curation.cli evaluate-independent \
  --features build/curation/iamd/evaluation/independent_v21/independent_validation_features_probed.jsonl \
  --reviews build/curation/iamd/evaluation/independent_v21/independent_validation_reviews.jsonl \
  --v2-decisions build/curation/iamd/evaluation/independent_v21/predictions/decisions_v2.jsonl \
  --v21-decisions build/curation/iamd/evaluation/independent_v21/predictions/decisions_v21.jsonl \
  --out-dir build/curation/iamd/evaluation/independent_v21/evaluation
```

Les cas `unresolved` sont exclus des dénominateurs binaires. Un passage annoté
comme bon ne certifie jamais la source entière.

Les exports lisibles produits par `export-judgments` peuvent aussi être fournis
à `evaluate-independent` : le champ `pipeline_decision` est normalisé sans
modifier les prédictions gelées. Cela permet de juxtaposer directement le
jugement de la pipeline et l'annotation humaine, sans conversion manuelle.

Pour obtenir le jugement machine avant toute écoute ou annotation sur un nouveau
lot, exporter explicitement les deux politiques :

```bash
.venv/bin/python -m openrestor.curation.cli export-judgments \
  --features build/curation/new_batch/features_probed.jsonl \
  --decisions build/curation/new_batch/decisions_v2.jsonl \
  --out build/curation/new_batch/pipeline_judgments_v2.jsonl
.venv/bin/python -m openrestor.curation.cli export-judgments \
  --features build/curation/new_batch/features_probed.jsonl \
  --decisions build/curation/new_batch/decisions_v21.jsonl \
  --out build/curation/new_batch/pipeline_judgments_v21.jsonl
```

Chaque ligne contient la décision et le score source, les motifs, les décisions
par passage, les segments acceptés et les champs de droits/provenance du
manifest. Si un fichier de reviews est fourni, les
annotations humaines sont ajoutées sous des champs séparés ; elles ne remplacent
jamais le jugement machine. Les deux exports doivent conserver le même identifiant
de lot que les features et les décisions gelées.
