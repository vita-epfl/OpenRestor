# OpenRestor Clean — résolution metadata-only Zenodo (29 octobre 2026)

Cette résolution interroge uniquement l'API officielle Zenodo. Aucun fichier
audio, archive ou membre d'archive n'a été téléchargé. Les checksums ci-dessous
sont ceux publiés par Zenodo pour les fichiers du dépôt ; ils ne prouvent pas
encore le format ni la provenance de chaque membre audio.

Le résultat machine complet est conservé localement dans
`build/clean_corpus/zenodo_metadata_resolutions.jsonl` et peut être régénéré
avec :

```bash
.venv/bin/python scripts/resolve_zenodo_metadata.py \
  --record 15081740 --record 5120004 --record 3371780 --record 14963133 \
  --out build/clean_corpus/zenodo_metadata_resolutions.jsonl
```

## Résolution des dépôts

| Dataset | Concept → record publié | Version | Licence API | Taille des fichiers du dépôt | Statut |
| --- | --- | --- | --- | ---: | --- |
| ChoraleBricks | 15081740 → 20849469 | 1.1.0 | CC BY 4.0 | 1 283 848 638 octets | métadonnées confirmées, membres à auditer |
| MusicNet | 5120003 → 5120004 | 1.0 | CC BY 4.0 | 11 100 040 075 octets | métadonnées confirmées, membres à auditer |
| GuitarSet | 1302059 → 3371780 | 1.1.0 | CC BY 4.0 | 8 197 291 438 octets | métadonnées confirmées, membres à auditer |
| Guitar-TECHS | 14963132 → 14963133 | non indiqué | CC BY 4.0 | 4 133 550 356 octets | métadonnées confirmées, membres à auditer |

Les totaux incluent annotations, MIDI, vidéos ou archives non audio ; ils ne
sont donc pas des estimations de volume audio clean.

## Fichiers et checksums publiés

Les archives audio restent non inspectées (`archive_members_inspected=false`).
Les noms et empreintes sont conservés dans le JSONL ; aucun fallback ni
conversion n'est appliqué.

Un inspecteur borné est disponible dans
`scripts/inspect_zenodo_zip_ranges.py`. Il lit uniquement la fin de l'archive
et sa table centrale avec deux requêtes HTTP `Range`, puis compte les membres
WAV/FLAC/AIFF. Les erreurs HTTP ou rate-limits sont conservés par archive et
la commande est reprenable. Un membre trouvé dans la table est toujours marqué
`ambiguous_original_status` : le ZIP ne prouve pas `source=original`, les
droits individuels ni l'absence de réencodage. Les archives ZIP64 et TAR.GZ
restent non résolues dans cette étape.

Le premier probe réussi sur `Guitar-TECHS/P1_chords.zip` est détaillé dans
[`clean_corpus_zenodo_zip_probe_2026-10-29.md`](clean_corpus_zenodo_zip_probe_2026-10-29.md).

### ChoraleBricks — record 20849469

- `01_AudioAndAnnotations.zip` — 1 157 617 569 octets — `md5:297f56cd78be1b3277a437c7206cfb7c`
- `02_ConductingVideos.zip` — 126 227 750 octets — `md5:2662e52d7539a342254774f0cc863ad1`
- `CHANGELOG.md` — 3 319 octets — `md5:6de157afc36e793fd9be6025f2cb4c0e`

### MusicNet — record 5120004

- `musicnet.tar.gz` — 11 097 394 998 octets — `md5:844764911fa0d5b97c97da944a057590`
- `musicnet_metadata.csv` — 43 775 octets — `md5:1caef62cee9c875235e62aac368b49d8`
- `musicnet_midis.tar.gz` — 2 601 302 octets — `md5:b5fa98a113bfc51c8a445def9f24dc7e`

### GuitarSet — record 3371780

- `annotation.zip` — 39 132 574 octets — `md5:b39b78e63d3446f2e54ddb7a54df9b10`
- `audio_mono-pickup_mix.zip` — 683 145 360 octets — `md5:aecce79f425a44e2055e46f680e10f6a`
- `audio_mono-mic.zip` — 656 927 981 octets — `md5:275966d6610ac34999b58426beb119c3`
- `audio_hex-pickup_original.zip` — 3 210 735 945 octets — `md5:f9911bf217cb40e9e68edf3726ef86cc`
- `audio_hex-pickup_debleeded.zip` — 3 607 349 578 octets — `md5:c31d97279464c9a67e640cb9061fb0c6`

### Guitar-TECHS — record 14963133

- 9 archives, total 4 133 550 356 octets ; les noms, tailles et MD5 sont dans
  `zenodo_metadata_resolutions.jsonl`.

## Interprétation droits

La licence CC BY 4.0 affichée par le record est un signal de provenance
plausible et permet de poursuivre un audit `public_research_candidate`. Elle ne
transforme pas automatiquement les fichiers en actifs redistribuables : il
faut encore inspecter les membres audio, confirmer le format réellement
lossless, conserver l'attribution exacte et vérifier que les enregistrements
et dérivés visés sont couverts par le même périmètre de droits. Aucun des
quatre datasets n'est donc ajouté au pool public ou commercial à cette étape.

Cette prudence suit aussi la règle de Zenodo : Zenodo héberge les dépôts mais ne
possède pas leur contenu ; la réutilisation dépend de la licence choisie par le
déposant et de son périmètre réel. Voir la [FAQ officielle Zenodo sur les
permissions d'un record](https://support.zenodo.org/help/en-gb/2-content/21-can-i-get-permission-to-use-a-specific-record)
(consultée le 29 octobre 2026). La licence du record ne remplace donc pas la
preuve que les contributeurs pouvaient licencier les enregistrements, ni la
validation de la provenance de chaque membre audio.
