# featcat

![CI](https://github.com/codepawl/featcat/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/featcat)
![Python](https://img.shields.io/pypi/pyversions/featcat)
![License](https://img.shields.io/pypi/l/featcat)

**AI-Powered Feature Catalog for Data Science Teams**

featcat là một Feature Catalog nhẹ, được thiết kế cho các team Data Science. Đây **không phải** là Feature Store (không có online serving) - mà là một công cụ quản lý metadata + AI layer để tìm kiếm, document, và giám sát chất lượng features.

## Vấn đề cần giải quyết

- **Features nằm rải rác**: Parquet files lưu ở nhiều nơi (local, S3, MinIO), không ai biết có những features gì
- **Thiếu documentation**: Columns trong dataset không có mô tả, người mới không biết `avg_session_duration` là gì
- **Khó tìm feature phù hợp**: Khi bắt đầu project mới (vd: churn prediction), không biết nên dùng features nào từ catalog hiện có
- **Không phát hiện data drift**: Features thay đổi phân phối mà không ai hay biết cho đến khi model suy giảm

## Tính năng chính

| Module | Mô tả | Phase |
|--------|-------|-------|
| **Catalog** | Đăng ký data sources, scan Parquet auto-extract schema + stats | 1 |
| **AI Discovery** | Mô tả use case -> AI gợi ý features phù hợp + feature mới cần tạo | 2 |
| **Auto-doc** | LLM tự động generate documentation cho từng feature | 2 |
| **NL Query** | Hỏi bằng tiếng Việt/Anh, AI tìm features liên quan | 2 |
| **Monitoring** | PSI drift detection, null spikes, range violations | 3 |
| **TUI** | Terminal UI với dashboard, feature browser, AI chat | 3 |
| **S3 Support** | Đọc Parquet trực tiếp từ S3/MinIO, không cần copy data về local | 1 |
| **Caching** | Cache LLM responses, tăng tốc doc generate và NL query | 3 |

## Quick Start

```bash
# 1. Clone và cài đặt
git clone <repo-url> && cd featcat
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

# 5. (Optional) Bật AI features - cần Ollama
ollama serve &
ollama pull qwen2.5:7b
featcat discover "churn prediction cho khách hàng"
featcat ask "features liên quan đến behavior người dùng"
```

## TUI (Terminal UI)

```bash
uv pip install -e ".[tui]"
featcat ui
```

<!-- Screenshot placeholder -->
<!-- ![featcat TUI](docs/assets/tui-screenshot.png) -->

Keybindings: `D` Dashboard | `F` Features | `M` Monitor | `C` Chat | `Q` Quit | `?` Help

## System Health Check

```bash
featcat doctor
```

```
[x] Python 3.10+
[x] SQLite catalog exists (catalog.db)
[x] Ollama running at localhost:11434
[x] Model qwen2.5:7b available
[x] 14 features registered
[x] 10 features have docs (71.4%)
[ ] 2 features have drift warnings
```

## Tech Stack

- **Python 3.10+** | **SQLite** (metadata only, không copy data)
- **Typer** + **Rich** (CLI) | **Textual** (TUI)
- **PyArrow** (Parquet schema + stats) | **s3fs** (S3/MinIO)
- **Ollama** (local LLM) | **Pydantic** (models + config)

## Cấu trúc project

```
featcat/
├── catalog/        # Models, DB, scanner, storage backends
├── llm/            # LLM abstraction (Ollama, llama.cpp)
├── plugins/        # Discovery, Autodoc, Monitoring, NL Query
├── utils/          # Prompts, catalog context, statistics, cache
├── tui/            # Textual TUI (screens, widgets)
├── config.py       # Pydantic settings
└── cli.py          # Typer CLI entry point
```

## License

MIT
