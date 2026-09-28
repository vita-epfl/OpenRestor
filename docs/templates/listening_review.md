# Structured Listening Review Template

## Summary

- Dataset:
- Review date:
- Reviewer:
- Sample size:
- Sample selection command:
- Listening path:
- Playback setup:
- Final quality status: pass / pass with filtering / fail / needs follow-up

## Sampling Command

```bash
mkdir -p /tmp/openrestor-listening/<dataset>

find /mnt/ssd2/datasets/OpenRestoreDataset/<source-root> \
  -type f -name '<extension>' \
  | shuf -n 20 \
  | while IFS= read -r f; do
      b=$(basename "$f" .<extension-without-dot>)
      ffmpeg -nostdin -v error -y -ss 30 -i "$f" -t 30 -ar 44100 -ac 2 \
        "/tmp/openrestor-listening/<dataset>/${b}.wav"
    done
```

## Review Criteria

Mark each sampled clip with:

- `pass`: clean enough for the intended role
- `minor`: usable, but has mild coloration, noise, codec history, or mastering issues
- `reject`: unsuitable as clean reference audio
- `unclear`: needs another listener or source/license check

Listen for:

- clipping or crushed mastering
- codec artifacts
- intrusive noise or hum
- reverb or room coloration already baked into the clean source
- dropouts, glitches, truncation, silence, or bad edits
- non-musical contamination
- wrong content type for the intended role
- mono/stereo problems or channel imbalance
- watermark, speech tag, or attribution tag

## Clip Notes

| Clip | Status | Issue tags | Notes |
| --- | --- | --- | --- |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |
|  | pass / minor / reject / unclear |  |  |

## Aggregate Notes

- Pass count:
- Minor count:
- Reject count:
- Unclear count:
- Estimated reject rate:
- Common issue tags:
- Recommended filtering changes:

## Decision

```text
State whether the dataset passes for its intended OpenRestore role, and list any filtering or follow-up required before release.
```
