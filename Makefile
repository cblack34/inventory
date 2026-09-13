.PHONY: check check-python install

install:
	uv sync --locked

# check-web is added by the web leaf slice; check depends on it once it exists.
check: check-python

check-python: install
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright
	uv run pytest -q
