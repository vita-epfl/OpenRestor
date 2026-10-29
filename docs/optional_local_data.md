# Optional Local Data Packs

SDD and MUSDB18-HQ are not part of the canonical OpenRestor public dataset. Their clean and
derived audio must not be uploaded by OpenRestor. They remain useful as optional diagnostics
for users who independently obtain the sources and are allowed to process them under the
upstream terms.

## Roles

| Data | Allowed OpenRestor role | Public artifact | Official score |
| --- | --- | --- | --- |
| SDD | Optional local transfer diagnostic | none | no |
| MUSDB18-HQ mixtures | Optional local academic transfer diagnostic | none | no |
| MUSDB18-HQ stems | excluded | none | no |

These packs may be used as extra training data only when both the upstream terms and the
rules of the experiment permit it. Results on them must be labelled separately and must
never be merged into the main OpenRestor score. A participant having trained on a pack must
not present evaluation on that same pack as unseen generalisation.

## Local Builder

The user downloads or obtains the dataset from its official source, reviews its terms, and
then runs:

```bash
source .venv/bin/activate
OPENRESTOR_ACCEPT_UPSTREAM_TERMS=1 \
  scripts/build_optional_local_transfer_pack.sh sdd /path/to/SDD/audio

OPENRESTOR_ACCEPT_UPSTREAM_TERMS=1 \
  scripts/build_optional_local_transfer_pack.sh musdb18_hq /path/to/musdb18hq
```

The script does not download anything. It writes private local artifacts below
`build/local-transfer/<dataset>/`, marks the directory local-only, renders canonical clips,
records checksums and verifies the result. Set `OPENRESTOR_LOCAL_CLIPS_PER_SOURCE` to a
positive integer to request more than one deterministic clip per source. The MUSDB18-HQ
configuration selects files named exactly `mixture.wav`; stems are excluded even when they
exist below the supplied source root.

Do not copy these directories into `build/release`, DASH, Zenodo, GitHub releases or any
other shared artifact store.

## Frozen v0.1 Build

The already rendered private v0.1 corpus is an immutable research record and still contains
SDD and MUSDB18-HQ partitions. It must not be rewritten. Publication is a derived view:
`configs/releases/publication_policy_v0_1.yaml` withholds both sources, and the public
packaging process omits their partitions entirely.
