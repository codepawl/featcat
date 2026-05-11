# Admin Guide

[Tiếng Việt](admin-guide-vi.md)

## Configuring S3 / MinIO

featcat supports reading Parquet directly from S3 or MinIO (S3-compatible).
Bulk discovery (`featcat scan-bulk s3://bucket/prefix`) and single-file
registration (`featcat add s3://bucket/file.parquet`) both work end-to-end
against any S3-compatible endpoint.

### AWS S3

```bash
export FEATCAT_S3_ACCESS_KEY=AKIA...
export FEATCAT_S3_SECRET_KEY=...
export FEATCAT_S3_REGION=ap-southeast-1
# Optional for STS / role-assume:
export FEATCAT_S3_SESSION_TOKEN=...

featcat add s3://my-bucket/features/data.parquet
featcat scan-bulk s3://my-bucket/features/ --recursive
```

### MinIO (Self-Hosted)

```bash
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
export FEATCAT_S3_ACCESS_KEY=minioadmin
export FEATCAT_S3_SECRET_KEY=minioadmin

featcat add s3://data-lake/features/data.parquet
featcat scan-bulk s3://data-lake/features/ --recursive
```

### Configuration reference

| Env var | Default | Purpose |
|---|---|---|
| `FEATCAT_S3_ENDPOINT_URL` | (unset = AWS) | Override for MinIO or other S3-compatible endpoints. `http://` triggers plain HTTP. |
| `FEATCAT_S3_ACCESS_KEY` | (unset) | Access key. **Must be set together with `FEATCAT_S3_SECRET_KEY` or both unset.** Partial config raises at startup. |
| `FEATCAT_S3_SECRET_KEY` | (unset) | Secret key. See pairing rule above. |
| `FEATCAT_S3_SESSION_TOKEN` | (unset) | STS session token (only meaningful with the two keys above set). |
| `FEATCAT_S3_REGION` | `us-east-1` | AWS region; MinIO usually ignores it but PyArrow requires a value. |
| `FEATCAT_S3_CONNECT_TIMEOUT_MS` | `10000` | TCP / TLS handshake timeout in milliseconds. |
| `FEATCAT_S3_REQUEST_TIMEOUT_MS` | `60000` | Per-request timeout in milliseconds. |

### Credential resolution order

When opening an S3 connection, credentials are looked up in this order:

1. **`FEATCAT_S3_ACCESS_KEY` + `FEATCAT_S3_SECRET_KEY`** (+ optional `FEATCAT_S3_SESSION_TOKEN`). These take precedence over anything else when set. The Settings validator requires both keys together — if only one is set the application refuses to start with a clear error message.
2. **Standard AWS environment variables** when our explicit keys are unset: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`. PyArrow's default credential chain handles these natively.
3. **`~/.aws/credentials` profiles** — also via PyArrow's default chain.
4. **IAM role / instance profile** when running on EC2 / ECS / EKS — also via the default chain.

> **Note**: featcat only reads metadata and a sample (first 10k rows). It never copies the full dataset.

## Changing the LLM Model

### Using llama.cpp Server

```bash
# Start llama.cpp server with a GGUF model
./server -m model.gguf --host 0.0.0.0 --port 8080

# Configure featcat
export FEATCAT_LLAMACPP_URL=http://localhost:8080
export FEATCAT_LLM_MODEL=gemma-4-E2B-it
```

### Recommended Models

| Model | RAM | Speed | Quality |
|-------|-----|-------|---------|
| `gemma-4-E2B-it` | 4GB | Fast | Good (default) |
| `llama3.1:8b` | 8GB | Medium | Good |

## Backup and Restore

### Backup

```bash
# Just copy catalog.db
cp catalog.db catalog.db.backup.$(date +%Y%m%d)

# Or use SQLite backup
sqlite3 catalog.db ".backup 'catalog_backup.db'"
```

### Restore

```bash
cp catalog_backup.db catalog.db
```

### Export Data Before Backup

```bash
# Export JSON
featcat export --format json --output backup/features.json

# Export Markdown docs
featcat doc export --output backup/features.md

# Export monitoring report
featcat monitor report --output backup/monitoring.md
```

## Troubleshooting

### LLM Connection Failed

```
[red]LLM unavailable.[/red] Ensure llama.cpp server is running.
```

**Cause**: llama.cpp server is not running or is on a different port.

**Fix**:
```bash
# Check if llama.cpp is running
curl http://localhost:8080/health

# If on a different port
export FEATCAT_LLAMACPP_URL=http://localhost:12345

# Verify everything
featcat doctor
```

### LLM Responds Slowly

**Cause**: Model too large, or insufficient RAM.

**Fix**:
- Try a smaller model: `export FEATCAT_LLM_MODEL=gemma-4-E2B-it`
- Increase timeout: `export FEATCAT_LLM_TIMEOUT=300`
- Reduce features sent to LLM: `export FEATCAT_MAX_CONTEXT_FEATURES=50`
- Use cache (enabled by default — just re-run the same query)

### Feature Not Found

```
[red]Feature not found:[/red] cpu_usage
```

**Fix**: Feature names include the source name as a prefix:
```bash
# Wrong
featcat feature info cpu_usage

# Correct
featcat feature info device_perf.cpu_usage

# Search if you don't remember the exact name
featcat feature search cpu
```

### S3 Permission Denied

```
OSError: When opening / reading from S3: Access Denied
```

**Fix**:
```bash
# Check credentials (both must be set together; partial config raises at startup)
echo $FEATCAT_S3_ACCESS_KEY
echo $FEATCAT_S3_SECRET_KEY

# Test directly with aws cli
aws s3 ls s3://bucket/path/ --endpoint-url $FEATCAT_S3_ENDPOINT_URL

# For MinIO, make sure the endpoint URL is correct
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
```

### S3 prefix not found

```
S3 prefix not found: s3://bucket/typo
```

**Fix**: Verify the prefix exists with `aws s3 ls s3://bucket/typo/`. The error fires from `featcat scan-bulk` when the bucket exists but no key matches.

### "FEATCAT_S3_ACCESS_KEY and FEATCAT_S3_SECRET_KEY must be set together"

The app refuses to start when one of the keys is set without the other — historically this silently fell back to the default credential chain, which made debugging painful. Fix by either setting both keys, or unsetting both so the standard AWS credential chain (env vars / `~/.aws/credentials` / IAM role) takes over.

### Database Corrupted

```bash
# Check integrity
sqlite3 catalog.db "PRAGMA integrity_check"

# If corrupted, restore from backup
cp catalog.db.backup catalog.db

# Or reinitialize and re-import
featcat init
python scripts/import_initial.py
```

## Automated Monitoring (cron)

```bash
# Run quality check every 6 hours
echo "0 */6 * * * cd /path/to/project && .venv/bin/featcat monitor check --refresh-baseline >> /var/log/featcat-monitor.log 2>&1" | crontab -
```
