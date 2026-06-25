# Hướng dẫn cài đặt featcat

[English](setup.md)

## Yêu cầu hệ thống

| Thành phần | Yêu cầu | Bắt buộc? |
|------------|---------|-----------|
| Python | >= 3.10 | Có |
| llama.cpp server | Docker image hoặc local binary | Không (chỉ cần cho AI features) |
| OS | Linux, macOS, WSL2 | Có |
| Disk | ~100MB cho model + DB | Có |

## Bước 1: Cài đặt Python environment

```bash
# Dùng uv (khuyến nghị)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Tạo virtual environment
cd featcat
uv venv
source .venv/bin/activate
```

## Bước 2: Cài đặt featcat

```bash
# Cài đặt cơ bản (chỉ catalog, không có AI)
uv pip install -e .

# Cài đặt đầy đủ với tất cả extras
uv pip install -e ".[dev,tui,server]"
```

Các extras:
- `dev` — pytest, test tools, MinIO testcontainer cho S3 tests
- `tui` — Textual terminal UI
- `server` — FastAPI + uvicorn cho REST API và Web UI

> Hỗ trợ S3 / MinIO đã có sẵn trong install mặc định (dùng PyArrow S3FileSystem
> tích hợp sẵn) — không cần extra riêng. Chỉ cần đặt biến môi trường `FEATCAT_S3_*`.

## Bước 3: Chạy llama.cpp (tuỳ chọn nhưng khuyến nghị)

featcat gọi llama.cpp-compatible HTTP server cho AI Discovery, Auto-doc, và NL Query. Script dev có thể khởi động server này:

```bash
./dev.sh
```

Hoặc tự chạy server rồi trỏ featcat tới endpoint đó:

```bash
export FEATCAT_LLAMACPP_URL=http://localhost:8080
export FEATCAT_LLM_MODEL=gemma-4-E2B-it
```

## Bước 4: Khởi tạo catalog

```bash
featcat init
# -> Tạo file catalog.db trong thư mục hiện tại
```

## Bước 5: Import data

```bash
# Đăng ký data source (local)
featcat source add device_perf /data/features/device_performance.parquet

# Đăng ký data source (S3/MinIO)
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
export FEATCAT_S3_ACCESS_KEY=minioadmin
export FEATCAT_S3_SECRET_KEY=minioadmin
featcat source add user_logs s3://data-lake/features/user_behavior_30d.parquet

# Scan để tự động tạo features
featcat source scan device_perf
featcat source scan user_logs
```

## Bước 6: Xác nhận

```bash
# Kiểm tra features đã đăng ký
featcat feature list

# Kiểm tra toàn bộ hệ thống
featcat doctor
```

## Cấu hình

featcat đọc cấu hình từ environment variables (prefix `FEATCAT_`):

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `FEATCAT_LLM_BACKEND` | `llamacpp` | Backend LLM |
| `FEATCAT_LLM_MODEL` | `gemma-4-E2B-it` | Model name |
| `FEATCAT_LLAMACPP_URL` | `http://localhost:8080` | llama.cpp server URL |
| `FEATCAT_CATALOG_DB_PATH` | `catalog.db` | Đường dẫn database |
| `FEATCAT_MAX_CONTEXT_FEATURES` | `100` | Số features tối đa gửi cho LLM |
| `FEATCAT_LLM_TIMEOUT` | `120` | Timeout (giây) cho LLM request |
| `FEATCAT_S3_ENDPOINT_URL` | *(none)* | S3/MinIO endpoint override (tiền tố `http://` cho plain HTTP) |
| `FEATCAT_S3_ACCESS_KEY` | *(none)* | S3 access key (phải đặt cùng `FEATCAT_S3_SECRET_KEY`) |
| `FEATCAT_S3_SECRET_KEY` | *(none)* | S3 secret key (phải đặt cùng `FEATCAT_S3_ACCESS_KEY`) |
| `FEATCAT_S3_SESSION_TOKEN` | *(none)* | STS session token (dùng kèm 2 key trên) |
| `FEATCAT_S3_REGION` | `us-east-1` | S3 region |
| `FEATCAT_S3_CONNECT_TIMEOUT_MS` | `10000` | S3 connection timeout (mili giây) |
| `FEATCAT_S3_REQUEST_TIMEOUT_MS` | `60000` | S3 request timeout (mili giây) |

Khi `FEATCAT_S3_ACCESS_KEY` / `_SECRET_KEY` chưa đặt, PyArrow default credential
chain sẽ dùng các biến chuẩn `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_SESSION_TOKEN`, profile `~/.aws/credentials`, hoặc IAM role
EC2/ECS/EKS. Xem admin guide cho thứ tự ưu tiên đầy đủ.

Ví dụ file `.env`:
```bash
FEATCAT_LLM_MODEL=gemma-4-E2B-it
FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
FEATCAT_S3_ACCESS_KEY=minioadmin
FEATCAT_S3_SECRET_KEY=minioadmin
```
