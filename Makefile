.PHONY: install lint format type-check test test-cov build clean distclean check release-check docs docs-check docs-serve docs-clean bench docker-version docker-build docker-push

DOCKER_IMAGE ?= nxank4/featcat
VERSION := $(shell grep '^__version__' featcat/__init__.py | cut -d'"' -f2)

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
	rm -rf dist/ build/ *.egg-info htmlcov .coverage coverage.xml
	rm -rf .pytest_cache .mypy_cache .ruff_cache test-results site
	rm -rf packages/client/.venv packages/client/.pytest_cache packages/client/.mypy_cache packages/client/.ruff_cache
	rm -f packages/client/uv.lock
	rm -rf web/playwright-report web/test-results web/tests/e2e/.tmp featcat/server/static
	find featcat tests packages/client/src packages/client/tests -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -f catalog.db catalog.db-shm catalog.db-wal web/catalog.db web/catalog.db-shm web/catalog.db-wal
	rm -rf .openpawl .superpowers .claude/plan .claude/settings.local.json

distclean: clean
	rm -rf .venv web/node_modules deploy/models data-test

# T3.3 — MkDocs site. Install once with: uv pip install -e ".[docs]"
docs:
	uv run mkdocs build

docs-check:
	python3 scripts/check_docs_consistency.py

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

# Docker image build + push. Version flows from featcat/__init__.py so it
# stays in lockstep with the PyPI release (Hatch reads the same file).
docker-version:
	@echo $(VERSION)

docker-build:
	docker build \
	  --build-arg VERSION=$(VERSION) \
	  --build-arg HTTP_PROXY=$${HTTP_PROXY:-} \
	  --build-arg HTTPS_PROXY=$${HTTPS_PROXY:-} \
	  --tag $(DOCKER_IMAGE):$(VERSION) \
	  --tag $(DOCKER_IMAGE):latest \
	  --file deploy/Dockerfile .

docker-push: docker-build
	docker push $(DOCKER_IMAGE):$(VERSION)
	docker push $(DOCKER_IMAGE):latest
