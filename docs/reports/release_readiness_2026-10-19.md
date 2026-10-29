# OpenRestor v0.1 — état de préparation à la diffusion (19 octobre 2026)

Ce document décrit une **candidate locale**, pas une autorisation d'upload. Le commit/tag
Git est l'artefact canonique des 14 RIR ; le corpus apparié gelé reste privé et inchangé.
Les deux profils sont « médias compatibles avec un usage commercial » et « recherche
effectivement non commerciale ». La licence proposée pour les composants EPFL est une
question distincte : elle n'accorde pas de licence commerciale du logiciel.

## Résultat vérifié

| Contrôle | Résultat |
| --- | --- |
| Registre privé par média | 26 245 entrées : 25 000 SonicMaster, 705 SDD, 144 MUSDB, 382 Blind-Real, 14 RIR. Voir `build/rights/media_registry.jsonl` (ignoré par Git). |
| Profils | Seuls les 14 RIR sont marqués approuvés côté provenance/licence dans les deux profils. Les pistes audio restent en attente ou bloquées. BY-SA et BY-NC-SA sont des familles de packs distinctes, jamais fondues dans le socle BY. |
| Candidate locale initiale | `build/release-candidates/rights-v0_1-20261019-final/` : quatre index vides (Diagnostic et Blind-Synthetic × deux profils), zéro audio synthétique, aucun `source_id` privé ; notices Apache, tierces, RIR et SHA-256 présentes. |
| RIR | 14 empreintes SHA-256 vérifiées ; attribution Spokane : `www.openairlib.net` et James Cadwallader, CC BY 3.0 et lien source dans `ATTRIBUTION.md`. |
| Blind-Real | 382 clips présents dans une ancienne candidate interne, mais aucun n'a passé la revue indépendante de titularité ; le packager échoue désormais avant copie tant que la provenance n'est pas approuvée par clip. |

Le registre contient des licences *observées*, parfois incomplètes. `null` signifie
« inconnu ». Les 25 000 entrées SonicMaster restent `pending`, y compris les 856 BY
signalées par l'API. Les 705 entrées SDD n'ont pas encore d'URL de licence ni de crédit
vérifié par piste. MUSDB n'a pas de droit de redistribution démontré. Les tags CC0/BY
d'Internet Archive pour Blind-Real sont des déclarations d'uploader, pas une preuve de
titularité. Les 14 RIR ont une revue de provenance documentée, mais **l'upload du projet
attend toujours l'accord EPFL/laboratoire/TTO**.

## À obtenir avant publication

1. Responsable de laboratoire/TTO : confirmer le titulaire et le statut de chaque
   contributeur, les contrats/financements/brevets, le périmètre du code EPFL et des
   métadonnées, le texte exact de la licence académique, le mode d'accès et le circuit
   pour entreprises. Compléter [l'inventaire logiciel](../templates/software_release_inventory.md)
   et envoyer la [demande d'accord](../templates/academic_supervisor_approval_request.md).
   Ne pas ajouter de `LICENSE` racine avant cette décision. Le code adapté de SonicMaster
   garde son Apache-2.0 et ses notices ; la frontière des modifications EPFL doit être
   validée.
2. RIR : conserver le commit/tag, `ATTRIBUTION.md` et les 14 SHA-256 dans toute release ;
   faire confirmer la diffusion finale avec les autres actifs EPFL. Le tarball standalone
   n'est nécessaire que si DASH/Zenodo/IT en fait la demande.
3. Blind-Real : documenter et signer la provenance par clip, notamment les exceptions,
   avant de passer `review_status` à `approved` dans une revue privée. Regénérer ensuite
   un pack neuf avec attributions, modifications et checksums. Aucun clip n'est publié
   sur la seule base d'un tag Internet Archive.
4. Audio synthétique : ne rien publier en v0.1. Conserver Diagnostic/Blind-Synthetic et
   SDD/MUSDB pour l'usage local autorisé ; pas de requalification silencieuse en entraînement
   principal. Étudier séparément une preuve directe d'artiste/source pour quelques pistes
   SonicMaster. Une réponse Jamendo serait utile mais n'est pas le chemin critique de la
   première diffusion. Ne pas acquérir massivement via l'API sans revue de ses
   [conditions](https://devportal.jamendo.com/api_terms_of_use), notamment commercial/offline.
5. Évaluation cachée (par exemple Montreux) : aucun scraping ni redistribution ; obtenir
   un accord écrit couvrant accès, usage, conservation et éventuels partenaires industriels.

## Reproduire les contrôles (sans upload)

```bash
bash scripts/prepare_rights_profiles.sh
bash scripts/test_rights_release.sh
# Pour créer une nouvelle candidate locale, choisir un chemin vide :
bash scripts/prepare_rights_profiles.sh --copy-into build/release-candidates/<nouveau-nom>
bash scripts/check_initial_release_candidate.sh build/release-candidates/<nouveau-nom>
```

Une future revue approuvée par média peut être fournie au constructeur du registre via
`RIGHTS_REVIEW_OVERRIDES=build/rights/reviews.jsonl bash scripts/prepare_rights_profiles.sh`.
Chaque entrée JSONL doit conserver l'identité
`media_key`, les preuves datées, l'URL/version exacte de licence, les crédits, les
permissions trivalentes et le nom du réviseur. Le constructeur ne contacte aucun service
externe ; la sortie détaillée et les overrides restent sous `build/` et ne sont pas à
committer. Le script de packaging reconstruit les shards HDF5 éligibles et vérifie
index, hash et IDs physiques avant une future remise à IT. Cela ne remplace ni la revue
juridique ni l'autorisation de mise en ligne.

Si des pistes NC sont un jour approuvées, leur pack exige en plus
`--noncommercial-use-approval build/rights/nc_access_approval.json` : le document privé
doit porter `approved_by`, `approved_at` (AAAA-MM-JJ), `approval_reference`,
`uses_effectively_noncommercial: true` et `access_mode` égal à
`controlled_research_access` ou `institutional_agreement`. Ce garde-fou ne suffit pas à
garantir que chaque usage réel est NC : le responsable/TTO doit valider le contrat et le
contrôle d'accès. Les packs adaptés BY-SA/BY-NC-SA reçoivent une notice séparée avec la
version et l'URL exactes ; seuls les médias effectivement distribués figurent dans
`MEDIA_ATTRIBUTION.jsonl`.
