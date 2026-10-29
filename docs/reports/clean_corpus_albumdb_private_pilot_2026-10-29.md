# AlbumDB — pilote audio privé (29 octobre 2026)

Ce pilote récupère uniquement les 12 membres sélectionnés dans
`clean_corpus_albumdb_metadata_2026-10-29.md`. Les fichiers sont sous
`build/clean_corpus/albumdb_private_pilot/`, qui reste privé et ignoré par Git.
Aucun benchmark, manifest public ou pool redistribuable n'a été modifié.

## Vérification du transfert

Les 12 membres ont été récupérés par plages HTTP avec reprise et vérifiés par
taille décompressée, CRC-32 ZIP et SHA-256 local. Le ledger est
`build/clean_corpus/albumdb_private_pilot/download_ledger.jsonl`.

| Élément | Résultat |
| --- | ---: |
| Membres sélectionnés / vérifiés | 12 / 12 |
| Octets compressés transférés | 614 273 352 |
| Octets WAV décompressés | 806 064 280 |
| Durée cumulée | 1 965,82 s (0,546 h) |
| WAV PCM 16-bit, 44,1 kHz | 12 / 12 |
| Canaux | 7 stéréo, 3 en 12 canaux, 2 mono |
| `source=original` explicitement vérifié | 0 ; statut conservé ambigu |

Les en-têtes ZIP et le record Zenodo donnent une provenance plausible, mais le
nom du membre et la licence `CC BY 4.0` du record ne suffisent pas à approuver
la redistribution de chaque enregistrement. Les 12 lignes portent donc
`provenance_approved=false` et `redistribution_approved=false`.

## Curation v2.1

Les commandes ont réutilisé les modèles, prompts et seuils déjà gelés. Les
features sont dans `features_probed.jsonl`, les décisions dans
`decisions_v21.jsonl` et le rapport détaillé dans `curation_report.md`.

| Décision | Nombre |
| --- | ---: |
| `auto_accept` | 1 |
| `manual_review` | 8 |
| `auto_reject` | 3 |

L'unique acceptation automatique est le fichier d'exemple
`song01_raw.wav`. Les trois rejets sont des stems isolés très clairsemés
(`drums_toms` ou `drums_cymbal_reverse`) : ce résultat ne dit pas que les
chansons AlbumDB sont mauvaises ; il indique que ces membres ne sont pas des
références musicales complètes. Les masters stéréo restent majoritairement en
revue, avec des scores acoustiques élevés mais des signaux CLAP divergents.
Les masters 7.1.4 restent aussi en revue, ce qui est une décision conservatrice
tant qu'ils n'ont pas été écoutés et que le comportement multicanal n'est pas
validé sur davantage de sources.

L'extraction conserve les masters de plus de huit canaux en WAV temporaire ;
elle ne les downmixe pas pour les clips. Les descripteurs et les entrées AST/
CLAP utilisent un downmix à énergie préservée pour éviter le faux signal de
quasi-silence créé par la moyenne de 12 canaux. Les seuils et les modèles n'ont
pas été modifiés.

## Écoute et suite

La page locale aveugle est
`build/clean_corpus/albumdb_private_pilot/pilot_listen.html`. Son ordre figé et
le verrou sont `blind_order.jsonl` et `blind_order.jsonl.lock.json`. Les
annotations éventuelles doivent distinguer le passage central de la source
entière ; une bonne écoute d'un extrait ne valide pas automatiquement tous les
stems.
L'export explicable correspondant est
`build/clean_corpus/albumdb_private_pilot/pipeline_judgments_v21.jsonl` : il
conserve les rôles master/stem, les motifs par passage et le statut de droits
pour chaque source.

L'audit acoustique
`build/clean_corpus/albumdb_private_pilot/acoustic_dedup_report.json` trouve
trois paires quasi identiques : les masters 7.1.4 et stéréo des morceaux 01,
02 et 03. Aucune suppression n'est effectuée automatiquement. Pour un pool
stéréo généraliste, la sélection devra préférer `full_mix_stereo_master` et
garder les versions immersives dans un sous-ensemble séparé ; les deux formats
ne doivent pas compter comme deux morceaux indépendants.

Le sélecteur report-only
`scripts/select_deduplicated_candidates.py` applique maintenant cette
préférence de façon déterministe au manifeste des clips v2.1. Il a produit
`clip_candidates_v21_dedup.jsonl` et
`clip_candidates_v21_dedup_report.json` : 12 segments provenant de 8 sources
deviennent 8 segments provenant de 5 sources. Les trois sources immersives
doublonnées sont écartées au profit de leur master stéréo ; les segments d'une
source retenue sont tous conservés. Aucun audio n'est copié, aucune décision
de curation ou de droit n'est modifiée, et les groupes restent à vérifier par
un humain.

Une page de vérification ciblée pour ces cinq sources est disponible dans
`build/clean_corpus/albumdb_private_pilot/dedup_pilot_listen.html`. Elle
réutilise les clips et les décisions déjà calculés ; elle ne révèle pas de
nouveaux droits et ne lance aucun téléchargement.

La file de revue juridique correspondante est
`build/clean_corpus/albumdb_private_pilot/dedup_rights_review_queue.jsonl`,
avec son rapport `dedup_rights_review_queue_report.json`. Elle contient les
mêmes cinq `source_key`, n'inclut aucun chemin audio et conserve les deux
approbations à `false` tant qu'une validation asset-level n'a pas été obtenue.
Elle est reproductible avec `scripts/export_clean_rights_review_queue.py` et
son option `--source-keys`.

Ce pilote démontre le chemin technique exact, mais ne fournit pas encore un
pool Clean public : une seule source est acceptée automatiquement et la
provenance asset-level reste non approuvée. Il faut écouter les masters,
clarifier les crédits et décider si les masters stéréo seulement doivent être
retenus avant tout lot AlbumDB plus large.

Les manifests portent désormais `asset_role` (`full_mix_stereo_master`,
`full_mix_immersive_master`, `full_mix_example` ou `isolated_stem_raw`). Le
sélecteur de candidats exclut par défaut les rôles de stem isolé, tout en
conservant leurs décisions acoustiques pour l'audit. Cette distinction ne
change ni la licence ni le score d'un fichier.

