# Featcat End-User Sandbox — Plan

> Mirrored from the planning session — `/home/nxank4/.claude/plans/phase-3-5-combined-synthetic-pascal.md`.
> Kept in-repo so future operators can read the design rationale without leaving the tree.

**Goal:** Ship `deploy/sandbox/` — an isolated end-user UAT sandbox that lets a DS team member walk through the full first-time-install → daily-use journey on a real Docker stack without ever touching the main repo working tree or the production deploy at `~/featcat`.

**Architecture:** A bash launcher clones the working tree into a timestamped directory under `/tmp/featcat-sandbox-<id>/`, generates a compose-project-scoped `.env` (with free ports auto-picked and `container_name:` overrides), and brings up the stack via `docker compose -p featcat-sandbox-<id> -f deploy/docker-compose.yml -f deploy/sandbox/compose/docker-compose.sandbox.yml up`. Teardown is `compose down -v` + `rm -rf` of the sandbox root.

**Tech Stack:** bash (strict mode), Docker Compose, sandbox fixture generator in polars (one-shot), Markdown findings template. No new runtime dependencies, no application code changes.

---

## Context

We need to UAT featcat end-to-end **as a brand-new user**, repeatedly, without:
- Editing the dev working tree (clones it instead — read-only relative to the source repo)
- Colliding with the production deploy at `~/featcat` (different compose project, different ports, different volumes)
- Leaving state behind between runs (one command full-reset)

Confirmed against the repo:
- Production compose pins `container_name:` on every service (`featcat-llm`, `featcat-postgres`, `featcat-server`, ...) — Docker treats those names as global, so a second compose project using the same compose file will fail with name collisions. The sandbox override **must blank `container_name:`** so the project-name prefix mechanism takes over.
- Production exposes `:8000` (featcat) and `:8080` (llm). Postgres is internal. Sandbox picks free triplets starting from `8100 / 8180 / 5532`.
- `deploy/models/gemma-4-E2B-it-Q4_K_M.gguf` (533 MB) is already on disk; the sandbox bind-mounts it read-only so it isn't re-downloaded.
- The first-time `featcat doctor` command and `/api/health` endpoint exist and are the canonical readiness probes.

---

## 1. Isolation strategy

### Sandbox root
`/tmp/featcat-sandbox-<YYYYMMDD-HHMMSS-PID>/` — timestamp + pid keeps concurrent sandboxes unique. Override with `--root <path>` for non-`/tmp` placement.

```
/tmp/featcat-sandbox-20260514-093015-12345/
├── repo/                  # `git clone --local` of the source repo
├── data/                  # bind-mounted to /sources
├── .env                   # generated, layered on deploy/.env.example
├── compose-project-name   # one-line file holding `featcat-sandbox-<id>`
└── run.log                # tee'd output (when launcher is run with tee)
```

### Repo clone vs git worktree — picked: `git clone --local`
Hardlinks where possible, no network, <1 s. Sandbox owns its `.git` (operator can `git status` inside without confusing the source). `git worktree` was rejected because it shares `.git` and a failed teardown leaves orphan refs upstream.

### Docker resource naming
- Compose project: `featcat-sandbox-<id>`.
- Container names: **blanked** by the override file → compose auto-names them as `<project>-<service>-1`.
- Volumes / network: project-prefixed automatically.

### Port isolation
Defaults `8100 / 8180 / 5532`. `start-sandbox.sh` walks upwards via `ss -tlnH` until it finds a free triplet (max 50 attempts).

### Data isolation
`data/` inside the sandbox root is bind-mounted at `/sources` and pre-seeded with `fixtures/synthetic.parquet`. No production data path is referenced.

---

## 2. Two host profiles

| Knob | `local` | `lab` |
|------|---------|-------|
| `HTTP_PROXY` / `HTTPS_PROXY` | unset | `http://proxy.hcm.fpt.vn:80` |
| Build `--network=host` | not used | requested |
| Runtime `NO_PROXY` | `localhost,127.0.0.1` | `llm,postgres,localhost,127.0.0.1,.fpt.vn` |
| Image pull | normal | rely on cached image; fail fast otherwise |
| Daemon DNS | system default | assumes FPT DNS already in `daemon.json` |

Profiles are static env files at `deploy/sandbox/compose/{local,lab}.env`. The launcher concatenates `deploy/.env.example` → profile → runtime overrides into the sandbox `.env`, so upstream changes to `.env.example` flow through automatically.

`--profile` is required. If `--profile local` is chosen but `HTTP_PROXY` is set in the calling shell, the launcher warns but does not auto-switch.

---

## 3. Lifecycle scripts

All scripts under `deploy/sandbox/scripts/`. Bash strict mode (`set -euo pipefail` + `IFS=$'\n\t'`). English identifiers and comments. Pass `shellcheck` cleanly except for two specific places in `reset-sandbox.sh` where word-splitting is the intentional and documented choice.

| Script | Purpose |
|--------|---------|
| `start-sandbox.sh` | Clone, env, ports, build, up, health-check, print URL |
| `reset-sandbox.sh` | `compose down -v` + orphan sweep + `rm -rf root` |
| `status-sandbox.sh` | Table of active sandboxes + orphan compose projects |
| `exec-sandbox.sh` | `docker compose -p <project> exec <service> <cmd>` shortcut |
| `lib/common.sh` | Sourced helpers (logging, port picker, compose-args builder) |

Shared helpers, defaults, and the resource-name prefix (`featcat-sandbox`) all live in `lib/common.sh` so a per-script change can't drift from the contract.

---

## 4. Test scenarios

| # | Area | Scenario |
|---|------|----------|
| a | Install path | clone → start → wait healthy → `/api/health` 200 |
| b | Doctor | `featcat doctor` (db / llm / data / network / deploy) |
| c | Source registration | `featcat source add` + `featcat source list` |
| d | Bulk inventory + browse + search | `featcat scan-bulk /sources`; feature list; search |
| e | Auto-doc | one feature, 10 features, full source |
| f | Feature Groups | create / add / list / remove |
| g | Feature Definitions | edit + audit log |
| h | AI chat (SSE) | `/api/ai/chat` end-to-end |
| i | Similarity graph | D3 render + interaction |
| j | PSI timeline | drift check + distribution shift |
| k | Documentation Debt Heatmap | coverage view |
| l | Health Score | per-feature score |
| m | Export to DataFrame | `featcat export` |
| n | Versioning + rollback | edit / snapshot / rollback |
| o | Teardown + reproduce | `reset-sandbox.sh` and re-run |

Phase 3 covers **a-d**. Everything else is a manual checklist for the operator running the UAT.

---

## 5. Findings capture

One file per run at `deploy/sandbox/findings/run-<YYYY-MM-DD>-<short-id>.md`. Template at `_TEMPLATE.md`. Each scenario has slots for time taken, steps that worked / broke (with verbatim error output), UX confusion, severity, and suggested fix. A summary table at the bottom and a "Reproduce this run" block at the end.

---

## 6. Repo hygiene

Committed: everything under `deploy/sandbox/` except `deploy/sandbox/.runs-cache/` (gitignored). Production files (`deploy/docker-compose.yml`, `deploy/Dockerfile`, `deploy/.env.example`, `deploy/setup.sh`, `deploy/README.md`) are not modified.

---

## 7. Isolation verification

```bash
docker compose -p featcat ps --format json > /tmp/before.json
curl -fsS http://localhost:8000/api/health > /tmp/before-health.json

bash deploy/sandbox/scripts/start-sandbox.sh --profile local

docker compose -p featcat ps --format json > /tmp/after.json
diff /tmp/before.json /tmp/after.json    # expected: empty

docker volume ls --filter name=featcat-sandbox
docker volume ls --filter name=^featcat_
# Disjoint sets.

curl -fsS http://localhost:8100/api/health   # sandbox
curl -fsS http://localhost:8000/api/health   # production unchanged
```

---

## 8. Non-goals

- No pytest / Playwright wrapping the sandbox itself
- No CI job runs the sandbox
- No refactor of production deploy files to share code with sandbox tooling
- No LLM model auto-download (fails loud with the `curl` command instead)
- Scenarios e-o stay manual — they are the human checklist
