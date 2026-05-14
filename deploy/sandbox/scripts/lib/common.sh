#!/usr/bin/env bash
# Shared helpers for the featcat sandbox launcher scripts.
#
# Sourced — do NOT execute directly. Every consumer sets strict mode itself;
# this file only provides functions and constants.
#
# Style: every identifier lowercase_snake. log_* prefix every message with a
# bracketed level so multi-process output stays readable when several sandbox
# scripts run concurrently.

# Resource-name prefix shared by every sandbox compose project. `export`
# alongside `readonly` so shellcheck recognises external use from the scripts
# that source this file.
export sandbox_project_prefix="featcat-sandbox"
readonly sandbox_project_prefix

# Default starting ports. The launcher walks upwards from these to find a free
# triplet, so production (8000 / 8080) and the chosen sandbox window never
# overlap on a default install.
export sandbox_default_featcat_port=8100
export sandbox_default_llm_port=8180
export sandbox_default_pg_port=5532
export sandbox_port_scan_limit=50
readonly sandbox_default_featcat_port sandbox_default_llm_port sandbox_default_pg_port sandbox_port_scan_limit

# ANSI colours for stderr logging. NO_COLOR=1 in the env disables them.
if [[ -n "${NO_COLOR:-}" || ! -t 2 ]]; then
  readonly _c_reset=""
  readonly _c_dim=""
  readonly _c_warn=""
  readonly _c_err=""
  readonly _c_ok=""
else
  readonly _c_reset=$'\033[0m'
  readonly _c_dim=$'\033[2m'
  readonly _c_warn=$'\033[33m'
  readonly _c_err=$'\033[31m'
  readonly _c_ok=$'\033[32m'
fi

log_info() {
  printf '%s[info]%s %s\n' "${_c_dim}" "${_c_reset}" "$*" >&2
}

log_ok() {
  printf '%s[ ok ]%s %s\n' "${_c_ok}" "${_c_reset}" "$*" >&2
}

log_warn() {
  printf '%s[warn]%s %s\n' "${_c_warn}" "${_c_reset}" "$*" >&2
}

log_error() {
  printf '%s[err ]%s %s\n' "${_c_err}" "${_c_reset}" "$*" >&2
}

# require_cmd <command> <install-hint>
# Exit 1 with a clear message if `command` is missing on PATH.
require_cmd() {
  local cmd="$1"
  local hint="${2:-install ${cmd} and retry}"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    log_error "${cmd} not found on PATH — ${hint}"
    exit 1
  fi
}

# timestamp_id
# Echo a sortable id of form YYYYMMDD-HHMMSS-PID. Unique per process.
timestamp_id() {
  printf '%s-%s\n' "$(date +%Y%m%d-%H%M%S)" "$$"
}

# pick_free_port <start>
# Walk upwards from <start> looking for a TCP port nothing is bound to. Echo
# the chosen port on stdout. Exit 1 if no free port found within
# sandbox_port_scan_limit attempts.
pick_free_port() {
  local start="$1"
  local port
  for ((port = start; port < start + sandbox_port_scan_limit; port++)); do
    if ! ss -tlnH "sport = :${port}" 2>/dev/null | grep -q .; then
      printf '%s\n' "${port}"
      return 0
    fi
  done
  log_error "no free port in [${start}, $((start + sandbox_port_scan_limit))]"
  return 1
}

# compose_args <project> <base-compose> <override-compose> <env-file>
# Echo the standard arg block every script passes to `docker compose`. Caller
# expands without quotes ("$(compose_args ...)" loses the spaces) — use the
# array helper compose_args_array when invoking docker compose directly.
compose_args() {
  printf -- '-p %s -f %s -f %s --env-file %s' "$1" "$2" "$3" "$4"
}

# compose_args_array <project> <base-compose> <override-compose> <env-file>
# Populates a global array `_compose_args` so callers can splat it correctly:
#   compose_args_array "$proj" "$base" "$over" "$env"
#   docker compose "${_compose_args[@]}" ps
# Cleaner than parsing the printf form when args contain spaces.
compose_args_array() {
  _compose_args=(-p "$1" -f "$2" -f "$3" --env-file "$4")
}

# list_sandbox_roots [parent-dir]
# Echo every existing /tmp/featcat-sandbox-* directory, one per line. Parent
# defaults to /tmp. No matches → empty stdout, exit 0.
list_sandbox_roots() {
  local parent="${1:-/tmp}"
  find "${parent}" -maxdepth 1 -type d -name "${sandbox_project_prefix}-*" 2>/dev/null | sort
}

# sandbox_project_for_root <root>
# Echo the compose project name recorded in <root>/compose-project-name, or
# nothing if the file is missing.
sandbox_project_for_root() {
  local root="$1"
  local file="${root}/compose-project-name"
  if [[ -f "${file}" ]]; then
    head -n1 "${file}"
  fi
}
