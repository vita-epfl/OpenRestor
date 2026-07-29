# Dataset Decision Record Template

## Summary

- Dataset:
- Version or snapshot:
- Review date:
- Reviewer:
- Local path:
- Access URL:
- Intended OpenRestore role:
- Final status: accepted / accepted with filtering / internal-only / rejected

## Role Decision

- Clean benchmark source: yes / no
- Main-track training source: yes / no
- Validation source: yes / no
- Public test source: yes / no
- Hidden evaluation source: yes / no
- Degradation material source: yes / no

Decision notes:

```text
Write the short rationale here.
```

## License And Redistribution

- Governing terms:
- Dataset card or license URL:
- Per-item license differences:
- Attribution requirements:
- Commercial-use restrictions:
- Model-training restrictions:
- Public redistribution allowed: yes / no / unclear
- Derived degraded clips redistribution allowed: yes / no / unclear
- OpenRestore release mode: public audio / manifests only / internal only / rejected

Open questions:

```text
List unresolved legal or redistribution checks here.
```

## Quality And Selection

- Accepted subset:
- Excluded subset:
- Minimum duration:
- Required sample rate or conversion:
- Channel policy:
- Known format issues:
- Known audio-quality issues:
- Duplicate or leakage risk:

Filtering rule to implement or verify:

```text
Example: include only SonicMasterDataset/clean/*.flac; exclude HDF5 degraded artifacts.
```

## Automated Audit

- Audit command:

```bash
openrestore-data audit --config configs/datasets/<dataset>.yaml --output build/audits/<dataset>.json --probe-limit 50
```

- Audio file count:
- Probed file count:
- Sample rates observed:
- Channel counts observed:
- Files below 30 seconds:
- Corrupt/unreadable files:

## Final Decision

```text
State the decision in one paragraph. Include exact role, redistribution status, and any required filtering.
```
