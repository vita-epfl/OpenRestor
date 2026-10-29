# OpenRestor Clean multi-datasets

Le registre de tri des droits est
[`configs/datasets/clean_corpus_rights_registry.yaml`](../configs/datasets/clean_corpus_rights_registry.yaml).
La matrice de priorité est dans
[`docs/reports/clean_corpus_priority_matrix_2026-10-29.md`](reports/clean_corpus_priority_matrix_2026-10-29.md).
Il n'accorde aucun droit : les autorisations restent au niveau de chaque
source/fichier dans le registre privé média.

L'audit local se lance avec
[`scripts/audit_clean_corpus_sources.py`](../scripts/audit_clean_corpus_sources.py).
Il ne télécharge pas d'audio et distingue explicitement :

- `clean_lossless` seulement si l'origine lossless est vérifiée ;
- `lossless_container_unverified` pour un WAV/FLAC/AIFF lisible dont la chaîne
  de provenance n'est pas encore prouvée ;
- `clean_lossy_hq` pour MP3/AAC et tout WAV décodé depuis une source lossy ;
- `technical_candidate`, `provenance_candidate` et
  `redistributable_candidate` séparément.

Après approbation d'un lot, le manifest peut être envoyé à la curation commune :

```bash
openrestor-curate extract --manifest <manifest.jsonl> \
  --out build/clean_corpus/features.jsonl \
  --clips-dir build/clean_corpus/clips --segment-seconds 24
openrestor-curate probe --features build/clean_corpus/features.jsonl \
  --out build/clean_corpus/features_probed.jsonl \
  --models ast,clap,aesthetics --cache-dir build/metric_tools/hf_cache
openrestor-curate score --features build/clean_corpus/features_probed.jsonl \
  --out build/clean_corpus/decisions_v21.jsonl --policy v21 \
  --config configs/curation/clean_music_v21.yaml
```

Les droits ne sont jamais déduits du score acoustique.

Pour produire un rapport reproductible par source après le scoreur (sans
inventer de labels humains), utiliser :

```bash
.venv/bin/python scripts/report_clean_curation.py \
  --features build/clean_corpus/private_pilot/features_probed_12.jsonl \
  --decisions build/clean_corpus/private_pilot/decisions_v21_probed_12.jsonl \
  --out build/clean_corpus/private_pilot/curation_report_12.json \
  --markdown build/clean_corpus/private_pilot/curation_report_12.md
```

Le rapport joint les décisions aux passages primaires, conserve aussi les
min/max/médianes de chaque métrique sur tous les passages échantillonnés,
résume les métriques par dataset/créateur/collection et conserve séparément les
statuts de droits. Il indique explicitement que la décision provient de
passages échantillonnés et ne valide pas toute la source.

Pour exporter ensuite les passages `auto_accept` dans un manifest de candidats
sans copier l'audio, utiliser
[`scripts/export_clean_clip_candidates.py`](../scripts/export_clean_clip_candidates.py) :

```bash
.venv/bin/python scripts/export_clean_clip_candidates.py \
  --features build/clean_corpus/private_pilot/features_probed_12.jsonl \
  --decisions build/clean_corpus/private_pilot/decisions_v21_probed_12.jsonl \
  --out build/clean_corpus/private_pilot/clip_candidates_v21.jsonl \
  --summary build/clean_corpus/private_pilot/clip_candidates_v21_summary.json
```

Par défaut, les sources `auto_accept` et `manual_review` sont admises, mais
seuls leurs segments `auto_accept` sont exportés ; les sources `auto_reject`
sont exclues. Chaque ligne reste un `sampled_segment_candidate`, conserve le
score et les motifs source/passage, et porte un gate de droits séparé. Une
acceptation acoustique ne passe jamais ce gate sans approbation explicite de la
provenance, de la redistribution et des dérivés. Les champs
`public_research_eligible` et `public_commercial_eligible` restent distincts ;
le second exige aussi `allow_commercial=true`.
Les manifests qui fournissent `metadata.asset_role` excluent par défaut les
stems isolés (`isolated_stem_raw`, `isolated_stem_mixed` et
`isolated_stem_mixed_dry`) de cet export ; le scoring et l'audit de ces fichiers
restent conservés.

Après export du CSV depuis une page aveugle, le remapping vers les identifiants
réels doit passer par l'ordre figé :

```bash
.venv/bin/python -m openrestor.curation.cli import-blind-reviews \
  --features build/clean_corpus/private_pilot/features_probed_12.jsonl \
  --csv build/clean_corpus/private_pilot/blind_order_12_annotations.csv \
  --order build/clean_corpus/private_pilot/blind_order_12.jsonl \
  --out build/clean_corpus/private_pilot/reviews_imported.jsonl
```

Les lignes vierges sont ignorées et ne deviennent jamais des labels positifs
ou négatifs ; un `blind_id` inconnu ou dupliqué fait échouer l'import.

Pour adapter un index provenant d'un autre dataset, utiliser ensuite
[`scripts/normalize_clean_manifest.py`](../scripts/normalize_clean_manifest.py) :

```bash
.venv/bin/python scripts/normalize_clean_manifest.py \
  --input build/clean_corpus/inventory.jsonl \
  --out build/clean_corpus/curation_manifest.jsonl
```

L'adaptateur accepte les alias usuels (`identifier`, `id`, `track_id`,
`audio_path`, `path`, `artist`, `composer`, `genre`, etc.), conserve les
checksums et les droits, et refuse les identifiants dupliqués contradictoires.
Le manifest produit est directement compatible avec `curation extract` pour les
fichiers effectivement présents localement. Si l'index source les contient déjà,
les champs `features`, `segments`, `segment_decisions`, `source_decision`,
`annotations` et `annotation_history` sont conservés afin de ne pas perdre les
mesures ou l'historique humain lors d'un changement d'adaptateur. Les fréquences,
canaux et durées numériques sont canonisés avant écriture, puis le fichier de
sortie est validé automatiquement contre le schéma commun.

Lors d'une extraction locale, ces champs de curation sont également recopiés dans
le cache. Une reprise qui réutilise les clips rafraîchit donc les décisions et leur
historique depuis le manifest sans réutiliser les anciens segments si l'audio ou la
politique d'échantillonnage a changé. Les champs retirés du manifest sont aussi
retirés du cache pour éviter de conserver une ancienne annotation ou un ancien
statut de provenance.

Valider ensuite le manifeste commun avant de lancer la curation ou les splits :

```bash
.venv/bin/python -m openrestor.validation.cli clean_manifest \
  --input build/clean_corpus/curation_manifest.jsonl
```

Ce contrôle vérifie la structure de chaque ligne ainsi que l'unicité et la
cohérence de `source_key = dataset:source_id`. Il ne valide ni les droits, ni
le codec réel, ni la qualité audio.

Pour les WAV/FLAC/AIFF, l'ingestion et l'extraction de passages disposent d'un
repli `libsndfile` lorsque `ffprobe`/`ffmpeg` n'est pas installé sur le nœud.
FFmpeg reste requis pour les codecs lossy non lisibles par `libsndfile`, pour le
filtre de normalisation `loudnorm` et pour les dégradations codec ; le pipeline
échoue alors explicitement au lieu de substituer silencieusement une autre
opération.
Un smoke test sur un extrait IAMD a validé les 19 recettes non-codec ; les
recettes `codec` et `neural_codec` attendent un nœud où FFmpeg est installé. Le
détail est dans
[`clean_corpus_degradation_compatibility_2026-10-29.md`](reports/clean_corpus_degradation_compatibility_2026-10-29.md).

Pour préparer les candidats IAMD dont les métadonnées Internet Archive ont été
résolues sans télécharger l'audio, utiliser
[`scripts/prepare_iamd_archive_manifest.py`](../scripts/prepare_iamd_archive_manifest.py) :

```bash
.venv/bin/python scripts/prepare_iamd_archive_manifest.py \
  --candidates build/iamd_feasibility/iamd_clean_candidate_identifiers.jsonl \
  --items build/iamd_feasibility/items.jsonl \
  --files build/iamd_feasibility/files.jsonl \
  --selection provenance \
  --out build/iamd_feasibility/iamd_archive_curation_manifest.jsonl \
  --report build/iamd_feasibility/iamd_archive_curation_manifest_report.json
```

La sortie actuelle contient 1 851 lignes metadata-only. Elle conserve les
URLs, tailles, durées, checksums SHA-1/MD5 et statuts `strict_original` déclarés
par Archive, mais ne renseigne aucun `audio_path`, ne vérifie pas le codec et
force `redistributable_candidate=false`, `provenance_approved=false` et les
permissions à `null`. Le registre privé peut donc les importer comme actifs en
attente :

```bash
.venv/bin/python scripts/build_media_rights_registry.py \
  --clean-corpus-manifest build/iamd_feasibility/iamd_archive_curation_manifest.jsonl
```

Le filtre de profils doit rester vide jusqu'à la revue asset-level. Dans le
rapport du 29 octobre, les 1 851 lignes sont bien classées `blocked` pour cette
raison ; aucun téléchargement n'est déclenché par l'adaptateur.

Pour construire le registre privé complet en combinant l'inventaire local, le
catalogue IAMD et les pilotes audio, utiliser le mergeur explicite :

```bash
.venv/bin/python scripts/merge_clean_manifests.py \
  --input build/clean_corpus/curation_manifest.jsonl \
  --input build/iamd_feasibility/iamd_combined_curation_manifest.jsonl \
  --input build/clean_corpus/private_pilot/curation_manifest.jsonl \
  --input build/iamd_feasibility/phase1b/curation_manifest.jsonl \
  --input build/clean_corpus/albumdb_archive_manifest.jsonl \
  --out build/clean_corpus/rights_registry_input.jsonl \
  --report build/clean_corpus/rights_registry_merge_report.json \
  --allow-overrides
.venv/bin/python scripts/build_media_rights_registry.py \
  --clean-corpus-manifest build/clean_corpus/rights_registry_input.jsonl
```

Les entrées ultérieures remplacent uniquement une ligne de même `source_key`
avec une preuve plus forte, et chaque remplacement est enregistré dans le
rapport. Sans `--allow-overrides`, tout doublon contradictoire est refusé.
La sortie est validée automatiquement contre le schéma du manifest commun avant
d'être acceptée. Cette fusion n'ouvre aucun profil public.

Le wrapper historique `scripts/prepare_rights_profiles.sh` accepte aussi
`CLEAN_CORPUS_MANIFEST=build/clean_corpus/rights_registry_input.jsonl` pour
reconstruire ce registre fusionné avant le calcul des profils. Son option
`--help` ne modifie pas le registre.

Pour auditer les doublons et les groupes de split sur cette même vue fusionnée,
recalculer le rapport metadata-only avant le gate de release :

```bash
.venv/bin/python scripts/prepare_clean_corpus_splits.py \
  --input build/clean_corpus/rights_registry_input.jsonl \
  --deduplicated-out build/clean_corpus/merged_split_manifest.jsonl \
  --split-out build/clean_corpus/merged_split.jsonl \
  --report build/clean_corpus/merged_split_audit.json \
  --seed 20261029 --validation-ratio 0.15 --test-ratio 0.15
```

Le premier pilote externe metadata-only est ChoraleBricks :

```bash
.venv/bin/python scripts/prepare_choralebricks_metadata.py \
  --out build/clean_corpus/choralebricks_metadata.jsonl
.venv/bin/python scripts/normalize_clean_manifest.py \
  --input build/clean_corpus/choralebricks_metadata.jsonl \
  --out build/clean_corpus/choralebricks_curation_manifest.jsonl
```

Il contient dix œuvres (402 secondes de durées de référence), sans `audio_path`.
La licence CC BY 4.0 est une preuve de catalogue/site, pas encore une
approbation de fichier : `technical_candidate` est faux et
`redistributable_candidate` reste faux jusqu'à résolution Zenodo, checksum et
notice d'attribution.

Pour capturer les notices et checksums de plusieurs dépôts Zenodo sans
télécharger leurs archives, utiliser le résolveur générique :

```bash
.venv/bin/python scripts/resolve_zenodo_metadata.py \
  --record 15081740 --record 5120004 --record 3371780 --record 14963133 \
  --out build/clean_corpus/zenodo_metadata_resolutions.jsonl
```

La sortie est reprise record par record, conserve les erreurs HTTP et reste
strictement fail-closed : `technical_candidate` et
`redistributable_candidate` restent faux tant que les membres audio, leur
format réel, leur attribution et leur provenance n'ont pas été vérifiés.
Le rapport correspondant est
[`clean_corpus_zenodo_metadata_2026-10-29.md`](reports/clean_corpus_zenodo_metadata_2026-10-29.md).

Les vues de droits du manifest multi-dataset se génèrent séparément de la
qualité audio. Pour l'audit complet courant, utiliser le manifest fusionné
`rights_registry_input.jsonl`, qui inclut l'inventaire local, le catalogue IAMD
et les pilotes audio :

```bash
.venv/bin/python scripts/filter_clean_manifest_profiles.py \
  --input build/clean_corpus/rights_registry_input.jsonl \
  --out-dir build/clean_corpus/merged_rights_profiles \
  --require-technical
```

La commande produit `public_research`, `public_commercial`,
`internal_research` et `blocked`. Elle exige une approbation de provenance et
un registre de droits complet au niveau asset ; une licence déclarée dans un
catalogue ou un score v2.1 ne suffit pas. Le gate `technical_candidate` est
actif par défaut et bloque les lignes metadata-only ;
`--allow-unverified-technical` est réservé au tri exploratoire et ne doit jamais
servir à construire un profil de release. Les décisions techniques et de droits
restent conceptuellement séparées. Les deux profils publics sont des vues
d'éligibilité cumulatives : une source approuvée pour `public_commercial` figure
aussi dans `public_research`, tandis qu'une source NC approuvée n'entre que
dans `public_research`. `internal_research` et `blocked` restent des catégories
de repli exclusives. Les comptages par profil ne doivent donc pas être
additionnés pour obtenir le nombre de sources publiques uniques. La commande
ne copie aucun audio.

Avant toute release, lancer le contrôle mécanique intégré :

```bash
.venv/bin/python scripts/audit_clean_release_readiness.py \
  --manifest build/clean_corpus/rights_registry_input.jsonl \
  --profiles-dir build/clean_corpus/merged_rights_profiles \
  --split-report build/clean_corpus/merged_split_audit.json \
  --out build/clean_corpus/merged_release_readiness.json \
  --verify-local-checksums
```

Le script retourne un code non nul pour `NO-GO`. Il vérifie les identifiants
uniques, la couverture de chaque source par une catégorie de base
(`public_research`, `internal_research` ou `blocked`), la présence de chaque
source commerciale aussi dans la vue recherche, la cohérence
manifest/profils, l'approbation asset-level, les notices,
les permissions, la présence d'un fichier lossless et les splits disjoints. Il
vérifie séparément `provenance_approved` et `redistribution_approved` dans
chaque profil public. Il ne déduit jamais une permission d'une licence
dataset-level ou d'un score
acoustique. Pour un lot local déjà approuvé, `--verify-local-checksums` ajoute
la vérification SHA-256 des fichiers référencés. L'audit reste mécanique et ne
remplace ni la validation juridique ni l'écoute scientifique.

Le dernier audit fusionné porte sur 28 014 lignes et répartit toutes les
sources dans `blocked` : zéro `public_research`, zéro `public_commercial` et
zéro `internal_research`. Ce résultat est le contrôle courant ;
`build/clean_corpus/release_readiness.json` reste l'audit historique de
l'inventaire local de 25 849 lignes.

Le split correspondant au manifest fusionné est
`build/clean_corpus/merged_split_audit.json` : 28 014 lignes d'entrée, 28 012
sources après deux doublons exacts, avec des groupes train/validation/test
disjoints. Il reste 26 152 sources sans créateur exploitable et 2 149 sans
checksum de contenu ; ce split est donc un audit metadata-only, pas un split
de release. Le fichier `--deduplicated-out` est validé automatiquement contre
le schéma du manifest commun ; le fichier `--split-out` reste une table de
correspondance source/groupe et ne porte pas les droits.

Pour auditer le codec des fichiers déjà téléchargés sans en récupérer d'autres,
utiliser `audit_clean_corpus_sources.py`. Le statut `clean_lossless` n'est
attribué que si le manifest déclare un original vérifié, que le fichier décodé
est WAV/FLAC/AIFF PCM ou IEEE_FLOAT et que son SHA-256 correspond. Un fichier
WAV issu d'un transfert MP3, ou dont le statut d'original est ambigu, reste
respectivement `clean_lossy_hq` ou `lossless_container_unverified`.

Les profils doivent toujours être audités avec le manifest qui a servi à les
générer. Par exemple, les profils IAMD combinés (catalogue metadata-only plus
le pilote audio privé) nécessitent
`build/iamd_feasibility/iamd_combined_curation_manifest.jsonl` et
`build/iamd_feasibility/combined_rights_profiles/`. Le manifest IAMD
metadata-only de 1 851 lignes ne doit pas être mélangé avec cette vue de
profils de 1 855 lignes ; l'audit échoue alors volontairement sur les quatre
clés du pilote.

Pour les archives ZIP Zenodo, une inspection bornée de la table centrale peut
ensuite compter les membres WAV/FLAC/AIFF sans télécharger leurs données :

```bash
.venv/bin/python scripts/inspect_zenodo_zip_ranges.py \
  --input build/clean_corpus/zenodo_metadata_resolutions.jsonl \
  --out build/clean_corpus/zenodo_zip_member_resolutions.jsonl
```

Cette étape télécharge uniquement des octets de métadonnées via HTTP `Range`.
Elle laisse `source_status=ambiguous_original_status` : le nom d'un membre ZIP
ne prouve ni `source=original`, ni sa licence individuelle, ni l'absence d'un
réencodage. Les archives TAR.GZ et les cas ZIP64 restent explicitement non
résolus. Le script utilise `curl` en secours lorsque l'API répond
temporairement `406`, conserve les erreurs par archive et reprend au prochain
lancement. Le premier inventaire complet est décrit dans
[`clean_corpus_zenodo_zip_probe_2026-10-29.md`](reports/clean_corpus_zenodo_zip_probe_2026-10-29.md).

Pour vérifier le format interne sur un petit échantillon, utiliser le probe de
headers borné :

```bash
.venv/bin/python scripts/probe_zenodo_member_headers.py \
  --input build/clean_corpus/zenodo_zip_member_resolutions.jsonl \
  --out build/clean_corpus/zenodo_member_header_probes.jsonl \
  --sample-per-archive 2 --max-probe-bytes 262144
```

Il récupère au plus le header ZIP local et 256 KiB du flux compressé par membre,
extrait le conteneur, le codec déclaré, le sample rate, les canaux et les bits
quand disponibles. Les résultats restent techniques et ambigus juridiquement ;
aucun fichier audio complet n'est reconstruit.

Pour un pilote privé complet (et uniquement après validation explicite), le
téléchargeur borné peut récupérer quelques membres sélectionnés, vérifier leur
CRC/taille/SHA-256 et les relire localement :

```bash
.venv/bin/python scripts/download_zenodo_member_pilot.py \
  --archives build/clean_corpus/zenodo_zip_member_resolutions.jsonl \
  --probes build/clean_corpus/zenodo_member_header_probes.jsonl \
  --out-dir build/clean_corpus/private_pilot \
  --max-members 3 --max-total-compressed-bytes $((50*1024*1024))
```

Le dossier porte une notice privée, un ledger reprenable et
`redistribution_approved=false`. Ce pilote n'ajoute aucun fichier au corpus
public et ne transforme pas une licence de record en autorisation asset-level.
Le premier résultat vérifié est consigné dans
[`clean_corpus_private_audio_pilot_2026-10-29.md`](reports/clean_corpus_private_audio_pilot_2026-10-29.md).

Pour transformer l'inventaire borné des membres Zenodo en manifest commun
metadata-only, utiliser :

```bash
.venv/bin/python scripts/prepare_zenodo_archive_manifest.py \
  --metadata build/clean_corpus/zenodo_metadata_resolutions.jsonl \
  --members build/clean_corpus/zenodo_zip_member_resolutions.jsonl \
  --out build/clean_corpus/zenodo_archive_curation_manifest.jsonl \
  --report build/clean_corpus/zenodo_archive_curation_manifest_report.json
```

Le résultat du 29 octobre contient 2 040 membres nommés WAV : 392
ChoraleBricks, 1 440 GuitarSet et 208 Guitar-TECHS. Tous restent
`technical_candidate=false`, `redistributable_candidate=false` et
`ambiguous_original_status` : le nom d'un membre ZIP ne vérifie ni le codec
réel, ni la provenance, ni les droits de l'asset. MusicNet n'est pas compté
dans cette sortie car son archive est TAR.GZ et n'a pas été inspectée par le
probe ZIP. Le détail est dans
[`clean_corpus_zenodo_archive_manifest_2026-10-29.md`](reports/clean_corpus_zenodo_archive_manifest_2026-10-29.md).

Pour préparer un lot exact très petit sans télécharger d'audio, sélectionner
ensuite un pilote déterministe par archive et morceau :

```bash
.venv/bin/python scripts/select_zenodo_member_pilot.py \
  --manifest build/clean_corpus/albumdb_archive_manifest.jsonl \
  --out build/clean_corpus/albumdb_pilot_selection.jsonl \
  --report build/clean_corpus/albumdb_pilot_selection_report.json \
  --max-items 12 --max-total-compressed-bytes $((750*1024*1024))
```

La sélection ne contient que des métadonnées, conserve les statuts de droits
en attente et ne déclenche aucun téléchargement. Le résultat AlbumDB actuel
sélectionne 12 membres, avec 614 273 352 octets compressés estimés.

Les 12 membres AlbumDB déjà téléchargés dans le pilote privé utilisent des
identifiants de travail différents de ceux du catalogue. Pour les rattacher
aux entrées canoniques sans dupliquer les sources ni changer les droits :

```bash
.venv/bin/python scripts/overlay_clean_verified_pilot.py \
  --catalogue build/clean_corpus/rights_registry_input.jsonl \
  --pilot build/clean_corpus/albumdb_private_pilot/curation_manifest.jsonl \
  --features build/clean_corpus/albumdb_private_pilot/features_probed.jsonl \
  --decisions build/clean_corpus/albumdb_private_pilot/decisions_v21.jsonl \
  --out build/clean_corpus/rights_registry_input_verified_pilot.jsonl \
  --report build/clean_corpus/rights_registry_input_verified_pilot_report.json \
  --source-keys-out build/clean_corpus/albumdb_verified_pilot_canonical_keys.jsonl
```

La jointure exige le même record, archive et membre, puis recontrôle la taille,
le CRC, le SHA-256, le format PCM, la fréquence et les canaux du fichier local.
Elle conserve la clé et les droits du catalogue ; le statut d'original et les
permissions restent ambigus/non approuvés. Les 32 passages mesurés et les
décisions v2.1 sont rattachés aux mêmes clés canoniques, avec leurs anciens
identifiants conservés pour traçabilité ; une décision de passage ne valide
pas la source entière. Le 30 octobre, elle rattache 12
fichiers aux 28 014 lignes existantes. La vue sans chevauchement exact garde
2 045 sources dont 1 759 candidats techniques, mais toujours zéro source
redistribuable ou `clean_lossless` confirmé. Pour recalculer les vues aval,
utiliser ce manifest comme `--candidates` dans l'audit de chevauchement et
comme `--input` dans le filtre de profils ; les rapports datés sont sous
`build/clean_corpus/*verified_pilot*`.

La file de revue ciblée sur ces 12 fichiers peut être exportée avec les outils
existants, sans chemin audio ni permission présélectionnée :

```bash
.venv/bin/python scripts/export_clean_rights_review_queue.py \
  --input build/clean_corpus/no_benchmark_overlap_verified_pilot.jsonl \
  --source-keys build/clean_corpus/albumdb_verified_pilot_canonical_keys.jsonl \
  --out build/clean_corpus/albumdb_verified_pilot_rights_queue.jsonl \
  --report build/clean_corpus/albumdb_verified_pilot_rights_queue_report.json
.venv/bin/python scripts/export_clean_rights_review_form.py \
  --input build/clean_corpus/albumdb_verified_pilot_rights_queue.jsonl \
  --out build/clean_corpus/albumdb_verified_pilot_rights_review.csv \
  --report build/clean_corpus/albumdb_verified_pilot_rights_review_report.json
```

La page locale correspondante est
`build/clean_corpus/albumdb_verified_pilot_rights_review.html`. La file fournit
les noms exacts des membres ZIP et le record Zenodo ; ses 12 décisions sont
vierges. Les validations humaines peuvent ensuite passer par
`import_clean_rights_review_form.py --expected-queue`.

Le pilote privé peut ensuite être branché sur la curation multi-dataset sans
réutiliser les descriptions de record comme labels de piste :

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
  --out build/clean_corpus/private_pilot/decisions_v21.jsonl --policy v21 \
  --config configs/curation/clean_music_v21.yaml
```

Le rapport de ce pilote est
[`clean_corpus_private_pilot_curation_2026-10-29.md`](reports/clean_corpus_private_pilot_curation_2026-10-29.md).
Les droits restent séparés du score : le pilote ne rend aucun fichier
redistribuable.

Pour le pilote IAMD borné, convertir uniquement les fichiers complets dont la
taille et le SHA-1/MD5 Archive concordent :

```bash
.venv/bin/python scripts/prepare_iamd_pilot_manifest.py \
  --pilot-dir build/iamd_feasibility/phase1b \
  --out build/iamd_feasibility/phase1b/curation_manifest.jsonl \
  --report build/iamd_feasibility/phase1b/curation_manifest_report.json
```

Le script sonde alors le conteneur local, calcule un SHA-256 et conserve les
permissions à `null`. Les fragments `.part`, fichiers absents ou checksums
incorrects sont exclus et comptés ; aucune reprise réseau n'est déclenchée.

Le rapport du premier échantillon de headers est
[`clean_corpus_zenodo_header_probe_2026-10-29.md`](reports/clean_corpus_zenodo_header_probe_2026-10-29.md).

Avant une curation audio, auditer les doublons exacts et préparer des splits
sans fuite entre sources d'un même créateur :

```bash
.venv/bin/python scripts/prepare_clean_corpus_splits.py \
  --input build/clean_corpus/curation_manifest.jsonl \
  --deduplicated-out build/clean_corpus/deduplicated_manifest.jsonl \
  --split-out build/clean_corpus/source_splits.jsonl \
  --report build/clean_corpus/split_audit.json
```

Le contrôle regroupe les checksums identiques entre datasets, conserve un
représentant déterministe et signale les sources sans checksum. Les créateurs
et les albums explicitement identifiés sont regroupés dans un split unique ;
les identités manquantes retombent au niveau `source_key`. Le record AlbumDB
`19683001` est traité comme un seul album même si le créateur des assets est
absent : ses stems et masters ne peuvent pas être répartis entre train,
validation et test. Pour un autre album, fournir `metadata.album_group_id` ;
ne pas attribuer aux interprètes les noms des auteurs du dataset. L'option
`--no-creator-grouping` désactive aussi ce regroupement par album et ne doit
pas être utilisée pour une release. Les ratios sont indicatifs et aucun droit n'est déduit de ce
traitement. Il s'agit d'une déduplication exacte, pas d'une déduplication
acoustique : un fingerprint audio devra être ajouté séparément lorsqu'il sera
disponible.

Le regroupement utilise les composantes liées checksum/créateur : si un
checksum relie deux créateurs, leurs autres enregistrements restent dans le
même groupe de split. Pour auditer le chevauchement exact avec les benchmarks
et validations gelés :

```bash
.venv/bin/python scripts/audit_clean_benchmark_overlap.py \
  --candidates build/clean_corpus/rights_registry_input.jsonl \
  --reference paired_benchmark=build/index.jsonl \
  --reference paired_release=build/private-releases/openrestore-paired-v0.1/index.jsonl \
  --reference blind_synthetic=build/blind-synthetic/manifest.jsonl \
  --reference blind_real_test=build/blind_real/blind_real_test_manifest.jsonl \
  --reference blind_real_control=build/blind_real/clean_control_manifest.jsonl \
  --reference blind_real_release=build/release/blind_real_public_v0_1/blind_real_test_manifest.jsonl \
  --reference iamd_independent=build/curation/iamd/evaluation/independent_v21/independent_validation_local_manifest.jsonl \
  --safe-out build/clean_corpus/no_benchmark_overlap_manifest.jsonl \
  --overlap-out build/clean_corpus/benchmark_overlap.jsonl \
  --report build/clean_corpus/benchmark_overlap_report.json
```

Le contrôle compare les identifiants de source, les identifiants Internet
Archive et les SHA-256 de l'original. Il ne lit pas l'audio et ne remplace pas
l'audit de doublons acoustiques. Les lignes en overlap sont exclues du
manifeste sûr, avec les raisons conservées dans le rapport.

Le manifest sans chevauchement exact peut ensuite recevoir des splits
reproductibles, sans changer son statut de droits :

```bash
.venv/bin/python scripts/prepare_clean_corpus_splits.py \
  --input build/clean_corpus/no_benchmark_overlap_manifest.jsonl \
  --deduplicated-out build/clean_corpus/no_benchmark_overlap_split_manifest.jsonl \
  --split-out build/clean_corpus/no_benchmark_overlap_splits.jsonl \
  --report build/clean_corpus/no_benchmark_overlap_split_audit.json \
  --seed 20261030 --validation-ratio 0.15 --test-ratio 0.15
```

Ce résultat reste un plan de sélection metadata-only : il ne certifie ni la
qualité audio ni la redistribution.

Pour produire une synthèse de volume et de concentration sur ce manifest :

```bash
.venv/bin/python scripts/report_clean_candidate_pool.py \
  --input build/clean_corpus/no_benchmark_overlap_manifest.jsonl \
  --report build/clean_corpus/no_benchmark_overlap_pool_report.json \
  --markdown build/clean_corpus/no_benchmark_overlap_pool_report.md
```

Le rapport sépare les axes `technical_candidate`, `provenance_candidate` et
`redistributable_candidate`, conserve les licences exactes et rend les champs
manquants explicites.

Pour préparer la revue privée des droits au niveau de chaque source, sans
inclure de chemin audio ni modifier les permissions :

```bash
.venv/bin/python scripts/export_clean_rights_review_queue.py \
  --input build/clean_corpus/no_benchmark_overlap_manifest.jsonl \
  --out build/clean_corpus/no_benchmark_overlap_rights_review_queue.jsonl \
  --report build/clean_corpus/no_benchmark_overlap_rights_review_queue_report.json
```

La file conserve l'identifiant, le membre Archive/Zenodo, la licence déclarée,
les crédits et les preuves disponibles. Elle reste privée et fail-closed : une
ligne ne devient redistribuable qu'après approbation de provenance et de
redistribution dans le registre média.

Pour limiter la première revue à un lot diversifié de 100 lignes :

```bash
.venv/bin/python scripts/select_clean_rights_review_batch.py \
  --input build/clean_corpus/no_benchmark_overlap_rights_review_queue.jsonl \
  --out build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.jsonl \
  --report build/clean_corpus/no_benchmark_overlap_rights_review_batch_100_report.json \
  --size 100
```

La sélection est déterministe et équilibre dataset, licence, collection puis
créateur. Les valeurs inconnues forment une strate explicite ; le classement ne
change ni les droits ni le statut technique.

Le formulaire CSV privé des 100 lignes se génère ainsi :

```bash
.venv/bin/python scripts/export_clean_rights_review_form.py \
  --input build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.jsonl \
  --out build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.csv \
  --report build/clean_corpus/no_benchmark_overlap_rights_review_batch_100_form_report.json
```

Après revue, seules les lignes dont `decision` est renseigné sont converties
en overrides privés. Les lignes vides restent hors de tout dénominateur :

```bash
.venv/bin/python scripts/import_clean_rights_review_form.py \
  --input build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.csv \
  --expected-queue build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.jsonl \
  --out /chemin/prive/clean_rights_overrides_batch_100.jsonl \
  --report /chemin/prive/clean_rights_overrides_batch_100_report.json
```

Une approbation exige la licence exacte, le crédit, une preuve datée, les
permissions explicites, `source_status_verified=original_verified` et le
SHA-256 du fichier original vérifié. Le formulaire ne contient aucun fichier
audio et son import ne déduit jamais une permission d’un champ vide. Le
sélecteur vérifie aussi que le CSV contient exactement les `source_key` du lot;
`--allow-subset` doit être explicite pour importer un extrait du formulaire.

Pour appliquer un fichier d’overrides au manifest privé après cet import,
utiliser l’étape séparée suivante :

```bash
.venv/bin/python scripts/apply_clean_rights_overrides.py \
  --manifest build/clean_corpus/no_benchmark_overlap_manifest.jsonl \
  --overrides /chemin/prive/clean_rights_overrides_batch_100.jsonl \
  --out build/clean_corpus/no_benchmark_overlap_manifest_reviewed.jsonl \
  --report build/clean_corpus/no_benchmark_overlap_manifest_reviewed_report.json \
  --applied-at 2026-10-30T00:00:00+00:00
```

La commande refuse les doublons, les `source_key` inconnus et les approbations
incomplètes. Elle conserve les champs audio et de curation, met à jour le
checksum top-level seulement lorsqu’il est fourni par une approbation vérifiée,
et ajoute un historique par source avec le digest de l’override. Elle est
idempotente pour un même digest; aucun audio n’est copié et aucune permission
n’est déduite.

La reconstruction du registre privé avec
`scripts/build_media_rights_registry.py --clean-corpus-manifest` conserve aussi
ce champ `rights_review_history`; il ne disparaît donc pas lors du passage du
manifest de revue au registre utilisé par les profils.

Une page locale avec recherche, filtres par dataset/décision et export CSV peut
être générée pour remplir ce formulaire plus rapidement :

```bash
.venv/bin/python scripts/build_clean_rights_review_html.py \
  --input build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.csv \
  --out build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.html \
  --report build/clean_corpus/no_benchmark_overlap_rights_review_batch_100_html_report.json
```

Elle n’effectue aucune requête réseau et ne charge aucun audio. Les annotations
restent dans le navigateur jusqu’au téléchargement explicite du CSV.

Avant la revue humaine, la cohérence des labels et URLs de licence peut être
contrôlée séparément :

```bash
.venv/bin/python scripts/audit_clean_rights_license_consistency.py \
  --input build/clean_corpus/no_benchmark_overlap_rights_review_queue.jsonl \
  --out build/clean_corpus/no_benchmark_overlap_rights_license_consistency.jsonl \
  --report build/clean_corpus/no_benchmark_overlap_rights_license_consistency_report.json
```

Ce contrôle reconnaît les URLs CC versionnées et les variantes `http`/`https`,
mais ne transforme jamais une concordance en approbation de droits.

Pour les fichiers déjà locaux, un audit acoustique report-only peut repérer des
transcodages ou copies probables entre datasets :

```bash
.venv/bin/python scripts/audit_clean_audio_duplicates.py \
  --input build/clean_corpus/private_pilot/curation_manifest.jsonl \
  --out build/clean_corpus/private_pilot/acoustic_dedup.jsonl \
  --report build/clean_corpus/private_pilot/acoustic_dedup_report.json
.venv/bin/python scripts/audit_clean_audio_duplicates.py \
  --input build/clean_corpus/no_benchmark_overlap_verified_pilot.jsonl \
  --local-only \
  --out build/clean_corpus/local_cross_dataset_acoustic_dedup.jsonl \
  --report build/clean_corpus/local_cross_dataset_acoustic_dedup_report.json
```

Il lit uniquement `audio_path`, ne supprime ni ne copie rien, ne modifie pas les
droits et marque toujours les groupes comme candidats nécessitant une
vérification humaine. Il complète la déduplication exacte par checksum sans la
remplacer. Sur la vue commune, `--local-only` examine les 28 fichiers déjà
disponibles parmi 2 045 lignes ; les 2 017 autres sans `audio_path` sont
comptées comme non examinées. Trois groupes candidats rapprochent les masters
stéréo et immersifs des mêmes morceaux AlbumDB ; aucun doublon inter-dataset
n'a été signalé dans ce pilote limité.

Pour appliquer une préférence de représentation au manifeste de clips, sans
copier ni supprimer d'audio :

```bash
.venv/bin/python scripts/select_deduplicated_candidates.py \
  --candidates build/clean_corpus/albumdb_private_pilot/clip_candidates_v21.jsonl \
  --dedup build/clean_corpus/albumdb_private_pilot/acoustic_dedup.jsonl \
  --out build/clean_corpus/albumdb_private_pilot/clip_candidates_v21_dedup.jsonl \
  --report build/clean_corpus/albumdb_private_pilot/clip_candidates_v21_dedup_report.json
```

Le sélecteur préfère, dans cet ordre, les masters stéréo, les exemples, puis
les masters immersifs et les stems. Il conserve tous les segments de la source
retenue, laisse passer les sources absentes du rapport acoustique et échoue si
un groupe est incohérent. Le résultat est un choix de curation réversible : il
ne vaut ni validation juridique ni suppression des doublons dans le corpus. Le
rapport enregistre les SHA-256 des deux entrées et du manifeste de sortie pour
permettre de reproduire exactement la sélection.

Une file de revue juridique peut ensuite être limitée aux `source_key` retenus,
sans inclure de chemin audio :

```bash
.venv/bin/python scripts/export_clean_rights_review_queue.py \
  --input build/clean_corpus/albumdb_private_pilot/curation_manifest.jsonl \
  --source-keys build/clean_corpus/albumdb_private_pilot/dedup_source_keys.jsonl \
  --out build/clean_corpus/albumdb_private_pilot/dedup_rights_review_queue.jsonl \
  --report build/clean_corpus/albumdb_private_pilot/dedup_rights_review_queue_report.json
```

Le script refuse une clé inconnue ou dupliquée et conserve les permissions à
leur valeur précédente ; ce sous-ensemble ne donne aucune autorisation.
