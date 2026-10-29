# Inventaire de redistribution — diffusion académique non commerciale

État au 29 octobre 2026. Cet inventaire porte sur les fichiers que **nous** pourrions
distribuer à des chercheurs, pas seulement sur ce qu'ils peuvent télécharger chez les
producteurs. Il n'autorise aucune publication à lui seul : le responsable du laboratoire
et le TTO doivent valider le périmètre, les contrats et le mode d'accès. La
[licence académique EPFL](https://www.epfl.ch/research/technology-transfer/disclose/manage-your-software/choose/)
envisagée ne s'applique qu'aux éléments dont l'EPFL détient les droits ; elle ne remplace
jamais la licence de chaque enregistrement, RIR ou morceau de code tiers.

Le registre privé `build/rights/media_registry.jsonl` distingue droits constatés et
approbation par média. La candidate locale v0.1 a **zéro audio Diagnostic et
Blind-Synthetic**. La voie non commerciale ajoutera éventuellement des pistes NC
*approuvées* au socle compatible commercial ; les pistes SA auront un pack séparé par
licence/version. Aucun identifiant SonicMaster/SDD bloqué n'entre dans le catalogue public.

**« Académique » n'est pas synonyme de « non commercial ».** Une activité universitaire
peut relever de NC selon son objet ; le statut d'université ne suffit pas. Inversement,
un acteur privé n'est pas automatiquement exclu par NC. Pour cette voie, nous retenons
uniquement les usages effectivement non commerciaux, et soumettons les cas ambigus au
titulaire des droits ou au TTO. Voir la [FAQ Creative Commons](https://creativecommons.org/faq/).
Pour les clips OpenRestor découpés, normalisés et/ou dégradés, la politique de release
traite prudemment le résultat comme une adaptation ; les pistes ND sont donc exclues.

## Ce qui peut entrer dans une release académique

| Élément | Quantité et licence de la source | État de redistribution par OpenRestor | Ce qui reste à faire |
| --- | --- | --- | --- |
| Code, schémas, configurations, documentation et manifests originaux EPFL | Licence académique EPFL **proposée**, pas encore accordée ; droits de base de données à clarifier pour les manifests | **En attente** d'accord du responsable et du TTO, pas de `LICENSE` global actuellement | Finaliser l'[inventaire des contributeurs et dépendances](templates/software_release_inventory.md), obtenir le texte, le périmètre et le mode de distribution approuvés. |
| Adaptation logicielle SonicMaster dans `openrestor/degradations/ariel_effects.py` | Code amont Apache-2.0 ; copie de la licence dans `LICENSES/Apache-2.0.txt` | **Conditionnel** dans la release logicielle ; la licence académique EPFL ne supprime pas les droits Apache déjà accordés sur le code amont | Vérifier la frontière exacte du portage, conserver notices et indication des changements ; revue TTO. |
| RIR OpenAIR v0.1 — 1st Baptist Nashville (3), Hoffmann Lime Kiln (6), Saint Lawrence Church (1), St Georges Episcopal Church (3) | **13 WAV**, Public Domain selon les fiches OpenAIR archivées | **Candidats prêts côté licence** ; déjà suivis dans Git | Garder la provenance par salle, le commit/tag canonique, `ATTRIBUTION.md` et les SHA-256 ; feu vert final de release. |
| RIR OpenAIR v0.1 — Spokane Woman's Club | **1 WAV**, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | **Candidat prêt côté licence** ; déjà suivi dans Git | Créditer `www.openairlib.net` et James Cadwallader, lier la licence et la source, indiquer l'usage en réverbération ; joindre [`ATTRIBUTION.md`](../assets/degradations/v0_1/real_rirs/ATTRIBUTION.md) et `degradation_assets_v0_1.sha256`. |
| Blind-Real Public, test et contrôle propre | **382 clips** : 376 CC BY (6 sous BY 2.0, 40 sous BY 2.5, 236 sous BY 3.0, 94 sous BY 4.0) et 6 CC0 1.0 ; dont 210 clips test et 172 contrôles | **Pack préparé, conditionnel à la validation de provenance.** Les étiquettes Internet Archive et les attributions sont enregistrées, mais ne prouvent pas à elles seules que chaque déposant avait les droits | Revoir les exceptions de provenance, conserver les URL de licence exactes par clip, les crédits, les modifications et les checksums ; approuver la publication. Voir `build/release/blind_real_public_v0_1/`. |
| SonicMaster/Jamendo, sous-ensemble potentiellement compatible NC | Parmi 25 000 `source_id` : **856 BY + 1 623 BY-SA + 482 BY-NC + 2 800 BY-NC-SA = 5 761 candidats** d'après l'API Jamendo actuelle | **Bloqué aujourd'hui**, même pour une release académique : la fiche SonicMaster affiche CC BY 2.0 pour l'ensemble, ce qui contredit les licences piste par piste ; le snapshot ne prouve pas les droits historiques ni l'autorité de relicencier | Réponse écrite AMAAI/Jamendo ou preuve indépendante par artiste/piste, attribution et version exactes, revue SA/NC, tri par `source_id`, repackaging des shards et contrôles de non-fuite. Pas de nouvelle collecte massive via l'API sans examen de ses conditions. |
| Song Describer Dataset (SDD), sous-ensemble sans ND | Sur 705 pistes auditées : **37 BY + 150 BY-SA + 15 BY-NC + 286 BY-NC-SA = 488 candidates** ; 8 Art Libre à revoir séparément | **Candidat seulement**, non inclus dans la release v0.1 : attribution et conditions piste par piste, licences SA de différentes versions, usage effectivement NC pour les 301 pistes NC, et pack isolé à valider | Faire relire les [licences par piste](https://zenodo.org/records/10072001), relier chaque `source_id` à son créateur et à son URL de licence, séparer les familles de licences et reconstruire les clips/shards éligibles. Le pack actuel reste local. |

## Pilotes externes ajoutés depuis l'inventaire initial

| Élément | État au 29 octobre 2026 |
| --- | --- |
| AlbumDB — 12 WAV du pilote privé | Le record Zenodo annonce `CC BY 4.0` et les 12 membres ont été vérifiés localement (PCM 16-bit, 44,1 kHz, checksum et CRC). Ils restent **hors de toute release** : le statut `source=original` est ambigu et la provenance/redistribution n'est pas approuvée au niveau asset. Les masters stéréo retenus après déduplication sont listés dans `build/clean_corpus/albumdb_private_pilot/dedup_rights_review_queue.jsonl`. |
| ChoraleBricks, MusicNet, GuitarSet et Guitar-TECHS | Les records Zenodo/portail annoncent des licences candidates, mais l'audit courant est metadata-only ou sans validation membre. Aucun audio n'est compté comme redistribuable. |
| IAMD / Internet Archive | Le catalogue est résolu metadata-only ; les originaux WAV/FLAC/AIFF restent à vérifier fichier par fichier. Aucun MP3 Hugging Face ou fichier réencodé n'est compté comme `clean_lossless`. |

Pour SonicMaster, le total de 5 761 n'inclut ni les **10 356 pistes ND**, ni les
**8 856 IDs absents** de l'API, ni les 23 sans URL de licence, ni les 4 Art Libre non
revues. Pour SDD, les **209 pistes ND** sont hors du pack OpenRestor transformé. Ces
nombres décrivent des **candidats**, pas un volume déjà autorisé ou empaqueté ; les
21 exemples Diagnostic par piste ne peuvent pas être publiés en réutilisant les shards
mixtes existants. Voir les [résultats de l'audit Jamendo](reports/sonicmaster_jamendo_licence_audit_2026-10-16.md)
et `build/sdd_track_licences.json`.

## Hors de la redistribution académique v0.1

| Élément | Motif et voie admise |
| --- | --- |
| MUSDB18-HQ (mixtures, stems, clips propres ou dégradés) | Le [projet MUSDB18](https://sigsep.github.io/datasets/musdb.html) impose une demande d'accès pour usage académique et renvoie à des droits par titre. Cela ne donne **pas** à OpenRestor le droit de redistribuer l'audio, même entre universités. Les ayants droit peuvent produire un pack de transfert **local**, jamais l'inclure dans notre release. |
| Versions SonicMaster déjà dégradées par SonicMaster | Non utilisées par OpenRestor ; ne pas les reconditionner. |
| Corpus Diagnostic et Blind-Synthetic gelés en entier | Mélangent SonicMaster non clarifié, SDD et MUSDB ; les index de publication actuels retiennent **zéro audio synthétique**. Le gel scientifique reste privé et intact. |
| Concerts Montreux / évaluation cachée | Aucune diffusion aux participants : accès organisateur seulement, sous accord écrit spécifique ; éventuel usage académique ou commercial à définir dans cet accord. |
| BBC Sound Effects, Freesound, FSD50K, MUSAN, RIR OpenAIR non retenus et anciens RIR/IR Poliphone | Pas d'actif audio v0.1 publié. Chaque futur effet ou RIR devra être audité à l'unité ; les anciens assets sont exclus. |

Les adaptations sous BY-SA ou BY-NC-SA doivent conserver les conditions SA applicables à
**l'audio adapté**. Elles ne peuvent pas simplement recevoir la licence académique du
code ou être étiquetées « licence OpenRestor ». Les versions/juridictions sont à traiter
par piste. Voir les [conditions CC](https://creativecommons.org/share-your-work/cclicenses/)
et leur [FAQ sur les adaptations et collections](https://creativecommons.org/faq/).

## Porte de sortie

Avant tout upload, produire une liste de fichiers et de `source_id` acceptés, une preuve
et une URL de licence exactes par source, des crédits et changements par clip, des shards
ne contenant **que** les pistes approuvées, les notices RIR/logiciel, et un rapport de
contrôle approuvé par le responsable/TTO. Le mode d'accès académique lui-même doit être
confirmé : l'[EPFL recommande](https://www.epfl.ch/research/technology-transfer/disclose/manage-your-software/distribute/)
selon le cas une licence signée ou une demande institutionnelle, pas automatiquement un
téléchargement Git/DASH ouvert à tous.
