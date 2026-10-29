# OpenRestor Clean — curation du pilote audio privé (29 octobre 2026)

Ce pilote applique le manifeste multi-dataset commun et la politique v2.1 aux
trois WAV déjà présents dans `build/clean_corpus/private_pilot/`. Il ne lance
aucun téléchargement et ne modifie aucun benchmark. Les fichiers restent
strictement privés : la licence Zenodo déclarée au niveau du record n'est pas
une approbation de redistribution au niveau du membre.

## Périmètre et reproductibilité

Le manifeste est généré par
[`scripts/prepare_clean_pilot_manifest.py`](../../scripts/prepare_clean_pilot_manifest.py)
à partir du ledger vérifié et des métadonnées Zenodo. Chaque ligne vérifie le
SHA-256 local avant d'être acceptée. Les descriptions générales des records
sont conservées dans `dataset_description`, mais ne sont pas utilisées comme
indices de contenu au niveau d'une piste : une mention de MIDI dans la
documentation d'un dataset ne transforme pas une prise audio en rendu MIDI.

Commandes exécutées :

```bash
.venv/bin/python scripts/prepare_clean_pilot_manifest.py \
  --ledger build/clean_corpus/private_pilot/download_ledger.jsonl \
  --metadata build/clean_corpus/zenodo_metadata_resolutions.jsonl \
  --audio-root build/clean_corpus/private_pilot/audio \
  --out build/clean_corpus/private_pilot/curation_manifest.jsonl
.venv/bin/python -m openrestor.curation.cli extract \
  --manifest build/clean_corpus/private_pilot/curation_manifest.jsonl \
  --clips-dir build/clean_corpus/private_pilot/clips \
  --out build/clean_corpus/private_pilot/features.jsonl --segment-seconds 24
.venv/bin/python -m openrestor.curation.cli enrich-acoustics \
  --features build/clean_corpus/private_pilot/features.jsonl \
  --out build/clean_corpus/private_pilot/features_acoustic.jsonl
.venv/bin/python -m openrestor.curation.cli score \
  --features build/clean_corpus/private_pilot/features_acoustic.jsonl \
  --out build/clean_corpus/private_pilot/decisions_v21.jsonl \
  --policy v21 --config configs/curation/clean_music_v21.yaml
build/metric_tools/audiobox_cpu_venv/bin/python -m openrestor.curation.cli probe \
  --features build/clean_corpus/private_pilot/features_acoustic.jsonl \
  --out build/clean_corpus/private_pilot/features_probed.jsonl \
  --models ast,clap,aesthetics --cache-dir build/metric_tools/hf_cache
build/metric_tools/audiobox_cpu_venv/bin/python -m openrestor.curation.cli score \
  --features build/clean_corpus/private_pilot/features_probed.jsonl \
  --out build/clean_corpus/private_pilot/decisions_v21_probed.jsonl \
  --policy v21 --config configs/curation/clean_music_v21.yaml
```

Les probes AST, CLAP et Audiobox ont ensuite été exécutées dans
`build/metric_tools/audiobox_cpu_venv`, avec les modèles et prompts déjà
gelés. Aucun modèle n'a été téléchargé pendant ce pilote.

## Résultat machine

| Source | Format / durée | Contrôles locaux | v2 | v2.1 | Droits |
| --- | --- | --- | --- | --- | --- |
| ChoraleBricks `03_bar.wav` | WAV PCM, 44,1 kHz, 59,19 s | pas de silence/clipping excessif ; bande passante ~15,6 kHz ; PQ 6,31 | `manual_review` (0,4777) | `manual_review` (0,4777) | CC BY record, asset/provenance en attente |
| GuitarSet `03_SS3-84-Bb_comp_mix.wav` | WAV PCM, 44,1 kHz, 45,71 s | pas de clipping ; bande passante ~12,9 kHz ; PQ 8,10 | `auto_accept` (0,8204) | `auto_accept` (0,8204) | CC BY record, asset/provenance en attente |
| GuitarSet `00_Jazz2-187-F#_solo_mic.wav` | WAV PCM, 44,1 kHz, 20,53 s | pas de clipping ; bande passante ~16,9 kHz ; PQ 8,57 | `auto_accept` (0,8614) | `auto_accept` (0,8614) | CC BY record, asset/provenance en attente |

Les deux acceptations sont des décisions acoustiques provisoires uniquement ;
elles ne constituent ni une approbation de provenance, ni une autorisation de
redistribution. ChoraleBricks reste en revue à cause du garde-fou `v21_low_pq_guard`.
Un fichier lisible ou un score élevé ne devient pas automatiquement un audio
redistribuable.

Les jugements explicables sont conservés séparément pour les deux politiques :
`build/clean_corpus/private_pilot/pipeline_judgments_v2.jsonl` et
`build/clean_corpus/private_pilot/pipeline_judgments_v21.jsonl`.
Les exports issus des probes sont
`build/clean_corpus/private_pilot/pipeline_judgments_v2_probed.jsonl` et
`build/clean_corpus/private_pilot/pipeline_judgments_v21_probed.jsonl`.
La file privée de revue asset-level, sans chemins locaux ni payload audio, est
`build/clean_corpus/private_pilot/rights_review_queue.jsonl` ; son résumé est
`rights_review_queue_report.json`. Elle est reproductible avec :

```bash
.venv/bin/python scripts/export_clean_rights_review_queue.py \
  --input build/clean_corpus/private_pilot/curation_manifest.jsonl \
  --input build/iamd_feasibility/phase1b/curation_manifest.jsonl \
  --out build/clean_corpus/private_pilot/rights_review_queue.jsonl \
  --report build/clean_corpus/private_pilot/rights_review_queue_report.json
```

Elle ne confère aucune permission.
Pour chaque membre d’archive, elle conserve aussi `archive_record_url`,
`archive_key`, `member_name`, `member_url`, CRC/taille et `identity`. Le champ
`creator` désigne uniquement le créateur de l’asset lorsqu’il est connu ; les
auteurs du record restent dans `dataset_creators` afin de ne pas confondre
attribution et titularité. `evidence_date` est propagé depuis la résolution
Zenodo pour dater la preuve de licence ; il ne transforme pas cette preuve en
approbation.
La page d'écoute locale est
`build/clean_corpus/private_pilot/pilot_listen.html` ; elle contient un extrait
par source et permet de corriger séparément le contenu, la qualité et la nature
de la source. Elle ne doit pas être servie publiquement.

## Interprétation et suite

- Le pipeline commun fonctionne sur deux datasets et conserve les checksums,
  métadonnées, segments, droits et décisions par source.
- Le pilote confirme la faisabilité technique de l'adaptateur et du scoring
  model-backed sur deux datasets, mais trois sources ne permettent pas
  d'estimer un rendement généralisable ni de valider les droits.
- La prochaine étape est d'exécuter les probes déjà approuvées dans un
  environnement contenant les modèles locaux, puis de faire une écoute courte
  stratifiée. Aucun lot de 200/750 membres ne doit être téléchargé avant cette
  étape et la validation asset-level.
- `redistributable_candidate=false` et
  `rights.provenance_approved=false` restent invariants pour les trois lignes.

Le filtre de droits strict (`--require-technical`) produit 3 lignes
`blocked`, 0 `public_research`, 0 `public_commercial` et 0
`internal_research`. Cela confirme que les deux `auto_accept` acoustiques ne
franchissent pas le gate juridique.

L'audit acoustique report-only (`acoustic_dedup_report.json`) a fingerprinté
les trois fichiers sans erreur et n'a trouvé aucun groupe candidat. Ce résultat
est uniquement local et ne constitue pas une preuve d'absence de doublons dans
les archives non téléchargées.

