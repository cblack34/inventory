# Slice plan — api

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/data-model.md`](../../data-model.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md); descriptive schema in [`docs/schema.md`](../../schema.md).
- **Human approval:** repository owner, 2026-09-14, after slice `persistence` merged; the owner also chose RFC 9457 Problem Details as the API error format.
- **Final acceptance advanced:** Login and deployment (unauthenticated matrix, cookie attributes, throttle, fail-fast startup); Money (Pydantic strict integers, OpenAPI declares `integer`, negatives rejected); Ingredients and recipes (API cost estimate 63/25/13); Locations (create kinds, immutable kind, built-in protection, deactivate with on-hand); Bake (422s, frozen costs, no PUT/PATCH on batches); Ledger, stock, and FIFO (no PUT/PATCH/DELETE on protected resources, stock endpoint equals fold, atomic rejection with named fields, atomic visit); Stand visit and Market visit (routing, rejections, `extra='forbid'`, persisted expected revenue); Profit; Corrections (reversal endpoint, rejections); Home screen and expiration (stock endpoint states).

## Outcome

A FastAPI application under `/api/v1` that fails fast on bad configuration, authenticates with the shared password through a signed session cookie, serves the built frontend, and exposes ingredients, recipes, locations, batches, movements, reversals, visits, entries, and stock as resources over the persistence write path. Every rejection is a Problem Details document carrying the domain error's fields. The OpenAPI document is real, so generated frontend types describe the actual contract.

## Why this slice is next

Persistence already enforces atomicity and serialization, so routes stay thin. This is the first callable product surface and the input the frontend slice needs for type generation. The suggested approach in the brief places the API immediately after persistence.

## Scope

### In scope

- Settings from environment with fail-fast validation; `python -m inventory` entrypoint.
- App factory with session dependencies, injected clock in the business timezone, docs routes disabled.
- Problem Details exception handlers and OpenAPI error schema declarations.
- Session cookie auth via Starlette `SessionMiddleware`, constant-time password check, stdlib per-IP login throttle, 401 for API routes, redirect for app routes, public login page and assets, static mount of the Vite build.
- Pydantic schemas with `extra='forbid'` and strict non-negative integers as the API contract.
- Catalog routes: ingredients, recipes with sizes and live cost estimate, locations, plus their persistence functions.
- Ledger routes: batches, movements, reversals, visits (discriminated by kind), entries, stock.
- Regenerated frontend API types.

### Out of scope

- Any screen beyond serving the existing bundle; `make e2e`; container, Compose, backup, deployment notes.
- Logout, password change, multiple users.
- Square, Found, price history, ingredient stock, unit conversion.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Pydantic schemas are the API contract; frontend types generated | Every route has input and output models; `make check` regenerates types from the real document. |
| Auth is a single shared password, constant-time, signed cookie from env | `SessionMiddleware` with `compare_digest`; cookie attributes and lifetime pinned by tests. |
| Non-negotiable 3, no endpoint asks for a batch | Request models carry recipe, size, count, and locations only. |
| Non-negotiable 4, integer money | Strict integer fields; OpenAPI integer assertion. |
| `/api/v1` resource map and Problem Details (build brief) | Routers per resource; one error envelope. |
| Fail fast at startup | Settings validation exits non-zero naming the variable. |

## Gates and dependencies

### Hard gates

- Catalog needs the foundation's app factory, auth, and error handlers; ledger needs catalog's routes to create fixtures through the API.

### Sequencing recommendations

- Foundation, then catalog, then ledger; strictly serial.

## Architecture and contracts

- **Affected seams:** new package `src/inventory/api/`, `src/inventory/settings.py`, `src/inventory/__main__.py`, `src/inventory/db/catalog.py`. Import direction api → db → domain.
- **Public contracts:** the `/api/v1` routes and their schemas become the frontend's contract; `src/web/src/api/types.ts` is regenerated in each leaf.
- **Data and migration considerations:** none; no schema change.

## High-level approach

Three serial leaf PRs into `slice/api`, each delegated with its issue as the packet. The foundation leaf establishes the app, auth, and error envelope with a tiny protected probe used only by tests; catalog and ledger add routers and their persistence functions. A fourth, unplanned leaf (#27, no issue) moved the project floor to Python 3.14 after the owner noticed compatibility shims for the 3.12 pin; it ran in parallel with catalog and landed between foundation and catalog. Copilot is requested by hand on each leaf; the spine PR to `main` gets it automatically.

## Verification

- `make check` exits zero locally on the spine head, and in CI on each leaf PR's merge ref.
- Every acceptance automated check that speaks HTTP has a test in `tests/api/`.
- Startup fail-fast pinned by a subprocess test.
- Repository definition-of-done commands remain mandatory.

## Risks and stop conditions

- Starlette `SessionMiddleware` behavior around `https_only` or cookie attributes differs from the pack's expectations; stop and report before hand-rolling anything.
- The static mount and SPA fallback interact with `/api/v1` routing order; pin with tests rather than assume.
- A data-model ambiguity surfaces at a route (for example partial recipe PATCH semantics); record the reading in the issue and confirm with the owner.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#23](https://github.com/cblack34/inventory/issues/23) — api/foundation: settings, app factory, Problem Details errors, session auth, static mount | The app skeleton every route depends on | None |
| [PR #27](https://github.com/cblack34/inventory/pull/27) — api/python314 (no issue; owner-raised during review) | Move the project floor to Python 3.14, drop future-annotations shims | #23 |
| [#24](https://github.com/cblack34/inventory/issues/24) — api/catalog: ingredients, recipes with sizes and cost estimate, locations | Catalog resources and their write paths | #23, #27 |
| [#25](https://github.com/cblack34/inventory/issues/25) — api/ledger: batches, movements, reversals, visits, entries, stock | Ledger resources over the persistence write path | #24 |

## Delivery shape

- **Topology:** per-slice spine with leaf PRs.
- **Branch or spine:** `slice/api`; leaves `api/foundation`, `api/catalog`, `api/ledger`.
- **Final PR:** [#30](https://github.com/cblack34/inventory/pull/30).
- **Human merge gate:** Only the human may physically merge the final PR to `main`. Agents must stop when it is ready.

## Amendments

None.

## Delivery record

Complete once when the final PR is ready for human merge. Do not use this section for WIP status.

- **Outcome:** Delivered 2026-09-14. `src/inventory/api/` and `src/inventory/settings.py` provide a FastAPI app under `/api/v1` that fails fast on bad configuration, authenticates with the shared password via a Starlette session cookie with a bounded per-IP throttle, serves the built frontend, and exposes ingredients, recipes, locations, batches, movements, reversals, visits, entries, and stock as resources over the persistence write path. Every error is an RFC 9457 Problem Details document; domain rejections name recipe, size, and location. The project floor moved to Python 3.14 in this slice.
- **Verification:** `rm -rf .venv src/web/node_modules && make check` exit 0 on code head 1c6d757 under Python 3.14.6 (pyright strict 0 errors, 448 pytest of which 182 are API tests, web stages green, types regenerated from 17 real paths with no drift). Spine-PR review added atomic throttle attempts, size-name preflight, an injected business date, eager recipe write responses, a single-entry history query, bounded password and id inputs (one shared id type for body and path parameters), redacted validation inputs, a gated `index.html` under every alias, collision-safe size renames, a public-file shortcut limited to direct children of the build, and Unicode case-fold name preflights on top of the merged leaves; the only commit after that code head is this record. Leaf evidence on [#26](https://github.com/cblack34/inventory/pull/26), [#27](https://github.com/cblack34/inventory/pull/27), [#28](https://github.com/cblack34/inventory/pull/28), [#29](https://github.com/cblack34/inventory/pull/29): green CI and a zero-inline-comment Copilot pass at each final head. Every acceptance automated check that speaks HTTP has a test in `tests/api/`, and fail-fast startup is pinned by a subprocess test. Issues [#23](https://github.com/cblack34/inventory/issues/23), [#24](https://github.com/cblack34/inventory/issues/24), [#25](https://github.com/cblack34/inventory/issues/25) carry the detailed trail.
- **Deviations:** An unplanned fourth leaf (#27) moved the project to Python 3.14 after the owner noticed compatibility shims for the 3.12 pin. `read_session`, `write_session`, and the clock moved to `api/deps.py` to break an import cycle. Ingredients may be reactivated (the agent's draft forbade it). Review cycles ran past the three-cycle bound on three of four leaves, each time on genuine findings, disclosed per PR. The domain planners' request types are consumed directly by the API rather than wrapped in db-layer duplicates.
- **Unresolved gates or risks:** Hosting target remains open. The throttle keys on `request.client`, which needs uvicorn's proxy-header flags behind Caddy (recorded in tech-stack.md for the deployment slice). Two review notes deferred to the next slice touching the API: `GET` on a POST-only `/api/v1` path answers 404 (the SPA catch-all claims it) where 405 with `Allow` would be more precise; and money, weight, and quantity inputs have no upper bound, so values near 2^63 would reach SQLite and fail as a 500 rather than a 422 (a shared cap around 10^9 keeps every product inside int64).
- **Final PR:** [#30](https://github.com/cblack34/inventory/pull/30).
- **Merge state:** Ready for the human to merge; agents do not merge to `main`.
