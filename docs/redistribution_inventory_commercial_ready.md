# Inventaire de redistribution — voie académique avec usage commercial possible

État au 29 octobre 2026. Cette voie choisit pour les **médias distribués** des droits
compatibles avec un éventuel usage commercial en aval. Ce n'est **pas** une licence
commerciale OpenRestor : le code et les manifests originaux EPFL resteraient sous les
termes académiques approuvés, et une entreprise devrait obtenir une licence distincte
auprès du [TTO EPFL](https://www.epfl.ch/research/technology-transfer/disclose/manage-your-software/choose/).
Le TTO ne peut pas accorder de droits supplémentaires sur des œuvres tierces. Le statut
« candidat » ci-dessous ne vaut pas autorisation de mise en ligne.

La candidate locale issue de `scripts/prepare_rights_profiles.sh` contient **zéro audio
synthétique** ; le registre détaillé est privé et le résumé partageable ne contient que
des totaux. Le socle commercial exige une revue approuvée, la redistribution et les
adaptations autorisées, et aucune clause NC/ND. Les éventuels médias BY-SA sont isolés
par licence/version et ne sont pas incorporés au socle BY.

## Tronc commun commercialement compatible

| Élément | Source et licence | État de redistribution par OpenRestor | Obligations / blocage restant |
| --- | --- | --- | --- |
| Code, schémas, configurations, documentation et manifests originaux EPFL | Licence académique EPFL envisagée, licence commerciale EPFL séparée si demandée | **En attente** d'approbation du responsable/TTO ; pas de droit commercial déjà accordé par le dépôt | Délimiter les éléments EPFL, droits des contributeurs et de base de données ; préparer le contact TTO et le mode de distribution. |
| Adaptation du code SonicMaster | Apache-2.0 pour les portions amont ; modifications EPFL à délimiter | **Conditionnel**, avec notices Apache conservées | Une entreprise peut se prévaloir de l'Apache-2.0 pour le code amont ; l'EPFL ne peut réserver commercialement **que ses propres contributions**. Vérification TTO du portage et des notices. |
| RIR OpenAIR v0.1 | **13 WAV Public Domain** (1st Baptist Nashville 3, Hoffmann Lime Kiln 6, Saint Lawrence Church 1, St Georges Episcopal Church 3) + **1 WAV CC BY 3.0** (Spokane Woman's Club) | **Candidats prêts côté licence**, déjà dans Git ; mêmes 14 fichiers que dans la voie académique | Distribuer avec les [crédits OpenAIR](../assets/degradations/v0_1/real_rirs/ATTRIBUTION.md), le lien [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), les modifications, les SHA-256 et le tag/commit exacts. Aucun nouveau RIR n'entre dans v0.1. |
| Blind-Real Public, test + contrôle propre | **382 clips** : 376 CC BY (BY 2.0 : 6 ; BY 2.5 : 40 ; BY 3.0 : 236 ; BY 4.0 : 94) et 6 CC0 1.0 | **Pack préparé, conditionnel à la validation de provenance** ; licences compatibles avec l'usage commercial déclaré | Attributions, URL/version de licence et transformation par clip dans `build/release/blind_real_public_v0_1/`. La marque CC de l'uploader n'est pas une preuve indépendante de titularité. |

La **base simple** de cette voie n'admet que CC0, Public Domain et CC BY pour l'audio,
et Apache-2.0 pour les portions logicielles tierces. Même pour ces fichiers, la revue de
provenance et le feu vert de diffusion demeurent nécessaires.

## Sous-ensembles audio supplémentaires possibles, mais non publiables aujourd'hui

| Source | Candidat sans NC/ND, d'après l'audit | Pourquoi ce n'est pas prêt |
| --- | --- | --- |
| SonicMaster/Jamendo, voie simple CC BY | **856 pistes CC BY** actuellement signalées par Jamendo, soit au plus 17 976 exemples Diagnostic et 856 Blind-Synthetic *avant validation* | **Tout SonicMaster reste bloqué** tant que le conflit entre la [fiche SonicMaster CC BY 2.0](https://huggingface.co/datasets/amaai-lab/SonicMasterDataset) et les licences de l'audio Jamendo n'est pas clarifié par écrit. Il faut l'historique des droits et une attribution par piste, puis repacker les shards mixtes. |
| Song Describer Dataset, voie simple CC BY | **37 pistes CC BY** (2.0/2.5/3.0) sur les 705 auditées, soit au plus 777 exemples Diagnostic avant validation | La [table piste par piste](https://zenodo.org/records/10072001) doit être rapprochée des créateurs, URL et fichiers effectivement publiés ; isoler et repacker ce sous-ensemble. Aucun pack SDD n'est aujourd'hui approuvé pour upload. |
| SonicMaster/Jamendo, voie ShareAlike distincte | **1 623 pistes CC BY-SA** supplémentaires, commercialement réutilisables en principe ; total BY + BY-SA : 2 479 pistes candidates | Plusieurs versions/juridictions SA : l'audio adapté doit respecter la licence applicable à chaque piste. Revue TTO des compatibilités et des notices, droits historiques Jamendo et pack séparé ; **pas** une simple extension du pack BY. |
| Song Describer Dataset, voie ShareAlike distincte | **150 pistes CC BY-SA** supplémentaires ; total BY + BY-SA : 187 pistes candidates | Même obligation SA/version par piste et repackaging séparé. Une licence académique restrictive ne peut pas être substituée à la licence de l'audio adapté. |

## Pilotes externes non encore publiables

| Source | Situation pour cette voie |
| --- | --- |
| AlbumDB — 12 WAV du pilote privé | Le record porte une mention `CC BY 4.0`, mais les 12 membres restent `provenance_approved=false` et `redistribution_approved=false`. Le statut original est ambigu ; aucun fichier n'entre dans le socle commercialement compatible. |
| ChoraleBricks, MusicNet, GuitarSet et Guitar-TECHS | Les métadonnées de record sont compatibles en première lecture, mais les membres audio et les crédits exacts ne sont pas encore validés. Ils restent metadata-only et hors du pack. |
| IAMD / Internet Archive | Les 11 945 candidats et les résultats de licence catalogue ne constituent pas une autorisation de redistribution. Aucun audio lossless n'est publié sans validation de l'original et de la licence applicable. |

Les **482 BY-NC et 2 800 BY-NC-SA SonicMaster**, les **15 BY-NC et 286 BY-NC-SA
SDD**, et tout contenu ND sont exclus de cette voie commercialement compatible.
Les 4 SonicMaster et 8 SDD sous Licence Art Libre sont laissés en revue distincte : ne
pas présumer leur compatibilité avec un pack CC BY. Les règles CC distinguent clairement
NC, ND et SA ; SA **n'interdit pas** l'usage commercial, mais encadre la licence de
l'adaptation. Voir [Creative Commons](https://creativecommons.org/share-your-work/cclicenses/).

## Exclus des deux voies sans nouvel accord

- **MUSDB18-HQ** : accès académique contrôlé, droits hétérogènes, aucun droit général
  de redistribution ou d'usage commercial démontré. Les mélanges et dérivés restent
  local-only ; voir [SigSep MUSDB18](https://sigsep.github.io/datasets/musdb.html).
- **Évaluation cachée Montreux** : matériel privé organisateur, non redistribué. Un
  éventuel usage industriel doit être couvert explicitement par l'accord avec le
  détenteur des masters, indépendamment du contrat TTO sur le logiciel.
- **Effets sonores tiers et RIR supplémentaires** : non présents dans le bundle v0.1.
  Tout ajout exige un nouvel audit par fichier et, s'il change les dégradations, une
  nouvelle version scientifique. Les RIR OpenAIR sous CC BY-SA 4.0 ne sont pas les 14
  RIR retenus pour v0.1.
- **Corpus gelés Diagnostic/Blind-Synthetic complets** : ne pas uploader les shards
  privés, qui mélangent des pistes non autorisées ; publier seulement des shards
  reconstruits à partir de `source_id` approuvés et contrôlés.

## Critère d'upload

Une release compatible commercial doit contenir un manifeste des droits par fichier
(titulaire, licence exacte et URL, source, modification, crédit), les notices Apache et
OpenAIR, les checksums, un contrôle automatique qu'aucune piste NC/ND/inconnue ne passe,
des shards physiquement séparés, et l'approbation écrite responsable/TTO pour les
éléments EPFL. La licence académique du code ne doit jamais être présentée comme une
licence commerciale du produit complet.
