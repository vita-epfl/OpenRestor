# OpenRestor Clean — pilote Zenodo privé, round 2 (29 octobre 2026)

Ce round étend le pilote de trois fichiers à douze membres sélectionnés parmi
les headers déjà sondés. Il reste strictement privé : aucun fichier n'est
ajouté à un profil public, à un benchmark ou à une release.

## Acquisition et vérifications

- 12/12 membres téléchargés sans archive complète ;
- 114 043 230 octets compressés et 224 608 150 octets décompressés ;
- 1 563,55 secondes d'audio (26,1 minutes) ;
- CRC-32 et taille ZIP vérifiés pour chaque membre ;
- SHA-256 calculé sur chaque fichier local ;
- lecture `soundfile` réussie pour tous les fichiers ;
- 10 fichiers lus comme WAV et 2 comme WAVEX ; 7 à 48 kHz, 5 à 44,1 kHz ;
- provenance et droits restent `ambiguous_original_status` et
  `metadata_confirmed_pending_asset_review`.

Répartition : 1 ChoraleBricks, 7 Guitar-TECHS et 4 GuitarSet. Le lot couvre
des accords, gammes, techniques, notes isolées et deux extraits musicaux, mais
ne constitue pas encore un échantillon représentatif d'un corpus généraliste.

## Curation automatique

Les extraits de 24 secondes ont été traités par les mesures acoustiques, puis
par AST, CLAP et Audiobox dans l'environnement CPU existant. La politique v2.1
est restée inchangée.

| Décision | Nombre |
| --- | ---: |
| `auto_accept` | 2 |
| `manual_review` | 10 |
| `auto_reject` | 0 |

Les scores `clean_score` vont de 0,3836 à 0,8614 (moyenne 0,6501). Les motifs
de revue les plus fréquents sont : garde PQ basse (6), accord multisignal
(5), garde CLAP de captation dégradée (3), bande passante (2) et désaccord
entre passages (2). Les deux acceptations concernent des extraits GuitarSet
avec score 0,8204 et 0,8614 ; elles restent des décisions acoustiques, pas des
autorisations de redistribution.

Le détail par source, les scores et les raisons est dans :

- `build/clean_corpus/private_pilot/pipeline_judgments_v21_probed_12.jsonl` ;
- `build/clean_corpus/private_pilot/decisions_v21_probed_12.jsonl` ;
- `build/clean_corpus/private_pilot/features_probed_12.jsonl`.

Le manifest de candidats de passages
`build/clean_corpus/private_pilot/clip_candidates_v21.jsonl` contient 3
segments `auto_accept` provenant de 3 sources. Le résumé associé est
`clip_candidates_v21_summary.json`. Les trois segments ont
`rights_gate_passed=false` (`provenance_not_approved`) : ce manifest facilite
la revue et la sélection de passages, mais n'ouvre aucun droit et ne copie
aucun audio.

Le rapporteur générique `scripts/report_clean_curation.py` a également produit
`build/clean_corpus/private_pilot/curation_report_12.json` et son équivalent
Markdown. Il conserve les métriques du passage primaire et les min/max/médianes
sur tous les passages, les agrégats par dataset/créateur/collection et le
statut des droits sans convertir les décisions de passages en labels humains.

La page d'écoute aveugle et son ordre figé sont :

- `build/clean_corpus/private_pilot/pilot_listen_12.html` ;
- `build/clean_corpus/private_pilot/pilot_listen_12_with_predictions.html` (vue
  d'analyse non aveugle, avec scores et motifs) ;
- `build/clean_corpus/private_pilot/blind_order_12.jsonl` ;
- `build/clean_corpus/private_pilot/blind_order_12_annotations.csv`.

Un extrait bien scoré ne valide pas toute la source : les décisions restent
au niveau des passages et la page permet d'écouter les passages alternatifs.
L'import prévu est `import-blind-reviews`, qui remappe les `blind_id` via
`blind_order_12.jsonl` et ignore les lignes non annotées.

## Droits et suite

La file de revue contient maintenant 16 assets (12 Zenodo et 4 IAMD), sans
chemins audio ni octets. Les profils privés donnent 12 `blocked`, zéro
`public_research` et zéro `public_commercial`. Les champs
`provenance_approved` et `redistribution_approved` sont faux partout.

Ce round confirme la chaîne technique, mais ne permet pas encore d'estimer un
rendement généralisable : il est très spécialisé instrument/collection et ne
comporte aucune annotation humaine définitive. La prochaine décision doit se
faire après écoute aveugle de ces 12 sources et revue asset-level ; aucun lot de
200 ou de 750 membres ne doit être lancé avant cette adjudication.

Un audit de split metadata-only sur les 2 040 candidats catalogue plus les 12
pilotes donne 2 052 sources, zéro doublon exact détecté et des groupes
disjoints. Après séparation entre attribution du record et créateur de l'asset,
la répartition déterministe est 1 404 train, 289 validation et 359 test ;
1 837 lignes restent sans créateur exploitable. Les 215 lignes identifiées
utilisent uniquement les interprètes explicitement présents dans les chemins
Guitar-TECHS (P1/P2/P3). Ce résultat est un audit de risque, pas un split de
release : les créateurs manquants devront être vérifiés dans les archives.
