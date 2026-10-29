# IAMD Phase 1b — pilote privé de qualification audio

Ce pilote **ne modifie ni le benchmark ni ses manifests**. IAMD reste un catalogue ;
les seules sources audio acceptées pour le pilote sont des fichiers Internet Archive
WAV/FLAC/AIFF, non privés, au format concordant, explicitement `source=original`,
avec taille et SHA1/MD5. Les règles `technical_candidate`,
`provenance_candidate` et `redistributable_candidate` restent celles de la
Phase 1. Ce dernier terme ne signifie toujours **pas** « droits de
redistribution vérifiés ».

## Exécution reproductible

Après `python3 scripts/audit_iamd_lossless_feasibility.py report` :

```bash
.venv/bin/python scripts/iamd_audio_pilot.py plan \
  --tracks 60 --seed 42 --max-new-gib 10 --passages 3 --passage-seconds 18
.venv/bin/python scripts/iamd_audio_pilot.py download
.venv/bin/python scripts/iamd_audio_pilot.py extract
.venv/bin/python scripts/iamd_audio_pilot.py score
.venv/bin/python scripts/iamd_audio_pilot.py report
```

Un seul pilote privé est figé dans `build/iamd_feasibility/phase1b/`. Les relances
`download`, `extract` et `score` reprennent le travail ; `plan` refuse d'écraser
un tirage existant. `--limit 10` sur `download` permet un essai borné aux dix
premières pistes *du même plan* ; les dix ne constituent pas un nouvel
échantillon aléatoire autonome. Aucun MP3, ViSQOL, restauration, entraînement
ou téléchargement global n'est utilisé. Le plafond de nouveaux octets est
persistant dans `download_ledger.json` ; les transferts sont séquentiels et
réservent le maximum annoncé avant chaque appel. Après une interruption, une
réservation non libérée reste comptée de façon conservatrice.

Le plan tire des **pistes/fichiers**, non des items Archive ni des segments
IAMD : tirage sans remise dans les douze plus grandes collections et une strate
« autres collections ». Les allocations, effectifs `N_h`, `n_h` et
probabilités `pi=n_h/N_h` sont consignés dans `plan.json` et `tracks.jsonl`.
Un même item Archive peut fournir plusieurs pistes. Seules les pistes à durée
déclarée suffisante pour les passages entrent dans la population d'inférence ;
les absences de réponse Archive et les échecs de téléchargement ne sont pas
extrapolés. Aucun quota de genre n'est imposé. Les créateurs et collections
sélectionnés sont comptés et les URL/licences/empreintes exactes sont conservées.

`segments.jsonl` et `clips/` forment le pack d'écoute : trois passages de 18 s
aux positions préfixées début/milieu/fin par défaut, avec provenance et
empreinte de l'original. Les clips FLAC sont des extraits lossless pour écoute,
**pas** une validation de la piste entière. `scores.jsonl` donne silence,
écrêtage, niveau, bande passante indicative, plancher et flatness. Ces valeurs
ne provoquent aucun rejet automatique ; une source sombre peut sembler limitée,
une piste musicale bruyante peut avoir une forte flatness. Elles servent à
prioriser la revue humaine.

Audiobox PQ est optionnel et se calcule sur un environnement qui dispose déjà
du modèle :

```bash
build/metric_tools/audiobox_cpu_venv/bin/python scripts/iamd_audio_pilot.py score --with-pq
```

Le script utilise le cache privé `build/metric_tools/hf_cache` en mode hors
ligne. Si le modèle/environnement manque, laisser `audiobox_status=not_run` ;
ne pas inventer de score. Les seuils éventuels se calibreront seulement après
annotations humaines.

## Annotation et rendement

Remplir une copie de `annotation_template.csv` : une ligne par passage,
`clean_quality` = `acceptable` / `degraded` / `uncertain`, `content` =
`recorded_instruments` / `synthetic` / `mixed` / `noise_experimental` / `other`,
`instruments` séparés par `;`, chaque utilité de tâche = `yes` / `no` /
`uncertain`. Décrire librement défauts, motifs de rejet et commentaires.
Ne pas convertir automatiquement « électronique », « MIDI-like » ou « pas de
cuivres » en rejet : l'usage EQ, débruitage, cuivres et batterie est séparé.

```bash
.venv/bin/python scripts/iamd_audio_pilot.py annotate-import --csv /chemin/revue_remplie.csv
.venv/bin/python scripts/iamd_audio_pilot.py report
```

L'import valide toutes les lignes avant de remplacer `annotations.jsonl`.
Tant que toutes les pistes du plan et tous leurs passages ne sont pas présents
et annotés, le rendement clean et le verdict audio restent **en attente**.
Après revue complète, le rapport estime par strate le taux de **durée des
passages échantillonnés** acceptables, avec intervalle approximatif si chaque
strate non exhaustive a au moins deux pistes. Il donne aussi les heures
d'extraits acceptés observées et les octets par heure d'extraits retenus. Il
**n'extrapole pas ces extraits en heures de chansons entièrement clean** ;
pour cela il faudrait une qualification des morceaux entiers. Un verdict GO
sur le corpus exigerait en outre une revue de provenance et de droits distincte.

Si Archive est inaccessible depuis le cluster, transférer `plan.json` et
`tracks.jsonl` avec ce script vers une machine autorisée, exécuter `download`
avec `--out` pointant vers le dossier transféré, puis rapatrier uniquement
`originals/`, `download_ledger.json` et `download_status.jsonl` sous le même
`--out`. Relancer `extract`, `score`, puis `report` localement ; la vérification
SHA1/MD5 est répétée avant toute extraction. Les audios restent privés.
