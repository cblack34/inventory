# Slice plan — finish

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/data-model.md`](../../data-model.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md).
- **Human approval:** repository owner, 2026-09-15, after slice `web-entry` merged. The owner approved adding the read-only `GET /api/v1/today` resource (a public-contract addition) and deferred the hosting decision, intending to run the Compose deployment on a home server for now.
- **Final acceptance advanced:** Money (maximal valid inputs answer 422 rather than overflowing the database); Login and deployment (the OpenAPI document declares no state-changing `GET`; `Allow` on POST-only paths); Bake (the expiration prefill derives from the business date); the final audit traces every automated acceptance check to a passing test.

## Outcome

No known defect remains. Persisted money totals and `shelf_life_days` are bounded so a well-formed request can never 500; a `GET` on a POST-only path answers 405 with `Allow`; the bake form prefills from the business date via `GET /api/v1/today`; CI runs its two commands as parallel jobs with a cached browser; and an acceptance audit records where every automated criterion in `docs/acceptance.md` is tested. The project is complete pending the owner's two human checks (phone check of every screen at 375 px; one backup run against a running instance) and the deferred hosting work.

## Why this slice is next

Every screen and the container exist. What remains is one recorded API defect (backlog #37), two deferred review notes, the CI split the owner asked for, and proof that final acceptance holds. Closing these together produces the completion evidence `AGENTS.md` requires before declaring the project done, without starting hosting work the owner has deferred.

## Scope

### In scope

- Backlog #37: one project-wide bound on persisted money totals checked before batch costs and visit expected revenue are written; `shelf_life_days` uses the shared bounded integer type; each rejection is a 422 Problem naming the field.
- 405 with `Allow` for a `GET` on a POST-only `/api/v1` path (the SPA catch-all currently answers 404).
- `GET /api/v1/today` returning the business date; the bake form prefills `baked` from it; regenerated frontend types.
- CI as two parallel jobs (`make check`, `make e2e`) with a Playwright browser cache; workflow doc sentence updated; required-check names noted for the ruleset.
- Acceptance audit: a table mapping every automated check in `docs/acceptance.md` to the test that pins it, with any gap fixed in this slice.

### Out of scope

- Hosting: Caddy, TLS, cron entry, object-storage upload (owner deferred; the Compose deployment is sufficient for acceptance).
- New screens or API resources beyond `today`; logout; multi-user.
- Square, Found, price history, ingredient stock, unit conversion, editing or deleting history.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Non-negotiable 4 and the Money criteria: integer cents, negatives rejected, no float | Bounds keep every persisted total inside SQLite's integer range; rejections are 422 Problems; no float introduced. |
| Every error response is a Problem Details document; API is resource-shaped | The bound and the 405 both render through the existing handler; `today` is a noun resource with a Pydantic response model. |
| Expiration uses the business timezone's "today" (data-model Expiration) | The bake prefill reads the server's business date instead of the browser clock. |
| Definition of done: `make check` and `make e2e`, single Makefile definition | CI jobs call the same two targets; nothing moves out of the Makefile. |
| Final acceptance: every item holds and every command passes | The audit table is the evidence; gaps found are fixed here. |

## Gates and dependencies

### Hard gates

- The acceptance audit cites the tests that `finish/api` adds, so it is written after that leaf merges.

### Sequencing recommendations

- `finish/api` and `finish/ci` in parallel (disjoint files); then the audit as a docs leaf on the spine.

## Architecture and contracts

- **Affected seams:** `src/inventory/api/` (schemas, static catch-all, one new route), `src/inventory/db/` write paths for the bound check, `src/web/src/features/bake/`, `src/web/src/api/types.ts` (regenerated), `.github/workflows/ci.yml`, docs.
- **Public contracts:** `GET /api/v1/today` added (owner-approved); `GET` on POST-only paths changes from 404 to 405; nothing else changes shape.
- **Data and migration considerations:** none; no schema change.

## High-level approach

Two leaf PRs in parallel into `slice/finish`, each delegated to a standard-tier agent with its issue as the packet, followed by the audit written against the merged spine. Copilot is requested by hand on each leaf; the spine PR to `main` gets it automatically. The owner's two human checks are listed in the record as the only items left after merge.

## Verification

- `make check` and `make e2e` exit zero on every leaf and on the spine.
- Curl evidence for the three bound rejections, the 405 with `Allow`, and `/today`.
- CI run showing two parallel jobs and the cached browser on a second run.
- The acceptance audit table with a test reference for every automated check.
- Repository definition-of-done commands remain mandatory.

## Risks and stop conditions

- Choosing where the total bound lives could tempt a change to the domain's pure functions; keep the check at the persistence boundary and raise the existing `DomainError` family.
- The 405 lookup must not shadow real 404s or the disabled docs routes; pin with tests.
- If the audit finds an acceptance check with no test, fix it in this slice; if it finds a criterion that cannot hold without a scope change, stop and return to the owner.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#49](https://github.com/cblack34/inventory/issues/49) — finish/api: bounds (#37), 405 on POST-only paths, `GET /api/v1/today` | Close every recorded API defect and deferred note | None |
| [#50](https://github.com/cblack34/inventory/issues/50) — finish/ci: parallel check and e2e jobs with a browser cache | The CI split the owner asked for | None |

The acceptance audit is a docs leaf on the spine after #49 merges; it needs no separate issue.

## Delivery shape

- **Topology:** per-slice spine with leaf PRs.
- **Branch or spine:** `slice/finish`; leaves `finish/api`, `finish/ci`, then `finish/audit`.
- **Final PR:** to be opened when verification passes on the spine.
- **Human merge gate:** Only the human may physically merge the final PR to `main`. Agents must stop when it is ready.

## Amendments

None.

## Delivery record

Complete once when the final PR is ready for human merge. Do not use this section for WIP status.

- **Outcome:** pending.
- **Verification:** pending.
- **Deviations:** pending.
- **Unresolved gates or risks:** pending.
- **Final PR:** pending.
- **Merge state:** pending.
