# Validation indépendante IAMD — écoute aveugle (27 octobre 2026)

Le lot indépendant de 120 sources est maintenant disponible localement pour
annotation aveugle. Il est distinct des 200 sources du pilot et des manifestes
Blind-Real.

## Acquisition et extraction

- 120/120 fichiers originaux Internet Archive vérifiés par SHA-1 ou MD5 ;
- 6,204 Gio téléchargés, sans fallback MP3 ;
- formats : 72 WAV, 46 FLAC et 2 AIFF ;
- 120 lignes de features locales ;
- 340 extraits FLAC représentatifs (1 à 3 passages selon la durée de la source) ;
- aucun score Audiobox, AST ou CLAP calculé sur ce lot ;
- aucune prédiction v2/v2.1 incluse dans la page.

Les fichiers téléchargés restent sous `build/curation/iamd/evaluation/independent_v21/download/`
et ne constituent pas une approbation de redistribution.

## Ordre et interface

- [page d'écoute aveugle](../../build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_listen.html)
- [ordre opaque gelé](../../build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_order.jsonl)
- [lock de l'ordre](../../build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_order.jsonl.lock.json)
- [template CSV](../../build/curation/iamd/evaluation/independent_v21/independent_validation_120_blind_order_annotations.csv)

La page affiche uniquement `Source 1` à `Source 120` et exporte des
`blind_id`. La correspondance avec les `source_key` est conservée dans le lock
opérateur et ne doit pas être communiquée pendant l'écoute.

## Action attendue

Écouter au minimum le passage central de chaque source, puis renseigner :

- `content_type` ;
- `audio_quality` ;
- `source_nature` ;
- `capture_quality` et `degradation_reason` lorsqu'ils sont pertinents ;
- `pool_suitability` ;
- `scope` pour indiquer si les autres passages ont été vérifiés ;
- une note courte pour les cas ambigus.

Ne pas révéler les prédictions v2/v2.1 avant l'export du CSV annoté. Après
l'annotation, le CSV devra être remappé par `blind_id` avec l'ordre privé avant
évaluation.
