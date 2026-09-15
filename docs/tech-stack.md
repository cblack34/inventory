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
| pytest, `httpx2` test client | adopted | Unit tests on the pure domain; a small set of API tests against a temporary SQLite file. `httpx2` is the successor to `httpx`, started by httpx's author and now maintained under the Pydantic organization (BSD-3-Clause); it is what Starlette's `TestClient` imports and type-checks against, and plain `httpx` is deprecated there. |
| Signed session cookie via Starlette `SessionMiddleware` (`itsdangerous`), password from env | adopted | One shared password. No user table, no OAuth. Starlette ships the middleware and requires `itsdangerous`. Its timestamp signer embeds a signed issued-at time in the cookie and rejects it once `max_age` has passed, on every request; that signed timestamp plus `max_age` is the expiry claim [`acceptance.md`](acceptance.md) requires, so nothing is hand-rolled. The cookie is re-signed only when the session is modified, so the lifetime is absolute, not sliding. |
| `pydantic-settings` | adopted | Typed environment contract with fail-fast validation (missing password, short cookie secret). FastAPI's own settings guidance. |
| `uvicorn` | adopted | The ASGI server FastAPI's documentation runs under. Behind Caddy it must run with `--proxy-headers` and `--forwarded-allow-ips` set to the proxy's address, otherwise every request appears to come from the proxy and the per-IP login throttle collapses into one shared counter. The deployment notes fix those flags. |

## Frontend

| Choice | Status | Why |
| --- | --- | --- |
| Vite, React, TypeScript strict | fixed | The user's daily stack. |
| TanStack Query | adopted | Invalidation after posting a visit without hand-rolled state. |
| React Router | adopted | Under ten routes. TanStack Router rejected as more setup than a handful of routes justify. |
| openapi-typescript (types generated from the FastAPI OpenAPI document) | adopted | Pydantic is the single type source. Hand-written API types are forbidden. Regeneration is `make generate-types`, the output is committed, and `make check` fails on drift via a non-mutating diff against a fresh generation. |
| Tailwind CSS with shadcn/ui components | adopted | Copy-in components, mobile-first, no runtime UI library. Mantine was the alternative. The current shadcn CLI (v4, preset-based `init`) pulls in `shadcn` and `cn` as runtime dependencies plus `radix-ui`, `class-variance-authority`, `lucide-react`, `tw-animate-css`, and a font package (`@fontsource-variable/geist` for the default `nova` preset) rather than the classic `clsx`/`tailwind-merge` pair; owner approved this full v4 footprint 2026-09-15. |
| react-hook-form with zod | adopted | Visit and bake forms are lists of number inputs; recipe, ingredient, location, and login forms mix text, date, and password fields. zod validates every form boundary. |
| Biome (lint and format) | adopted | One tool. ESLint and Prettier rejected for a solo project. |
| vitest | adopted | For the little pure frontend logic that exists. No component-test scaffolding. |
| Playwright | adopted | Exactly one smoke test: log in, load home. Run by `make e2e`, which arrives with the login-and-home slice rather than the CI bootstrap. |

## Shipping

| Choice | Status | Why |
| --- | --- | --- |
| One container: FastAPI serves the built Vite bundle as static files | adopted | No CORS, one deploy artifact. |
| Docker Compose with a persistent volume for the SQLite file | adopted | Runs identically on a laptop and the host. The image installs the `sqlite3` CLI (slim Python images ship the library but not the binary); `DB` is an environment variable holding the absolute path of the database file on the named volume; Compose bind-mounts a host `./backups` directory at `/backups`. |
| Caddy for TLS on a VPS, or on an AWS Lightsail instance (a VM running Docker Compose with an attached block disk); either way Caddy terminates HTTPS, which `Secure` cookies require | open gate | User has not chosen between the two VM options. Lightsail Container Service and App Runner are both rejected: neither offers a persistent disk for SQLite. |
| Nightly host cron runs `cd /srv/inventory && docker compose exec -T app sh -c 'sqlite3 "$DB" ".backup /backups/inventory.db"'` (the project directory holding `compose.yaml` and `.env`; deployment notes fix the path) with `/backups` bind-mounted from the host, then uploads that host file to object storage. `-T` disables the TTY cron lacks, and the single quotes defer `$DB` expansion to the container where it is defined | adopted | The `sqlite3` CLI and the database path live in the container; cron and object-storage credentials live on the host. The bind mount is the boundary. |
| GitHub Actions running `make check` on every PR, plus `make e2e` once it exists | adopted | Repository is `cblack34/inventory` on GitHub. |
| `Makefile` as the single definition of verification commands | adopted | `AGENTS.md` and `acceptance.md` reference only `make check` and `make e2e`. |

## Dependency policy

Runtime dependencies are the rows above, plus the packages an adopted row's own registry or official documentation requires in order to work — for example `radix-ui`, `class-variance-authority`, `cn`, `lucide-react`, `tw-animate-css`, and a font package for shadcn/ui components (see the Frontend table), and `@hookform/resolvers` for react-hook-form's zod resolver. A row pre-approves its required companions; the lead records them in the lockfile without asking. Adding anything else at runtime requires the user's approval. Dev-only tooling that directly supports an adopted row (a Biome plugin, a pytest plugin) is at the lead's discretion. Prefer a well-maintained library over hand-rolled code for anything security-sensitive or fiddly; prefer the standard library and existing dependencies over a new package for a few lines of plain logic.

## License policy

The application is deployed as a service and its source is not distributed, but the owner does not want a dependency that could obligate publishing this code.

- **Fine without asking:** MIT, BSD (2- and 3-clause), Apache-2.0, ISC, PSF, Unlicense, public domain, LGPL, MPL-2.0, and OFL-1.1 for font files (it governs the font, not the code that loads it).
- **Ask first:** GPL (any version).
- **Never:** AGPL, SSPL, and any license that conditions use on publishing the calling code.

Enforced by hand: the lead checks the license when proposing a dependency and records it in the approval. No license scanner runs in `make check`; add one only if the dependency count makes hand checks unreliable. Every row adopted above is MIT, BSD, Apache-2.0, ISC, or public domain.
