# Contributing to featcat

## Development Setup

We use [uv](https://docs.astral.sh/uv/) for fast dependency management:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repo
git clone https://github.com/codepawl/featcat.git
cd featcat

# Create virtual environment
uv venv && source .venv/bin/activate

# Install with dev dependencies + pre-commit hooks
make install
```

## Running Tests

```bash
# Run all tests
make test

# Run with coverage report
make test-cov

# Run a specific test file
pytest tests/test_catalog.py -v
```

## Code Quality

```bash
# Lint (check only)
make lint

# Auto-format + auto-fix
make format

# Type checking
make type-check

# Run all checks (lint + type-check + test)
make check
```

## PR Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run checks: `make check`
5. Commit with a descriptive message (see convention below)
6. Push and open a Pull Request
7. Wait for CI to pass and a review

## Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add S3 support for MinIO endpoints
fix: handle null stats in monitoring PSI computation
docs: update admin guide with S3 troubleshooting
chore: bump pyarrow to 16.0
refactor: simplify JSON extraction in LLM base
test: add integration tests for autodoc batch mode
```

## Code Style

- **Formatter/Linter**: ruff (enforced via pre-commit and CI)
- **Type hints**: Required for all public functions
- **Line length**: 120 characters
- **Docstrings**: Required for modules and public classes/functions
- **Imports**: Sorted by ruff (isort-compatible)

## Project Structure

```
featcat/
├── catalog/    # Data models, SQLite DB, Parquet scanner, storage backends
├── llm/        # LLM abstraction layer (Ollama, llama.cpp, caching)
├── plugins/    # AI plugins (discovery, autodoc, monitoring, NL query)
├── utils/      # Prompts, catalog context formatters, statistics, cache
├── tui/        # Terminal UI (Textual screens and widgets)
├── config.py   # Pydantic settings
└── cli.py      # Typer CLI entry point
```

## Releasing

1. Update version in `featcat/__init__.py`
2. Update `CHANGELOG.md`
3. Commit: `git commit -am "release: v0.x.0"`
4. Push to main — a draft GitHub Release is auto-created
5. Review the draft, click "Publish"
6. The publish workflow handles TestPyPI verification and PyPI upload
