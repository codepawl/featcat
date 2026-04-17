# Admin Guide

[Tiếng Việt](admin-guide-vi.md)

## Configuring S3 / MinIO

featcat supports reading Parquet directly from S3 or MinIO (S3-compatible).

### AWS S3

```bash
export FEATCAT_S3_ACCESS_KEY=AKIA...
export FEATCAT_S3_SECRET_KEY=...
export FEATCAT_S3_REGION=ap-southeast-1

featcat source add s3_data s3://my-bucket/features/data.parquet
featcat source scan s3_data
```

### MinIO (Self-Hosted)

```bash
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
export FEATCAT_S3_ACCESS_KEY=minioadmin
export FEATCAT_S3_SECRET_KEY=minioadmin

featcat source add minio_data s3://data-lake/features/data.parquet
featcat source scan minio_data
```

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
| `qwen2.5:14b` | 16GB | Slow | Excellent |

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
botocore.exceptions.ClientError: Access Denied
```

**Fix**:
```bash
# Check credentials
echo $FEATCAT_S3_ACCESS_KEY

# Test directly with aws cli
aws s3 ls s3://bucket/path/ --endpoint-url $FEATCAT_S3_ENDPOINT_URL

# For MinIO, make sure the endpoint URL is correct
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
```

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
