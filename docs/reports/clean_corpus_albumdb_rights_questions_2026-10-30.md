# AlbumDB — dossier de revue des droits (30 octobre 2026)

Ce document prépare une validation asset-level ; il ne constitue ni un avis
juridique ni une approbation de redistribution. Aucun droit du registre privé
n'est modifié par ce constat.

## Éléments vérifiés dans les sources publiées

- La [fiche officielle Aalto](https://research.aalto.fi/en/datasets/albumdb-a-multitrack-dataset-of-a-ten-song-album-with-stereo-and-/)
  décrit *Extraordinary*, un album de dix chansons de Tom McKenzie, avec des
  stems et des masters stéréo/7.1.4 en WAV PCM 16 bits, 44,1 kHz. Elle affiche
  `CC BY 4.0` et le DOI `10.5281/zenodo.19683000`.
- Le catalogue Zenodo local résout ce concept vers le record `19683001` et
  donne `cc-by-4.0` pour le record. Les 298 membres WAV identifiés sont des
  entrées d'archives, pas 298 enregistrements musicaux indépendants : plusieurs
  stems, mixes et masters proviennent des mêmes dix chansons.
- La [licence CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
  prévoit partage et adaptation, sous réserve d'attribution, lien de licence
  et indication des modifications. La [FAQ Zenodo](https://support.zenodo.org/help/en-gb/2-content/21-can-i-get-permission-to-use-a-specific-record)
  précise que Zenodo n'est pas le titulaire des droits sur le contenu déposé.

## Questions à trancher avant toute approbation

1. La licence du record couvre-t-elle bien **chaque** master, stem et mix
   d'exemple envisagé, et non seulement les métadonnées/documentation du
   dataset ? Vérifier au besoin les notices internes aux archives.
2. Quels crédits exacts faut-il porter pour l'album, l'interprète, les
   enregistrements et les auteurs du dataset ? Les auteurs de la fiche
   scientifique ne doivent pas être automatiquement présentés comme
   interprètes ou titulaires de tous les enregistrements.
3. Le déposant confirme-t-il que les droits sur compositions, interprétations,
   phonogrammes et éventuels éléments tiers permettent la redistribution de
   ces fichiers, ainsi que la création et redistribution d'extraits ou de
   versions dégradées ?
4. Pour chaque asset retenu : confirmer le membre ZIP, le checksum, le codec
   réellement décodé, la durée, la source originale et la preuve datée.

Le formulaire privé à renseigner reste
`build/clean_corpus/albumdb_verified_pilot_rights_review.csv` (12 assets).
Jusqu'à réponse documentée, `provenance_approved`,
`redistribution_approved`, `allow_redistribution` et `allow_derivatives`
restent inconnus/faux ; le profil public reste vide. L'acceptation acoustique
ne change pas cette décision.

### Message prêt à envoyer aux auteurs du dataset

> Subject: AlbumDB CC BY 4.0 scope and attribution for an academic audio dataset
>
> Dear AlbumDB authors,
>
> We are preparing OpenRestor Clean, an academic dataset of short clean-music
> references and synthetically degraded counterparts. Your Aalto/Zenodo page
> lists AlbumDB under CC BY 4.0. Could you confirm whether this licence covers
> the audio files in `masters_stereo.zip`, `masters_7.1.4.zip`, `stems_raw.zip`
> and `example_usage_automatic_mixing.zip`, including the underlying musical
> compositions, performances and recordings? Would redistribution of 20–30 s
> clean excerpts and corresponding degraded versions be permitted under those
> terms? Are any stems, samples or MEGAMI example mixes subject to different
> third-party rights or conditions? Finally, what exact attribution and links
> should accompany each excerpt and its derived version?
>
> We will keep the files private until the scope and credits are clear. Thank
> you for your help.

## Fuite de split corrigée

L'absence de `creator` sur les assets AlbumDB ne signifie pas que ces assets
sont indépendants. Avant correction, les 298 lignes se répartissaient entre
train (208), validation (51) et test (39). Le split courant regroupe désormais
le record `19683001` comme un album unique : 298/298 en validation. Ce choix
conservateur évite de placer des stems et masters du même album dans des
partitions différentes. Il ne résout pas les doublons acoustiques éventuels
avec d'autres datasets ni l'absence de genre détaillé.
