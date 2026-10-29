# OpenRestor Clean — premier probe de membres ZIP (29 octobre 2026)

Seize archives ZIP ont été inspectées pour mesurer la faisabilité de l'étape
asset-level, sans télécharger de membre audio. Le JSONL complet est conservé
dans `build/clean_corpus/zenodo_zip_member_resolutions.jsonl`.

| Record | Archive(s) | Membres | WAV exploitables par extension | Sidecars macOS | WAV décompressés | Statut source |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Guitar-TECHS `14963133` | 9 archives | 720 | 208 | 99 | 6 770 145 150 octets | `ambiguous_original_status` |
| ChoraleBricks `20849469` | audio + vidéo | 1 488 | 392 | 0 | 1 404 986 428 octets | `ambiguous_original_status` |
| GuitarSet `3371780` | 4 archives audio + annotations | 1 800 | 1 440 | 0 | 13 543 913 568 octets | `ambiguous_original_status` |

Total : 16 archives, 4 008 membres, 2 040 WAV, 99 sidecars et
21 719 045 146 octets WAV décompressés. Les 4 008 membres incluent les
fichiers d'annotation et autres entrées non audio.

Pour `P1_chords.zip`, les 56 membres WAV totalisent 1 073 845 078 octets
décompressés et
786 885 741 octets compressés dans l'archive. Les 35 entrées `__MACOSX/._…`
ont été exclues du compte audio. La table centrale indique une compression ZIP
(méthode 8), mais cela décrit l'archive et non le codec interne des WAV.

Ces probes démontrent que le comptage des membres et le filtrage des sidecars
est possible avec seulement les tables centrales (environ 1,3 Mo pour les
16 archives). Ils ne permettent pas encore de
confirmer :

- `source=original` ou une autre provenance de chaque WAV ;
- sample rate, canaux, durée ou codec PCM sans lire l'en-tête audio ;
- licence individuelle et attribution des enregistrements ;
- absence de réencodage en amont.

Les 2 040 membres restent donc des candidats techniques ambigus, pas des sources
`clean_lossless` ni des éléments redistribuables. Le résultat complet de
l'inspecteur est reprenable via
`scripts/inspect_zenodo_zip_ranges.py` ; les archives ZIP64 et TAR.GZ restent
à traiter séparément.
