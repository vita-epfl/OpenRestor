# OpenRestor Clean — manifest metadata-only des membres Zenodo (29 octobre 2026)

Le script `scripts/prepare_zenodo_archive_manifest.py` transforme le probe de
table centrale ZIP en manifest commun, sans télécharger ni extraire de fichier
audio. Il ne s'agit donc pas encore d'un inventaire de fichiers lossless
vérifiés.

## Résultat

| Mesure | Valeur |
| --- | ---: |
| Records Zenodo résolus en entrée | 4 |
| Archives inspectées | 16 |
| Membres WAV/FLAC/AIFF nommés | 2 040 |
| `technical_candidate` | 0 |
| `provenance_candidate` | 2 040 |
| `redistributable_candidate` | 0 |
| `ambiguous_original_status` | 2 040 |
| Audio téléchargé | non |

Tous les membres retenus sont nommés WAV dans ce probe. La répartition est :

| Dataset | Membres WAV nommés |
| --- | ---: |
| ChoraleBricks | 392 |
| GuitarSet | 1 440 |
| Guitar-TECHS | 208 |
| MusicNet | 0 |

MusicNet est distribué dans un TAR.GZ non inspecté par le probe ZIP ; son zéro
ne signifie pas qu'il n'a pas d'audio, seulement qu'aucun membre n'a été
résolu par cette étape.

Les autres entrées ont été écartées parce qu'elles étaient des annotations,
MIDI, vidéos, répertoires ou sidecars macOS (1 742 membres non audio et 226
répertoires/sidecars). Aucun MP3 n'est utilisé comme repli.

## Portée et suite

Chaque ligne conserve le record, l'archive, le nom du membre, les tailles, le
CRC32 publié et l'URL de l'archive. Elle n'a ni `audio_path`, ni SHA-256 local,
ni durée/codec réellement lus. Le conteneur WAV indiqué par un nom de membre
ne prouve donc pas l'absence de transcodage ; le statut reste explicitement
`ambiguous_original_status` et les droits restent en attente d'une revue de
l'asset exact.

Le manifest machine est privé sous
`build/clean_corpus/zenodo_archive_curation_manifest.jsonl`, avec son résumé
`build/clean_corpus/zenodo_archive_curation_manifest_report.json`. Avant tout
lot plus large, la prochaine étape est un téléchargement pilote borné de
membres sélectionnés, avec checksum/lecture locale et validation de la portée
CC BY. Rien dans ce rapport n'autorise une redistribution.
