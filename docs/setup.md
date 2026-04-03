# Hướng dẫn cài đặt featcat

## Yêu cầu hệ thống

| Thành phần | Yêu cầu | Bắt buộc? |
|------------|---------|-----------|
| Python | >= 3.10 | Có |
| Ollama | >= 0.1.0 | Không (chỉ cần cho AI features) |
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
uv pip install -e ".[dev,tui,search,s3]"
```

Các extras:
- `dev` - pytest, test tools
- `tui` - Textual terminal UI
- `search` - rapidfuzz cho fuzzy search (fallback khi không có LLM)
- `s3` - s3fs để đọc Parquet từ S3/MinIO

## Bước 3: Cài đặt Ollama (optional nhưng khuyến nghị)

Ollama là local LLM server. Cài đặt để dùng AI Discovery, Auto-doc, và NL Query.

```bash
# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Khởi động Ollama
ollama serve

# Pull model (cửa sổ terminal khác)
ollama pull qwen2.5:7b
```

> **Tip**: Model `qwen2.5:7b` chạy tốt trên máy 8GB RAM. Nếu máy yếu hơn, thử `qwen2.5:3b`.

### Tự động khởi động Ollama (systemd)

```bash
# Tạo systemd service
sudo tee /etc/systemd/system/ollama.service << 'EOF'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
ExecStart=/usr/local/bin/ollama serve
Restart=always
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ollama
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
| `FEATCAT_LLM_BACKEND` | `ollama` | Backend LLM: `ollama` hoặc `llamacpp` |
| `FEATCAT_LLM_MODEL` | `qwen2.5:7b` | Model name |
| `FEATCAT_OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `FEATCAT_CATALOG_DB_PATH` | `catalog.db` | Đường dẫn database |
| `FEATCAT_MAX_CONTEXT_FEATURES` | `100` | Số features tối đa gửi cho LLM |
| `FEATCAT_LLM_TIMEOUT` | `120` | Timeout (giây) cho LLM request |
| `FEATCAT_S3_ENDPOINT_URL` | *(none)* | S3/MinIO endpoint |
| `FEATCAT_S3_ACCESS_KEY` | *(none)* | S3 access key |
| `FEATCAT_S3_SECRET_KEY` | *(none)* | S3 secret key |
| `FEATCAT_S3_REGION` | `us-east-1` | S3 region |

Ví dụ file `.env`:
```bash
FEATCAT_LLM_MODEL=qwen2.5:7b
FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
FEATCAT_S3_ACCESS_KEY=minioadmin
FEATCAT_S3_SECRET_KEY=minioadmin
```
