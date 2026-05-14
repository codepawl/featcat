#!/usr/bin/env bash
# Shortcut for `docker compose -p featcat-sandbox-<id> exec featcat <cmd>`.
#
# Usage:
#   exec-sandbox.sh [--id <sandbox-id>] [--service <name>] -- <command> [args...]
#
# With no --id, picks the most recent sandbox root under /tmp.
# Default service is `featcat` — pass --service llm or --service postgres to
# exec into another container.

set -euo pipefail
IFS=$'\n\t'

# shellcheck source=deploy/sandbox/scripts/lib/common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

sandbox_id=""
root_parent="/tmp"
service="featcat"
cmd_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id)
      sandbox_id="${2:-}"
      shift 2
      ;;
    --root)
      root_parent="${2:-}"
      shift 2
      ;;
    --service)
      service="${2:-}"
      shift 2
      ;;
    --)
      shift
      cmd_args=("$@")
      break
      ;;
    -h | --help)
      cat <<'USAGE' >&2
Usage: exec-sandbox.sh [--id <id>] [--service <name>] -- <command> [args...]

  --id        Pick a specific sandbox (default: latest under --root).
  --service   Container service to exec into (default: featcat).
  --          Separates exec-sandbox flags from the command to run inside.

Examples:
  exec-sandbox.sh -- featcat doctor
  exec-sandbox.sh --id 20260514-094501-1234 -- bash
  exec-sandbox.sh --service postgres -- psql -U featcat featcat
USAGE
      exit 0
      ;;
    *)
      log_error "unknown flag: $1 — did you forget the -- separator?"
      exit 2
      ;;
  esac
done

if [[ ${#cmd_args[@]} -eq 0 ]]; then
  log_error "missing command (use -- before the command, e.g. 'exec-sandbox.sh -- featcat doctor')"
  exit 2
fi

require_cmd docker "install Docker Engine"

# Resolve the sandbox root.
sandbox_root=""
if [[ -n "${sandbox_id}" ]]; then
  sandbox_root="${root_parent}/${sandbox_project_prefix}-${sandbox_id}"
else
  # Latest sandbox = last entry in sorted list (timestamp ids sort lexically).
  while IFS= read -r line; do
    sandbox_root="${line}"
  done < <(list_sandbox_roots "${root_parent}")
fi

if [[ -z "${sandbox_root}" || ! -d "${sandbox_root}" ]]; then
  log_error "no sandbox root found (looked for ${sandbox_root:-<latest>})"
  exit 1
fi

project="$(sandbox_project_for_root "${sandbox_root}")"
project="${project:-$(basename "${sandbox_root}")}"
base_compose="${sandbox_root}/repo/deploy/docker-compose.yml"
override_compose="${sandbox_root}/repo/deploy/sandbox/compose/docker-compose.sandbox.yml"
env_file="${sandbox_root}/.env"

compose_args_array "${project}" "${base_compose}" "${override_compose}" "${env_file}"

exec docker compose "${_compose_args[@]}" exec "${service}" "${cmd_args[@]}"
