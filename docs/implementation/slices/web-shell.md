# Slice plan — web-shell

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/data-model.md`](../../data-model.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md).
- **Human approval:** repository owner, 2026-09-14, after slice `api` merged; the owner approved splitting the frontend into two slices, this shell-and-home slice first and an entry-screens slice after.
- **Final acceptance advanced:** Login and deployment (redirect and 401 behavior exercised by a real client; `make e2e` exists and runs in CI; the 375 px human check begins); Home screen and expiration (stock grouped by inventory location with both expiry markers per batch; toss on kitchen stock); Profit (history newest first with revenue and profit, voided visits shown without profit); Corrections (undo action on every non-voided entry).

## Outcome

The frontend becomes a real mobile-first app: a shell with routing, server state, styling, and a typed API client that understands Problem Details; a login screen; the home screen (stock by location with expiring and expired batch flags, toss on kitchen stock, history newest first with visit profit and undo); and `make e2e` running one Playwright smoke test locally and in CI.

## Why this slice is next

The brief's suggested step 4 is the frontend, and the API slice delivered every route these screens read. The definition of done in `AGENTS.md` ties `make e2e` to the slice that introduces login and home, so home belongs in the first frontend slice. Building the foundation together with the screen that reads the most endpoints settles every drift-prone tooling decision once (Tailwind v4, shadcn/ui, React Router, TanStack Query, Playwright), so the entry screens that follow are mechanical. Real data entry starts after the deployment slice either way, so splitting the frontend does not delay it.

## Scope

### In scope

- Runtime dependencies from the adopted rows only: React Router, TanStack Query, Tailwind CSS with its Vite plugin, shadcn/ui components with their pre-approved companions, react-hook-form, zod, and the zod resolver. Playwright as a dev dependency.
- A typed fetch wrapper over the generated OpenAPI types that parses RFC 9457 Problem Details and sends the client to `/login` on 401; a Vite dev proxy for `/api`.
- Login screen posting to `POST /api/v1/session`, surfacing invalid-credentials and throttle problems.
- Home screen over `GET /stock`, `GET /entries`, and `GET /locations`, with toss via `POST /movements` (Kitchen to Waste) and undo via `POST /reversals`, invalidating queries after each mutation.
- `make e2e`: build the frontend, migrate a temporary SQLite file, start the API with local-dev environment, run one Playwright test (log in, home renders); CI runs it after `make check`.

### Out of scope

- Every entry screen: ingredients, recipes, locations, bake, stand visit, market visit, manual movement form (next slice, `web-entry`).
- Logout, password change, any change to API routes or schemas; the deferred API review note (`GET` on a POST-only path answers 404 rather than 405) stays deferred because this slice does not touch API code.
- Container, Compose, backup script, deployment notes, the container entrypoint that runs migrations.
- Square, Found, price history, ingredient stock, unit conversion, multi-user.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Frontend types are generated, never hand-written | The client is typed only from `src/web/src/api/types.ts`; that file is untouched. |
| The frontend never derives inventory or profit | Home renders `GET /stock`, `GET /entries`, and visit fields as returned; no arithmetic on stock or money beyond formatting cents. |
| Non-negotiable 3, the user never picks a batch | The toss form sends size and count only. |
| UI is mobile-first; every screen usable at 375 px | Stacked cards, numeric inputs, Playwright runs at a 375 px viewport; the owner checks on a phone. |
| Definition of done: `make e2e` ships with login and home | The e2e leaf adds the target and the CI step; the spine PR carries every stage. |
| Server state lives in TanStack Query; zod at form boundaries | Query keys per resource, invalidation after mutations, zod schemas on the login and toss forms. |

## Gates and dependencies

### Hard gates

- The e2e and home leaves both need the foundation leaf (login page, shell, client, shadcn components).

### Sequencing recommendations

- Foundation first; e2e and home in parallel on separate branches since they touch disjoint files (`Makefile`, CI, and `src/web/e2e/` versus `src/web/src/`).

## Architecture and contracts

- **Affected seams:** `src/web/` only for application code; `Makefile` and `.github/workflows/ci.yml` for the new verification stage. No Python change.
- **Public contracts:** the `/api/v1` contract is consumed, not changed. `make e2e` becomes part of the definition of done from this slice on.
- **Data and migration considerations:** none.

## High-level approach

Three leaf PRs into `slice/web-shell`, each delegated to a standard-tier agent with its issue as the packet. The foundation leaf installs the adopted frontend rows, verifies each against current official docs, and lands the client, layout, and login with a placeholder home. The e2e leaf adds the Makefile target, the Playwright config whose web server is `python -m inventory` against a migrated temporary database, the single smoke test, and the CI step. The home leaf fills the placeholder with the stock and history sections and their two mutations. Copilot is requested by hand on each leaf; the spine PR to `main` gets it automatically.

## Verification

- `make check` and `make e2e` exit zero locally on the spine head, and in CI on each leaf PR's merge ref once the e2e leaf has landed.
- With a seeded database, home shows a size row holding one expired and one expiring-soon batch with both markers and per-batch counts; toss reduces kitchen stock and appends a manual entry; undo restores stock and labels the entry voided; a visit row shows revenue and profit.
- The owner confirms login and home are usable at 375 px without horizontal scrolling.
- Repository definition-of-done commands remain mandatory.

## Risks and stop conditions

- shadcn's CLI, Tailwind v4, and Biome may disagree on generated component formatting or path aliases; format generated files with Biome and stop before hand-rolling components if the CLI cannot target this setup.
- Playwright browser installation in CI adds minutes; stop and report before adding caching if the job approaches its 15-minute budget.
- The API entrypoint fixes port 8000 and does not run migrations; `make e2e` migrates first and fails if the port is busy. Acceptable for a two-person project; revisit only if it bites.
- A home-screen need that the current API cannot serve (for example a field missing from `GET /entries`) is a stop condition: record it in the issue and return to the owner rather than deriving it in the frontend.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#31](https://github.com/cblack34/inventory/issues/31) — web-shell/foundation: deps, typed API client, router, layout, login screen | The shell every screen builds on | None |
| [#32](https://github.com/cblack34/inventory/issues/32) — web-shell/e2e: make e2e, Playwright smoke test, CI step | The second definition-of-done command | #31 |
| [#33](https://github.com/cblack34/inventory/issues/33) — web-shell/home: stock by location with expiry markers, toss, history with undo | The home screen the brief describes | #31 |

## Delivery shape

- **Topology:** per-slice spine with leaf PRs.
- **Branch or spine:** `slice/web-shell`; leaves `web-shell/foundation`, `web-shell/e2e`, `web-shell/home`.
- **Final PR:** [#38](https://github.com/cblack34/inventory/pull/38).
- **Human merge gate:** Only the human may physically merge the final PR to `main`. Agents must stop when it is ready.

## Amendments

None.

## Delivery record

Complete once when the final PR is ready for human merge. Do not use this section for WIP status.

- **Outcome:** Delivered 2026-09-15. `src/web/` is a mobile-first app: React Router 8, TanStack Query 5, Tailwind CSS 4 with shadcn/ui v4 components, react-hook-form with zod; a typed client over the generated OpenAPI types that parses Problem Details and sends the browser to `/login` on 401; a login screen; and the home screen with stock grouped by inventory location, per-batch expiring-soon and expired badges, toss on kitchen rows, and history newest first with visit revenue and profit, a voided label, and undo on every non-voided bake, visit, or manual entry. `make e2e` builds the frontend, migrates a scratch SQLite file, starts the API through Playwright's web server, and runs the one smoke test; CI runs it after `make check`.
- **Verification:** `make check` exit 0 and `make e2e` exit 0 on code head ac9dee0 (ruff, pyright strict, 458 pytest, Biome, tsc, vitest 8, vite build, OpenAPI types with no drift; Playwright log in and load home at a 375 px viewport). A seeded 375×812 screenshot showed no horizontal scrolling, both expiry badges on one row broken out by batch, a visit with revenue and profit, and undo on each non-voided entry; the same Kitchen-to-Waste movement and reversal the UI issues round-tripped stock through the API. Leaf evidence on [#34](https://github.com/cblack34/inventory/pull/34), [#35](https://github.com/cblack34/inventory/pull/35), [#36](https://github.com/cblack34/inventory/pull/36): green CI and a HEAD-matched Copilot pass with zero new comments at each final head. Issues [#31](https://github.com/cblack34/inventory/issues/31), [#32](https://github.com/cblack34/inventory/issues/32), [#33](https://github.com/cblack34/inventory/issues/33) carry the detailed trail. The only commit after the code head is this record.
- **Deviations:** shadcn's current CLI (v4) bundles a font package, `lucide-react`, `cn`, and `shadcn` itself as runtime dependencies; the owner approved that footprint on 2026-09-15 instead of pinning the generator to v3 or hand-rolling components, and `docs/tech-stack.md` records it along with OFL-1.1 as fine for font files. React Router's current stable is major 8, not 7. The home leaf's third Copilot pass left five suppressed accessibility and refetch nits; they were applied in one commit on the spine so the leaf's clean review stayed valid. On the spine PR the owner and Copilot both flagged that awaiting refetches with `throwOnError` made a committed toss or undo look retryable; the final shape closes the toss form and hides Undo as soon as the POST succeeds and lets a failed refetch surface as the query's own error. A later pass added the Problem `detail` to the home screen's query errors and named every toss control for its recipe and size. The spine PR used its three review cycles; the last pass left one inline nit (Cancel unnamed) and three long-name wrapping nits, applied in the final code commit without a further Copilot pass, the owner then re-requested Copilot, whose pass surfaced three more suppressed notes (the dropped Problem `instance`, profit still shown on a just-voided card, no `h1` on the login page, then the Voided badge and revenue not following the local undo state), fixed in the final code commits; a history card now derives every voided-dependent field from one flag. The foundation and home leaves each used the full three review cycles on genuine findings.
- **Unresolved gates or risks:** Hosting target remains open. `make e2e` binds port 8000 and fails if a local dev server holds it. Backlog [#37](https://github.com/cblack34/inventory/issues/37) (SQLite-safe bounds on derived money aggregates and `shelf_life_days`, from the #30 review) and the deferred 404-versus-405 note in the api slice record await the next slice that touches the API.
- **Final PR:** [#38](https://github.com/cblack34/inventory/pull/38).
- **Merge state:** Ready for the human to merge; agents do not merge to `main`.
