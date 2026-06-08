.PHONY: install lint format type-check test test-cov build clean check release-check docs docs-serve docs-clean bench

install:
	@if [ ! -d ".venv" ] && [ -z "$$VIRTUAL_ENV" ] && [ -z "$$CONDA_PREFIX" ]; then \
		echo "Creating virtual environment..."; \
		uv venv; \
	fi
	uv pip install -e ".[dev,tui,s3,server]"
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

type-check:
	uv run mypy featcat/

test:
	uv run pytest

test-cov:
	uv run pytest --cov=featcat --cov-report=html
	@echo "Open htmlcov/index.html to view coverage report"

build:
	uv run python -m build

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml

# T3.3 — MkDocs site. Install once with: uv pip install -e ".[docs]"
docs:
	uv run mkdocs build

docs-serve:
	uv run mkdocs serve --dev-addr 0.0.0.0:8001

docs-clean:
	rm -rf site/

check: lint type-check test

# Live-Postgres pgvector benches. See docs/contributing/benchmarks.md.
# Requires a running Postgres + pgvector at localhost:5432 (default URL
# below) and the ``[bench]`` extra installed (`uv pip install -e ".[bench]"`).
# Override FEATCAT_BENCH_DB_URL to point at a different bench DB.
bench:
	FEATCAT_BENCH_DB_URL=$${FEATCAT_BENCH_DB_URL:-postgresql+psycopg2://featcat:featcat@localhost:5432/featcat} \
	  uv run pytest tests/perf -m perf --bench -v --no-cov --timeout=600

release-check: clean check build
	uv run twine check dist/*
