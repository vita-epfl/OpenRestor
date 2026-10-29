#!/usr/bin/env bash
set -euo pipefail

# Check a local, metadata-only candidate before any human release approval.
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
candidate=${1:-"$repo_root/build/release-candidates/rights-v0_1-initial"}
if [[ ! -d "$candidate" ]]; then
  printf 'ERROR: candidate does not exist: %s\n' "$candidate" >&2
  exit 2
fi
jq -e '.status == "local_candidate_complete" and .upload_approved == false and
       (.corpora | length) == 2 and (.profiles | length) == 2' \
  "$candidate/candidate_status.json" >/dev/null
for corpus in diagnostic blind_synthetic; do
  for profile in commercial_compatible academic_noncommercial; do
    report="$candidate/$corpus/$profile/publication_report.json"
    index="$candidate/$corpus/$profile/base/index.jsonl"
    jq -e '.packaged_synthetic_audio == 0 and .upload_approved == false' "$report" >/dev/null
    test -f "$index"
    test ! -s "$index"
  done
done
jq -e '.approved_by_dataset.openair_rir == 14 and
       .profiles.commercial_compatible.openair_rir == 14 and
       .profiles.academic_noncommercial.openair_rir == 14' \
  "$candidate/rights_summary.json" >/dev/null
if find "$candidate" -type f \( -name '*.wav' -o -name '*.flac' -o -name '*.h5' \) -print -quit | rg -q .; then
  printf 'ERROR: initial candidate contains audio\n' >&2
  exit 3
fi
if rg -l '"(source_id|media_key|evidence_url)"' "$candidate" --glob '*.json' --glob '*.jsonl' | rg -q .; then
  printf 'ERROR: candidate exposes private per-media fields\n' >&2
  exit 3
fi
for relative in THIRD_PARTY_NOTICES.md LICENSES/Apache-2.0.txt \
  assets/degradations/v0_1/real_rirs/ATTRIBUTION.md docs/degradation_assets_v0_1.sha256; do
  cmp "$repo_root/$relative" "$candidate/$relative"
done
rg -q 'www.openairlib.net.*James Cadwallader' \
  "$candidate/assets/degradations/v0_1/real_rirs/ATTRIBUTION.md"
rg -q 'creativecommons.org/licenses/by/3.0/' \
  "$candidate/assets/degradations/v0_1/real_rirs/ATTRIBUTION.md"
(cd "$repo_root" && sha256sum -c docs/degradation_assets_v0_1.sha256 >/dev/null)
printf 'Initial candidate: zero synthetic audio, no private IDs, four notices, 14 valid RIR hashes.\n'
