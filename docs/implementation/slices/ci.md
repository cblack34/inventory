# Slice plan — ci

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md)
- **Human approval:** repository owner, 2026-09-13, in the implementation-lead session that proposed this slice.
- **Final acceptance advanced:** "Run and verify" (`make check` exists and gates every PR); the Money criterion's pyright-strict requirement; the code-quality rule that frontend API types are generated and drift fails `make check`.

## Outcome

`make check` exists, defines every stage the definition of done lists except the end-to-end smoke test, runs green locally and in GitHub Actions on every pull request, and the build pack records the decisions made when this slice was approved.

## Why this slice is next

The workflow doc mandates CI bootstrap as the first code-bearing delivery unit, and every later PR is gated on `make check`. The repository has no code, no `Makefile`, and no CI. Nothing else can be integrated safely before this exists.

## Scope

### In scope

- Build-pack amendments decided on 2026-09-13: per-slice delivery topology, deferred Playwright stage, `/api/v1` prefix and REST resource map, library-first preference, dependency license policy, `src/inventory` and `src/web` layout.
- Root uv project with ruff, pyright strict, pytest, and a FastAPI app factory exposing only `GET /api/v1/health`.
- `src/web` Vite React TypeScript scaffold with Biome, tsc, vitest, and the production build.
- OpenAPI type generation from `app.openapi()` in-process, committed output, drift check.
- `Makefile` as the single definition of `make check`; GitHub Actions running it on every PR.

### Out of scope

- Any domain rule, SQLAlchemy model, or Alembic migration.
- `make e2e` and Playwright; these arrive with the login-and-home slice.
- Tailwind, shadcn/ui, React Router, TanStack Query, react-hook-form, zod; each arrives with the first screen that needs it.
- Container, Compose, backup, deployment notes.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| AGENTS.md definition of done | Creates `make check` with every listed stage except e2e, which AGENTS.md now defers to the login-and-home slice. |
| workflow.md CI bootstrap | Ships `.github/workflows/ci.yml` running `make check` on every PR. |
| code-quality.md generated frontend types | Generation script and drift check exist from the first frontend commit. |
| acceptance.md Money, pyright strict | pyright strict is configured before any typed field exists. |
| build-brief.md architecture boundaries | Records `/api/v1` and the resource map so later slices build one API shape. |

## Gates and dependencies

### Hard gates

- None. No research gate blocks tooling.

### Sequencing recommendations

- Docs first, so the other leaves follow amended rules. Python before web, because the web leaf extends the `Makefile` and workflow the Python leaf creates.

## Architecture and contracts

- **Affected seams:** repository layout, verification commands, CI. No domain or persistence code.
- **Public contracts:** `GET /api/v1/health` is the only route and may be removed later. The `/api/v1` prefix and resource map become an architecture contract in the build brief.
- **Data and migration considerations:** none.

## High-level approach

Three leaf PRs into `slice/ci`: documentation amendments, the Python toolchain and CI workflow, then the frontend toolchain and type generation. Each leaf is reviewed per the workflow's reviewer ladder (Copilot, requested explicitly on leaf PRs; `review-pr` as fallback) and merged into the spine by the implementation lead once green. The spine PR to `main` carries `Closes` references and stops for the owner to merge.

## Verification

- `make check` exits zero locally on the spine head, and in CI on each leaf PR's merge ref (CI never runs against the spine's own head; see workflow.md).
- Editing the generated types file by hand makes `make check` fail.
- Every stage AGENTS.md lists for `make check` is present and none is a no-op.
- Repository definition-of-done commands remain mandatory; `make e2e` is deferred by the AGENTS.md amendment in this slice.

## Risks and stop conditions

- Copilot review does not post on a leaf PR within a reasonable wait after an explicit request: re-request once, then fall back per workflow.md.
- A tool's current release conflicts with pyright strict or Biome defaults: fix configuration inside the leaf; stop if it requires a substitution from the tech-stack doc.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#2](https://github.com/cblack34/inventory/issues/2) — ci/docs: slice plan and build-pack amendments | Record approved decisions before code follows them | None |
| [#3](https://github.com/cblack34/inventory/issues/3) — ci/python: uv project, ruff, pyright, pytest, Makefile, GitHub Actions | Python stages of `make check` and the CI workflow | #2 |
| [#4](https://github.com/cblack34/inventory/issues/4) — ci/web: Vite scaffold, Biome, tsc, vitest, build, OpenAPI type generation | Frontend stages and the drift check | #3 |

## Delivery shape

- **Topology:** per-slice spine with leaf PRs.
- **Branch or spine:** `slice/ci`; leaves `ci/docs`, `ci/python`, `ci/web`.
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
