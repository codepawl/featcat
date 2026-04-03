# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/codepawl/featcat/releases/tag/v0.1.0
