# Hidden Evaluation Data Contract

The official OpenRestor leaderboard must use organizer-controlled recordings that
participants cannot lawfully download as a complete training set. Public datasets such as
SDD and MUSDB18-HQ are unsuitable for this role even when excerpt timestamps are secret:
participants can train on the complete songs and invalidate the generalisation claim.

## Montreux Jazz Festival Candidate

High-quality Montreux Jazz Festival recordings are a strong scientific candidate because
they provide real performances, diverse rooms and production conditions. They are not an
approved source merely because an EPFL researcher can access them. Before any file is copied
or ingested, a written agreement reviewed through the appropriate EPFL process must establish
who can grant each required right.

The preferred transfer is original or archival masters supplied directly through an
authorised channel, prioritising performances that have not been publicly released or
streamed. Do not scrape or download YouTube copies. YouTube availability is neither proof of
copyright ownership nor permission for automated download, and a public copy of the same
performance weakens the contamination barrier even when the hidden excerpt is different.

Use `configs/datasets/montreux_jazz_hidden.template.yaml` only after its
`rights_status` is changed from `approval-required` in a private configuration backed by a
signed record. Never commit the private configuration, identities, paths or rights register.

## Rights Gate

The agreement must explicitly cover, as applicable:

1. EPFL receiving and storing the recording masters in organizer-controlled infrastructure;
2. selecting excerpts, resampling, loudness processing and creating degraded derivatives;
3. using the clean and degraded material for machine-learning research and evaluation;
4. running third-party submitted software against the material on EPFL infrastructure;
5. retaining private inputs, clean references, system outputs and audit logs;
6. publishing aggregate metrics, methods and non-identifying dataset statistics;
7. the intended duration, territory, project/laboratory and authorized personnel;
8. whether performer, master-recording, composition/publishing and neighbouring rights need
   separate approvals; and
9. the required deletion, renewal and incident-response procedures.

Access to an archive or a festival account is not evidence that these uses are permitted.
Record one entry per master in a private rights register conforming to
`schemas/hidden_rights_record.schema.json`. Store agreement references, not agreement files,
in that register; signed documents belong in the approved legal records system.

## Contamination Gate

Rights clearance and benchmark secrecy are separate gates. Before freezing an item, search
the provider's catalogue and major public music/video catalogues for the same performance,
then run audio-fingerprint matching where lawful. Record the review in the private rights
register. Prefer unreleased archival performances; exclude a known public version from the
official generalisation score, or place it in a separately labelled contamination study.

Keep complete concerts and artists source-disjoint from internal development material. Do
not rely on secret timestamps: a model can train on a full public concert without knowing the
selected excerpt.

## Leakage And Execution Boundary

Participants submit a container; organizers run it server-side. The hidden runner must:

- disable network access and external mounts;
- mount hidden inputs read-only and use an ephemeral writable directory;
- impose CPU, GPU, memory, disk and wall-time limits;
- validate the output schema and reject extra files or oversized outputs;
- prevent participants from downloading restored hidden audio, per-item scores, logs
  containing identities, or degradation metadata;
- return only aggregate metrics with a minimum cohort size;
- retain access and execution logs; and
- rotate a compromised hidden set rather than continuing to score it.

Because an audio output can itself exfiltrate its input, restored hidden files stay
organizer-only. A public debugging set must be separate and rights-cleared for distribution.

## Dataset Design

Keep artists, concerts and recording sessions source-disjoint across any internal development
and hidden test partitions. Balance genres, production eras, venues and degradation classes,
then freeze hashes and seeds in organizer-controlled storage. Do not disclose source URLs,
titles, timestamps, fingerprints, contamination records or per-item degradation recipes.

The hidden set is a leaderboard instrument, not training data. SDD/MUSDB local diagnostics
and Blind-Real Public remain outside it and must be reported separately.
