# Tech Stack

Adopted by the user. Substituting a listed choice requires the user's approval. Versions are the current stable release at implementation time; the lead records exact versions in the lockfiles, not here.

## Backend

| Choice | Status | Why |
| --- | --- | --- |
| Python, FastAPI, Pydantic v2 | fixed | The user's daily stack. |
| SQLite | adopted | Two users, tens of rows a week, one file to back up. No database server to run or pay for. |
| SQLAlchemy 2.0 with separate Pydantic API schemas | adopted | Keeps DB tables and API contracts distinct. SQLModel rejected: lags SQLAlchemy releases and blurs that line. |
| Alembic | adopted | Real bakes will exist before the schema is final. Every schema change ships a migration. |
| `uv` | adopted | Lockfile, fast, one tool for env and scripts. |
| ruff (lint and format), pyright strict | adopted | Enforce in `make check`; don't restate rules in prose. |
| pytest, httpx test client | adopted | Unit tests on the pure domain; a small set of API tests against a temporary SQLite file. |
| Signed session cookie, password from env | adopted | One shared password. No user table, no OAuth. |

## Frontend

| Choice | Status | Why |
| --- | --- | --- |
| Vite, React, TypeScript strict | fixed | The user's daily stack. |
| TanStack Query | adopted | Invalidation after posting a visit without hand-rolled state. |
| React Router | adopted | Four screens. TanStack Router rejected as more setup than four routes justify. |
| openapi-typescript (types generated from the FastAPI OpenAPI document) | adopted | Pydantic is the single type source. Hand-written API types are forbidden. Regeneration is a script in `package.json` and its output is committed so `make check` can fail on drift. |
| Tailwind CSS with shadcn/ui components | adopted | Copy-in components, mobile-first, no runtime UI library. Mantine was the alternative. |
| react-hook-form with zod | adopted | Visit and bake forms are lists of number inputs; recipe, ingredient, location, and login forms mix text, date, and password fields. zod validates every form boundary. |
| Biome (lint and format) | adopted | One tool. ESLint and Prettier rejected for a solo project. |
| vitest | adopted | For the little pure frontend logic that exists. No component-test scaffolding. |
| Playwright | adopted | Exactly one smoke test: log in, load home. Run by `make e2e`. |

## Shipping

| Choice | Status | Why |
| --- | --- | --- |
| One container: FastAPI serves the built Vite bundle as static files | adopted | No CORS, one deploy artifact. |
| Docker Compose with a persistent volume for the SQLite file | adopted | Runs identically on a laptop and the host. |
| Caddy for TLS on a VPS, or an AWS Lightsail instance (a VM running Docker Compose with an attached block disk) | open gate | User has not chosen between the two VM options. Lightsail Container Service and App Runner are both rejected: neither offers a persistent disk for SQLite. |
| Nightly `sqlite3 "$DB" ".backup '$DEST'"` then copy `$DEST` to object storage, by cron | adopted | One line of shell. Documented in deployment notes. |
| GitHub Actions running `make check` and `make e2e` on every PR | adopted | Repository is `cblack34/inventory` on GitHub. |
| `Makefile` as the single definition of verification commands | adopted | `AGENTS.md` and `acceptance.md` reference only `make check` and `make e2e`. |

## Dependency policy

Runtime dependencies are the rows above. Adding another requires the user's approval. Dev-only tooling that directly supports an adopted row (a Biome plugin, a pytest plugin) is at the lead's discretion. Prefer the standard library and existing dependencies; a few lines of code beat a new package.
