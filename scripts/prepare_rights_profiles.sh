#!/usr/bin/env bash
set -euo pipefail

# Offline, repeatable preparation. Does not upload or acquire anything from Jamendo.
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
runner="$repo_root/.venv/bin/python"
if [[ ! -x "$runner" ]]; then
  printf 'ERROR: project virtualenv missing at %s\n' "$runner" >&2
  exit 2
fi
registry_args=()
if [[ -n "${RIGHTS_REVIEW_OVERRIDES:-}" ]]; then
  registry_args+=(--review-overrides "$RIGHTS_REVIEW_OVERRIDES")
fi
if [[ -n "${CLEAN_CORPUS_MANIFEST:-}" ]]; then
  registry_args+=(--clean-corpus-manifest "$CLEAN_CORPUS_MANIFEST")
fi
for arg in "$@"; do
  if [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
    exec "$runner" "$repo_root/scripts/build_publication_subset.py" "$@"
  fi
done
"$runner" "$repo_root/scripts/build_media_rights_registry.py" "${registry_args[@]}"
"$runner" "$repo_root/scripts/build_publication_subset.py" "$@"
