# Hướng dẫn Admin cho featcat

## Cấu hình S3 / MinIO

featcat hỗ trợ đọc Parquet trực tiếp từ S3 hoặc MinIO (S3-compatible).

### AWS S3

```bash
export FEATCAT_S3_ACCESS_KEY=AKIA...
export FEATCAT_S3_SECRET_KEY=...
export FEATCAT_S3_REGION=ap-southeast-1

featcat source add s3_data s3://my-bucket/features/data.parquet
featcat source scan s3_data
```

### MinIO (self-hosted)

```bash
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
export FEATCAT_S3_ACCESS_KEY=minioadmin
export FEATCAT_S3_SECRET_KEY=minioadmin

featcat source add minio_data s3://data-lake/features/data.parquet
featcat source scan minio_data
```

> **Lưu ý**: featcat chỉ đọc metadata và sample (10k rows đầu). Không bao giờ copy toàn bộ data.

## Thay đổi LLM model

### Dùng model khác trên Ollama

```bash
# Pull model mới
ollama pull llama3.1:8b

# Cấu hình featcat
export FEATCAT_LLM_MODEL=llama3.1:8b

# Kiểm tra
featcat doctor
```

### Dùng llama.cpp server

```bash
# Khởi động llama.cpp server
./server -m model.gguf --host 0.0.0.0 --port 8080

# Cấu hình featcat
export FEATCAT_LLM_BACKEND=llamacpp
export FEATCAT_LLAMACPP_URL=http://localhost:8080
```

### Khuyến nghị model

| Model | RAM | Tốc độ | Chất lượng |
|-------|-----|--------|------------|
| `qwen2.5:3b` | 4GB | Nhanh | Tạm ổn |
| `qwen2.5:7b` | 8GB | Trung bình | Tốt |
| `llama3.1:8b` | 8GB | Trung bình | Tốt |
| `qwen2.5:14b` | 16GB | Chậm | Rất tốt |

## Backup và restore

### Backup

```bash
# Chỉ cần copy file catalog.db
cp catalog.db catalog.db.backup.$(date +%Y%m%d)

# Hoặc dùng SQLite backup
sqlite3 catalog.db ".backup 'catalog_backup.db'"
```

### Restore

```bash
cp catalog_backup.db catalog.db
```

### Xuất data trước khi backup

```bash
# Xuất JSON
featcat export --format json --output backup/features.json

# Xuất Markdown docs
featcat doc export --output backup/features.md

# Xuất monitoring report
featcat monitor report --output backup/monitoring.md
```

## Troubleshooting

### Ollama không kết nối được

```
[red]LLM unavailable.[/red] Ensure Ollama is running: ollama serve
```

**Nguyên nhân**: Ollama chưa khởi động hoặc đang chạy trên port khác.

**Cách xử lý**:
```bash
# Kiểm tra Ollama đang chạy?
curl http://localhost:11434/api/tags

# Nếu không, khởi động
ollama serve

# Nếu port khác
export FEATCAT_OLLAMA_URL=http://localhost:12345

# Kiểm tra toàn bộ
featcat doctor
```

### LLM trả lời chậm

**Nguyên nhân**: Model quá lớn, hoặc máy không đủ RAM.

**Cách xử lý**:
- Dùng model nhỏ hơn: `export FEATCAT_LLM_MODEL=qwen2.5:3b`
- Tăng timeout: `export FEATCAT_LLM_TIMEOUT=300`
- Giảm số features gửi cho LLM: `export FEATCAT_MAX_CONTEXT_FEATURES=50`
- Sử dụng cache (mặc định bật, chỉ cần chạy lại cùng query)

### Feature không tìm thấy

```
[red]Feature not found:[/red] cpu_usage
```

**Cách xử lý**: Feature name bao gồm cả source name prefix:
```bash
# Sai
featcat feature info cpu_usage

# Đúng
featcat feature info device_perf.cpu_usage

# Tìm nếu không nhớ tên chính xác
featcat feature search cpu
```

### S3 permission denied

```
botocore.exceptions.ClientError: Access Denied
```

**Cách xử lý**:
```bash
# Kiểm tra credentials
echo $FEATCAT_S3_ACCESS_KEY

# Test trực tiếp với aws cli
aws s3 ls s3://bucket/path/ --endpoint-url $FEATCAT_S3_ENDPOINT_URL

# Với MinIO, đảm bảo endpoint URL đúng
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
```

### Database bị lỗi

```bash
# Kiểm tra integrity
sqlite3 catalog.db "PRAGMA integrity_check"

# Nếu bị lỗi, restore từ backup
cp catalog.db.backup catalog.db

# Hoặc khởi tạo lại và re-import
featcat init
python scripts/import_initial.py
```

## Monitoring tự động (cron)

```bash
# Chạy quality check mỗi 6 tiếng
echo "0 */6 * * * cd /path/to/project && .venv/bin/featcat monitor check --refresh-baseline >> /var/log/featcat-monitor.log 2>&1" | crontab -
```
