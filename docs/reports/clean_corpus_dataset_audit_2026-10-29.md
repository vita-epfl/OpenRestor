# OpenRestor Clean — audit initial multi-datasets (29 octobre 2026)

Ce rapport est un audit d'inventaire et de droits, pas une autorisation de
redistribution. Aucun téléchargement n'a été lancé par ce travail.

## Décision immédiate

Le corpus local actuellement exploitable contient trois familles très
différentes :

| Dataset local | Sources indexées | Durée | Fichier d'origine/indexé | Statut technique | Statut de droits |
| --- | ---: | ---: | --- | --- | --- |
| SonicMaster clean | 25 000 | 208,33 h | FLAC | `lossless_container_unverified` | bloqué en attente de preuve par `source_id` |
| SDD | 705 | 23,14 h | MP3 | `clean_lossy_hq` uniquement | interne ; licences par piste, NC/ND présentes |
| MUSDB18-HQ | 144 indexés (50 fichiers source accessibles dans le miroir actuel) | 9,79 h indexées | WAV | `lossless_container_unverified` | interne, académique seulement, aucune redistribution |

Le WAV transféré depuis un MP3 SDD n'est jamais compté comme lossless. De même,
un FLAC SonicMaster n'est pas déclaré `clean_lossless` tant que son origine et
l'absence de réencodage ne sont pas documentées.

Les données détaillées et le résumé reproductible sont dans
`build/clean_corpus/inventory.jsonl` et
`build/clean_corpus/inventory_summary.json`.

## Registre de droits dataset-level

Le registre de tri est
`configs/datasets/clean_corpus_rights_registry.yaml`. Il sépare :

- `public_research_candidate` : piste à vérifier au niveau asset avant publication ;
- `internal_research` : traitement local autorisé ou plausible, sans redistribution ;
- `needs_permission` : source/conditions insuffisamment établies ;
- les cas `item_dependent` : jamais transformés en autorisation collective.

Le registre ne remplace pas le registre privé média
`build/rights/media_registry.jsonl`. Pour un asset redistribuable, il faut une
licence exacte, l'attribution, une preuve datée, l'approbation de provenance et
les droits d'adaptation nécessaires.

Le filtre multi-dataset `scripts/filter_clean_manifest_profiles.py` a été
exécuté sur le manifest local. Résultat : 25 849 `blocked`, 0
`public_research`, 0 `public_commercial` et 0 `internal_research`, car aucune
ligne ne porte encore `provenance_approved=true`. Ce résultat est volontairement
fail-closed ; il ne signifie pas que les 25 849 sources sont juridiquement
interdites, seulement qu'aucune approbation asset-level n'est enregistrée.

## Priorité d'intégration

1. **ChoraleBricks** : premier candidat externe à auditer, car le site officiel
   annonce CC BY 4.0 pour les données. Petit, WAV/multitrack, utile pour ajouter
   du vent/chorale, mais trop étroit pour constituer le corpus généraliste.
2. **GuitarSet / Guitar-TECHS** : pilotes techniques après capture exacte des
   droits Zenodo et des fichiers ; compléments instrumentaux, pas le pool principal.
3. **MusicNet / URMP** : candidats classiques de volume limité ; vérifier les
   droits des enregistrements et ne pas les présenter comme commercialement
   redistribuables sans preuve.
4. **IAMD → Internet Archive** : poursuivre uniquement avec les originaux WAV/FLAC/AIFF
   résolus et des licences par item ; c'est le principal espoir de diversité.
5. **FMA** : grand catalogue multi-genre, mais l'audio officiel est MP3 et chaque
   piste a sa propre licence ; uniquement `clean_lossy_hq` après filtrage piste par
   piste, jamais le pool lossless.
6. **MAESTRO, MedleyDB, MoisesDB** : techniquement bons mais classiques ou
   non-commerciaux/restrictifs ; utiles en `internal_research`, pas dans le pool
   public commercial-compatible.

Les sources officielles donnent notamment les ordres de grandeur suivants :
MusicNet annonce 330 enregistrements PCM WAV et 11,1 Go ([Zenodo](https://zenodo.org/records/5120004));
GuitarSet annonce 8,2 Go de fichiers audio/annotations ([Zenodo](https://zenodo.org/records/3371780));
Guitar-TECHS annonce trois interprètes et plusieurs modes de capture ([Zenodo](https://zenodo.org/records/14963133));
ChoraleBricks couvre dix chorales et quatre parties instrumentales
([site officiel](https://www.audiolabs-erlangen.de/resources/MIR/2025-ChoraleBricks));
MAESTRO v3 annonce 1 276 performances, 198,7 h et 120,2 Go décompressés
([site officiel](https://magenta.withgoogle.com/datasets/maestro)).

## Ce qui est déjà réutilisable

Le manifest commun de curation existant accepte déjà `dataset`, `source_id`,
`audio_path`, métadonnées et `rights`. La commande générique `curation extract`
produit les passages de 20–30 secondes ; `probe` et `score` réutilisent AST,
CLAP, Audiobox et la politique v2.1. La nouvelle commande d'inventaire ne
télécharge rien :

```bash
.venv/bin/python scripts/audit_clean_corpus_sources.py \
  --index build/indexes/sonicmaster.jsonl \
  --index build/indexes/sdd.jsonl \
  --index build/indexes/musdb18_hq.jsonl \
  --audio-root build/clean/transfer \
  --rights-registry build/rights/media_registry.jsonl \
  --out build/clean_corpus/inventory.jsonl \
  --summary build/clean_corpus/inventory_summary.json
```

Chaque source reçoit trois niveaux distincts :

- `technical_candidate` : fichier lisible et format exploitable ;
- `provenance_candidate` : un indice de provenance/licence existe, sans
  approbation automatique ;
- `redistributable_candidate` : registre média approuvé, dérivés autorisés et
  redistribution explicitement permise.

L'adaptateur générique
`scripts/normalize_clean_manifest.py` transforme l'inventaire en
`build/clean_corpus/curation_manifest.jsonl` (25 849 sources dans l'audit
actuel). Il accepte les alias de colonnes courants et conserve les checksums,
les métadonnées et les droits sans copier les fichiers.

Un audit de déduplication exact et de splits a ensuite été exécuté sur ce
manifest (seed `20261029`, 15 % validation, 15 % test). Il donne 25 847
représentants après suppression de 2 doublons exacts par checksum, avec 18 071
sources train, 3 959 validation et 3 817 test. Les groupes sont disjoints ;
les 25 849 lignes ne contiennent toutefois pas de créateur exploitable, donc
ce résultat garantit seulement la séparation par source/checksum, pas
l'absence de fuite entre artistes. Le rapport est reproductible avec
`scripts/prepare_clean_corpus_splits.py` et ne lit pas les fichiers audio.

Le pilote externe metadata-only ChoraleBricks est généré par
`scripts/prepare_choralebricks_metadata.py` et contient les dix œuvres de la
table officielle (402 secondes de durée de référence). Il est volontairement
non téléchargeable et non redistribuable à ce stade : seules la provenance du
site et la licence annoncée sont enregistrées.

AlbumDB est maintenant identifié comme un candidat externe distinct : le portail
de recherche Aalto décrit dix chansons indie rock/folk, des stems de 13 à 35
pistes par chanson, des masters stéréo et 7.1.4, et des fichiers audio PCM WAV
16-bit/44,1 kHz sous CC BY 4.0 ([record Aalto](https://research.aalto.fi/en/datasets/albumdb-a-multitrack-dataset-of-a-ten-song-album-with-stereo-and-immersive-714-masters/),
[record Zenodo](https://zenodo.org/records/19683000)). Il reste metadata-only
jusqu'à la vérification des membres, de la provenance des enregistrements et des
crédits exacts. Sa couverture indie rock/folk est trop étroite pour le pool
généraliste, mais il constitue un bon petit pilote de production.

La résolution bornée du record Zenodo publié `19683001` a identifié 298 membres
WAV sur quatre archives (272 stems bruts, 10 masters stéréo, 10 masters 7.1.4
et 6 fichiers d'exemple), soit environ 10,73 Go décompressés. Deux archives
`ZIP64` (`stems_mixed.zip` et `stems_mixed_dry.zip`) restent non inspectées par
la sonde bornée. Ces 298 lignes restent techniquement ambiguës et ne comptent
dans aucun pool redistribuable ; le détail est dans
[`clean_corpus_albumdb_metadata_2026-10-29.md`](clean_corpus_albumdb_metadata_2026-10-29.md).
Une sélection reproductible de 12 membres est prête pour un futur pilote exact,
mais elle reste metadata-only et ne constitue pas une autorisation de
téléchargement ou de redistribution.
Le pilote privé exact a depuis vérifié 12 WAV PCM (0,546 h) ; il reste hors des
profils publics tant que les droits asset-level et l'écoute ne sont pas validés.

La même résolution metadata-only est maintenant réutilisable pour les records
Zenodo de ChoraleBricks, MusicNet, GuitarSet et Guitar-TECHS avec
`scripts/resolve_zenodo_metadata.py`. Les quatre records exposent CC BY 4.0,
mais leurs membres audio restent à inspecter ; aucun n'est donc encore copié
dans un pool public. Les tailles et checksums d'archives sont consignés dans
[`clean_corpus_zenodo_metadata_2026-10-29.md`](clean_corpus_zenodo_metadata_2026-10-29.md).

## Risques et critères GO/NO-GO

Le pool généraliste n'est pas encore GO : les fichiers locaux connus sont soit
juridiquement bloqués (SonicMaster/MUSDB/SDD), soit lossy (SDD), soit trop
spécialisés. Le prochain GO doit exiger :

1. plusieurs centaines de sources `clean_lossless` réellement vérifiées ;
2. diversité par genre, créateur et collection non concentrée sur classique ;
3. licences et dérivés approuvés asset par asset ;
4. séparation des artistes/sources entre train et validation ;
5. pilote curation v2.1 et écoute stratifiée avant tout lot massif.

Les datasets restreints restent utilisables pour les diagnostics locaux sans
entrer dans les manifests publics ni les benchmarks gelés.
