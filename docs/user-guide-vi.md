# Hướng dẫn sử dụng featcat

[English](user-guide.md)

## CLI Reference

### Quản lý data sources

```bash
# Đăng ký data source local
featcat source add <tên> <đường_dẫn>
featcat source add device_perf /data/features/device_performance.parquet

# Đăng ký data source S3
featcat source add user_logs s3://bucket/path/file.parquet

# Xem danh sách
featcat source list

# Scan source -> tự động tạo features
featcat source scan device_perf
```

### Quản lý features

```bash
# Xem tất cả features
featcat feature list

# Lọc theo source
featcat feature list --source device_perf

# Xem chi tiết 1 feature
featcat feature info device_perf.cpu_usage

# Thêm tags
featcat feature tag device_perf.cpu_usage performance infra

# Tìm kiếm (keyword)
featcat feature search "cpu"
```

### AI Discovery

```bash
# Gợi ý features cho use case
featcat discover "churn prediction cho khách hàng telecom"

# Tiếng Việt cũng được
featcat discover "dự đoán khách hàng rời mạng dựa trên hành vi sử dụng"
```

Output gồm:
1. **Existing Features** — features hiện có phù hợp, xếp hạng theo relevance
2. **New Feature Suggestions** — features mới nên tạo từ data hiện có
3. **Strategy Summary** — tóm tắt chiến lược feature engineering

### AI Documentation

```bash
# Generate doc cho 1 feature
featcat doc generate device_perf.cpu_usage

# Generate doc cho tất cả features chưa có doc
featcat doc generate

# Xem doc
featcat doc show device_perf.cpu_usage

# Xuất ra Markdown
featcat doc export
featcat doc export --output docs/my_features.md

# Xem thống kê doc coverage
featcat doc stats
```

### Natural Language Query

```bash
# Hỏi bằng tiếng Anh
featcat ask "features related to user behavior in the last 30 days"

# Hỏi bằng tiếng Việt
featcat ask "các feature liên quan đến hành vi người dùng"

# Khi không có Ollama, tự động dùng fuzzy search
```

### Quality Monitoring

```bash
# Tạo baseline (chạy 1 lần đầu)
featcat monitor baseline

# Kiểm tra drift
featcat monitor check

# Kiểm tra 1 feature cụ thể
featcat monitor check device_perf.cpu_usage

# Kiểm tra với LLM analysis
featcat monitor check --llm

# Kiểm tra + cập nhật baseline
featcat monitor check --refresh-baseline

# Xuất report
featcat monitor report
```

### System Health

```bash
# Kiểm tra toàn bộ hệ thống
featcat doctor

# Xem thống kê tổng quát
featcat stats

# Xuất data
featcat export --format json     # JSON
featcat export --format csv      # CSV
featcat export --format markdown  # Markdown
```

### TUI (Terminal UI)

```bash
featcat ui
```

#### Dashboard (phím D)
- Tổng quan: số features, sources, doc coverage, alerts
- Recent alerts từ monitoring
- Quick actions

#### Feature Browser (phím F)
- Bảng features bên trái (70%) — sắp xếp, lọc theo keyword
- Chi tiết feature bên phải (30%) — stats, docs, tags
- Gõ search ở trên để lọc real-time
- Phím `/` để focus search

#### Monitoring (phím M)
- Bảng kết quả quality check với severity colors
- Summary bar: healthy/warning/critical
- Phím `R` để run check, `B` để compute baseline

#### AI Chat (phím C)
- Hỏi-đáp tự nhiên về features
- Commands đặc biệt: `/discover <use case>`, `/search <query>`, `/monitor`
- Streaming response từ LLM

## Workflow ví dụ

### 1. Bắt đầu project mới

```bash
# Tìm features phù hợp cho bài toán
featcat discover "dự đoán khách hàng ngừng sử dụng dịch vụ internet"

# Xem chi tiết các features được gợi ý
featcat feature info user_behavior_30d.session_count
featcat feature info user_behavior_30d.complaint_count

# Đọc documentation
featcat doc show user_behavior_30d.session_count
```

### 2. Thêm data source mới

```bash
# Đăng ký source
featcat source add payment_history /data/features/payment_history.parquet

# Scan
featcat source scan payment_history

# Generate docs
featcat doc generate

# Tag features
featcat feature tag payment_history.late_payment_count billing churn
featcat feature tag payment_history.avg_payment_amount billing revenue
```

### 3. Kiểm tra chất lượng data hàng tuần

```bash
# Chạy quality check
featcat monitor check --llm

# Xuất report
featcat monitor report --output docs/weekly_report.md

# Nếu có vấn đề, xem chi tiết
featcat feature info device_perf.cpu_usage
featcat monitor check device_perf.cpu_usage --llm
```

## Mẹo và thủ thuật

- **Cache**: Auto-doc và NL query được cache. Dùng `--no-cache` để bypass
- **Offline mode**: Khi không có Ollama, `featcat ask` tự động dùng fuzzy search
- **Shell completion**: `featcat --install-completion bash` (hoặc zsh/fish)
- **Export nhanh**: `featcat export --format json > features.json`
- **Backup**: Chỉ cần copy file `catalog.db` là đủ
