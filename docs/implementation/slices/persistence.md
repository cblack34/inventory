# Slice plan — persistence

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/data-model.md`](../../data-model.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md); descriptive schema in [`docs/schema.md`](../../schema.md).
- **Human approval:** repository owner, 2026-09-14, after slice `domain` merged; the owner also chose to land `docs/schema.md` in this slice.
- **Final acceptance advanced:** Bake (bake entry, frozen costs, DB-level immutability trigger, undo of a bake); Locations (five built-ins after migration); Ledger, stock, and FIFO (fold equality, serialized removals, atomic rejection, atomic visit); Stand visit and Market visit (persisted expected revenue, fee zero for stands, rejections); Profit (separate cost lines, voided visit excluded); Home screen and expiration (stock grouped by inventory location with per-batch states); Corrections (reversal rows with `reverses_movement`, unique constraint, all-or-nothing); Login and deployment (a test migrates an empty database and finds the built-ins); Money (SQLAlchemy columns are `Integer`).

## Outcome

The schema in `docs/schema.md` exists as SQLAlchemy models with one Alembic migration, and a write path records bakes, manual moves, undo, and stand and market visits as entry plus movement rows inside one `BEGIN IMMEDIATE` transaction by calling the domain planners. Stock, history, and profit are read from the ledger by queries. No HTTP yet.

## Why this slice is next

The build brief's known dependencies put the ledger causally first and the API after it; the API slice needs a write path that already enforces atomicity and serialization rather than adding them later. Real bakes will exist before the schema is final, so the pack wants Alembic in place from the first table. The domain slice supplies every rule this slice calls, so no rule is reimplemented here.

## Scope

### In scope

- SQLAlchemy 2.0 models for the ten tables in `docs/schema.md`, integer money, weight, and quantity columns, CHECK and UNIQUE constraints, no cascading deletes.
- Initial Alembic migration: tables, constraints, the five built-in locations, `BEFORE UPDATE` triggers that freeze batch cost columns.
- Engine factory implementing SQLAlchemy's pysqlite recipe for `BEGIN IMMEDIATE`, foreign keys on, busy timeout.
- Write path: bake, manual move, undo, stand visit, market visit; each a function over an open session, with a transaction wrapper that commits or rolls back everything.
- Read path: stock fold, batch order, unit costs, stock grouped by location with expiry states, history with profit for non-voided visits, visit profit.
- Tests for every acceptance behavior above that can be expressed without HTTP, including the two-thread concurrency check and the DB-level cost immutability check.

### Out of scope

- FastAPI routes, Pydantic schemas, HTTP error mapping, auth, settings, the static mount.
- Ingredient, recipe, size, and location CRUD beyond what test fixtures insert directly (the API slice owns those write paths together with their validation).
- Any screen; `make e2e`; container, Compose, backup.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Non-negotiable 1, append-only ledger, derived stock | No update or delete path for movements or entries; stock is a fold in `load_stock`; undo appends a reversal entry. |
| Non-negotiable 2, frozen batch cost | Costs written once at bake; DB trigger rejects any update; test changes a price after a bake. |
| Non-negotiable 3, automatic FIFO; undo targets the original batch | Write path calls `allocate_fifo` and `plan_reversal`; no function accepts a batch id from a caller for a removal. |
| Non-negotiable 4, integer money | `Integer` columns only, checked by a mapper-registry walk. |
| Architecture boundary: source of truth is the SQLite database owned by the API | Every write goes through this package's functions in one transaction. |
| data-model.md serialized write transaction | Engine `begin` event issues `BEGIN IMMEDIATE`; two-thread test proves one of two over-removals fails. |
| build-brief risk: schema change after real data | Alembic from the first table; every later schema change ships a migration. |

## Gates and dependencies

### Hard gates

- The writes leaf needs the models and migration; the visits leaf needs `load_stock` and the transaction wrapper.

### Sequencing recommendations

- Schema, then writes, then visits; strictly serial because each builds on the previous leaf's files.

## Architecture and contracts

- **Affected seams:** new package `src/inventory/db/`, root `alembic.ini` and `alembic/`. Import direction is db → domain only; the domain purity test keeps it that way.
- **Public contracts:** none over HTTP. The write and read function signatures in the issues are the contract the API slice calls.
- **Data and migration considerations:** first migration `0001_initial`; built-in locations are looked up by kind, never by hard-coded id. `docs/schema.md` is the descriptive record and must be updated in the same PR as any divergence.

## High-level approach

Three serial leaf PRs into `slice/persistence`, each delegated to a standard-tier agent with its issue as the packet. The engine recipe is verified against SQLAlchemy's current SQLite dialect documentation before it is written. The concurrency test runs against a file-backed database with two real threads. Copilot is requested by hand on each leaf; the spine PR to `main` gets it automatically.

## Verification

- `make check` exits zero locally on the spine head, and in CI on each leaf PR's merge ref.
- Every automated check listed under "Final acceptance advanced" that does not require HTTP has a test in `tests/db/`.
- `alembic upgrade head` on an empty file is idempotent and `alembic check` reports no model drift.
- Repository definition-of-done commands remain mandatory.

## Risks and stop conditions

- The pysqlite `BEGIN IMMEDIATE` recipe interacts badly with SQLAlchemy's session autobegin or with the test fixture; stop and report rather than loosening isolation.
- A data-model rule proves ambiguous at the write path (for example, which destination a manual "sale" resolves to); record the reading in the issue and confirm with the owner.
- A schema defect surfaces after the schema leaf merges: fix by a new migration, never by editing `0001`.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#16](https://github.com/cblack34/inventory/issues/16) — persistence/schema: models, initial migration, built-ins, cost triggers, engine factory | The tables and the serialized engine | None |
| [#17](https://github.com/cblack34/inventory/issues/17) — persistence/writes: transaction wrapper, stock loading, bake, manual move, undo | The atomic write path and the concurrency proof | #16 |
| [#18](https://github.com/cblack34/inventory/issues/18) — persistence/visits: stand and market recording, profit and stock queries | Visits as entries, plus the reads the API needs | #17 |

## Delivery shape

- **Topology:** per-slice spine with leaf PRs.
- **Branch or spine:** `slice/persistence`; leaves `persistence/schema`, `persistence/writes`, `persistence/visits`.
- **Final PR:** to be added in the delivery record.
- **Human merge gate:** Only the human may physically merge the final PR to `main`. Agents must stop when it is ready.

## Amendments

None.

## Delivery record

Complete once when the final PR is ready for human merge. Do not use this section for WIP status.

- **Outcome:** pending
- **Verification:** pending
- **Deviations:** pending
- **Unresolved gates or risks:** pending
- **Final PR:** pending
- **Merge state:** pending
