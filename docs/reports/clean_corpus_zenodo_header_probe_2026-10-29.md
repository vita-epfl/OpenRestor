# OpenRestor Clean — probe des headers audio (29 octobre 2026)

Un membre audio a été tiré de façon déterministe dans chacune des archives ZIP
contenant de l'audio, avec `seed=20261029`, `sample_per_archive=1` et un
maximum de 64 KiB du flux compressé par membre. Aucun fichier audio complet n'a
été reconstruit.

## Résultat agrégé

| Archives audio sondées | Headers résolus | Conteneur | Codec déclaré | Sample rates | Bits | Canaux |
| ---: | ---: | --- | --- | --- | --- | --- |
| 14 | 14 | 14 WAV | 12 PCM, 2 `WAVE_FORMAT_EXTENSIBLE` | 9×48 kHz, 5×44,1 kHz | 10×16, 4×24 | 7 mono, 5 stéréo, 2×6 canaux |

Les deux archives sans membre audio sélectionné sont `02_ConductingVideos.zip`
(ChoraleBricks) et `annotation.zip` (GuitarSet). Les 14 lignes détaillées sont
dans `build/clean_corpus/zenodo_member_header_probes.jsonl`.

## Échantillons

| Dataset | Archives audio | Observations |
| --- | ---: | --- |
| Guitar-TECHS | 9 | WAV 48 kHz ; mono/stéréo ; 16 ou 24 bits |
| ChoraleBricks | 1 | WAV PCM 44,1 kHz, 16 bits, mono |
| GuitarSet | 4 | WAV 44,1 kHz ; mono ou 6 canaux ; 16 bits |

Le champ `source_status` reste `ambiguous_original_status` pour chaque ligne.
Le probe confirme le conteneur et certains paramètres de l'échantillon, mais ne
prouve pas :

- que tous les membres de l'archive ont les mêmes paramètres ;
- que `WAVE_FORMAT_EXTENSIBLE` est bien un sous-format PCM sans lire le GUID ;
- l'absence de réencodage antérieur ;
- la provenance `source=original`, la licence individuelle ou l'attribution ;
- la qualité acoustique ou la valeur musicale.

Ces lignes sont donc des candidats techniques à vérifier, pas encore des
`clean_lossless` ni des actifs redistribuables. L'étape suivante raisonnable est
un petit téléchargement pilote explicitement autorisé, avec vérification
SHA-256 et écoute, avant toute acquisition plus large.
