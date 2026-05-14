#!/usr/bin/env bash
# Summarise every active featcat sandbox on this host.
#
# Walks /tmp/featcat-sandbox-* roots, pairs each with its compose project
# state and `/api/health` reachability, and cross-references `docker compose ls`
# so orphan projects (no matching root) surface explicitly.
#
# Usage:
#   status-sandbox.sh [--root <path>]

set -euo pipefail
IFS=$'\n\t'

# shellcheck source=lib/common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

root_parent="/tmp"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      root_parent="${2:-}"
      shift 2
      ;;
    -h | --help)
      echo "Usage: status-sandbox.sh [--root <path>]" >&2
      exit 0
      ;;
    *)
      log_error "unknown flag: $1"
      exit 2
      ;;
  esac
done

require_cmd docker "install Docker Engine"

# Header — fixed-width columns so the output stays grep-friendly.
printf '%-26s  %-46s  %-6s  %-8s  %s\n' "ID" "PROJECT" "HEALTH" "PORTS" "ROOT"
printf '%-26s  %-46s  %-6s  %-8s  %s\n' "--" "-------" "------" "-----" "----"

found_any=false

while IFS= read -r root; do
  [[ -z "${root}" ]] && continue
  found_any=true
  basename="$(basename "${root}")"
  id="${basename#"${sandbox_project_prefix}-"}"
  project="$(sandbox_project_for_root "${root}")"
  project="${project:-${basename}}"

  port=""
  if [[ -f "${root}/.env" ]]; then
    port="$(awk -F= '/^FEATCAT_PORT=/{print $2; exit}' "${root}/.env")"
  fi

  health="unknown"
  if [[ -n "${port}" ]]; then
    if curl -fsS --max-time 2 "http://localhost:${port}/api/health" >/dev/null 2>&1; then
      health="ok"
    else
      health="down"
    fi
  fi

  printf '%-26s  %-46s  %-6s  %-8s  %s\n' "${id}" "${project}" "${health}" "${port:-?}" "${root}"
done < <(list_sandbox_roots "${root_parent}")

if ! ${found_any}; then
  echo "(no sandbox roots under ${root_parent})"
fi

# Orphan projects: compose projects whose name starts with the sandbox prefix
# but have no corresponding root dir. We list them so the operator can run
# `reset-sandbox.sh --id <id>` even though the root is gone.
printf '\n'
printf '%s\n' "Docker compose projects:"
docker compose ls --format json 2>/dev/null \
  | jq -r --arg prefix "${sandbox_project_prefix}" \
      '.[] | select(.Name | startswith($prefix)) | "  \(.Name)  \(.Status)"' \
  || echo "  (none)"
