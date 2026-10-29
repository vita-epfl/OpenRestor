#!/usr/bin/env bash
set -euo pipefail

# Audit the Creative Commons licence reported by Jamendo for every SonicMaster
# source_id. The API credential is read from the environment and is never
# written to the output.

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
input=${1:-"$repo_root/configs/datasets/sonicmaster_original_split.jsonl"}
output_dir=${2:-"$repo_root/build/licence-audits/sonicmaster_jamendo"}
batch_size=${JAMENDO_AUDIT_BATCH_SIZE:-50}
delay_seconds=${JAMENDO_AUDIT_DELAY_SEC:-0.25}

if [[ -z "${JAMENDO_CLIENT_ID:-}" ]]; then
  printf '%s\n' \
    'ERROR: JAMENDO_CLIENT_ID is not set.' \
    'Create an API application at https://devportal.jamendo.com/ and export its client ID.' >&2
  exit 2
fi

for command in awk basename comm curl cut date jq paste sha256sum sleep sort split wc; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' "$command" >&2
    exit 2
  fi
done

if [[ ! -f "$input" ]]; then
  printf 'ERROR: input manifest not found: %s\n' "$input" >&2
  exit 2
fi

case "$batch_size" in
  ''|*[!0-9]*) printf 'ERROR: JAMENDO_AUDIT_BATCH_SIZE must be an integer.\n' >&2; exit 2 ;;
esac
if (( batch_size < 1 || batch_size > 50 )); then
  printf 'ERROR: JAMENDO_AUDIT_BATCH_SIZE must be between 1 and 50 (Jamendo API limit).\n' >&2
  exit 2
fi

mkdir -p "$output_dir/raw" "$output_dir/requests"
ids_file="$output_dir/source_ids.txt"
jq -r '.source_id' "$input" | sort -u > "$ids_file"

if [[ -s "$ids_file" ]] && ! awk '/^[0-9]+$/ { next } { exit 1 }' "$ids_file"; then
  printf 'ERROR: every source_id must be a numeric Jamendo track ID.\n' >&2
  exit 2
fi

expected_count=$(wc -l < "$ids_file")
if (( expected_count == 0 )); then
  printf 'ERROR: no source_id found in %s\n' "$input" >&2
  exit 2
fi

chunk_prefix="$output_dir/requests/batch_"
split -d -a 4 -l "$batch_size" "$ids_file" "$chunk_prefix"

batch_number=0
for request_file in "${chunk_prefix}"*; do
  batch_name=$(basename "$request_file")
  response_file="$output_dir/raw/${batch_name}.json"
  requested=$(wc -l < "$request_file")

  if [[ -f "$response_file" ]] \
      && jq -e '.headers.status == "success" and (.results | type == "array")' \
        "$response_file" >/dev/null 2>&1; then
    printf 'cached  %s (%s IDs)\n' "$batch_name" "$requested"
    batch_number=$((batch_number + 1))
    continue
  fi

  ids=$(paste -sd' ' "$request_file")
  printf 'fetch   %s (%s IDs)\n' "$batch_name" "$requested"
  curl --fail --silent --show-error --location \
    --retry 5 --retry-all-errors \
    --get 'https://api.jamendo.com/v3.0/tracks/' \
    --data-urlencode "client_id=${JAMENDO_CLIENT_ID}" \
    --data-urlencode 'format=json' \
    --data-urlencode "limit=${batch_size}" \
    --data-urlencode "id=${ids}" \
    --data-urlencode 'include=licenses' \
    --output "$response_file"

  if ! jq -e '.headers.status == "success" and (.results | type == "array")' \
      "$response_file" >/dev/null; then
    printf 'ERROR: Jamendo rejected %s: %s\n' \
      "$batch_name" \
      "$(jq -r '.headers.error_message // "invalid response"' "$response_file" 2>/dev/null)" >&2
    exit 3
  fi

  batch_number=$((batch_number + 1))
  sleep "$delay_seconds"
done

tracks_file="$output_dir/tracks.jsonl"
tracks_unsorted="$output_dir/tracks.unsorted.jsonl"
fetched_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
jq -c --arg fetched_at "$fetched_at" '
  def licence_url:
    (.license_ccurl // .licenses.ccurl // .license.ccurl // "") | tostring;
  def decision:
    (licence_url | ascii_downcase) as $url
    | if $url == "" then "withhold_missing_licence"
      elif ($url | test("publicdomain|zero/1\\.0")) then "publish_cc0"
      elif ($url | test("by-nc-nd|by-nd")) then "withhold_no_derivatives"
      elif ($url | test("by-nc-sa|by-nc")) then "withhold_noncommercial"
      elif ($url | test("by-sa")) then "review_share_alike"
      elif ($url | test("/by/")) then "publish_cc_by"
      else "withhold_unknown_licence"
      end;
  .results[]
  | {
      source_id: (.id | tostring),
      track_name: (.name // null),
      artist_id: ((.artist_id // null) | if . == null then null else tostring end),
      artist_name: (.artist_name // null),
      album_id: ((.album_id // null) | if . == null then null else tostring end),
      album_name: (.album_name // null),
      share_url: (.shareurl // null),
      licence_url: licence_url,
      audiodownload_allowed: (.audiodownload_allowed // null),
      publication_decision: decision,
      evidence_source: "Jamendo API v3 /tracks include=licenses",
      fetched_at: $fetched_at
    }
' "$output_dir"/raw/batch_*.json > "$tracks_unsorted"
jq -sc 'sort_by(.source_id | tonumber)[]' "$tracks_unsorted" > "$tracks_file"
rm "$tracks_unsorted"

jq -r '.source_id' "$tracks_file" | sort -u > "$output_dir/resolved_source_ids.txt"
comm -23 "$ids_file" "$output_dir/resolved_source_ids.txt" > "$output_dir/missing_source_ids.txt"

resolved_count=$(wc -l < "$output_dir/resolved_source_ids.txt")
missing_count=$(wc -l < "$output_dir/missing_source_ids.txt")

jq -s \
  --arg input "${input#"$repo_root/"}" \
  --arg input_sha256 "$(sha256sum "$input" | cut -d' ' -f1)" \
  --arg fetched_at "$fetched_at" \
  --argjson expected "$expected_count" \
  --argjson resolved "$resolved_count" \
  --argjson missing "$missing_count" '
  {
    audit: "sonicmaster-jamendo-track-licences",
    input: $input,
    input_sha256: $input_sha256,
    fetched_at: $fetched_at,
    expected_source_ids: $expected,
    resolved_source_ids: $resolved,
    missing_source_ids: $missing,
    by_publication_decision: (group_by(.publication_decision)
      | map({key: .[0].publication_decision, value: length}) | from_entries),
    by_licence_url: (group_by(.licence_url)
      | map({key: (.[0].licence_url | if . == "" then "<missing>" else . end), value: length})
      | from_entries)
  }
' "$tracks_file" > "$output_dir/summary.json"

{
  printf '# SonicMaster Jamendo licence audit\n\n'
  printf -- '- Input: `%s`\n' "${input#"$repo_root/"}"
  printf -- '- Audited at: `%s`\n' "$fetched_at"
  printf -- '- Expected source IDs: **%s**\n' "$expected_count"
  printf -- '- Resolved source IDs: **%s**\n' "$resolved_count"
  printf -- '- Missing source IDs: **%s**\n\n' "$missing_count"
  printf '## Publication decisions\n\n| Decision | Tracks |\n| --- | ---: |\n'
  jq -r '.by_publication_decision | to_entries[] | "| \(.key) | \(.value) |"' \
    "$output_dir/summary.json"
  printf '\n## Exact licence URLs\n\n| Licence URL | Tracks |\n| --- | ---: |\n'
  jq -r '.by_licence_url | to_entries[] | "| `\(.key)` | \(.value) |"' \
    "$output_dir/summary.json"
  printf '\n`ND` and missing/unknown licences are withheld. `NC` is withheld from the '\
'commercially reusable release. `SA` requires a project decision before publication.\n'
} > "$output_dir/audit_report.md"

printf '\nAudit written to %s\n' "$output_dir"
jq '.' "$output_dir/summary.json"

if (( missing_count > 0 )); then
  printf 'ERROR: %s source IDs were not returned by Jamendo; the audit is incomplete.\n' \
    "$missing_count" >&2
  exit 4
fi
