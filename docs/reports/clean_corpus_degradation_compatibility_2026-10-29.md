# Compatibilité du générateur de dégradations — pilote Clean (29 octobre 2026)

Ce smoke test vérifie la chaîne de dégradation sur un extrait IAMD local de
18 secondes. Il ne télécharge rien, ne modifie aucun benchmark et ne donne
aucune autorisation de redistribution.

## Résultat

- entrée : `build/iamd_feasibility/phase1b/clips/ecfc2d49d5723e98-p1.flac` ;
- configuration de référence : `configs/degradations/single/v0_1.yaml` ;
- seed : `20261029` ;
- recettes testées sans modification de leurs paramètres : **19/19 réussies** ;
- sorties : 19 WAV, 19 checksums SHA-256, 60 329 636 octets ;
- recettes non exécutées : `codec` et `neural_codec`.

Les sorties et le manifest privé sont dans
`build/iamd_feasibility/phase1b/degradation_smoke_noncodec/`.

## Limite d’environnement

Les recettes `codec` et `neural_codec` appellent `ffmpeg`. Le binaire n’est pas
présent sur ce nœud ; leur exécution s’arrête donc avec
`RuntimeError: codec_resampling requires FFmpeg on PATH`. Ce n’est pas un
échec silencieux : les 19 autres recettes ont été vérifiées et les deux
recettes restantes doivent être relancées dans l’environnement de production
où FFmpeg est installé.

## Interprétation

La compatibilité du manifest Clean et des opérations acoustiques est démontrée
sur cet extrait. Le test ne valide pas encore les recettes codec, la qualité
perceptuelle des sorties ni les droits des sources ; les fichiers restent sous
`build/` et hors de tous les profils publics.
