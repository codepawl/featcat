.PHONY: install test lint clean

install:
	uv pip install -e ".[dev]"

test:
	pytest tests/ -v

clean:
	rm -f catalog.db
	rm -rf __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
