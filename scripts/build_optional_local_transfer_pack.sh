#!/usr/bin/env bash
set -euo pipefail

# Build a non-redistributable SDD or MUSDB18-HQ pack from audio that the user
# obtained independently under the upstream terms. This script never downloads
# data and never writes into a public release directory.

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

usage() {
  printf '%s\n' \
    "Usage: OPENRESTOR_ACCEPT_UPSTREAM_TERMS=1 $0 <sdd|musdb18_hq> <source-root> [output-dir]" \
    "" \
    "The default output is build/local-transfer/<dataset>."
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage >&2
  exit 2
fi

dataset=$1
source_root=$2
output_dir=${3:-"$repo_root/build/local-transfer/$dataset"}
clips_per_source=${OPENRESTOR_LOCAL_CLIPS_PER_SOURCE:-1}

if [[ "${OPENRESTOR_ACCEPT_UPSTREAM_TERMS:-}" != "1" ]]; then
  printf '%s\n' \
    'ERROR: this pack is local-only and governed by upstream dataset terms.' \
    'Review those terms, then set OPENRESTOR_ACCEPT_UPSTREAM_TERMS=1.' >&2
  exit 2
fi

case "$dataset" in
  sdd) config="$repo_root/configs/datasets/sdd_transfer.yaml" ;;
  musdb18_hq) config="$repo_root/configs/datasets/musdb18_hq_transfer.yaml" ;;
  *) printf 'ERROR: unsupported local transfer dataset: %s\n' "$dataset" >&2; usage >&2; exit 2 ;;
esac

case "$clips_per_source" in
  ''|*[!0-9]*) printf 'ERROR: OPENRESTOR_LOCAL_CLIPS_PER_SOURCE must be a positive integer.\n' >&2; exit 2 ;;
esac
if (( clips_per_source < 1 )); then
  printf 'ERROR: OPENRESTOR_LOCAL_CLIPS_PER_SOURCE must be a positive integer.\n' >&2
  exit 2
fi

if [[ ! -d "$source_root" ]]; then
  printf 'ERROR: source root does not exist: %s\n' "$source_root" >&2
  exit 2
fi

for command in ffmpeg openrestor-data; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 2
  fi
done

if [[ -d "$output_dir" ]] && find "$output_dir" -mindepth 1 -print -quit | grep -q .; then
  printf 'ERROR: output directory is not empty; refusing to overwrite: %s\n' "$output_dir" >&2
  exit 2
fi

umask 077
mkdir -p "$output_dir"

printf '%s\n' \
  'LOCAL-ONLY OPENRESTOR TRANSFER PACK' \
  'Do not upload, publish, or copy this directory into a release.' \
  'The source and derived audio remain governed by the upstream dataset terms.' \
  > "$output_dir/LOCAL_ONLY.txt"

openrestor-data audit \
  --config "$config" \
  --source-root "$source_root" \
  --output "$output_dir/audit.json"

openrestor-data ingest \
  --config "$config" \
  --source-root "$source_root" \
  --output "$output_dir/source_index.jsonl"

openrestor-data source-stats \
  --manifest "$output_dir/source_index.jsonl" \
  --output "$output_dir/source_statistics.json"

openrestor-data segment \
  --sources "$output_dir/source_index.jsonl" \
  --output-root "$output_dir/audio" \
  --manifest "$output_dir/manifest.jsonl" \
  --checksums "$output_dir/checksums.jsonl" \
  --clips-per-source "$clips_per_source"

openrestor-data verify \
  --root "$output_dir/audio" \
  --checksums "$output_dir/checksums.jsonl"

openrestor-data stats \
  --manifest "$output_dir/manifest.jsonl" \
  --output "$output_dir/statistics.json"

printf '\nCreated local-only pack: %s\n' "$output_dir"
printf 'Do not include this directory in an OpenRestor release.\n'
