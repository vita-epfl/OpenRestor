# IAMD → Internet Archive : Phase 1 hors ligne / machine externe

Cette procédure ne télécharge **aucun audio**. IAMD est seulement le catalogue de
départ. Les MP3 déjà récupérés depuis Hugging Face ne sont jamais assimilés à des
originaux lossless.

## Fichiers à transférer sur une machine qui atteint Internet Archive

- `build/iamd_feasibility/iamd_clean_candidate_identifiers.jsonl` : un
  `identifier` unique par ligne, avec les métadonnées IAMD. Cette liste exclut
  Blind-Real et les collections non musicales ou à licence douteuse déjà connues.
- `scripts/resolve_iamd_archive_metadata.py` : script autonome, Python 3.10+
  et bibliothèque standard uniquement.

Ne publiez pas la liste ni les résultats détaillés avant revue de provenance.

## Résolution sur la machine externe

Commencer par dix items :

```bash
python3 resolve_iamd_archive_metadata.py \
  --input iamd_clean_candidate_identifiers.jsonl \
  --output iamd_archive_resolution.jsonl \
  --max-items 10
```

Si `/metadata/` ne fonctionne pas mais `/download/` répond pour les petits XML,
ajouter `--xml-fallback`. Cela interroge `<identifier>_files.xml` et
`<identifier>_meta.xml`, **jamais un fichier audio**. Sans `_meta.xml`, la
licence et les droits de l'item restent inconnus, même si `_files.xml` décrit
un fichier original.

Poursuivre en relançant la même commande sans `--max-items`. Le JSONL est
écrit après chaque item avec synchronisation disque ; une relance saute les
items déjà résolus. `--retry-errors` retente les erreurs et ajoute une nouvelle
ligne pour ces identifiants ; l'import utilise la dernière ligne. Le délai
entre items est de 0,25 s par défaut (`--sleep`) et chaque requête a un timeout
de 20 s (`--timeout`). Ajuster prudemment en cas de limitations côté Archive.

Le champ `files` contient uniquement les extensions WAV/FLAC/AIFF déclarées
originales ou ambiguës. Les dérivés et fichiers privés sont comptés, mais non
retenus. Un fichier `source=original` et dont le champ `format` concorde avec
l'extension reçoit `original_status=strict_original` ; les statuts manquants ou
discordants restent à part. Chaque entrée conservée porte nom, source, format,
taille, durée déclarée si disponible, SHA1/MD5 disponibles et URL du fichier,
mais cette URL n'est pas appelée.

## Rapport entièrement hors ligne dans OpenRestor

Rapatrier seulement `iamd_archive_resolution.jsonl` dans un emplacement privé,
puis exécuter dans le dépôt :

```bash
python3 scripts/audit_iamd_lossless_feasibility.py import \
  --resolution-jsonl /chemin/prive/iamd_archive_resolution.jsonl
python3 scripts/audit_iamd_lossless_feasibility.py report
```

Lire `build/iamd_feasibility/report.md` et `summary.json`. Tant que la
couverture n'est pas complète, tous les volumes sont **observés uniquement**,
pas des totaux du pool. L'import utilise la dernière ligne complète pour chaque
`identifier` (les retries externes sont append-only), ignore une unique ligne
finale incomplète et refuse toute ligne malformée au milieu. Il remplace le
cache de cet audit en une transaction : un échec de validation laisse intact le
cache précédent. `import_summary.json` indique notamment les lignes partielles
ignorées. Un timeout importé est un **échec**, distinct d'un `identifier` non
encore tenté.

Le rapport fournit le funnel par `identifier`, puis les heures, octets, formats,
licences exactes, genres, collections, créateurs et concentrations. Les
distributions complètes et les nombres d'items par artiste/collection sont dans
`summary.json` ; le Markdown montre les 25 groupes principaux. Les niveaux sont :

- `technical_candidate` : au moins un WAV/FLAC/AIFF non privé, avec extension
  et format Archive concordants, explicitement `source=original` ;
- `provenance_candidate` : précédent + URL de licence CC0/CC BY concordante
  avec IAMD, créateur indiqué et aucune collection déjà signalée ;
- `redistributable_candidate` : précédent + au moins un tel fichier avec taille
  et SHA1 ou MD5. C'est **une piste à vérifier**, pas une autorisation de publier.

`ambiguous_original_status` conserve séparément les cas où `source` est absent.
Ni un MP3, ni un dérivé, ni un statut absent ne devient automatiquement un
original strict. Les durées manquantes sont estimées à partir de la taille et du
débit médian observé dans le même format, avec le nombre non estimable indiqué.

Le verdict GO/NO-GO est une **heuristique de faisabilité**, pas une décision de
licence : plusieurs milliers de sources sont opérationnalisées à au moins 2 000
`identifier` candidats, au moins 500 h estimées, 80 % de métadonnées résolues,
50 % des sources techniques conservées à l'étape finale, aucune collection au-delà
de 70 %, aucun créateur au-delà de 10 % et au moins 100 créateurs effectifs.
Ces garde-fous sont affichés dans le rapport pour être discutés ; **aucun quota
de genre n'est appliqué**. Tant que des items n'ont pas été interrogés, le
NO-GO est provisoire et ne signifie pas que le corpus est trop petit.

Aucune assertion de métadonnées ne remplace la preuve de titularité ou la
vérification du codec source. Ne pas passer à la Phase 2 sans décision explicite.
