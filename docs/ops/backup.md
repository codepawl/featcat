# Backup and recovery

Two things to back up: the **database** (catalog metadata) and the **source files** (parquet inputs you registered with featcat). The source files are usually owned by another system; this page focuses on the catalog DB.

## What's actually stateful

| What | Where | Critical? |
|---|---|---|
| Catalog DB | PostgreSQL `pgdata` volume *or* SQLite `catalog.db` | Yes — features, docs, groups, baselines, monitoring history live here |
| Source parquets | Whatever you mounted to `/sources` | Should already be backed up by the upstream owner |
| LLM model | `deploy/models/*.gguf` | No — re-downloadable from HuggingFace |
| Built static UI | inside container | No — rebuilt from `web/` source |
| Logs | Wherever your driver ships them | Depends on your retention policy |

If you lose `pgdata` and have no backup, you can re-bootstrap by re-scanning sources (gets features back), but **lose all docs, baselines, monitoring history, group memberships, and certification status**. Always keep a backup.

## PostgreSQL backups

### Daily logical dump

```bash
# Save with timestamp, custom format, compressed
docker compose exec -T postgres pg_dump \
    -U featcat \
    -F custom \
    --no-owner --no-acl \
    featcat > /backups/featcat-$(date +%Y%m%d).dump
```

Schedule with cron + ship to off-host storage:

```cron
0 3 * * * docker compose -f /opt/featcat/deploy/docker-compose.yml exec -T postgres pg_dump -U featcat -F custom featcat | gzip | aws s3 cp - s3://my-backups/featcat/$(date +\%Y\%m\%d).dump.gz
```

### Restore

Empty the database first if it has any rows (pg_restore won't merge cleanly):

```bash
docker compose exec postgres dropdb -U featcat --if-exists featcat
docker compose exec postgres createdb -U featcat featcat
docker compose exec -T postgres pg_restore \
    -U featcat -d featcat --no-owner --no-acl \
    < /backups/featcat-20260507.dump
```

Then re-run alembic to verify the schema head matches the running code:

```bash
docker compose exec featcat alembic current
```

### Continuous backup (PITR)

For low-RPO requirements, configure PostgreSQL WAL archiving:

```conf
# postgresql.conf
archive_mode = on
archive_command = 'aws s3 cp %p s3://my-backups/featcat-wal/%f'
wal_level = replica
```

Combined with a base backup (`pg_basebackup`) every week, gives sub-minute RPO. Setup is more involved — only worth it for teams that can't afford to lose a day.

## SQLite backups

SQLite uses WAL by default (`PRAGMA journal_mode=WAL`). Don't just `cp catalog.db` while the API is running — you'll get an inconsistent snapshot.

The right way:

```bash
sqlite3 /path/to/catalog.db ".backup /path/to/catalog-$(date +%Y%m%d).db"
gzip /path/to/catalog-*.db
aws s3 cp /path/to/catalog-*.db.gz s3://my-backups/featcat/
```

`.backup` is atomic and safe to run while the API is serving requests.

Restore: stop the API, replace the `.db` file, start the API. If you copy in a `.db` without its `.db-wal` and `.db-shm` siblings, that's correct — the WAL is checkpointed into the main file.

## Backup verification

A backup that doesn't restore is no backup. Test restores quarterly:

```bash
# Stand up a scratch container
docker run --rm -v /backups:/backups pgvector/pgvector:pg16 bash -c '
    pg_restore -d "postgres://test:test@scratch:5432/test" \
        --no-owner --no-acl /backups/featcat-20260501.dump
    psql "postgres://test:test@scratch:5432/test" -c "SELECT count(*) FROM features"
'
```

Confirm the row count matches the production catalog at the time of the dump (`SELECT count(*) FROM features` should be in the right ballpark).

## Source file backups

featcat assumes source parquets are owned by their producers (your data platform / S3 bucket / SFTP drop). featcat stores only the *path*, not the file content. If a path moves:

1. Update the source: `featcat sources update user_behavior --path /new/path/to/file.parquet`
2. Re-scan: `featcat scan user_behavior` (preserves the existing feature rows; only updates stats)

Don't re-add the source — that creates a duplicate `data_sources` row.

## Disaster recovery runbook

**Scenario**: host disk dies. Spare host available. Backups in S3.

1. Provision a new Docker host with the same compose stack:
   ```bash
   git clone https://github.com/codepawl/featcat.git /opt/featcat
   cd /opt/featcat/deploy
   git checkout v1.4.0
   ```

2. Restore the postgres volume from backup:
   ```bash
   docker compose up -d postgres        # creates empty pgdata
   sleep 10
   docker compose exec postgres dropdb -U featcat --if-exists featcat
   docker compose exec postgres createdb -U featcat featcat
   aws s3 cp s3://my-backups/featcat/latest.dump - | \
       docker compose exec -T postgres pg_restore -U featcat -d featcat --no-owner --no-acl
   ```

3. Re-download the LLM model:
   ```bash
   ./dev.sh --download-model-only
   ```

4. Bring up the rest of the stack:
   ```bash
   docker compose up -d
   docker compose exec featcat alembic upgrade head
   curl http://localhost:8000/api/health
   ```

5. Verify the catalog is intact:
   ```bash
   docker compose exec featcat featcat features list --limit 5
   ```

Target RTO: < 30 min on prepared infrastructure. Do a tabletop run quarterly to keep this honest.

## Retention

Suggested retention schedule:

- Daily dumps: 14 days
- Weekly dumps: 8 weeks
- Monthly dumps: 12 months
- Yearly dumps: forever (or until you decommission featcat)

`tools/expire-backups.sh` (in the repo) implements this if you want to lift it.

## Related

- **[Deployment](deployment.md)** — what state lives where
- **[Architecture › Data Layer](../architecture/data.md)** — schema overview
- **[Monitoring](monitoring.md)** — detecting failures that should trigger restore
- **[Troubleshooting](troubleshooting.md)** — when restore goes wrong
