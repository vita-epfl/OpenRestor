#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
runner="$repo_root/.venv/bin/python"
if [[ ! -x "$runner" ]]; then
  printf 'ERROR: project virtualenv missing at %s\n' "$runner" >&2
  exit 2
fi
# Some cluster shells omit FFmpeg from PATH although the project venv bundles it.
for ffmpeg_dir in "$repo_root"/.venv/lib/python*/site-packages/static_ffmpeg/bin/linux; do
  if [[ -x "$ffmpeg_dir/ffmpeg" && -x "$ffmpeg_dir/ffprobe" ]]; then
    export PATH="$ffmpeg_dir:$PATH"
    break
  fi
done
cd "$repo_root"
if [[ "${OPENRESTOR_TEST_SCOPE:-rights}" == all ]]; then
  "$runner" -m unittest discover -s tests
else
  "$runner" -m unittest tests.test_rights_release tests.test_publication_policy
fi
sha256sum -c docs/degradation_assets_v0_1.sha256
if [[ -f build/rights/media_registry.jsonl ]]; then
  if gate_output=$("$runner" scripts/package_blind_real_release.py 2>&1); then
    printf 'ERROR: Blind-Real packager accepted unreviewed clips\n' >&2
    exit 3
  fi
  if [[ "$gate_output" != *'382 clips lack approved provenance'* ]]; then
    printf 'ERROR: unexpected Blind-Real gate result: %s\n' "$gate_output" >&2
    exit 3
  fi
  printf 'Blind-Real gate: 382 clips blocked pending provenance.\n'
fi
