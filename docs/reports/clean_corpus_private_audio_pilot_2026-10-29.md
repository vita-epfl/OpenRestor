# OpenRestor Clean — pilote audio privé (29 octobre 2026)

Un pilote de trois membres a été téléchargé depuis les archives ZIP Zenodo,
sans télécharger d'archive complète. Le budget était plafonné à 50 MiB et le
tirage a retenu les trois plus petits membres parmi le probe de headers.

## Vérifications

- 8 368 709 octets compressés téléchargés au total ;
- CRC-32 de chaque membre égal à la valeur de la table ZIP ;
- taille décompressée vérifiée ;
- SHA-256 calculé sur chaque WAV local ;
- lecture `soundfile` réussie pour les trois fichiers ;
- tous les trois sont WAV PCM, 44,1 kHz, mono ;
- sortie conservée sous `build/clean_corpus/private_pilot/` avec une notice
  interdisant la redistribution.

## Membres

| Record | Membre | Taille compressée | Taille WAV | SHA-256 |
| --- | --- | ---: | ---: | --- |
| ChoraleBricks `20849469` | `Telemann_DerLiebenSonneLichtUndPracht/.../03_bar.wav` | 4 171 108 | 5 221 042 | `a54d4bdcbe83bb2f2b3485854d2b25da99f4348e7f7f4ddc8368347e03a6bfe8` |
| GuitarSet `3371780` | `00_Jazz2-187-F#_solo_mic.wav` | 1 098 106 | 1 810 966 | `746aefd895490a408a36e4f1932ba3badfd4e98e30da2a4fe560b0a867f9607d` |
| GuitarSet `3371780` | `03_SS3-84-Bb_comp_mix.wav` | 3 099 495 | 4 031 454 | `20278c8dda530d677237b4de828109a9ffa832da7857c854e26b1a53261a4a02` |

## Statut juridique et technique

Le record Zenodo expose CC BY 4.0, mais ce pilote ne constitue pas une
approbation asset-level. Les trois lignes restent
`source_status=ambiguous_original_status`, `rights_status=metadata_confirmed_pending_asset_review`
et `redistribution_approved=false`. Aucun fichier n'est ajouté à un manifest
public, à un benchmark ou à un pack de release.

Le pilote établit seulement que les membres sélectionnés sont lisibles et
conformes aux empreintes ZIP. Il ne vérifie pas la qualité musicale, la
provenance antérieure, l'absence de réencodage, ni les droits individuels.
