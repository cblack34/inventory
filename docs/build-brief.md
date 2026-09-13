# Build Brief

_Read this first, then follow the active-pack order in `AGENTS.md`. This document defines the complete strategic outcome; the implementation agent will inspect the repository and propose the tactical plan with the user._

_Code, types, schemas, and file layouts are **illustrative guidance, not mandated implementation**. Described behavior, architecture contracts, non-negotiables, and [`acceptance.md`](acceptance.md) are authoritative._

## Product outcome

A small web app for a two-person cottage-law snack business run from a home kitchen under an LLC. The owners bake batches, stock one or more honor-system farm stands weekly, and sell at farmers markets using free-tier Square for checkout. Fresh goods go to stands; goods nearing expiration are pulled to markets to sell them before they spoil; market leftovers return and go back out to stands.

The app answers one question after each market or stand trip: **how much did we make?** To do that it must know what each unit cost to make, where every unit is, and what happened to it. The primary user is the co-owner who sits down after a market or stand visit, sometimes on a phone, and records what happened. Entry must be counting, not bookkeeping.

Scale: roughly ten recipes and twenty to thirty units sold per week. Shelf life is mostly one month, some longer. The business is one week old; the design should stay simple and grow by adding rows, not features.

## In scope

- **Ingredients and recipes.** A shared ingredient list with a current price per unit. Recipes reference ingredients with quantities. Packaging is just another ingredient.
- **Multi-size yield.** A recipe yields several sizes (for example large bag, small bag, sample). Each size has a portion weight and a sale price. A sample is an ordinary size with a zero price; nothing special-cases it. The recipe stores a typical yield per size as a prefill.
- **Recipe costing.** Cost per size shown on the recipe screen, computed from current ingredient prices and portion weights.
- **Bake.** Record a batch: recipe, date, actual count per size, expiration date prefilled from the recipe's shelf life and editable. Batch cost is computed and frozen at that moment.
- **Locations.** Kitchen plus any number of user-created stands and markets. Stands and markets are rows in a table, not code.
- **Movements and derived stock.** Every change in where units are is an append-only movement between two locations, including the source location Production and the terminal destinations Sold, Waste, and Sampled, so a bake is a movement like any other rather than a special case. On-hand per location, recipe, size, and batch is derived. FIFO picks batches automatically.
- **Stand visit.** Enter counted units per recipe and size, units tossed, cash collected, then units pulled back to the kitchen and fresh units added from the kitchen. Missing units since the last visit are recorded as Sold (priced sizes) or Sampled (zero-price sizes). The visit shows expected cash versus actual cash so shrink is visible.
- **Market visit.** Enter units taken from the kitchen, revenue as one total, booth fee, units returned to the kitchen, and units tossed. Sample returns prefill to zero and are editable. Missing units are Sold or Sampled by the same price rule.
- **Visit profit.** Revenue minus fee minus the frozen cost of every unit that left inventory during the visit (sold, wasted, sampled). Waste and samples are shown as their own lines.
- **Home screen.** Stock by location, units expiring within seven days highlighted, expired units flagged until someone records them as waste, a "toss" action for kitchen stock, and a history of entries (bakes, visits, manual operations) newest first, visits showing profit, each non-voided entry with an undo action.
- **Corrections.** An undo action on any bake, visit, or manual operation that appends compensating movements, plus a manual movement form for anything else. No editing or deleting of history.
- **Single shared login.** One password from configuration, session cookie. No user table.
- **Deployment shape.** One container serving the API and the built frontend, SQLite on a persistent volume, a documented nightly file backup. The container must run locally with Docker Compose.

## Out of scope

- **Square API integration.** Market revenue is typed from Square's daily summary. Revisit if typing it becomes a chore. Design nothing for it now.
- **Found (bank) receipt import.** Receipts stay in Found for taxes. Ingredient prices are typed by hand.
- **Ingredient stock tracking.** The app tracks finished goods only. It never knows how much flour is on hand.
- **Ingredient price history.** Current price only. Batches snapshot cost, which is all the history the business needs.
- **Unit conversion.** An ingredient's unit is a free-text label. Recipe quantities are in that unit.
- **Multiple users, roles, or per-user audit.** Two people, one password.
- **Editing or deleting movements or visits.** Corrections are new movements.
- **Live or in-market use.** The app is after-the-fact entry. No offline mode, no real-time sync.
- **Labor or mileage costing.** Booth fees are the only non-goods cost in v1.

## User directives and non-negotiables

Numbered consistently with `AGENTS.md`.

1. **Append-only movement ledger; stock is derived.** Failure mode: a stored count drifts from history and profit reports can't be explained. Verification: no update or delete route for movements; a test derives on-hand from movements and matches the API. See [`data-model.md`](data-model.md).
2. **Batch cost frozen at bake time.** Failure mode: raising the flour price changes last month's profit. Verification: a test changes an ingredient price after a bake and asserts the batch cost is unchanged.
3. **Automatic FIFO for user-initiated removals; the user never picks a batch.** Failure mode: a form or endpoint requires a batch id for a sale, waste, or move. Verification: recipe, size, and count are the only batch-selection fields in a sale, waste, or move request — a manual move additionally carries its source and destination locations; a test with two batches confirms the older one is drained first. Undo is the one internal exception: each reversal targets the same batch as the movement it undoes, not the current FIFO head (see [`data-model.md`](data-model.md)).
4. **Money in integer cents; no float anywhere.** Failure mode: a per-size cost split drifts from the batch cost by more than a bounded rounding remainder, or any money, weight, or quantity field uses a float. Verification: a test walks every SQLAlchemy column and every Pydantic field and asserts none is typed `float`, backed by pyright strict; a test asserts `Σ (unit_cost × count_made)` stays within `ceil(total_units / 2)` cents of the batch cost (exact equality is not achievable for every yield; see [`data-model.md`](data-model.md)).

Directives that are not invariants but must hold: the stack in [`tech-stack.md`](tech-stack.md) is chosen and not up for substitution; the UI is mobile-first and every visit screen is a list of number inputs, not a table to navigate.

## Architecture boundaries and contracts

- **Source of truth is the SQLite database owned by the API.** The frontend never derives inventory or profit itself; it displays what the API computes. Reason: one implementation of the money rules.
- **Domain rules are pure Python with no framework or IO imports:** FIFO allocation, batch cost calculation, per-size cost split, visit settlement (counted versus expected, sold versus sampled), and profit. The FastAPI layer and SQLAlchemy layer sit outside them. Reason: these rules are the whole product and must be unit-testable in milliseconds.
- **Pydantic schemas are the API contract.** Frontend TypeScript types are generated from the OpenAPI document, never hand-written. Reason: one type system, regenerated by one command.
- **Locations are data.** Kitchen, Sold, Waste, Sampled, and Production are built-in rows created by migration and cannot be deleted. Stands and markets are user rows with a type. Adding a stand is a row, not a deploy.
- **Sample is not a concept in code.** A size with price zero behaves identically to any other size except where the price rule (zero price means Sampled, not Sold) applies. Do not add an `is_sample` flag.
- **Every movement belongs to exactly one entry: bake, visit, manual, or reversal.** A visit is an entry, so every movement it creates references that visit and profit per visit is one query. A bake is an entry too; its Production-to-Kitchen movements reference it and the batch it creates stores a reference back to it. A manual operation is also an entry and may contain several movement rows, one per batch FIFO selected. Undo appends a reversal entry that targets any of the other three kinds.
- **Extension seams, deliberately empty:** the location kind enum is the full list in [`data-model.md`](data-model.md) (`kitchen`, `stand`, `market`, `production`, `sold`, `waste`, `sampled`), but only `stand` and `market` are user-creatable today, leaving room to add a third user-creatable kind later; visit revenue is one field so Square import could later populate it. Build neither.
- **Auth is a single shared password** compared server-side, session held in a signed cookie. The password and cookie secret come from environment variables. Reason: two users on the internet need a lock, not an identity system.

Details: [`data-model.md`](data-model.md), [`tech-stack.md`](tech-stack.md).

## Research, decisions, and open gates

Adopted decisions, all made by the user in discussion:

- Visit-centric design instead of live stock; the app is used after trips, not during.
- FIFO everywhere instead of batch selection.
- Cost split across sizes by portion weight, not by count, so giveaways don't inflate the cost of what is sold.
- Sample is an ordinary zero-price size, allowed at any location, because the owners intend to trial samples at stands.
- Expected-versus-actual cash per stand visit as the shrink measure; no separate theft or loss concept.
- One revenue total per visit; no cash and card split.
- Stack and tooling per [`tech-stack.md`](tech-stack.md).

Assumptions the implementation lead may rely on unless the user says otherwise:

- Expiring-soon horizon is seven days. It matches the weekly stand cadence.
- Units pulled from a stand go to the kitchen, and units taken to a market come from the kitchen. Visit forms only offer the kitchen as the other end of a transfer; the manual movement form allows any inventory location except a market as destination.
- A market's on-hand during a visit is modeled as stock at the market location, moved there when the visit is recorded and moved back on return. Nothing is left at a market between visits; a manual movement can never create market carry-over because its destination may not be a market (see [`data-model.md`](data-model.md)).

Open gates, none blocking implementation:

- **Hosting target.** The user has not chosen between a generic VPS and AWS Lightsail Containers. The single-container plus persistent-volume shape works on both. Decide before the first deployment.
- **Copilot review request method.** Copilot review is enabled on the repository but the exact request mechanism has not been exercised here. Verify on the first PR and record it in `workflow.md`.

No external standards or licenses shape this project. No research doc is needed.

## Risks and failure modes

- **Count higher than on-hand.** A stand count or a return count exceeding what the ledger says is at that location. Mitigation: reject with a message naming the location, recipe, size, on-hand, and entered counts. The user fixes it with a manual movement. Detection: API test.
- **Expiration is a label, not a fact.** Units expire on paper while still sitting on a shelf. Mitigation: the app flags expired stock and never auto-wastes it. Accepted by the user.
- **SQLite on a single volume.** Disk loss is data loss. Mitigation: documented nightly file copy to object storage, and the backup command is part of the deployment docs. Accepted risk owner: the user.
- **Schema change after real data exists.** Mitigation: Alembic migrations from the first schema; every schema change ships a migration in the same PR.
- **Typing revenue from Square by hand.** Transposition errors. Mitigation: the visit screen shows expected revenue from units sold next to the entered total so a mismatch is obvious. Accepted.
- **Feature creep toward a general inventory system.** Mitigation: out-of-scope list above and the "never implement deferred scope" rule in `AGENTS.md`.

## Known dependencies

- Per-size cost cannot be computed before portion weights and actual yield counts exist, so the recipe and bake capabilities must exist before any visit can report profit.
- Visit settlement (what went missing at a stand) depends on derived on-hand at that location, which depends on the movement ledger and FIFO allocation. The ledger is causally first.
- Generated TypeScript types depend on stable Pydantic schemas for the routes being built. Frontend screens for a capability follow its API.
- Nightly backup and deployment depend on the hosting decision, which is open. Nothing in code depends on it.

## Suggested implementation approach

_This is strategic guidance, not a required sequence. The implementation agent should evaluate it against the live repository and may reorder it when code, tests, or unforeseen constraints support a better plan._

1. **Repository skeleton, tooling, CI, and the `make check` and `make e2e` targets.** Reason: every later PR is gated on them, and CI does not exist yet.
2. **Domain core: ledger, FIFO, batch cost, cost split, settlement, profit, as pure Python with tests.** Reason: it is the product and every screen depends on it; getting it right with no framework in the way is cheapest.
3. **Persistence, migrations, built-in locations, and the API for ingredients, recipes, bakes, movements, and visits.** Reason: exposes the core; unlocks type generation.
4. **Frontend: recipes, bake, visit, home, login, in whatever order lets the owners start entering real data soonest.** Reason: real data exposes model mistakes faster than tests.
5. **Container, Compose, backup script, deployment notes.** Reason: last because it depends on the open hosting gate and nothing else depends on it.

## Definition of done

Both commands in `AGENTS.md` pass on the completed spine, every item in [`acceptance.md`](acceptance.md) holds, and the co-owner can record a real stand visit and a real market visit from a phone and read the profit for each without help.
