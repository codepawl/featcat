# Triển khai featcat với Docker

## Yêu cầu

- Docker >= 20.10
- Docker Compose >= 2.0

## Cài đặt lần đầu

```bash
# Clone repo
git clone https://github.com/codepawl/featcat.git
cd featcat/deploy

# Tạo file cấu hình
cp .env.example .env

# Sửa DATA_DIR trong .env — trỏ đến thư mục chứa file Parquet
nano .env

# Chạy setup (pull model, start services)
bash setup.sh
```

## Truy cập

- **Web UI:** http://<server-ip>:8000
- **API:** http://<server-ip>:8000/api/health
- **CLI từ máy khác:**
  ```bash
  pip install featcat
  featcat config set server http://<server-ip>:8000
  featcat stats
  ```

## Import dữ liệu

```bash
# Copy file Parquet vào thư mục DATA_DIR, sau đó:
docker exec featcat-server featcat add /sources/your_file.parquet --owner <tên>

# Hoặc import nhiều file:
docker exec featcat-server featcat add /sources/ --name my-dataset --owner <tên>
```

## Các lệnh hữu ích

```bash
# Xem logs
docker compose logs -f featcat

# Restart server
docker compose restart featcat

# Dừng tất cả
docker compose down

# Khởi động lại
docker compose up -d

# Health check
docker exec featcat-server featcat doctor

# Xem thống kê catalog
docker exec featcat-server featcat stats

# Xem scheduled jobs
docker exec featcat-server featcat job list

# Chạy manual job
docker exec featcat-server featcat job run monitor_check
```

## Nâng cấp

```bash
cd featcat
git pull
cd deploy
docker compose build featcat
docker compose up -d
```

## Backup

```bash
# Backup catalog database
docker exec featcat-server cp /data/catalog.db /sources/backup/catalog-$(date +%Y%m%d).db

# Hoặc copy từ Docker volume
docker cp featcat-server:/data/catalog.db ./backup/
```

## Cấu hình

Sửa file `.env` và restart:

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `DATA_DIR` | Thư mục chứa file Parquet trên host | `./data` |
| `FEATCAT_PORT` | Port expose cho Web UI + API | `8000` |
| `LLM_MODEL` | Model LLM sử dụng | `lfm2.5:latest` |
| `SERVER_AUTH` | Token xác thực API (để trống = không cần auth) | _(trống)_ |

## Xử lý sự cố

**featcat không kết nối được Ollama:**
```bash
# Kiểm tra Ollama đang chạy
docker compose ps
docker compose logs ollama

# Restart Ollama
docker compose restart ollama
```

**Model chưa được pull:**
```bash
docker exec featcat-ollama ollama list
docker exec featcat-ollama ollama pull lfm2.5:latest
```

**Catalog database bị lỗi:**
```bash
# Xóa và init lại
docker exec featcat-server rm /data/catalog.db
docker compose restart featcat
```
