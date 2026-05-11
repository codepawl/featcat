# Hướng dẫn Admin cho featcat

[English](admin-guide.md)

## Cấu hình S3 / MinIO

featcat hỗ trợ đọc Parquet trực tiếp từ S3 hoặc MinIO (S3-compatible).
Cả bulk discovery (`featcat scan-bulk s3://bucket/prefix`) lẫn đăng ký
file đơn (`featcat add s3://bucket/file.parquet`) đều hoạt động end-to-end
với bất kỳ endpoint S3-compatible nào.

### AWS S3

```bash
export FEATCAT_S3_ACCESS_KEY=AKIA...
export FEATCAT_S3_SECRET_KEY=...
export FEATCAT_S3_REGION=ap-southeast-1
# Tuỳ chọn cho STS / role-assume:
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

### Bảng tham chiếu cấu hình

| Env var | Mặc định | Mục đích |
|---|---|---|
| `FEATCAT_S3_ENDPOINT_URL` | (không đặt = AWS) | Endpoint override cho MinIO hoặc S3-compatible khác. Tiền tố `http://` bật plain HTTP. |
| `FEATCAT_S3_ACCESS_KEY` | (không đặt) | Access key. **Phải đặt cùng với `FEATCAT_S3_SECRET_KEY` hoặc cùng để trống.** Cấu hình lệch raise lỗi khi khởi động. |
| `FEATCAT_S3_SECRET_KEY` | (không đặt) | Secret key. Xem quy tắc cặp ở trên. |
| `FEATCAT_S3_SESSION_TOKEN` | (không đặt) | STS session token (chỉ có ý nghĩa khi cả 2 key trên đã đặt). |
| `FEATCAT_S3_REGION` | `us-east-1` | AWS region; MinIO thường bỏ qua nhưng PyArrow vẫn yêu cầu giá trị. |
| `FEATCAT_S3_CONNECT_TIMEOUT_MS` | `10000` | Timeout TCP / TLS handshake (mili giây). |
| `FEATCAT_S3_REQUEST_TIMEOUT_MS` | `60000` | Timeout mỗi request (mili giây). |

### Thứ tự ưu tiên credential

Khi mở kết nối S3, credential được tra cứu theo thứ tự:

1. **`FEATCAT_S3_ACCESS_KEY` + `FEATCAT_S3_SECRET_KEY`** (+ `FEATCAT_S3_SESSION_TOKEN` tuỳ chọn). Đặt giá trị thì các nguồn khác bị bỏ qua. Settings validator yêu cầu cả 2 key cùng đặt — nếu chỉ đặt 1 thì ứng dụng từ chối khởi động với thông báo rõ ràng.
2. **AWS environment variables chuẩn** khi key của ta chưa đặt: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`. PyArrow default credential chain xử lý native.
3. **Profile `~/.aws/credentials`** — cũng qua default chain.
4. **IAM role / instance profile** khi chạy trên EC2 / ECS / EKS — cũng qua default chain.

> **Lưu ý**: featcat chỉ đọc metadata và sample (10k rows đầu). Không bao giờ copy toàn bộ data.

## Thay đổi LLM model

### Dùng llama.cpp server

```bash
# Khởi động llama.cpp server với model GGUF
./server -m model.gguf --host 0.0.0.0 --port 8080

# Cấu hình featcat
export FEATCAT_LLAMACPP_URL=http://localhost:8080
export FEATCAT_LLM_MODEL=gemma-4-E2B-it
```

### Khuyến nghị model

| Model | RAM | Tốc độ | Chất lượng |
|-------|-----|--------|------------|
| `gemma-4-E2B-it` | 4GB | Nhanh | Tốt (mặc định) |
| `llama3.1:8b` | 8GB | Trung bình | Tốt |

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

### LLM không kết nối được

```
[red]LLM unavailable.[/red] Ensure llama.cpp server is running.
```

**Nguyên nhân**: llama.cpp server chưa khởi động hoặc đang chạy trên port khác.

**Cách xử lý**:
```bash
# Kiểm tra llama.cpp đang chạy?
curl http://localhost:8080/health

# Nếu port khác
export FEATCAT_LLAMACPP_URL=http://localhost:12345

# Kiểm tra toàn bộ
featcat doctor
```

### LLM trả lời chậm

**Nguyên nhân**: Model quá lớn, hoặc máy không đủ RAM.

**Cách xử lý**:
- Thử model nhỏ hơn: `export FEATCAT_LLM_MODEL=gemma-4-E2B-it`
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
OSError: When opening / reading from S3: Access Denied
```

**Cách xử lý**:
```bash
# Kiểm tra credentials (cả 2 phải đặt cùng nhau; lệch sẽ raise khi khởi động)
echo $FEATCAT_S3_ACCESS_KEY
echo $FEATCAT_S3_SECRET_KEY

# Test trực tiếp với aws cli
aws s3 ls s3://bucket/path/ --endpoint-url $FEATCAT_S3_ENDPOINT_URL

# Với MinIO, đảm bảo endpoint URL đúng
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
```

### S3 prefix not found

```
S3 prefix not found: s3://bucket/typo
```

**Cách xử lý**: Kiểm tra prefix tồn tại bằng `aws s3 ls s3://bucket/typo/`. Lỗi này phát sinh từ `featcat scan-bulk` khi bucket có nhưng không có key nào khớp prefix.

### "FEATCAT_S3_ACCESS_KEY and FEATCAT_S3_SECRET_KEY must be set together"

App từ chối khởi động khi chỉ đặt 1 trong 2 key — trước đây trường hợp này âm thầm rơi về default credential chain, gây khó debug. Sửa bằng cách hoặc đặt cả 2 key, hoặc bỏ cả 2 để standard AWS credential chain (env vars / `~/.aws/credentials` / IAM role) xử lý.

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

## Chạy test với backend S3 thật

`make test` mặc định chạy suite MinIO-testcontainer (`@pytest.mark.s3`)
khi có Docker. Để xác nhận end-to-end với deployment target thật (AWS S3
hoặc MinIO nội bộ), opt-in vào suite `s3_real` — mặc định bị loại trừ qua
addopt `-m "not s3_real"`.

### Setup

1. Chọn bucket riêng cho integration test. Suite chỉ đọc, không bao giờ
   ghi; fixture do bạn upload trước.
2. Upload fixture nhỏ vào `${BUCKET}/featcat-fixtures/`:

```bash
# Trên máy bất kỳ có boto3 + pyarrow:
python <<PY
import io, boto3, pyarrow as pa, pyarrow.parquet as pq

ENDPOINT = "https://s3.amazonaws.com"   # hoặc URL MinIO của bạn
BUCKET   = "featcat-it"                  # bucket test của bạn

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id="...",
    aws_secret_access_key="...",
)
for key, data in [
    ("featcat-fixtures/sample.parquet", {"x": [1, 2, 3], "y": [0.1, 0.2, 0.3]}),
    ("featcat-fixtures/nested/leaf.parquet", {"k": ["a", "b"]}),
]:
    buf = io.BytesIO()
    pq.write_table(pa.table(data), buf); buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.read())
PY
```

3. Chạy suite:

```bash
FEATCAT_S3_TEST_ENDPOINT=https://s3.amazonaws.com \
FEATCAT_S3_TEST_ACCESS_KEY=AKIA... \
FEATCAT_S3_TEST_SECRET_KEY=... \
FEATCAT_S3_TEST_BUCKET=featcat-it \
    pytest -m s3_real -v
```

Khi chưa đặt env vars, `pytest -m s3_real` sẽ skip cleanly với thông báo
liệt kê các biến còn thiếu.

### Phạm vi cover

| Test | Mục đích |
|---|---|
| `test_real_s3_schema_read` | Đọc schema PyArrow từ `${BUCKET}/featcat-fixtures/sample.parquet` |
| `test_real_s3_discovery_recursive` | `discover_parquet_files` walk `${BUCKET}/featcat-fixtures/` và tìm thấy parquet |
| `test_real_s3_bad_credentials_raises` | Credentials sai surface ra `OSError` (không treo âm thầm) |
| `test_real_s3_unreachable_endpoint_times_out` | Endpoint sai tuân thủ `connect_timeout` (không treo vô hạn) |
