# Featcat sandbox — operator's guide

This directory ships an **isolated UAT sandbox** for featcat. It exists so a DS
team member can simulate the full "first-time install → daily use" journey on a
real Docker stack without ever touching:

- The main repo working tree (the launcher clones it instead).
- The production deploy at `~/featcat` (different compose project, different
  ports, different volumes — they can run side by side).
- Any host state outside the sandbox root and the namespaced Docker resources.

Everything below assumes you are inside a featcat checkout. The full design
rationale is in [`PLAN.md`](PLAN.md).

## Prerequisites

- Docker Engine (24+ recommended) reachable as the current user
- Bash, git, curl, jq, ss (in `iproute2`)
- For the lab profile: FPT proxy + DNS already configured at the host level
- The LLM model on disk at `deploy/models/gemma-4-E2B-it-Q4_K_M.gguf`. If
  missing, the launcher fails fast with the exact `curl` command to fetch it
  (we never auto-download a 533 MB file).

## TL;DR

```bash
# Start a fresh sandbox.
bash deploy/sandbox/scripts/start-sandbox.sh --profile local

# (the launcher prints the URL, the sandbox id, and the teardown command)

# Run featcat commands inside.
bash deploy/sandbox/scripts/exec-sandbox.sh -- featcat doctor

# See what's running.
bash deploy/sandbox/scripts/status-sandbox.sh

# Tear everything down.
bash deploy/sandbox/scripts/reset-sandbox.sh
```

## What you get

Each run creates a fully-namespaced compose project:

| Resource     | Pattern                                                  |
|--------------|----------------------------------------------------------|
| Sandbox root | `/tmp/featcat-sandbox-<YYYYMMDD-HHMMSS-PID>/`            |
| Project name | `featcat-sandbox-<id>` (passed to every `docker compose -p`) |
| Containers   | `featcat-sandbox-<id>-{featcat,postgres,llm}-1`          |
| Volumes      | `featcat-sandbox-<id>_{featcat_data,featcat-postgres-data}` |
| Network      | `featcat-sandbox-<id>_default`                           |
| Host ports   | featcat `8100+`, llama.cpp `8180+`, postgres `5532+`     |

Ports are auto-picked starting at the defaults — multiple sandboxes can run
concurrently and they walk upwards to avoid collisions.

## Profiles

One required flag: `--profile {local,lab}`.

- `local`: WSL2 / direct-internet developer machines. No proxy.
- `lab`: FPT lab boxes behind the corporate proxy. Build args, runtime
  `NO_PROXY`, and pull strategy match the production deploy quirks.

The profiles are just layered `.env` files at
`deploy/sandbox/compose/{local,lab}.env`. They override
`deploy/.env.example` for the launcher only; production env files are never
touched.

## Scripts

| Script               | What it does |
|----------------------|--------------|
| `start-sandbox.sh`   | Clone, generate `.env`, pick ports, build, up, wait healthy, print URL |
| `reset-sandbox.sh`   | `compose down -v`, sweep orphan volumes/networks, `rm -rf` the root |
| `status-sandbox.sh`  | List active sandboxes + Docker compose projects starting with `featcat-sandbox-` |
| `exec-sandbox.sh`    | Shortcut for `docker compose -p <project> exec <service> <cmd>` |
| `lib/common.sh`      | Sourced helpers (no shebang needed; consumed via `source`) |

Each script lives at `deploy/sandbox/scripts/<name>.sh`. All pass `shellcheck`.
Bash strict mode (`set -euo pipefail` + tab-only IFS) is on by default.

## Walking the UAT

`deploy/sandbox/findings/_TEMPLATE.md` is the report shape. Copy it to
`run-<YYYY-MM-DD>-<short-id>.md` at the start of a run, fill in scenarios as
you go, and commit the result so future operators can see what you saw.

The 15 scenarios are listed in `PLAN.md` § 4. Scenarios a–d are the install
smoke test (always done). e–o are the deep dive (do them in order; skip and
mark `-` if blocked).

## Isolation guarantees

Concrete: if the production deploy is running at `~/featcat`, none of these
calls should differ between "before a sandbox is up" and "after a sandbox is
up":

```bash
docker compose -p featcat ps
curl -fsS http://localhost:8000/api/health
ls ~/featcat
```

The sandbox only ever creates resources named `featcat-sandbox-*`. The reset
command removes those names and nothing else.

## Troubleshooting

| Symptom                                                | Fix |
|--------------------------------------------------------|-----|
| `LLM model not found`                                  | Run the `curl` printed by the launcher. ~533 MB. |
| `--profile lab` but build cannot reach the proxy       | Pre-build the image with `docker build --network=host` once; the launcher reuses the cache. |
| `/api/health never returned ok within 90s`             | Inspect with `bash exec-sandbox.sh -- featcat doctor`, then logs via `docker compose -p <project> logs`. |
| Port conflict (`failed to bind`)                       | Another sandbox is using the port. The launcher walks upwards, but if 50 candidates are taken something else is wrong; `status-sandbox.sh` lists them. |
| `reset-sandbox.sh` left a volume                       | Re-run; the second pass uses `docker volume rm` directly on anything matching `featcat-sandbox-*_`. |

## Not goals

This sandbox is intentionally:

- **Not automated.** Phase 3 has one human-driven smoke test; nothing runs in
  CI.
- **Not shared infra.** Two sandboxes are two separate compose projects with
  zero shared state. Test failures don't bleed across runs.
- **Not a production replacement.** It deliberately overrides bits of the
  production compose. Use the real `deploy/` setup for real deployments.
