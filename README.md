# featcat

![CI](https://github.com/codepawl/featcat/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/featcat)
![Python](https://img.shields.io/pypi/pyversions/featcat)
![License](https://img.shields.io/pypi/l/featcat)

**AI-Powered Feature Catalog for Data Science Teams**

[Tiếng Việt](docs/README-vi.md)

featcat is a lightweight Feature Catalog designed for Data Science teams. It is **not** a Feature Store (no online serving) — it's a metadata management tool with an AI layer for searching, documenting, and monitoring feature quality.

## The Problem

- **Features scattered everywhere**: Parquet files stored across local disks, S3, and MinIO — nobody knows what features exist
- **Missing documentation**: Dataset columns have no descriptions; new team members don't know what `avg_session_duration` means
- **Hard to find the right features**: Starting a new project (e.g. churn prediction) with no idea which features are already available
- **Undetected data drift**: Feature distributions change silently until model performance degrades

## Key Features

| Module | Description | Phase |
|--------|-------------|-------|
| **Catalog** | Register data sources, scan Parquet to auto-extract schema + stats | 1 |
| **AI Discovery** | Describe a use case → AI recommends relevant features + suggests new ones | 2 |
| **Auto-doc** | LLM automatically generates documentation for each feature | 2 |
| **NL Query** | Ask in natural language (English or Vietnamese), AI finds relevant features | 2 |
| **Monitoring** | PSI drift detection, null spikes, range violations | 3 |
| **TUI** | Terminal UI with dashboard, feature browser, AI chat | 3 |
| **S3 Support** | Read Parquet directly from S3/MinIO — never copies data locally | 1 |
| **Caching** | Cache LLM responses to speed up doc generation and NL queries | 3 |

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/codepawl/featcat.git && cd featcat
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Initialize catalog
featcat init

# 3. Register and scan a data source
featcat source add device_perf /data/features/device_performance.parquet
featcat source scan device_perf

# 4. Browse features
featcat feature list
featcat feature info device_perf.cpu_usage

# 5. (Optional) Enable AI features — requires Ollama
ollama serve &
ollama pull lfm2.5-thinking
featcat discover "churn prediction for telecom customers"
featcat ask "features related to user behavior"
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
[x] Model lfm2.5-thinking available
[x] 14 features registered
[x] 10 features have docs (71.4%)
[ ] 2 features have drift warnings
```

## Tech Stack

- **Python 3.10+** | **SQLite** (metadata only, never copies data)
- **Typer** + **Rich** (CLI) | **Textual** (TUI)
- **PyArrow** (Parquet schema + stats) | **s3fs** (S3/MinIO)
- **Ollama** (local LLM) | **Pydantic** (models + config)

## Project Structure

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
