#!/usr/bin/env bash
# Tear down sandbox(es) created by start-sandbox.sh.
#
# Removes Docker compose project resources (containers, volumes, networks) AND
# the matching /tmp/featcat-sandbox-<id> root. Idempotent — running twice on
# the same id is a no-op the second time.
#
# Usage:
#   reset-sandbox.sh [--id <sandbox-id>] [--root <path>] [--keep-data] [--dry-run]
#
# With no --id, every sandbox root found under <root> is torn down.

set -euo pipefail
IFS=$'\n\t'

# shellcheck source=lib/common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"

sandbox_id=""
root_parent="/tmp"
keep_data=false
dry_run=false

usage() {
  cat <<'USAGE' >&2
Usage: reset-sandbox.sh [options]

Optional:
  --id <sandbox-id>     Tear down only the given sandbox. Default: every
                        sandbox found under --root.
  --root <path>         Parent directory containing sandbox roots (default /tmp).
  --keep-data           Keep the sandbox root directory after removing Docker
                        resources. Useful when inspecting failures.
  --dry-run             Print actions; do not execute.
  -h, --help            This message.

USAGE
}

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
    --keep-data)
      keep_data=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      log_error "unknown flag: $1"
      usage
      exit 2
      ;;
  esac
done

require_cmd docker "install Docker Engine"

# Run a command, or echo it under --dry-run. Honours quoting via "$@".
run_or_echo() {
  if ${dry_run}; then
    printf '+ %s\n' "$*" >&2
  else
    "$@"
  fi
}

# Tear down a single sandbox root. The caller passes either an existing root
# directory OR a synthesised one (when only --id was provided). Missing pieces
# are tolerated so re-runs are clean.
teardown_one() {
  local root="$1"
  local project=""

  if [[ -d "${root}" ]]; then
    project="$(sandbox_project_for_root "${root}")"
  fi
  if [[ -z "${project}" ]]; then
    # Fall back: derive the project name from the root's basename, which is
    # what start-sandbox.sh always sets.
    project="$(basename "${root}")"
  fi

  log_info "teardown ${project} (root: ${root})"

  # `docker compose ... down -v` only works if the compose file is present.
  # When the operator runs --id <id> on a sandbox whose root has already been
  # removed, the project may still own dangling resources; we fall through to
  # the orphan-cleanup pass below to handle that.
  local base_compose="${root}/repo/deploy/docker-compose.yml"
  local override_compose="${root}/repo/deploy/sandbox/compose/docker-compose.sandbox.yml"
  local env_file="${root}/.env"
  if [[ -f "${base_compose}" && -f "${override_compose}" && -f "${env_file}" ]]; then
    compose_args_array "${project}" "${base_compose}" "${override_compose}" "${env_file}"
    run_or_echo docker compose "${_compose_args[@]}" down -v --remove-orphans --timeout 5
  else
    log_warn "compose files missing under ${root}; relying on orphan cleanup"
  fi

  # Orphan cleanup. `down -v` should have caught these but we re-check so a
  # half-deleted sandbox still finishes cleanly.
  local volumes
  volumes="$(docker volume ls --quiet --filter "name=^${project}_")" || volumes=""
  if [[ -n "${volumes}" ]]; then
    # shellcheck disable=SC2086  # word-splitting is intentional here.
    run_or_echo docker volume rm ${volumes}
  fi
  local networks
  networks="$(docker network ls --quiet --filter "name=^${project}_")" || networks=""
  if [[ -n "${networks}" ]]; then
    # shellcheck disable=SC2086  # word-splitting is intentional here.
    run_or_echo docker network rm ${networks}
  fi
  local stragglers
  stragglers="$(docker ps -aq --filter "label=com.docker.compose.project=${project}")" || stragglers=""
  if [[ -n "${stragglers}" ]]; then
    # shellcheck disable=SC2086  # word-splitting is intentional here.
    run_or_echo docker rm -f ${stragglers}
  fi

  if [[ -d "${root}" ]] && ! ${keep_data}; then
    run_or_echo rm -rf "${root}"
  fi

  log_ok "teardown complete: ${project}"
}

# Build the work list.
roots=()
if [[ -n "${sandbox_id}" ]]; then
  roots+=("${root_parent}/${sandbox_project_prefix}-${sandbox_id}")
else
  while IFS= read -r line; do
    roots+=("${line}")
  done < <(list_sandbox_roots "${root_parent}")
fi

if [[ ${#roots[@]} -eq 0 ]]; then
  log_info "no sandboxes found under ${root_parent}"
  exit 0
fi

# `set -e` doesn't get rid of the ShellCheck SC2317 if we ever change the way
# the array is iterated; for now a vanilla for-each is the readable choice.
for root in "${roots[@]}"; do
  teardown_one "${root}"
done

# shellcheck disable=SC2086  # noqa: the explicit disables above stand alone;
# this final disable is for the safety net below where we re-scan for ANY
# straggler resources whose names start with the sandbox prefix. We only do
# this when --id was NOT given, i.e. operator asked for a sweep.
if [[ -z "${sandbox_id}" ]]; then
  log_info "sweeping orphan resources whose names start with ${sandbox_project_prefix}-"
  orphan_volumes="$(docker volume ls --quiet --filter "name=^${sandbox_project_prefix}-")" || orphan_volumes=""
  if [[ -n "${orphan_volumes}" ]]; then
    run_or_echo docker volume rm ${orphan_volumes}
  fi
  orphan_networks="$(docker network ls --quiet --filter "name=^${sandbox_project_prefix}-")" || orphan_networks=""
  if [[ -n "${orphan_networks}" ]]; then
    run_or_echo docker network rm ${orphan_networks}
  fi
fi

log_ok "all done"
