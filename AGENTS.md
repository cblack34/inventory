# AGENTS.md — Snack Inventory

Instructions for the AI agent that plans and builds this project. This file is the source of truth for **how** to work; the active strategic pack listed below defines **what** must be true.

**Code, types, schemas, commands, and file layouts in strategic docs are illustrative guidance, not mandates.** Described behavior, architecture contracts, non-negotiables, and final acceptance are authoritative. Verify implementation details against current official documentation and the live repository.

## What this is

A two-person web app for a cottage-law craft snack business. It costs recipes, tracks baked batches as they move between the kitchen, honor-system farm stands, and markets, and reports profit per market or stand visit. Backend: Python, FastAPI, Pydantic, SQLAlchemy, SQLite, managed with `uv`. Frontend: Vite, React, TypeScript. One container serves both. Layout: root `pyproject.toml` and `uv.lock` with the Python package at `src/inventory/` and tests at `tests/`; the frontend is a separate npm project at `src/web/` with its own `package-lock.json`. Stack detail and rationale: [`docs/tech-stack.md`](docs/tech-stack.md).

## Prime directive

**Cold-read the active pack and current repository, then propose only the single best next implementation slice before coding.** Preserve the complete strategic outcome and stop when final acceptance passes.

The pack's high-level suggested implementation approach is informed but non-binding. Keep hard causal dependencies, but revise advisory order when current code, tests, or unforeseen constraints justify a better plan. Discuss material replanning with the user.

The user (repository owner) approves each slice, authorizes GitHub issue and PR creation per slice, and is the only person who merges to `main`. Scope changes, new paid services, and new runtime dependencies beyond [`docs/tech-stack.md`](docs/tech-stack.md) need the user's approval.

## Definition of done

Run these exact commands before every code-bearing PR is integration-ready, and unconditionally before declaring the project complete:

```bash
make check
make e2e
```

`make check` must run, in one invocation: Python lint and format check (ruff), Python type check (pyright), Python tests (pytest), frontend lint and format check (Biome), frontend type check (tsc), frontend unit tests (vitest), the production frontend build, and regenerating the frontend API types from the OpenAPI schema with a failure if the committed output differs. `make e2e` must build the frontend, start the API against a temporary SQLite file, and run the Playwright smoke test. Both must exit non-zero on any failure. The `Makefile` is the single place those underlying commands are defined. `make check` ships in the CI-bootstrap slice (see [`docs/engineering/workflow.md`](docs/engineering/workflow.md)) with every stage above; the type-generation stage may run against the minimal OpenAPI document that exists at that point. `make e2e` does not exist until the slice that delivers the login and home screens, because a Playwright stage with nothing real to drive would cost CI minutes for no evidence; until then `make check` alone is the definition of done and CI runs only it, and the slice that introduces login and home must ship `make e2e` and add it to CI. Within a slice, a leaf PR may carry a subset of the stages when a later leaf of the same slice adds the rest; the spine PR to `main` must carry every stage that exists. No stage may be silently skipped or removed once it exists.

Every item in [`docs/acceptance.md`](docs/acceptance.md) must also pass. Slice-level checks show progress but never replace final acceptance.

## Non-negotiables

1. **The movement ledger is append-only.** Stock on hand is always derived from movements, never stored. Corrections are new compensating movements. Reason: every profit number must be reconstructible from history.
2. **Batch cost is frozen at bake time.** Changing an ingredient price never changes an existing batch's cost. Reason: past profit reports must not drift.
3. **FIFO is automatic for user-initiated removals.** The user enters counts per recipe and size; the system picks the earliest-expiring batch. No screen or endpoint asks the user to choose a batch. Undo is the one internal exception: a reversal targets the same batch as the movement it undoes, not the current FIFO head. Reason: that is how the business already operates, and choosing batches by hand is the error-prone step this app removes.
4. **Money is never a float.** Store and compute in integer cents. Reason: cost splitting and profit must be computed without floating-point drift. A per-size cost split may leave a bounded rounding remainder against the batch's total cost (see [`docs/data-model.md`](docs/data-model.md)); bound and document that remainder, never chase it to exact equality with float math.

## Strategic-to-tactical handoff

- The strategic lead and pack own scope, directives, architecture boundaries, research gates, risks, known dependencies, suggested high-level order, and final acceptance.
- The implementation lead understands the full strategy but proposes, plans, and executes only one slice at a time. It retains issue, sequencing, integration, and verification responsibility.
- Create the slice plan, GitHub issues, branches, PRs, or sub-agent assignments only after that slice is agreed and the relevant action is authorized.
- Keep the durable slice plan focused on high-level what and why. Use linked GitHub issues for task checklists, WIP, blockers, assignments, and evidence.
- Give execution sub-agents bounded code and test assignments. Select the least expensive capable model and reasoning effort for each task rather than inheriting the primary agent's configuration. They surface surprises to the implementation lead rather than changing scope or replanning the broader effort.
- When evidence invalidates the plan, explain the impact and propose a revision; do not treat the strategic suggestion as a hard sequence.

## Delivery governance

- A human is the only authority that physically merges to `main` in GitHub. Agents never merge into `main`, enable auto-merge or a merge queue on `main`, automate the merge UI for `main`, or push directly to `main`, and never delegate any of those actions. Squash-merging a clean, reviewed leaf PR into the slice spine is the implementation lead's job and is not covered by this ban.
- **Active topology:** per-slice spine with leaf PRs. Each approved slice gets a spine branch `slice/<name>` from `main`; work lands as leaf PRs `<name>/<unit>` into the spine. The implementation lead may squash-merge clean, reviewed, green leaf PRs into the spine; the spine PR to `main` requires human merge, and the next slice starts only after that merge.
- Repository: `cblack34/inventory` on GitHub, public, default branch `main`. GitHub Copilot code review is the first-choice reviewer; it must be requested explicitly on leaf PRs, with the identifier and command recorded in [`docs/engineering/workflow.md`](docs/engineering/workflow.md), which also defines the fallbacks (`review-pr`, then a fresh review sub-agent). The author's own self-review never satisfies the independent gate.
- Use a Conventional Commits PR title and the workflow's issue-closing rules; only a PR to `main` may carry `Closes #N`.

## Always / Ask first / Never

- **Always:** follow [`docs/engineering/workflow.md`](docs/engineering/workflow.md); verify unfamiliar APIs against current official docs; run required checks; update affected strategic and descriptive docs with behavior changes; add an Alembic migration with every schema change.
- **Ask first or stop:** changing active scope, directives, public contracts, non-negotiables, final acceptance, or an architecture boundary; adopting a paid service; adding a runtime dependency not listed in [`docs/tech-stack.md`](docs/tech-stack.md); making an external or destructive change beyond recorded authority; starting a broad refactor.
- **Never:** invent repository facts; commit secrets; bypass red verification; merge into `main`, auto-merge or queue on `main`, or push directly to `main`, or delegate any of those; force current code into an obsolete plan; implement deferred scope (e.g. Square API, Found, price history, ingredient stock, multi-user — full list in [`docs/acceptance.md`](docs/acceptance.md)'s "Deliberately excluded" section) or speculative adapters for it.

## Dependencies

Prefer a well-maintained library over hand-rolled code for anything security-sensitive or fiddly (signing, sessions, settings parsing); a maintained library patches bugs and vulnerabilities before a two-person project would notice them. The standard library counts as maintained. The adopted set and the license policy are in [`docs/tech-stack.md`](docs/tech-stack.md). Adding anything else at runtime requires the user's approval; dev-only tooling that supports an adopted choice is at the lead's discretion.

## Code quality

- Follow [`docs/engineering/code-quality.md`](docs/engineering/code-quality.md).
- Keep it small. This is a handful of screens for two users. Prefer deleting over abstracting.

## Active build pack

Read in this order:

1. [`docs/build-brief.md`](docs/build-brief.md) — entry point. Product outcome, scope, non-negotiables, architecture boundaries, risks, suggested approach.
2. [`docs/data-model.md`](docs/data-model.md) — domain concepts, ledger semantics, FIFO and cost-split rules, visit math.
3. [`docs/tech-stack.md`](docs/tech-stack.md) — adopted stack with rationale and dependency policy.
4. [`docs/acceptance.md`](docs/acceptance.md) — final project-level acceptance and verification.
5. [`docs/engineering/workflow.md`](docs/engineering/workflow.md) — handoff, spine-and-leaf delivery, review loop, stop conditions.
6. [`docs/engineering/code-quality.md`](docs/engineering/code-quality.md) — code rules.

There are no archived packs.
