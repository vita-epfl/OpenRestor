.PHONY: install lint format test docs docs-serve clean

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
	uv run zensical build

docs-serve:
	uv run zensical serve

clean:
	rm -rf code-docs/site/ dist .mypy_cache .ruff_cache .pytest_cache