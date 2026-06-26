# featcat

![CI](https://github.com/codepawl/featcat/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/featcat)
![Python](https://img.shields.io/pypi/pyversions/featcat)
![License](https://img.shields.io/pypi/l/featcat)

**Feature Store tích hợp AI cho các team Data Science**

[English](index.md)

featcat là một Feature Store nhẹ, được thiết kế cho các team Data Science. Công cụ này kết hợp registry, quét nguồn offline, build training dataset, audit materialization, online serving, và AI layer để tìm kiếm, document, giám sát chất lượng, và theo dõi lineage của features.

## Vấn đề cần giải quyết

- **Features nằm rải rác**: Parquet files lưu ở nhiều nơi (local, S3, MinIO), không ai biết có những features gì
- **Thiếu documentation**: Columns trong dataset không có mô tả, người mới không biết `avg_session_duration` là gì
- **Khó tìm feature phù hợp**: Khi bắt đầu project mới (vd: churn prediction), không biết nên dùng features nào từ catalog hiện có
- **Không phát hiện data drift**: Features thay đổi phân phối mà không ai hay biết cho đến khi model suy giảm

## Tính năng chính

| Module | Mô tả | Phase |
|--------|-------|-------|
| **Feature Store** | Đăng ký data sources, scan Parquet auto-extract schema + stats | 1 |
| **AI Discovery** | Mô tả use case → AI gợi ý features phù hợp + feature mới cần tạo | 2 |
| **Auto-doc** | LLM tự động generate documentation cho từng feature | 2 |
| **NL Query** | Hỏi bằng tiếng Việt/Anh, AI tìm features liên quan | 2 |
| **Monitoring** | PSI drift detection, null spikes, range violations | 3 |
| **Materialization** | Ghi audit materialization và phục vụ giá trị online mới nhất | 3 |
| **TUI** | Terminal UI với dashboard, feature browser, AI chat | 3 |
| **S3 Support** | Đọc Parquet trực tiếp từ S3/MinIO, không cần copy data về local | 1 |
| **Caching** | Cache LLM responses, tăng tốc doc generate và NL query | 3 |

## Bắt đầu nhanh

```bash
# 1. Clone và cài đặt
git clone https://github.com/codepawl/featcat.git && cd featcat
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Khởi tạo catalog
featcat init

# 3. Đăng ký và scan data source
featcat source add device_perf /data/features/device_performance.parquet
featcat source scan device_perf

# 4. Xem features
featcat feature list
featcat feature info device_perf.cpu_usage

# 5. (Tuỳ chọn) Bật AI features — cần llama.cpp server
export FEATCAT_LLAMACPP_URL=http://localhost:8080
featcat discover "churn prediction cho khách hàng"
featcat ask "features liên quan đến behavior người dùng"
```

## Tài liệu

- [Hướng dẫn cài đặt](setup-vi.md)
- [Hướng dẫn sử dụng](user-guide-vi.md)
- [Hướng dẫn Admin](admin-guide-vi.md)

## License

MIT
