#!/usr/bin/env bash
set -euo pipefail

# Build the optional standalone v0.1 RIR artifact. Git is the canonical source;
# this archive exists only for release systems that need a single downloadable file.

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output_dir=${1:-"$repo_root/build/release_assets"}
archive="$output_dir/openrestor-degradation-assets-v0_1.tar.gz"

cd "$repo_root"
sha256sum -c docs/degradation_assets_v0_1.sha256

rir_count=$(find assets/degradations/v0_1/real_rirs -type f -name '*.wav' | wc -l)
if [[ "$rir_count" -ne 14 ]]; then
  printf 'ERROR: expected 14 RIR WAV files, found %s.\n' "$rir_count" >&2
  exit 2
fi

mkdir -p "$output_dir"
tar --sort=name \
  --mtime='UTC 2026-10-16' \
  --owner=0 --group=0 --numeric-owner \
  -cf - \
  assets/degradations/v0_1/real_rirs \
  THIRD_PARTY_NOTICES.md \
  docs/degradation_assets.md \
  docs/degradation_assets_v0_1.sha256 \
  | gzip -n > "$archive"

sha256sum "$archive" > "$archive.sha256"
printf 'Created %s\n' "$archive"
printf 'Created %s.sha256\n' "$archive"
