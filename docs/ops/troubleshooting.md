# Troubleshooting

Quick reference for the operational issues that have actually shown up. Symptoms → likely cause → fix.

## API won't start

### "Address already in use" on :8000

Another process owns the port. Common culprit: a previous `featcat serve` that didn't shut down cleanly.

```bash
ss -lntp | grep :8000
kill <pid>
docker compose restart featcat
```

### "Connection refused" to postgres on startup

Postgres container isn't ready when featcat tries to connect. Check:

```bash
docker compose logs postgres | tail -20
```

If postgres is fine but featcat is racing it, add a healthcheck-based dependency in `docker-compose.yml`:

```yaml
featcat:
  depends_on:
    postgres:
      condition: service_healthy
```

### "alembic.util.exc.CommandError: Multiple head revisions are present"

You have two divergent migration heads. Fix:

```bash
docker compose exec featcat alembic heads
# 25c2acba0f39 (head)
# 842a42f73f0f (head)
docker compose exec featcat alembic merge -m "merge T1.1 + T2.2" 25c2acba0f39 842a42f73f0f
docker compose exec featcat alembic upgrade head
```

Commit the new merge migration. This happens any time two stacked PRs each add a migration; convention is the second-to-merge PR adds the merge revision in its branch.

## LLM issues

### "llm: down" in /api/health

Check the container:

```bash
docker compose ps llm
docker compose logs llm | tail -30
```

Common causes:

- **Model not mounted**: `LLAMA_ARG_MODEL` points at a file that's not in the volume. Run `ls deploy/models/` to confirm the GGUF is there.
- **Cold start**: llama.cpp takes ~30s to load on first request. Just wait. Subsequent requests are fast.
- **OOM**: container was killed for exceeding memory limits. Check `docker compose logs llm --tail 5` for `OOMKilled`. Bump container memory or use a smaller quant.

### Doc gen returns `{}` for every feature

JSON parse failures. Re-run with verbose logging:

```bash
featcat doc generate user_behavior.session_count_30d --no-cache
```

Look for "JSON parse failed" in the output. If the model is consistently producing malformed output, the prompt template may be at fault for that model — try a different quant or model file.

### Chat agent loops on the same tool

The agent should detect duplicate `(tool_name, args)` calls and short-circuit, but a misformatted prompt can confuse it. Workaround: cap rounds.

```bash
FEATCAT_LLM_MAX_TOOL_ROUNDS=1 featcat serve
```

## Search returns nothing

### "Why does search return no results for a feature I can see in the list?"

Most common: the `search_tsv` generated column wasn't created. Happens if you upgraded code without running `alembic upgrade head`.

```bash
docker compose exec postgres psql -U featcat -c "\d features" | grep search_tsv
```

If absent, run alembic:

```bash
docker compose exec featcat alembic upgrade head
```

Then trigger a re-population (the column is `GENERATED ALWAYS`, so it'll fill itself, but a `VACUUM ANALYZE features` makes the index pick it up immediately).

### Search returns *only* exact name matches

You're on SQLite. SQLite's fallback is a token-scan over name + description + tags. It works but doesn't rank like postgres FTS. Either:

- Switch to PostgreSQL for production
- Live with it (token-scan is plenty for ≤ 1k features)

## Drift detection silent

### "monitor_check hasn't fired in 24 hours"

```bash
curl http://localhost:8000/api/scheduler/jobs | jq '.[] | select(.name == "monitor_check")'
```

Check `next_run_at`. If it's in the past:

- Scheduler is down. Restart: `docker compose restart featcat`.
- Cron expression is wrong. Reset: `featcat job schedule monitor_check "0 */6 * * *"`.

If `next_run_at` is in the future but jobs aren't logging, look at `job_logs`:

```sql
SELECT * FROM job_logs WHERE job_name='monitor_check' ORDER BY started_at DESC LIMIT 5;
```

`status='error'` rows include the exception. Fix the underlying issue (bad parquet path, dead source, etc.).

### "PSI is suddenly very high after a baseline refresh"

You set a new baseline against a non-representative window. Reset:

```bash
featcat monitor baseline
```

Drift on the next check should be near-zero.

## Performance

### Catalog list is slow

Look at the request log:

```bash
docker compose logs featcat | jq 'select(.path == "/api/features") | {duration_ms, query_string}'
```

p95 should be under 100ms for ≤ 10k features on PostgreSQL. If higher:

- Missing index: `EXPLAIN` the query in psql, look for `Seq Scan`. Add an index for the filter you're using.
- Postgres autovacuum hasn't run lately: `VACUUM ANALYZE features`.
- The `LIMIT/OFFSET` is deep (offset > 10000): switch to keyset pagination (cursor-based).

### Doc generation is too slow

Single-feature is ~5–15s on CPU. Batch of 100 is ~10–20 min. To speed up:

- Run a smaller model (`gemma-2B-Q4_K_M.gguf`) — trades quality for speed.
- Move to a GPU host: `LLAMA_ARG_NGL=99` offloads all layers to GPU.
- Run multiple llama.cpp instances behind a round-robin LB.

### Disk filling up

PostgreSQL `pg_xlog` / `pg_wal` growing without bound usually means archiving is misconfigured. Check `archive_command` runs successfully. If you're not using PITR, set `archive_mode=off`.

`monitoring_checks` grows ~6 rows / feature / day. Trim old rows monthly:

```sql
DELETE FROM monitoring_checks WHERE checked_at < now() - interval '180 days';
VACUUM FULL monitoring_checks;
```

## Web UI

### "Page reloads but state is empty / loading forever"

Open browser DevTools → Network. Look for `/api/*` requests:

- 5xx → server-side error, check `docker compose logs featcat`.
- CORS error → `FEATCAT_CORS_ORIGINS` doesn't include your front-end origin.
- 404 on `/api/*` → reverse proxy isn't forwarding the path. Verify the proxy config.

### "I see the old UI after deploying a new version"

Browser cache. Hard reload (Ctrl-Shift-R). The Vite build adds content hashes to bundle names, so this shouldn't normally happen — if it persists, set explicit `Cache-Control: no-cache` for `/index.html` at the proxy.

## Notifications

### "I'm not getting drift notifications"

```bash
featcat feature info <name>
```

If `null`, set an owner:

```bash
curl -X PATCH 'http://localhost:8000/api/features/by-name?name=<name>' \
    -H 'Content-Type: application/json' \
    -d '{"owner": "alice"}'
```

Notifications route to the feature's owner. No owner → goes to the `__catchall__` actor visible only on the dashboard.

## Where to ask

- Check `docker compose logs featcat -f` and `docker compose logs llm -f` first.
- Share the output (with secrets redacted) when asking for help.
- File at <https://github.com/codepawl/featcat/issues> with: featcat version (`featcat --version`), command run, full traceback or relevant log slice.

## Related

- **[Monitoring](monitoring.md)** — what to watch so you find issues early
- **[Backup](backup.md)** — recover from data loss
- **[Architecture Overview](../architecture/overview.md)** — to localize where a problem lives
