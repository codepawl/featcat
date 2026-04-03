.PHONY: install lint format type-check test test-cov build clean check release-check

install:
	pip install -e ".[dev,tui,s3]"
	pre-commit install

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

type-check:
	mypy featcat/

test:
	pytest

test-cov:
	pytest --cov=featcat --cov-report=html
	@echo "Open htmlcov/index.html to view coverage report"

build:
	python -m build

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml

check: lint type-check test

release-check: clean check build
	twine check dist/*
