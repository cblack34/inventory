# Slice plan — web-entry

## Strategic source

- **Active build pack:** [`AGENTS.md`](../../../AGENTS.md), [`docs/build-brief.md`](../../build-brief.md), [`docs/data-model.md`](../../data-model.md), [`docs/tech-stack.md`](../../tech-stack.md), [`docs/acceptance.md`](../../acceptance.md), [`docs/engineering/workflow.md`](../../engineering/workflow.md), [`docs/engineering/code-quality.md`](../../engineering/code-quality.md).
- **Human approval:** repository owner, 2026-09-15, after slice `deploy-local` merged.
- **Final acceptance advanced:** Ingredients and recipes (all three criteria); Bake (form with prefilled, editable expiration and counts); Locations (create, rename, deactivate and reactivate; inactive hidden from pickers); Stand visit and Market visit (form shape and prefill criteria); Profit (saved visit shows revenue, fee, three cost lines, profit); Corrections (manual movement form); Login and deployment (the 375 px human check extends to every screen).

## Outcome

Every data-entry screen the brief names: ingredients, locations, and recipes with sizes and the live cost estimate; the bake form; the stand and market visit forms with their prefills and a saved-visit view showing expected versus actual and profit; and the manual movement form. With the home screen already shipped, the owners can run the business from the app. Only hosting remains after this slice.

## Why this slice is next

The brief's step 4 in full. The shell, typed client, and home screen exist; every route these screens call is shipped, typed, and tested; the container is ready to receive real data. Real entry is what exposes model mistakes, so finishing the screens is the shortest path to the definition of done's last line: the co-owner records a real stand visit and a real market visit from a phone.

## Scope

### In scope

- Catalog screens: ingredients (list, create, edit, active toggle), locations (list, create stand or market, rename, deactivate and reactivate), recipes (list, create, edit lines and sizes, per-size cost estimate from the API).
- Bake form: recipe, baked date, expiration prefilled from shelf life and editable, count per size prefilled from typical yield; result shows the frozen costs.
- Manual movement form: source, size, destination limited by the data-model rules (active inventory location that is not a market, or Waste, Sold, Sampled), count.
- Stand visit form: rows for stock at the stand with counted prefilled to on-hand, tossed, pulled; Kitchen rows with added; cash collected. Market visit form: Kitchen rows with taken; returned and tossed per taken size with returned prefilled to zero for zero-price sizes and required for priced ones; revenue and fee. Saved-visit view with expected versus actual, the difference (labelled shrink for stands), and profit with the three cost lines.
- Routes and nav links in the shell; history rows link to saved visits.

### Out of scope

- Any API, schema, or Python change; backlog [#37](https://github.com/cblack34/inventory/issues/37).
- Logout, password change, multi-user.
- Caddy, TLS, hosting; the CI job split (waits for a slice that opens `ci.yml`).
- Square, Found, price history, ingredient stock, unit conversion, editing or deleting history.

## Strategic traceability

| Strategic requirement or criterion | How this slice advances it |
| --- | --- |
| Entry is counting, not bookkeeping; every visit screen is a list of number inputs | Visit, bake, and move forms are stacked numeric rows with the acceptance prefills. |
| Non-negotiable 3: the user never picks a batch | Bake, move, and visit forms carry recipe, size, count, and locations only. |
| The frontend never derives inventory or profit | Forms prefill from `GET /stock` and `GET /recipes`; the saved view renders `VisitRead` as returned; the only client arithmetic is zod's cross-field checks and the expiration date prefill. |
| Sample is not a concept in code | A zero-price size is just `price_cents === 0`; the market form's returned prefill keys off that. |
| Non-negotiable 4: integer cents | Inputs are integers; any dollars entry is parsed to cents without float multiplication. |
| Locations are data | Stands and markets are created and edited as rows; built-ins are shown but never editable. |
| Frontend types are generated | All screens type against `types.ts`; the file is untouched. |

## Gates and dependencies

### Hard gates

- None beyond `main` at b3c65d8. Each leaf seeds its walkthrough through the API with curl, so no leaf waits on another.

### Sequencing recommendations

- Three leaves in parallel on separate worktrees; they share only route and nav lines in `App.tsx` and `Layout.tsx`, which the lead reconciles at merge.

## Architecture and contracts

- **Affected seams:** `src/web/src/features/*`, `App.tsx`, `Layout.tsx`, one link in the history section. No Python, no schema, no Makefile or CI.
- **Public contracts:** the `/api/v1` contract is consumed, not changed.
- **Data and migration considerations:** none.

## High-level approach

Three leaf PRs into `slice/web-entry`, each delegated to a standard-tier agent with its issue as the packet, run in parallel in isolated worktrees with a port rule so their local API instances never collide. Each leaf verifies through the real UI with Playwright at a 375 px viewport against a curl-seeded API and attaches screenshots. On the spine, one end-to-end walkthrough through the screens (ingredient, recipe, bake, stand visit, market visit, manual toss, undo) with profit matched against the API. Copilot is requested by hand on each leaf; the spine PR to `main` gets it automatically.

## Verification

- `make check` and `make e2e` exit zero on every leaf and on the spine; the smoke test is unchanged.
- Per-leaf Playwright walkthroughs as specified in each issue, with screenshots in the PR.
- Spine walkthrough: from an empty database, through the screens only, create an ingredient and a recipe with a priced and a zero-price size, bake, move units to a stand, record a stand visit with a short cash count, record a market visit with a return and a toss, toss from Kitchen, undo the toss; every displayed number equals the corresponding API response.
- The owner checks each screen at 375 px on a phone.
- Repository definition-of-done commands remain mandatory.

## Risks and stop conditions

- A visit form needs something `GET /stock` or `GET /recipes` does not return; stop and record it rather than deriving it client-side.
- react-hook-form field arrays over stock rows with per-row zod bounds are fiddly; keep each row's schema data-driven from the fetched on-hand, and stop if a correct schema needs a new dependency.
- Three leaves editing `App.tsx` and `Layout.tsx`: additions only, one line each, no reordering; the lead resolves the trivial conflicts.
- Dollars entry: if a float sneaks into a cents conversion, that is a non-negotiable 4 violation; use string parsing and a vitest.

## Execution issues

GitHub issues are the WIP tracker and source of task-level detail.

| Issue | Purpose | Dependencies |
| --- | --- | --- |
| [#42](https://github.com/cblack34/inventory/issues/42) — web-entry/catalog: ingredients, locations, recipes with sizes and live cost estimate | Catalog management screens | None |
| [#43](https://github.com/cblack34/inventory/issues/43) — web-entry/bake-move: bake form with prefilled expiration and counts; manual movement form | Recording batches and manual moves | None |
| [#44](https://github.com/cblack34/inventory/issues/44) — web-entry/visits: stand and market visit forms with prefills; saved-visit view with profit | The product's core entry screens and the profit answer | None |

## Delivery shape

- **Topology:** per-slice spine with leaf PRs.
- **Branch or spine:** `slice/web-entry`; leaves `web-entry/catalog`, `web-entry/bake-move`, `web-entry/visits`.
- **Final PR:** [#48](https://github.com/cblack34/inventory/pull/48).
- **Human merge gate:** Only the human may physically merge the final PR to `main`. Agents must stop when it is ready.

## Amendments

None.

## Delivery record

Complete once when the final PR is ready for human merge. Do not use this section for WIP status.

- **Outcome:** Delivered 2026-09-15. `src/web/src/features/catalog/` (ingredients, locations, recipes with sizes and the API's estimated unit cost), `features/bake/` (bake form with expiration prefilled from shelf life and counts from typical yield), `features/movements/` (manual move with the data-model destination rules), and `features/visits/` (stand and market forms with the acceptance prefills, a saved-visit view with expected versus actual, Shrink or Difference, and profit with three cost lines); routes and a wrapping nav in the shell; history cards link to saved visits. One shared `lib/dollars.ts` parses dollars to cents by string math with the API's bound.
- **Verification:** `make check` exit 0 on code head e810803 (vitest 42). `make e2e` was not run locally on the spine because the owner's Compose container held port 8000; CI runs it on the spine PR, and the leaf PRs' CI ran it. A full walkthrough through the real screens at 375×812 on a fresh database compared 37 screen values with the API and all matched (recipe costs, batch total and unit costs, stand visit expected 300 / shrink 50 / profit 136, market visit expected 600 / difference 50 / profit -384, priced `returned` empty and zero-price `returned` prefilled 0, toss and undo restoring Kitchen stock, Expired badge from a back-dated bake); every screen measured `scrollWidth === 375`. Leaf evidence on [#45](https://github.com/cblack34/inventory/pull/45), [#46](https://github.com/cblack34/inventory/pull/46), [#47](https://github.com/cblack34/inventory/pull/47); issues [#42](https://github.com/cblack34/inventory/issues/42), [#43](https://github.com/cblack34/inventory/issues/43), [#44](https://github.com/cblack34/inventory/issues/44) carry the trail. The only commit after the code head is this record.
- **Deviations:** Two leaves created `components/ui/select.tsx` with different APIs; the native one was renamed `NativeSelect` on the spine. The visits leaf's duplicate dollars helper was folded into `lib/dollars.ts` on the spine. After #45 merged, the other two leaves conflicted with the spine in `App.tsx` and `Layout.tsx`; CI runs on the PR merge ref, so it silently stopped running on their pushes until each leaf was re-synced (the shared-file "append only" rule prevents semantic conflicts but not textual ones). Copilot claims pushed back with evidence: shadcn's `data-checked`/`data-open` selectors are custom variants over Radix `data-state`; the create-mode Remove size control deletes nothing persisted. The bake date defaults from the browser clock rather than the business timezone; deferred, since a fix needs an API endpoint. The spine PR's first Copilot pass added seven items, all applied on the spine: `addDays` returns null out of range and the bake prefill falls back, one shared `parseRouteId` for visit and recipe routes, the bake form freezes its recipe snapshot, and every form loader blocks on a query error only when it has no cached data. Its second pass added two date edge cases (years 0–99 and past 9999 in `addDays`), also applied.
- **Unresolved gates or risks:** Hosting target open. Owner's phone check of every screen at 375 px. Backlog [#37](https://github.com/cblack34/inventory/issues/37) untouched. Deferred: business-date endpoint for the bake prefill; the CI job split noted for the deployment work.
- **Final PR:** [#48](https://github.com/cblack34/inventory/pull/48).
- **Merge state:** Ready for the human to merge once CI (including `make e2e`) and the Copilot pass are green; agents do not merge to `main`.
