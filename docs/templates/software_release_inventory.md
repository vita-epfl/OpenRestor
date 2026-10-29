# OpenRestor Software Release Inventory

Complete this inventory before requesting approval for the proposed EPFL Source Code
Academic License. It covers EPFL-controlled software and original manifests, not the audio,
model weights, room impulse responses or private evaluation material.

As of 19 October 2026, this is **not complete**. The project has prepared two media-rights
profiles and a zero-synthetic-audio local candidate, but no project-wide licence or upload
approval. Attach `docs/reports/release_readiness_2026-10-19.md` and the two redistribution
inventories to the supervisor/TTO request; share only the aggregate rights summary, never
the private per-media registry or frozen indexes.

## Contributors and ownership

Confirm status at the time of each contribution. A Git identity is not proof of employment
or copyright ownership.

| Contributor / Git identities | EPFL status while contributing | Contribution | Ownership or assignment evidence |
| --- | --- | --- | --- |
| Adrien Lefevre (`adrien.lefevre@epfl.fr`, `lefevre.adrien8@gmail.com`) | TODO: employee / student / visitor / other | Primary implementation and documentation | TODO |
| Son Pham-Ba (`son.phamba@epfl.ch`) | TODO: employee / student / visitor / other | TODO: review commits and describe | TODO |

If a contributor was not an EPFL employee, ask the TTO whether a contributor licence
agreement or copyright assignment is required before release.

## Funding, contracts, patents and valorisation

| Question | Answer / evidence |
| --- | --- |
| Grants or sponsors that funded the work | TODO |
| Collaboration, consortium or data-access agreements | TODO |
| Pre-existing code brought into the project | TODO |
| SonicMaster/ARIEL adaptation | Review `openrestor/degradations/ariel_effects.py` against SonicMaster `dataset_scripts` (Apache-2.0); record upstream notices and modifications. |
| Patent disclosures or potentially patentable work | TODO |
| Planned commercialisation or industrial transfer | TODO |
| TTO review required or completed | TODO |

## Declared software dependencies

Record the resolved version and verified upstream licence from the release lock file or
environment. Do not infer compatibility from the package name alone.

| Dependency group | Packages / tools | Version and upstream licence review |
| --- | --- | --- |
| Runtime | PyYAML, NumPy, SciPy, SoundFile, librosa, pyloudnorm, pyroomacoustics, jsonschema, Matplotlib, h5py | TODO |
| Optional catalogue | pyarrow, fsspec, aiohttp | TODO |
| Optional perceptual metrics | PyTorch, torchaudio, LAION-CLAP, `fadtk`, `audiobox-aesthetics` | TODO |
| External runtime tools | FFmpeg, libsndfile | TODO |
| Development and release tools | Node.js, Repomix, test and lint tools | TODO |
| Container base images and system libraries | TODO: enumerate image digests and packages | TODO |

Transitive dependencies must also be captured in the final software bill of materials or
lock-file review. Dataset and media licences belong in the dataset attribution and
publication-policy records, not in this table.

## Proposed release files

- `LICENSE`: TTO-approved EPFL academic terms for the components EPFL can license.
- `LICENSES/Apache-2.0.txt`: unmodified upstream Apache-2.0 terms for adapted SonicMaster code.
- `THIRD_PARTY_NOTICES.md`: upstream software and media attribution, with modification notes.
- package metadata and source headers: mark licence scope only after the TTO confirms it.
- original-manifest terms: TTO-approved academic data clause if the software template is insufficient.
- dataset and asset attribution files: separate from the project software licence.

Do not add a project-wide licence until the supervisor/TTO has confirmed ownership,
contributor status, contractual constraints, adapted-code scope and metadata rights.
