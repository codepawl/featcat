# Production deployment

This page covers deploying featcat to a production host. For the conceptual layout, see [Architecture › Deployment](../architecture/deployment.md). For local dev, see [Installation](../getting-started/installation.md).

## Recommended target

A single host (4 vCPU, 16 GB RAM, 100 GB SSD) running Docker Compose handles up to ~50 concurrent users and ~10k features. Beyond that, split services across hosts and front with a load balancer.

OS: any Linux with Docker 24+ and Docker Compose v2. Tested on Ubuntu 22.04 LTS and Debian 12.

## Pre-flight

- [ ] DNS A record (`featcat.team.example.com`) pointing at the host
- [ ] TLS termination upstream (Caddy / nginx / Cloudflare). featcat itself is HTTP only.
- [ ] Block port 5432 / 6379 / 8080 from the public internet — only `:8000` should be reachable through the proxy.
- [ ] Off-host backup destination ready (see [Backup](backup.md))

## Compose stack

```bash
git clone https://github.com/codepawl/featcat.git /opt/featcat
cd /opt/featcat
git checkout v0.4.0   # or whatever tag

# .env at repo root, gitignored
cat > .env <<'EOF'
POSTGRES_PASSWORD=<strong-password>
FEATCAT_DB_BACKEND=postgres
FEATCAT_DB_URL=postgresql+psycopg2://featcat:<same-password>@postgres:5432/featcat
FEATCAT_LLAMACPP_URL=http://llm:8080
DATA_DIR=/var/featcat/data       # mounted to /sources read-only
FEATCAT_AUTH_REQUIRED=true
FEATCAT_AUTH_ALLOWED_EMAIL_DOMAINS=["fpt.com"]
FEATCAT_CORS_ORIGINS=https://featcat.team.example.com
EOF

# Pull the GGUF model once
mkdir -p deploy/models
curl -L -o deploy/models/gemma-4-E2B-it-Q4_K_M.gguf \
    "https://huggingface.co/bartowski/google_gemma-4-E2B-it-GGUF/resolve/main/google_gemma-4-E2B-it-Q4_K_M.gguf"

# Bring up
cd deploy
docker compose pull
docker compose up -d
```

After ~30s the API is up. Verify:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","version":"0.4.0","db":true,"llm":true,...}
curl http://localhost:8000/api/ready
# {"status":"ready","version":"0.4.0","db_backend":"postgres","db":true}
```

The container startup script applies Alembic migrations and runs `featcat init`
before serving traffic. If either step fails, the container exits instead of
continuing with a partially initialized feature store.

## Reverse proxy (Caddy example)

`/etc/caddy/Caddyfile`:

```
featcat.team.example.com {
    reverse_proxy localhost:8000 {
        header_up X-Forwarded-Proto {scheme}
    }
    encode gzip
}
```

Caddy auto-fetches the cert. Reload: `systemctl reload caddy`.

## Tasks profile (Celery + Redis)

Off by default. Bring up if you need distributed batch processing:

```bash
docker compose --profile tasks up -d
# featcat + llm + postgres + redis + celery-worker + celery-beat
```

Set `FEATCAT_TASKS_BACKEND=celery` in `.env` and restart `featcat`. APScheduler in-process jobs stop firing; Celery beat takes over.

To add worker capacity:

```bash
docker compose --profile tasks up -d --scale celery-worker=4
```

Workers share the same broker; tasks are distributed by Celery's default round-robin.

## Multi-host split

Beyond ~50 concurrent users, separate hosts:

| Host | Service | Notes |
|---|---|---|
| `featcat-api` | featcat container × N | Behind LB, sticky sessions not required |
| `featcat-llm` | llama.cpp on a GPU box | Big throughput win; 50× CPU latency |
| `featcat-db` | Postgres dedicated | RAM + SSD focus |
| `featcat-tasks` | celery-worker × N | Optional, only if `[tasks]` enabled |

Use `docker-compose.override.yml` per host, or move to k8s with the same service decomposition.

## Updates

```bash
cd /opt/featcat
git fetch --tags
git checkout v0.4.1
cd deploy
docker compose pull && docker compose up -d
docker compose exec featcat featcat doctor  # smoke
```

If alembic fails (multi-head, version mismatch), see [Troubleshooting](troubleshooting.md).

Rollback:

```bash
git checkout v0.4.0
docker compose pull && docker compose up -d
docker compose exec featcat alembic downgrade <prev-head>
```

Always have a `pg_dump` from before the upgrade. Schema downgrades are tested but not always painless.

## Resource sizing

| Component | CPU | RAM | Disk |
|---|---|---|---|
| featcat (4 workers) | 0.5 vCPU baseline, 2 vCPU under load | 500 MB | 50 MB binary |
| llama.cpp | 2–4 vCPU per request | 5 GB idle, 8 GB peak | 4 GB model |
| postgres | 0.5 vCPU baseline | 1–2 GB shared_buffers | 100 MB / 1k features |
| celery-worker × 1 | 0.5 vCPU baseline, 2 vCPU under load | 500 MB | negligible |
| redis | negligible | 100 MB | < 100 MB |

Stress-test with `tests/perf/` before sizing. Real workloads vary.

## Hardening

- Set `FEATCAT_CORS_ORIGINS` to your front-end domain only — default is `*` for dev convenience.
- Run the API container as a non-root user (Dockerfile already does, verify with `docker exec featcat id`).
- Use Docker secrets or k8s Secrets for `POSTGRES_PASSWORD`, not env files.
- Enable PostgreSQL `log_statement=ddl` to audit schema changes. `log_min_duration_statement=500` to catch slow queries.

## Auth (optional)

featcat is public by default. Anyone can browse the app without signing in.

If you want optional company identity or admin scoping, featcat also supports:

- **Bearer token**: set `FEATCAT_SERVER_AUTH_TOKEN` and the API requires `Authorization: Bearer <token>` on `/api/*`.
- **Trusted proxy / SSO**: put featcat behind an SSO proxy (oauth2-proxy / Pomerium / Cloudflare Access), set `FEATCAT_AUTH_REQUIRED=true`, and configure the proxy to send one of the trusted identity headers: `X-Auth-Request-Email`, `X-Forwarded-Email`, `Cf-Access-Authenticated-User-Email`, or `X-User-Email`.

Role mapping is configured with `FEATCAT_AUTH_ADMIN_USERS`, `FEATCAT_AUTH_EDITOR_USERS`,
`FEATCAT_AUTH_ADMIN_GROUPS`, and `FEATCAT_AUTH_EDITOR_GROUPS`. Group headers are
read from `X-Auth-Request-Groups`, `X-Forwarded-Groups`, or `Cf-Access-Groups`.

For company onboarding, the UI also exposes an `@fpt.com` request-access form. Control the accepted email domains with `FEATCAT_AUTH_ALLOWED_EMAIL_DOMAINS` (default: `["fpt.com"]`).

The account panel is optional; if a user signs in, the current identity and role appear in the UI. Proxy mode still carries the upstream role mapping when configured.

## Related

- **[Architecture › Deployment](../architecture/deployment.md)** — service layout
- **[Monitoring](monitoring.md)** — what to scrape
- **[Backup](backup.md)** — disaster recovery
- **[Troubleshooting](troubleshooting.md)** — common issues
