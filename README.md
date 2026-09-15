# inventory

Recipe costing, batch tracking, and per-visit profit for a small cottage-law snack business.

Agents and contributors: start at [AGENTS.md](AGENTS.md), then [docs/build-brief.md](docs/build-brief.md).

## Layout

- `src/inventory/` — Python package: domain rules, persistence, FastAPI app. Managed by `uv` from the root `pyproject.toml`.
- `src/web/` — Vite + React + TypeScript frontend, its own npm project.
- `tests/` — Python tests.
- `docs/` — the build pack; `docs/implementation/slices/` holds per-slice plans.

## Checks

`make check` runs every lint, type, test, and build stage for both halves. It is the only place those commands are defined and CI runs it on every pull request.

`make e2e` builds the frontend, migrates a scratch SQLite file, starts the API on port 8000, and runs the one Playwright smoke test (log in, home renders). CI runs it after `make check`. It fails if port 8000 is already in use by another process, such as a local dev server started per the section below.

## Local development

In one terminal, migrate and run the API (it stays in the foreground):

```bash
export DB=/tmp/inv-dev.db SHARED_PASSWORD=pw SESSION_SECRET=00000000000000000000000000000000 TIMEZONE=UTC INSECURE_COOKIES=true
uv run alembic upgrade head
uv run python -m inventory
```

In a second terminal, run the frontend, which proxies `/api` to it:

```bash
npm run dev --prefix src/web
```

## Running it in Docker

`docker compose up --build` builds one image and runs the app the way it
runs in deployment. See [docs/deployment.md](docs/deployment.md) for
configuration, the backup command, and secret rotation.
