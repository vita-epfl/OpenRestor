# OpenRestor Clean — matrice de priorité (29 octobre 2026)

Les scores ci-dessous sont des priorités d'ingénierie, pas des décisions
juridiques. `public_research` et `public_commercial` ne sont attribués qu'après
validation de chaque asset.

| Dataset | Volume/format connu | Diversité utile | Sécurité juridique actuelle | Effort | Priorité | Décision immédiate |
| --- | --- | --- | --- | --- | --- | --- |
| IAMD → Internet Archive | 11 945 candidats ; 11 913 réponses résolues ; 2 324 originaux déclarés stricts ; 1 851 candidats de provenance ; pilote : 4 originaux vérifiés / 12 passages | potentiellement multi-genre et grande, distribution réelle à vérifier | `needs_permission`, licence/provenance par item | élevé | 1 | Phase 1 metadata-only terminée ; pilote audio borné en attente d'écoute, ne pas élargir avant adjudication |
| ChoraleBricks | 10 chorales, multitrack ; format/archive à vérifier | faible largeur, forte diversité d'instruments à vent | CC BY 4.0 annoncé par le site officiel | faible à moyen | 2 | meilleur premier adaptateur externe |
| GuitarSet | 8,2 GB ; hex-pickup/mic WAV | guitare acoustique uniquement | record Zenodo 3371780 : CC BY 4.0 ; membres à auditer | moyen | 3 | petit pilote technique après vérification |
| Guitar-TECHS | ~4,1 GB ; DI/mic/stéréo, WAV | guitare électrique et captures | record Zenodo 14963133 : CC BY 4.0 ; membres à auditer | moyen | 4 | supplément instrumental, pas pool généraliste |
| MusicNet | 330 enregistrements, 11,1 GB, PCM WAV | classique, instruments variés mais étroit | record Zenodo 5120004 : CC BY 4.0 ; membres à auditer | moyen | 5 | candidat classique pour `public_research` après audit |
| URMP | 44 pièces / 149 pistes annoncées dans les sources secondaires | chambre/classique | licence et dépôt original à confirmer | moyen | 7 | metadata + permission avant audio |
| FMA | 106 574 pistes, 161 genres ; MP3 | excellente largeur de genres | licence par artiste, pas licence globale | moyen à élevé | 8 | `clean_lossy_hq` seulement, pas lossless |
| MTG-Jamendo | grand catalogue ; format à vérifier | large tags/genres | licence par piste et historique à vérifier | élevé | 9 | ne pas confondre avec preuve SonicMaster |
| MAESTRO v3 | 1 276 performances, 198,7 h ; WAV PCM | presque exclusivement piano classique | CC BY-NC-SA 4.0 | moyen | 10 | `internal_research`/public NC éventuel, jamais commercial |
| MoisesDB | 240 pistes, >14 h, multitrack | genres multiples, volume réduit | recherche non commerciale uniquement | moyen | 11 | interne seulement sans permission supplémentaire |
| MedleyDB | multitrack, accès restreint | large mais droit restrictif | CC BY-NC-SA 4.0, non-commercial | élevé | 12 | ne pas intégrer au pool public |
| MUSDB18-HQ | 144 indexés localement ; WAV mixtures | large styles | académique, sources mixtes | nul (déjà local) | 13 | transfert interne uniquement |
| SDD | 705, 23,14 h ; MP3 | song collection large | licences par piste, NC/ND ; dérivés parfois interdits | nul (déjà local) | 14 | `clean_lossy_hq` interne, aucun public |
| SonicMaster clean | 25 000, 208,33 h ; FLAC local | large mais contenu/licence à vérifier | publication bloquée ; audit Jamendo insuffisant | nul (déjà local) | 15 | ne pas publier ni traiter comme clean lossless vérifié |
| AlbumDB | 10 chansons ; 13–35 stems/chanson ; PCM WAV 16-bit/44,1 kHz ; stéréo + 7.1.4 | indie rock/folk, couverture étroite mais production utile | CC BY 4.0 déclarée par le portail Aalto/Zenodo ; revue asset-level encore nécessaire | faible à moyen | 6 | petit pilote après inspection des membres et confirmation des crédits ; ne remplace pas le pool généraliste |

## Lecture opérationnelle

Le ratio volume réellement redistribuable / effort favorise actuellement :

1. ChoraleBricks pour valider la chaîne complète sur un petit corpus clair ;
2. MusicNet et GuitarSet pour augmenter rapidement le nombre de sources WAV,
   mais avec une séparation stricte des droits et des genres ;
3. IAMD pour la diversité et le volume, seulement après résolution des
   originaux et des licences ;
4. AlbumDB comme petit pilote lossless CC BY, sans le compter comme diversité
   générale ;
5. FMA comme complément lossy, jamais comme solution au pool lossless.

Le rapport Phase 1 IAMD (`build/iamd_feasibility/report.md`) est désormais
résolu pour 11 913 des 11 945 candidats. Ses 2 324 candidats techniques et
1 851 candidats de provenance restent des déclarations metadata-only : aucun
codec n'a été vérifié sur les fichiers originaux et aucun droit n'est approuvé
asset par asset. Le corpus ne doit pas être déclaré GO parce qu'un dataset est téléchargeable ou
que son dépôt est marqué « Open ». Le critère reste : fichier original vérifié,
licence applicable à l'audio, dérivés autorisés, provenance approuvée et
curation v2.1 validée sur un pilote indépendant.

La résolution API metadata-only du 29 octobre confirme la licence déclarée des
quatre records Zenodo, mais n'inspecte pas les membres des archives et ne
change pas encore leur statut de publication. Voir
[`clean_corpus_zenodo_metadata_2026-10-29.md`](clean_corpus_zenodo_metadata_2026-10-29.md).

## Sources officielles consultées

- [ChoraleBricks](https://www.audiolabs-erlangen.de/resources/MIR/2025-ChoraleBricks)
- [MusicNet](https://zenodo.org/records/5120004)
- [GuitarSet](https://zenodo.org/records/3371780)
- [Guitar-TECHS](https://zenodo.org/records/14963133)
- [MAESTRO](https://magenta.withgoogle.com/datasets/maestro)
- [AlbumDB — portail Aalto](https://research.aalto.fi/en/datasets/albumdb-a-multitrack-dataset-of-a-ten-song-album-with-stereo-and-immersive-714-masters/)
- [MedleyDB](https://zenodo.org/records/1649325)
- [FMA](https://github.com/mdeff/fma)
