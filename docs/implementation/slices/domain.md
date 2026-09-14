# Slice plan — domain

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/data-model.md`](../../data-model.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md)
- **Human approval:** repository owner, 2026-09-14, in the implementation-lead session that proposed this slice after slice `ci` merged.
- **Final acceptance advanced:** the automated checks under Ingredients and recipes (63/25/13 estimate), Bake (51 and 222/111/56 splits, drift bound), Ledger, stock, and FIFO (fold equality, two-batch FIFO order, atomic rejection), Stand visit and Market visit (settlement routing and rejections), Profit (cost lines), Corrections (sequential undo, same-batch reversal), Home screen and expiration (soon vs expired), and the Money criterion's no-float rule for domain dataclasses.

## Outcome

Every money and stock rule in the data model exists as pure Python under `src/inventory/domain/`, importing nothing from FastAPI, SQLAlchemy, or IO, with unit tests that pin the acceptance numbers and behaviors. Later slices call these functions; none reimplements a rule.

## Why this slice is next

The build brief's dependency graph puts the ledger and cost math causally first: settlement depends on derived on-hand and FIFO, profit depends on frozen unit costs, and every screen depends on all of them. The brief's rationale holds: these rules are the product, and getting them right with no framework in the way is cheapest. No research gate blocks them. Slice `ci` provides the `make check` gate they will be tested under.

## Scope

### In scope

- `round_half_up` on integers; recipe cost; batch cost split by portion weight; the drift bound.
- Movement and planned-movement types; on-hand fold; FIFO allocation by expires, baked, id; sequential reversal planning targeting the original batch.
- Stand and market settlement producing planned movements and expected revenue; visit profit with separate Sold, Waste, and Sampled cost lines; expiration state from an injected date.
- Tests for all of the above, the import-purity subprocess check, and a no-float walk over domain dataclasses.
- Project-wide unit decisions recorded here: weights are integer grams (`_g`), money is integer cents (`_cents`).

### Out of scope

- SQLAlchemy models, Alembic migrations, built-in location rows, transactions and `BEGIN IMMEDIATE`.
- Any FastAPI route or Pydantic schema; HTTP error mapping.
- Any screen; the weight-to-count helper for sample sizes belongs to the frontend slice.
- `make e2e`.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Non-negotiable 1, append-only ledger with derived stock | `on_hand` is the only way stock is computed; nothing here stores a count. |
| Non-negotiable 2, frozen batch cost | `split_unit_costs` is a pure function of inputs at bake time; persistence later stores its output once. |
| Non-negotiable 3, automatic FIFO; undo targets the original batch | `allocate_fifo` is the single allocation path; `plan_reversal` bypasses it by design. |
| Non-negotiable 4, integer money | No float or Decimal in the package; enforced by a dataclass walk and pyright strict. |
| Architecture boundary: domain rules are pure Python | Purity test imports every submodule in a subprocess and fails if FastAPI or SQLAlchemy loads. |
| data-model.md settlement order and sequential undo | Pinned by tests on two-batch fixtures. |

## Gates and dependencies

### Hard gates

- The visits leaf needs the costing and ledger modules on the spine first.

### Sequencing recommendations

- Costing and ledger in parallel; they own disjoint files. Visits last.

## Architecture and contracts

- **Affected seams:** new package `src/inventory/domain/`. Nothing outside it changes except tests.
- **Public contracts:** none exposed over HTTP yet. The function signatures in the issues are the contract later slices build on; renaming them later is cheap because there is one caller per rule.
- **Data and migration considerations:** none. Plain dataclasses only.

## High-level approach

Three leaf PRs into `slice/domain`. A shared `DomainError` base lands on the spine before the leaves start so parallel leaves never edit the same file. Each leaf is a module plus its tests, delegated to a standard-tier agent with the issue as its packet. Copilot is requested by hand on each leaf; the spine PR to `main` gets it automatically.

## Verification

- `make check` exits zero locally on the spine head, and in CI on each leaf PR's merge ref.
- Every automated check listed under "Final acceptance advanced" that can be expressed against pure functions has a test; the API-level versions arrive with the persistence and API slices.
- The purity subprocess test and the no-float walk pass.
- Repository definition-of-done commands remain mandatory.

## Risks and stop conditions

- A data-model rule turns out to be ambiguous when written as code (for example, how `added` interacts with FIFO when a size has stock at both stand and kitchen). Stop, record the reading in the issue, and confirm with the owner before choosing.
- An interface fixed in an issue proves wrong for the visits leaf. Adjust in that leaf's PR and note it in the issue; that is ordinary discovery, not a plan amendment.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#9](https://github.com/cblack34/inventory/issues/9) — domain/costing: round_half_up, recipe cost estimate, batch cost split by weight | Money math and the purity test | None |
| [#10](https://github.com/cblack34/inventory/issues/10) — domain/ledger: movement types, on-hand fold, FIFO allocation, sequential undo planning | Stock derivation, FIFO, reversal planning | None |
| [#11](https://github.com/cblack34/inventory/issues/11) — domain/visits: stand and market settlement, visit profit, expiration flags | Settlement, profit, expiration, no-float walk | #9, #10 |

## Delivery shape

- **Topology:** per-slice spine with leaf PRs.
- **Branch or spine:** `slice/domain`; leaves `domain/costing`, `domain/ledger`, `domain/visits`.
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
