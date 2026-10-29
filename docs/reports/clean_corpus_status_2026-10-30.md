# OpenRestor Clean v0.1 — état vérifié au 30 octobre 2026

Ce point est un état de dépôt et de manifests. Il ne constitue pas une
autorisation de redistribution et ne transforme aucun candidat en donnée
publique.

## État technique

- La branche `roadmap-sync` est synchronisée avec `origin/roadmap-sync`.
- La suite complète exécute **274 tests**, dont 4 ignorés ; les 270 autres
  passent.
- Les manifests sans chevauchement exact avec les benchmarks contiennent
  **2 045 sources** ; le manifest fusionné de droits en contient **28 014**.
- Les deux manifests principaux passent la validation `clean_manifest`.
- L'extraction locale et la reprise du cache conservent maintenant les
  annotations, décisions de source et historique humain du manifest. Les
  segments sont toutefois régénérés si le fichier ou la politique
  d'échantillonnage change.

## État des candidats audio

Le rapport `build/clean_corpus/no_benchmark_overlap_verified_pilot_pool_report.json`
résume la vue sans chevauchement exact après rattachement des 12 fichiers WAV
AlbumDB du pilote privé. Le rapport lui-même ne lit pas l'audio ; la jointure
qui le précède recontrôle les fichiers locaux par taille, CRC, SHA-256 et
format PCM.

Les 12 fichiers ont aussi récupéré leurs **32 passages** et les décisions v2.1
déjà calculées : 1 `auto_accept`, 8 `manual_review`, 3 `auto_reject` au niveau
source. Ces décisions sont acoustiques et portent sur les passages échantillonnés.

| Champ | Valeur |
| --- | ---: |
| Sources candidates | 2 045 |
| Durée connue (1 759/2 045 sources) | 183,74 h |
| Taille non compressée connue (310/2 045 sources) | 10,95 Go |
| Candidats techniques | 1 759 |
| Candidats de provenance heuristiques | 2 045 |
| Candidats redistribuables approuvés | 0 |
| `clean_lossless` confirmé | 0 |
| `clean_lossy_hq` confirmé | 0 |
| Statut original ambigu | 310 |
| Original déclaré, non vérifié | 1 731 |
| Original Archive téléchargé, codec encore à vérifier | 4 |

Les 2 045 lignes sont réparties entre IAMD (1 735), AlbumDB (298),
Guitar-TECHS (7), GuitarSet (4) et ChoraleBricks (1). Les formats déclarés
sont WAV (1 382), FLAC (669), AIFF (22) et WAVEX (2), sans que cette
déclaration metadata-only prouve encore un fichier original réellement
lossless. Douze membres AlbumDB sont reliés à leur fichier local ; leur statut
d'original et leurs droits restent ambigus. Les genres restent inconnus pour
2 039 lignes ; ce point interdit de conclure à la diversité musicale avant
lecture et annotation. La durée des 286 autres sources et la taille de 1 735
sources IAMD ne sont pas connues dans ce rapport ; les valeurs du tableau sont
des sommes partielles, pas une estimation complète du coût d'acquisition.

## Droits et release

- Le lot déterministe de revue contient 100 lignes réparties sur les cinq
  datasets. Le formulaire CSV est encore vierge : aucune approbation humaine
  n'a été importée.
- Une file plus immédiate de 12 membres AlbumDB vérifiés est disponible dans
  `build/clean_corpus/albumdb_verified_pilot_rights_review.csv` et sa page
  HTML locale ; elle utilise les identifiants canoniques et garde ses 12
  décisions vierges.
- La cohérence licence/URL est vérifiée mécaniquement pour 2 045 lignes,
  mais cela ne prouve ni la titularité, ni le statut original, ni le droit de
  redistribution de l'audio.
- `release_readiness_verified_pilot.json` donne **NO-GO**, sans erreur
  structurelle : `public_research=0`, `public_commercial=0`,
  `internal_research=0`, `blocked=28 014`.
- Les vues `public_research` et `public_commercial` sont désormais
  cumulatives : un asset commercial approuvé figure dans les deux vues, sans
  être compté deux fois comme source publique unique. La porte de release
  vérifie cette inclusion et refuse une vue qui modifierait les droits ou le
  checksum du manifest canonique. Le pilot courant reste à zéro source
  publique ; ce correctif ne crée aucune nouvelle permission.
- Aucun audio Clean n'a été copié ou téléversé dans une release ; les droits
  n'ont pas été inférés. Le candidat de release RIR séparé passe avec 14 RIR et leurs
  notices/checksums.
- L'audit de chevauchement exact garde 2 045 sources, dont les 12 AlbumDB
  rattachées ; le split recalculé est disjoint. La jointure change exactement
  ces 12 lignes techniques, sans modifier un seul objet `rights`. Un risque de
  fuite album a été corrigé : auparavant, les 298 assets AlbumDB d'un même
  album étaient répartis entre train (208), validation (51) et test (39).
  Ils sont maintenant tous regroupés en validation dans le split courant.
- L'audit acoustique commun a décodé les 28 fichiers déjà locaux des cinq
  datasets (0 échec). Il propose trois paires de doublons, toutes entre la
  version stéréo et immersive d'un même morceau AlbumDB ; ce sont des
  candidats de revue, pas des suppressions automatiques.
- La fiche officielle Aalto et le catalogue Zenodo indiquent CC BY 4.0 pour
  AlbumDB, mais la portée exacte de cette licence sur chaque enregistrement et
  les crédits à appliquer restent à confirmer. Les questions ciblées sont
  consignées dans
  [`clean_corpus_albumdb_rights_questions_2026-10-30.md`](clean_corpus_albumdb_rights_questions_2026-10-30.md).

## Suite priorisée

1. Examiner d'abord les 12 membres AlbumDB locaux, notamment les masters
   stéréo, et faire valider leurs droits asset-level (licence exacte,
   attribution, preuve, checksum et permissions). Le lot de revue de 100
   sources reste disponible pour la suite.
2. Appliquer les overrides validés, reconstruire le registre et relancer les
   audits de profils et de release.
3. Pour les assets approuvés, confirmer le statut d'original et la qualité
   sonore, puis poursuivre la curation multi-passages et la déduplication
   acoustique déjà commencées sur le pilote privé.
4. Recalculer les splits sans chevauchement, puis préparer un petit pack
   public de recherche ; aucun téléchargement massif ni modification de
   benchmark n'est requis avant ces trois validations.

Le prochain jalon objectif est un profil `public_research` non vide avec des
preuves asset-level complètes. Tant qu'il n'est pas atteint, le verdict reste
NO-GO et les candidats restent privés.
