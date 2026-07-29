# MUSDB18-HQ Listening Review

## Summary

- Dataset: Music Demixing Dataset 2018 High Quality (MUSDB18-HQ)
- Review date: 2026-07-15
- Reviewer: project owner
- Sample size: informal random sample
- Listening path: `/tmp/openrestore-listening/musdb18_hq`
- Final quality status: pass as validation-only, high-quality mixture reference material

## Aggregate Notes

- Overall quality: very good
- Common issue tags: none noted in the sampled clips
- Recommended filtering changes: keep MUSDB18-HQ validation-only and mixture-only under the current benchmark policy.

## Decision

MUSDB18-HQ mixtures are very good source material and should remain part of the high-quality
validation pool. For the current OpenRestore policy, only full-song mixtures are accepted; stems are
excluded, and the dataset is not used for main-track training or public test audio.
