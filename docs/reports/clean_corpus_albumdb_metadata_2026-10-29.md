# AlbumDB — résolution metadata-only (29 octobre 2026)

Cette étape ne télécharge aucun fichier audio. Elle vérifie seulement les
métadonnées du record Zenodo et les entrées de répertoires ZIP accessibles par
inspection bornée.

## Résultat

Le concept demandé `19683000` redirige vers le record publié `19683001`, dont
les métadonnées indiquent `CC BY 4.0`. Les six archives représentent
15 338 467 723 octets compressés au niveau des archives. L'inspection bornée a
résolu quatre archives et trouvé 298 membres WAV :

| Archive | Membres WAV | Taille décompressée estimée | Statut |
| --- | ---: | ---: | --- |
| `stems_raw.zip` | 272 | 8 068 283 366 octets | membre identifié, original non vérifié |
| `masters_stereo.zip` | 10 | 358 890 288 octets | membre identifié, original non vérifié |
| `masters_7.1.4.zip` | 10 | 2 251 188 396 octets | membre identifié, original non vérifié |
| `example_usage_automatic_mixing.zip` | 6 | 50 696 844 octets | membre identifié, original non vérifié |
| `stems_mixed.zip` | 0 | — | ZIP64 non supporté par la sonde bornée |
| `stems_mixed_dry.zip` | 0 | — | ZIP64 non supporté par la sonde bornée |

Le manifest produit est
`build/clean_corpus/albumdb_archive_manifest.jsonl` et son résumé est
`build/clean_corpus/albumdb_archive_manifest_report.json`. Il contient 298
lignes metadata-only, toutes en format candidat WAV, pour 10 729 058 894
octets décompressés estimés. Les 15 entrées de répertoire ou sidecar macOS et
les deux archives ZIP64 non résolues sont exclues du comptage.

Un pilote borné de 12 membres a ensuite été sélectionné par
`scripts/select_zenodo_member_pilot.py`, en faisant tourner les archives et les
groupes de morceaux. Le résultat est
`build/clean_corpus/albumdb_pilot_selection.jsonl` avec son rapport
`build/clean_corpus/albumdb_pilot_selection_report.json` : 614 273 352 octets
compressés et 806 064 280 octets décompressés estimés. Ce fichier est une
liste de récupération future uniquement ; aucun audio n'a été téléchargé.

## Interprétation et prochaine étape

Les 298 lignes sont `technical_candidate=false`,
`redistributable_candidate=false` et `source_status=ambiguous_original_status`.
Le nom WAV dans une table ZIP ne prouve ni le codec PCM effectivement décodé,
ni le statut `source=original`, ni les droits sur chaque enregistrement. La
licence du record est une piste de provenance, pas une approbation asset-level.

AlbumDB est donc un petit complément de production potentiellement utile, mais
pas encore un pool Clean public. La suite doit sélectionner quelques membres
représentatifs, récupérer les fichiers exacts avec reprise et checksum, puis
faire la revue de provenance et de qualité avant tout téléchargement important.
Le pilote privé réalisé après cette sélection est documenté dans
[`clean_corpus_albumdb_private_pilot_2026-10-29.md`](clean_corpus_albumdb_private_pilot_2026-10-29.md).

