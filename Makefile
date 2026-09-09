.PHONY: install lint format test docs clean

install:
	uv sync
	uv run lefthook install

lint:
	uv run ruff check openrestore
	uv run ruff format --check openrestore
	uv run mypy openrestore
	uv run codespell openrestore

format:
	uv run ruff format openrestore
	uv run ruff check --fix openrestore

test:
	uv run pytest tests/test_schemas.py -q

docs:
	uv run sphinx-build -b html code-docs code-docs/_build/html

clean:
	rm -rf code-docs/_build dist .mypy_cache .ruff_cache .pytest_cache
