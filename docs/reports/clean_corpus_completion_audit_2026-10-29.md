# OpenRestor Clean v0.1 — audit de complétude (29 octobre 2026)

Ce document confronte le cahier des charges Clean v0.1 à l'état vérifiable du
dépôt. Il ne transforme pas les candidats en données publiables et ne vaut pas
autorisation juridique.

## État des livrables

| Exigence | Preuve actuelle | Statut | Limite restante |
| --- | --- | --- | --- |
| Registre des droits et quatre pools | `configs/datasets/clean_corpus_rights_registry.yaml`, `scripts/build_media_rights_registry.py --clean-corpus-manifest`, `scripts/filter_clean_manifest_profiles.py` | partiel mais opérationnel | l'approbation doit rester asset par asset |
| Inventaire local | `docs/reports/clean_corpus_dataset_audit_2026-10-29.md`, `build/clean_corpus/inventory*` | réalisé | SonicMaster/MUSDB/SDD restent non publiables |
| Matrice volume/diversité/effort | `docs/reports/clean_corpus_priority_matrix_2026-10-29.md` | réalisé | les chiffres IAMD restent metadata-only |
| Manifest commun multi-dataset | `scripts/normalize_clean_manifest.py`, `scripts/merge_clean_manifests.py`, `schemas/clean_manifest.schema.json`, `openrestor-validate clean_manifest`, `scripts/prepare_clean_pilot_manifest.py`, `scripts/prepare_iamd_archive_manifest.py`, `scripts/prepare_zenodo_archive_manifest.py` | réalisé sur pilotes, Zenodo metadata-only, IAMD metadata-only et pilote audio privé séparé ; normalisation et fusion valident maintenant structure, identité et unicité des lignes | AlbumDB/URMP/etc. n'ont pas encore de fichiers locaux validés |
| Classification lossless/lossy | `scripts/audit_clean_corpus_sources.py` | réalisé | 4 originaux IAMD sont maintenant `clean_lossless` techniquement ; les autres sources restent à vérifier |
| Déduplication exacte et splits | `scripts/prepare_clean_corpus_splits.py`, `build/iamd_feasibility/iamd_archive_split_audit.json`, `build/clean_corpus/zenodo_combined_split_audit.json` | réalisé sur l'inventaire, IAMD metadata-only et 2 052 lignes Zenodo ; regroupement checksum/créateur par composantes liées | 2 040 lignes Zenodo n'ont aucun checksum local ; créateurs d'assets encore manquants pour la plupart |
| Chevauchement avec benchmarks/tests gelés | `scripts/audit_clean_benchmark_overlap.py`, `build/clean_corpus/benchmark_overlap_report.json` | réalisé metadata-only : 25 969/28 014 lignes recouvrent des manifests de benchmark ou validation ; 2 045 restent sans correspondance exacte | l'absence d'identité exacte ne prouve pas l'absence de doublon acoustique ; exécuter l'audit fingerprint après accès aux originaux |
| Rapport de volume/diversité des candidats sans overlap | `scripts/report_clean_candidate_pool.py`, `build/clean_corpus/no_benchmark_overlap_pool_report.json` | réalisé : 2 045 lignes, 1 747 candidats techniques, 0 candidats redistribuables ; les licences et genres inconnus restent explicites | la durée est une estimation metadata-only ; qualité audio, checksums originaux et droits restent à valider |
| File privée de revue asset-level hors benchmark | `scripts/export_clean_rights_review_queue.py`, `build/clean_corpus/no_benchmark_overlap_rights_review_queue.jsonl` | réalisé : 2 045 lignes, aucun chemin audio, permissions inchangées | chaque licence, provenance, crédit et checksum doit encore être validé par asset |
| Lot priorisé de revue des droits | `scripts/select_clean_rights_review_batch.py`, `build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.jsonl` | réalisé : 100 lignes déterministes, 5 datasets représentés, droits inchangés | ce lot reste metadata-only et ne constitue pas un pilote audio ou une autorisation |
| Formulaire CSV et import des décisions de droits | `scripts/export_clean_rights_review_form.py`, `scripts/import_clean_rights_review_form.py`, `build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.csv` | réalisé : 100 lignes vierges, import fail-closed et overrides privés compatibles avec le registre | aucune décision humaine n'est encore renseignée ; aucune approbation n'est produite |
| Cohérence des licences déclarées | `scripts/audit_clean_rights_license_consistency.py`, `build/clean_corpus/no_benchmark_overlap_rights_license_consistency_report.json` | réalisé : 2 045/2 045 labels concordent avec une URL CC versionnée ; 0 URL manquante, inconnue ou contradictoire | cette concordance ne prouve ni titularité, ni original, ni redistribution |
| Interface locale de revue des droits | `scripts/build_clean_rights_review_html.py`, `build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.html` | réalisé : 100 lignes, 5 datasets, filtres et export CSV local, aucun audio ni réseau | aucune décision humaine n'est encore renseignée |
| Déduplication acoustique | `scripts/audit_clean_audio_duplicates.py`, `scripts/select_deduplicated_candidates.py` | outil réalisé, pilote exécuté et sélection report-only vérifiée | le corpus complet n'a pas encore été téléchargé/lu ; les groupes restent à confirmer humainement |
| Curation AST/CLAP/Audiobox | `openrestor/curation`, pilote Zenodo privé 12 fichiers, pilote IAMD commun 4 fichiers | réalisé sur 16 sources | aucune annotation Zenodo définitive ; pas d'estimation statistique généralisable |
| Export des passages candidats | `scripts/export_clean_clip_candidates.py`, manifest v2.1 du pilote Zenodo | réalisé metadata-only : 3 segments sur 3 sources | les trois gates de droits restent bloqués ; un segment accepté ne valide pas sa source entière |
| Rapport source-level multi-passages | `scripts/report_clean_curation.py`, `build/clean_corpus/private_pilot/curation_report_12.json` | réalisé | descriptif uniquement ; ne remplace pas l'adjudication humaine |
| Passages de 20–30 secondes et écoute | `build/clean_corpus/private_pilot/pilot_listen.html` | réalisé sur 3 sources | écoute humaine encore nécessaire |
| Provenance/checksum/attribution par asset | manifest pilote + ledger + registry, `scripts/prepare_iamd_pilot_manifest.py` | partiel | 4 fichiers IAMD complets vérifiés, 56 non vérifiés (dont 1 transfert en erreur avec fragment `.part`) ; droits en attente |
| Compatibilité avec génération de dégradations | smoke test IAMD : 19/21 recettes sur extrait local | partiel mais vérifié techniquement | `codec`/`neural_codec` exigent FFmpeg ; aucun candidat redistribuable approuvé |
| Corpus public train/validation | aucun profil public non vide ; IAMD Phase 1 metadata-only et pilote audio privé | non réalisé | volume lossless redistribuable insuffisant et droits asset-level non approuvés |
| Estimation commercial-compatible | profils `public_commercial` vides | non réalisé | licences et dérivés non approuvés asset-level |
| Audit mécanique de release | `scripts/audit_clean_release_readiness.py`, `scripts/check_initial_release_candidate.sh`, `build/clean_corpus/merged_release_readiness.json` | réalisé, verdict NO-GO pour l'audio Clean ; candidat metadata-only validé | aucun profil public approuvé ; le code de sortie bloque la release audio |

## Vérification mécanique courante

Les vues générées après le renforcement du contrôle de provenance sont
cohérentes :

- le manifest local historique contient 25 849 lignes ; le manifest fusionné
  courant (`build/clean_corpus/rights_registry_input.jsonl`) contient 28 014
  lignes après déduplication des clés et quatre remplacements explicitement
  enregistrés ;
- le split correspondant (`build/clean_corpus/merged_split_audit.json`) en
  conserve 28 012 après deux doublons exacts et confirme des groupes disjoints.
  Le regroupement par composantes liées checksum/créateur donne 28 012 sources
  dans 26 941 groupes (`train=19 571`, `validation=4 332`, `test=4 109`) ;
- les quatre profils multi-dataset fusionnés contiennent 28 014 lignes `blocked`, zéro
  `public_research`, zéro `public_commercial` et zéro `internal_research` ;
  le rapport distingue 27 716 lignes sans approbation de provenance et 298 lignes
  AlbumDB encore `technical_candidate=false` ;
- la vue IAMD combinée contient 1 855 lignes et ses profils ont la même
  partition complète, sans erreur mécanique ;
- le résumé privé des droits ne compte comme publiables que les 14 RIR dont la
  provenance a été explicitement vérifiée. Aucun asset Clean audio n'est ainsi
  implicitement autorisé par sa seule licence catalogue.
- le packager exige maintenant explicitement `provenance_approved=true` **et**
  `redistribution_approved=true`, en plus des permissions de licence ; les 14
  RIR approuvés portent ces deux validations.

Les preuves correspondantes sont `build/clean_corpus/merged_split_audit.json`,
`build/clean_corpus/merged_release_readiness.json`,
`build/iamd_feasibility/combined_release_readiness.json` et
`build/rights/public_summary.json`.

Le candidat local metadata-only est décrit dans
[`clean_corpus_release_candidate_2026-10-29.md`](clean_corpus_release_candidate_2026-10-29.md).
Le contrôle passe les invariants de notices, checksums RIR, absence d'audio et
d'identifiants privés, tout en conservant `upload_approved=false`.

Une relance du gate le 30 octobre 2026 (`build/clean_corpus/merged_release_readiness_current.json`)
confirme la partition complète des 28 014 lignes : 28 014 `blocked`, zéro
`internal_research`, zéro `public_research` et zéro `public_commercial`. Le
verdict est `NO-GO` avec zéro erreur structurelle et l'avertissement
`no_public_sources`. Cela signifie qu'aucune approbation asset-level n'est
enregistrée ; ce n'est pas un refus juridique individuel de chaque source. Le
candidat RIR indépendant continue de passer
`scripts/check_initial_release_candidate.sh` avec 14 RIR et aucun audio.

Le registre privé courant est reconstruit depuis
`build/clean_corpus/rights_registry_input.jsonl` par
`scripts/merge_clean_manifests.py` puis
`scripts/build_media_rights_registry.py` : 28 410 assets sont indexés, dont
1 855 IAMD, 298 AlbumDB metadata-only et 12 membres Zenodo. Les quatre lignes IAMD audio vérifiées
remplacent leurs doublons metadata-only ; les 1 855 lignes IAMD, les 12 lignes
Zenodo et les sources locales restent `pending`/non approuvées. Les profils
agrégés ne comptent donc toujours que les 14 RIR approuvés. Les 12 lignes
Zenodo portent désormais `evidence_date=2026-10-29`, issue de la résolution
metadata-only ; cette date ne vaut pas validation asset-level.

Le probe Zenodo a également été transformé en manifest multi-dataset
metadata-only : 2 040 membres WAV nommés (392 ChoraleBricks, 1 440 GuitarSet,
208 Guitar-TECHS), tous avec `technical_candidate=false`, droits en attente et
`ambiguous_original_status`. Ce manifest n'ajoute aucun audio au corpus et ne
change pas le verdict de release ; MusicNet reste non résolu dans ce probe car
le record AlbumDB est suivi séparément : ses 298 membres WAV metadata-only sont
répertoriés dans `clean_corpus_albumdb_metadata_2026-10-29.md` et restent eux
aussi exclus des profils publics.
son archive est TAR.GZ.

Un second pilote privé a depuis vérifié 12 membres Zenodo (1 563,55 secondes,
114 043 230 octets compressés) avec CRC, taille, SHA-256 et lecture locale.
AST/CLAP/Audiobox et v2.1 donnent 2 `auto_accept` et 10 `manual_review`, sans
`auto_reject`. Les fichiers restent tous bloqués juridiquement et le résultat
est documenté dans
[`clean_corpus_zenodo_private_pilot_round2_2026-10-29.md`](clean_corpus_zenodo_private_pilot_round2_2026-10-29.md) ; il ne constitue pas une
validation statistique ni une autorisation de téléchargement massif.

## Résultat vérifié du pilote externe

Trois fichiers déjà téléchargés et vérifiés par checksum ont été traités : un
ChoraleBricks et deux GuitarSet. AST, CLAP et Audiobox ont fonctionné dans
l'environnement CPU existant. La v2.1 donne deux `auto_accept` et une
`manual_review`, mais le filtre de droits donne trois `blocked` et zéro source
dans les trois autres pools.

Le pilote IAMD Phase 1b a vérifié quatre pistes originales (WAV/FLAC) et douze
extraits de 18 secondes. Les mesures acoustiques et Audiobox PQ ont été
calculées sur ces extraits ; les médianes PQ par piste vont de 5.97 à 8.16.
Une cinquième tentative a atteint le timeout et reste un fragment `.part` ; elle
est comptée dans les 56 sources non vérifiées et n'est pas utilisée comme audio
valide. Les autres sources du plan restent non téléchargées ; les 12 passages
restent en attente d'annotation humaine et ce résultat n'est donc pas
extrapolable.

Ces quatre pistes ont ensuite traversé le manifeste et le scoreur commun
AST/CLAP/Audiobox avec des passages de 24 secondes. Les quatre décisions v2.1
sont `manual_review` (aucune acceptation ou rejet automatique), avec les motifs
et les scores conservés dans
`build/iamd_feasibility/phase1b/common_curation/`. Le détail est dans
[`clean_corpus_iamd_common_curation_pilot_2026-10-29.md`](clean_corpus_iamd_common_curation_pilot_2026-10-29.md).

Le nouveau gate technique
`scripts/audit_clean_corpus_sources.py` confirme séparément les quatre fichiers
comme `clean_lossless` : trois WAV et un FLAC, 0,225 heure, codec PCM et
SHA-256 local concordant avec le manifeste. Cette conclusion est strictement
technique ; les quatre lignes restent `pilot_pending_asset_review`, avec
`redistributable_candidate=false`, jusqu'à l'approbation de provenance et de
redistribution.

Pour IAMD, le plan audio privé borné existe dans
`build/iamd_feasibility/phase1b/plan.json` : 60 fichiers tirés par collection,
3 passages de 18 secondes et un plafond de 10 Gio. Le plan n'est pas une
autorisation de téléchargement ou de publication. L'état courant contient
quatre pistes vérifiées, une tentative en erreur et 12 passages en attente de
revue ; il ne doit donc pas être interprété comme un rendement généralisable ni
comme une approbation de publication. Le manifeste Phase 1 et le split audit
restent metadata-only.

Le split audit IAMD (`build/iamd_feasibility/iamd_archive_split_audit.json`)
donne 1 851 sources, zéro doublon exact observé, 1 851 groupes sans checksum
local et des groupes créateurs disjoints entre train/validation/test. Le
résultat est utile pour préparer le pilote, mais ne remplace pas la
déduplication après vérification des fichiers originaux.

L'audit exact de chevauchement
`build/clean_corpus/benchmark_overlap_report.json` exclut 25 849 lignes qui
correspondent aux manifests paired/blind-synthetic historiques et 120 lignes
de la validation IAMD indépendante. Les mêmes 25 849 lignes sont aussi
présentes dans l'index de la release paired ; le contrôle couvre également les
manifests Blind-Real de test et de release. Il laisse 2 045 lignes sans identité
exacte correspondante dans ces références. Cette liste est un filtre de
provenance scientifique, pas une preuve de qualité audio ou de droits ; les
doublons acoustiques nécessitent encore des fichiers originaux et un fingerprint.

Les 2 045 lignes restantes ont reçu un split metadata-only dans
`build/clean_corpus/no_benchmark_overlap_split_audit.json` : 1 383 train,
282 validation et 380 test, avec 1 025 groupes liés et aucun chevauchement de
groupe. Ce manifest demeure un ensemble de candidats : 2 029 lignes n'ont pas
encore de checksum de contenu et les droits restent indépendants.

La synthèse `build/clean_corpus/no_benchmark_overlap_pool_report.json` estime
183,191 heures à partir des durées de catalogue, mais **0 candidat
redistribuable** et 2 039 genres inconnus. La répartition est dominée par
IAMD (1 735/2 045) et `opensource_audio` (1 289/2 045) ; ces chiffres décrivent
la composition du catalogue résiduel, pas un corpus clean validé.

La file privée `build/clean_corpus/no_benchmark_overlap_rights_review_queue.jsonl`
reprend ces 2 045 sources avec les identifiants de fichier, les notices et les
preuves disponibles. Elle confirme `audio_paths_included=false`,
`rights_are_not_inferred=true`, et zéro approbation de redistribution ou de
provenance. Elle sert à la revue juridique asset-level ; elle n'ouvre aucun
profil public.

Le premier lot priorisé
`build/clean_corpus/no_benchmark_overlap_rights_review_batch_100.jsonl` contient
100 lignes : 44 AlbumDB, 44 IAMD, 7 Guitar-TECHS, 4 GuitarSet et 1
ChoraleBricks. La sélection équilibre aussi les licences et les collections,
mais ne prétend pas représenter la qualité audio ni la diversité finale du
corpus. Son empreinte de clés est
`b4441284f61a9fb923d408394e338755f6363889484b963bbd975cd8a2e6b15d`.

Le formulaire CSV associé contient 100 décisions vierges. L'importeur accepte
`approved`, `rejected` ou `pending`, ignore les lignes sans décision et exige
pour une approbation la licence exacte, le crédit, les permissions, la preuve,
le statut d'original vérifié et le SHA-256. Il vérifie aussi l'ensemble des
`source_key` contre le lot JSONL et refuse les identifiants inconnus ou manquants
par défaut. Il ne peut donc pas transformer une ligne non annotée en
autorisation. L'import du formulaire actuel confirme 100 lignes attendues,
100 lignes vierges et 0 override (`build/clean_corpus/no_benchmark_overlap_rights_review_batch_100_import_report.json`).

L'audit de cohérence des licences sur les 2 045 lignes donne 2 045 URLs CC
versionnées et concordantes avec leur label déclaré, réparties sur les cinq
datasets. Il s'agit uniquement d'un contrôle de métadonnées : les 2 045 lignes
restent `pending`, sans approbation de provenance ou de redistribution.

La page HTML locale de revue du lot de 100 reprend la même empreinte de clés
(`b4441284f61a9fb923d408394e338755f6363889484b963bbd975cd8a2e6b15d`). Son
rapport indique `audio_loaded=false`, `network_requests=false` et
`permissions_changed=false`.

L'étape `scripts/apply_clean_rights_overrides.py` applique désormais les
overrides non vides au manifest privé après import CSV. Elle refuse les
doublons et identifiants inconnus, conserve les chemins audio et les scores,
met à jour le checksum top-level seulement lorsqu'il est vérifié, et ajoute
un historique par source avec le digest de la décision. Testée sur le
formulaire courant, elle a conservé les 2 045 lignes avec zéro override et
zéro copie audio ; la sortie reste donc entièrement en attente de revue.

Sur le pilote AlbumDB, l'audit acoustique a identifié trois paires stéréo /
7.1.4. Le sélecteur report-only a retenu les masters stéréo de ces groupes et
conservé tous les segments des sources retenues : 12 segments sur 8 sources
deviennent 8 segments sur 5 sources. La sortie est
`build/clean_corpus/albumdb_private_pilot/clip_candidates_v21_dedup.jsonl`;
aucun fichier audio n'est copié ou supprimé et aucun droit n'est déduit de ce
choix. Les masters immersifs restent disponibles dans le pilote pour une
vérification séparée.

Ce résultat montre que la chaîne technique est exécutable ; il ne démontre ni
la qualité globale des datasets, ni l'autorisation de redistribution, ni la
diversité du futur corpus.

## Verdict

**NO-GO pour une release Clean v0.1 publique à ce stade.** Le dépôt possède
les registres, adaptateurs, contrôles et un pilote reproductible. La Phase 1
IAMD a maintenant résolu 11 913/11 945 réponses Archive : 2 324 items sont
des candidats techniques stricts, 1 851 des candidats de provenance et 1 851
des candidats redistribuables au sens heuristique du rapport
`build/iamd_feasibility/report.md`. Ces nombres ne valent ni validation du
codec, ni preuve de titularité, ni autorisation de redistribution : la
résolution Phase 1 elle-même n'a demandé aucun audio IAMD. Un pilote privé
Phase 1b contient quatre originaux vérifiés et douze passages mesurés, mais il
reste hors des profils publics et ne constitue pas une source disponible pour
redistribution.

Le prochain jalon GO est conditionné à une revue humaine du pilote audio
original, une validation asset-level et des splits sans fuite. Le catalogue
prioritaire doit être mis à jour après chaque résolution, sans traiter les
candidats IAMD comme un pool public avant ces contrôles.

