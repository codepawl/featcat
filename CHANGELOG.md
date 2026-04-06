# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.2.0] - 2026-04-06

### Added

- **CatalogBackend Interface**: Abstract interface for local/remote catalog backends with factory pattern
- **`featcat add` Command**: One-step source registration + scan + auto-doc shortcut
- **Config Management**: YAML config file support (`featcat.yaml`, `~/.config/featcat/config.yaml`) with `featcat config show/set/get/reset/path` commands and layered priority (env > project > user > defaults)
- **Server Mode**: FastAPI server (`featcat serve`) with REST API for all catalog operations, RemoteBackend HTTP client, optional auth token, CORS support
- **Vietnamese Support**: Generalized bilingual support across all plugins via `localize_system_prompt()`, language detection in `utils/lang.py`
- **LFM 2.5 Optimizations**: JSON mode for Ollama, per-task LLM config (model/temperature), reduced prompt lengths, improved JSON extraction with array support
- **Job Scheduler**: APScheduler-based internal scheduler with 4 default jobs (monitor_check, doc_generate, source_scan, baseline_refresh), execution logging, retention policy, sparkline stats
- **Job API**: `/api/jobs` endpoints for listing, running, updating, and monitoring scheduled jobs
- **Job CLI**: `featcat job list/logs/run/enable/disable/schedule` commands
- **Web UI Dashboard**: 5-page vanilla HTML/JS/CSS dashboard served by FastAPI alongside the API
  - Dashboard: metric cards, drift alerts, job activity, sparkline visualization
  - Feature Browser: search, filter, sort, pagination, detail panel, add source modal
  - Monitoring: severity summary, drift table, Chart.js trend chart, baseline refresh, report export
  - Jobs: schedule cards with toggle/edit, execution history, stats chart
  - AI Chat: SSE streaming, shortcut buttons, discovery integration
- **Dark Mode**: CSS variables with `prefers-color-scheme` media query across all Web UI pages
- **Responsive Design**: Desktop, tablet, and mobile breakpoints for Web UI
- **SSE Streaming**: Server-Sent Events endpoint for real-time AI chat responses
- **LLM Benchmark Script**: `scripts/benchmark_llm.py` for measuring latency and JSON parse success rate

## [0.1.0] - 2026-04-03

### Added

- **Catalog**: Register data sources (local + S3/MinIO), scan Parquet files, auto-extract schema and statistics
- **AI Discovery**: Describe a use case, get ranked feature recommendations and new feature suggestions via LLM
- **Auto-doc**: LLM-powered documentation generation for features, with batch processing and Markdown export
- **NL Query**: Natural language search across the feature catalog, with Vietnamese language detection and fuzzy fallback
- **Quality Monitoring**: PSI drift detection, null spike alerts, range violation checks, zero variance detection
- **LLM Backends**: Ollama and llama.cpp server support with streaming, retry logic, and JSON extraction
- **Response Caching**: SQLite-backed LLM response cache with configurable TTL per plugin
- **TUI**: Terminal UI with dashboard, feature browser, monitoring view, and AI chat (Textual)
- **S3 Support**: Read Parquet metadata directly from AWS S3 and MinIO via PyArrow S3FileSystem
- **CLI Commands**: `init`, `source add/list/scan`, `feature list/info/tag/search`, `discover`, `ask`, `doc generate/show/export/stats`, `monitor baseline/check/report`, `doctor`, `stats`, `export`, `cache stats/clear`, `ui`
- **Configuration**: Pydantic settings loaded from `FEATCAT_*` environment variables
- **Documentation**: README, setup guide, user guide, and admin guide (Vietnamese with English technical terms)

[Unreleased]: https://github.com/codepawl/featcat/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/codepawl/featcat/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/codepawl/featcat/releases/tag/v0.1.0
