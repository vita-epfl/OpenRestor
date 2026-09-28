.PHONY: install lint format test docs clean

install:
	uv sync
	uv run lefthook install

lint:
	uv run ruff check openrestor
	uv run ruff format --check openrestor
	uv run mypy openrestor
	uv run codespell openrestor

format:
	uv run ruff format openrestor
	uv run ruff check --fix openrestor

test:
	uv run pytest tests -q

docs:
	uv run sphinx-build -b html code-docs code-docs/_build/html

clean:
	rm -rf code-docs/_build dist .mypy_cache .ruff_cache .pytest_cache
