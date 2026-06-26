# Operational monitoring

This page is about *operational* monitoring — keeping featcat itself healthy. For monitoring the data your features represent, see [User Guide › Monitoring](../user-guide/monitoring.md).

## What to watch

| Signal | Why | Source |
|---|---|---|
| API uptime | Tells you if anyone can use the feature store | `GET /api/ready` |
| LLM uptime | Tells you if doc gen + chat work | `GET /api/health` (`llm` field) |
| DB latency | Feature browsing slows when this rises | Postgres `pg_stat_statements` or app logs |
| Scheduler heartbeat | Drift checks need this. Silent failure is the worst kind. | `job_logs` table |
| Disk usage | Postgres + GGUF model are the big eaters | host metrics |
| RAM | llama.cpp peaks at ~8 GB; OOM kills the LLM | host metrics |
| Notification queue | Backlogged notifications = something automated is broken | `notifications` count where `read=false` |

## Health endpoint

```bash
curl http://localhost:8000/api/health
{
  "status": "ok",
  "version": "0.4.0",
  "db": true,
  "llm": true,
  "model": "gemma-4-E2B-it",
  "checks": []
}
```

Returns 200 for process-level health. If the DB metadata query fails, the response is still JSON but `status` becomes `degraded` and `db` is `false`. LLM-down returns 200 with `llm: false` because most feature-store paths still work.

For a load-balancer probe, hit `GET /api/ready`. It returns 200 only when the feature-store database can answer a cheap metadata query:

```json
{"status":"ready","version":"0.4.0","db_backend":"postgres","db":true}
```

## Logging

Default: application logs go to stdout/stderr and can be collected by Docker or your host logging agent.

```json
request method=GET path=/api/features status=200 duration_ms=12.34 request_id=...
```

Ship to your stack of choice — Loki / OpenSearch / Datadog / CloudWatch — via the Docker logging driver:

```yaml
# docker-compose.override.yml
services:
  featcat:
    logging:
      driver: gelf
      options:
        gelf-address: udp://logs.internal:12201
```

Useful filters:

- `level=warn or level=error` — what's broken
- `path=/api/ai/chat` — agent activity
- `duration_ms > 500` — slow requests
- `logger=featcat.scheduler` — scheduler firings

## Slow queries

PostgreSQL: enable `pg_stat_statements`:

```sql
CREATE EXTENSION pg_stat_statements;

-- Top 10 slowest by mean
SELECT round(mean_exec_time::numeric, 2) AS mean_ms,
       calls, query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC LIMIT 10;
```

In application logs, every request logs `duration_ms`. Tail with:

```bash
docker compose logs featcat | jq 'select(.duration_ms > 500)'
```

Common culprits:

- pgvector similarity without `ef_search` tuning → bump `SET LOCAL ef_search = 100`
- Catalog list with no filter → make sure the index covers the sort key
- Doc generation in a request path → it shouldn't be; offload to Celery

## Scheduler health

`job_logs` table records every scheduled job firing:

```sql
SELECT job_name,
       count(*) FILTER (WHERE status = 'success') AS ok,
       count(*) FILTER (WHERE status = 'error') AS err,
       max(finished_at) AS last_run
FROM job_logs
WHERE started_at > now() - interval '24 hours'
GROUP BY job_name
ORDER BY last_run DESC;
```

API:

```bash
curl http://localhost:8000/api/scheduler/jobs
# Returns each job's next-fire time and last status
```

Alert if `monitor_check` hasn't fired in > 12 hours. Alert if its error count > 0 over 24h.

## Metrics (Prometheus)

A Prometheus exporter is on the roadmap (T-future). Until it lands, scrape these endpoints periodically and parse:

- `GET /api/health/stats/counts` — total features, sources, groups, drift counts
- `GET /api/health/stats/doc-debt` — doc coverage %
- `GET /api/scheduler/jobs` — last-run timestamps

All return JSON; convert to Prom format with a small script.

## LLM monitoring

llama.cpp exposes `/v1/models` (just confirms the model is loaded) and `/health` (200 OK when ready). For latency / token-throughput:

```bash
docker compose logs llm | grep "tokens"
# llama_perf_context_print: prompt eval time = ... ms / NN tokens
# llama_perf_context_print: eval time = ... ms / NN tokens
```

These print after every completion. For load monitoring, instrument at the app side: featcat logs `llm_call_duration_ms` for every plugin/agent call.

## Alerting recipes

| Alert | Trigger | Why it matters |
|---|---|---|
| `featcat-api-down` | `/api/ready` 5xx for > 2 min | Feature store unreachable |
| `featcat-db-slow` | p99 request `duration_ms > 1000` over 5 min | UX degraded |
| `featcat-llm-down` | `/api/health` `llm=false` for > 5 min | Doc gen + chat broken |
| `featcat-scheduler-stale` | `monitor_check` last_run > 12 h ago | Drift detection silent |
| `featcat-disk-low` | host `/var/lib/docker` > 85 % full | Postgres at risk |
| `featcat-high-error-rate` | `level=error` count > 50/min | Something cascading |

## Audit trail

Status changes (`features.status`) are logged in `feature_versions` with `changed_by` and `notes`. Useful for "who certified `churn_v2.feature_X` and when?"

Source scans, dataset builds, materialization runs, feature versions, and access requests have dedicated audit tables. Source metadata changes should be tracked through the feature-store API and database backups until a separate source-change audit table is added.

## Related

- **[Architecture Overview](../architecture/overview.md)** — what the moving parts are
- **[Deployment](deployment.md)** — production setup
- **[Backup](backup.md)** — when monitoring tells you something's wrong
- **[Troubleshooting](troubleshooting.md)** — common failure modes
