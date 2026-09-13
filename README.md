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
