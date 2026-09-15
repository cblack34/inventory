.PHONY: check check-python check-web check-types install install-web generate-types e2e

install:
	uv sync --locked

install-web:
	npm ci --prefix src/web

check: check-python check-web check-types

check-python: install
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright
	uv run pytest -q

check-web: install-web
	npm run --prefix src/web lint
	npm run --prefix src/web typecheck
	npm run --prefix src/web test
	npm run --prefix src/web build

# Verifies the committed types match a fresh regeneration, without mutating
# the tracked file (a hand edit or a schema change both show up as a diff).
check-types: install install-web
	tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	uv run python -m inventory.openapi > $$tmp/openapi.json && \
	npx --prefix src/web openapi-typescript $$tmp/openapi.json -o $$tmp/types.ts && \
	diff -u src/web/src/api/types.ts $$tmp/types.ts

# Regenerates the committed types in place, to fix drift check-types finds.
generate-types: install install-web
	tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	uv run python -m inventory.openapi > $$tmp/openapi.json && \
	npx --prefix src/web openapi-typescript $$tmp/openapi.json -o src/web/src/api/types.ts

# Builds the frontend, migrates a scratch SQLite file, then runs the one
# Playwright smoke test against a real server (Playwright's `webServer`
# starts `python -m inventory`, which never migrates on its own).
e2e: install install-web
	npm run --prefix src/web build
	npx --prefix src/web playwright install chromium
	tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	DB=$$tmp/e2e.db uv run alembic upgrade head && \
	DB=$$tmp/e2e.db SHARED_PASSWORD=e2e-password \
	SESSION_SECRET=00000000000000000000000000000000 \
	TIMEZONE=UTC INSECURE_COOKIES=true \
	npm run --prefix src/web test:e2e
