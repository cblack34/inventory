# Final Acceptance and Verification

The active scope is complete when every criterion below holds and every required command passes. Tactical replanning may derive additional slice checks but may not weaken or replace this contract.

## Run and verify

```bash
make check
make e2e
```

Both exit zero on the completed spine. `make check` covers ruff, pyright, pytest, Biome, tsc, vitest, the production frontend build, and regenerating the frontend API types from the OpenAPI schema with a failure if the committed output differs. `make e2e` builds the frontend, starts the API against a temporary SQLite file, and runs the Playwright smoke test. Their definitions live only in the `Makefile`.

## Ingredients and recipes

- [ ] An ingredient has a name, a free-text unit label, and a current price in cents. Editing the price on the ingredient changes the computed cost of every recipe that uses it.
- [ ] A recipe has a name, a non-negative shelf life in days, ingredient lines with non-negative quantities, and one or more sizes each with a strictly positive portion weight, a non-negative sale price in cents, and a non-negative typical yield count. A size with price zero is accepted. A recipe is rejected if the total typical-yield weight (Σ portion weight × typical yield count across sizes) is zero, since recipe cost cannot be split by weight in that case.
- [ ] The recipe screen shows the computed cost per size from current ingredient prices and typical yield. _Automated check:_ API returns per-size cost that matches the cost-split rule in `data-model.md` for a recipe with three sizes of different weights.

## Bake

- [ ] Recording a bake requires a recipe, date, and actual count per size, with expiration prefilled as date plus shelf life and editable. The editable expiration must be on or after the baked date; an earlier expiration is rejected. Both dates may be in the past for a historical bake, as long as expires ≥ baked date. _Automated check:_ a bake request with expiration before the baked date returns 422.
- [ ] WHEN a bake is recorded, it creates a `bake` entry, the batch stores total cost and per-size unit cost computed from ingredient prices at that moment and references that entry, and a movement per size moves the counted units from Production to Kitchen. _Automated check:_ `|Σ (unit_cost × count_made) − batch_cost| ≤ ceil(total_units / 2)` cents, and a 1010-cent single-size bake of 20 units yields a unit cost of 51 (exact equality is not achievable for every yield; see [`data-model.md`](data-model.md)).
- [ ] WHEN an ingredient price changes after a bake, that batch's stored costs are unchanged. _Automated check:_ non-negotiable 2.
- [ ] WHEN all counts are zero, the bake is rejected.
- [ ] Batch cost fields are immutable: no API route updates a batch, and a direct attempt to change a cost field is rejected. _Automated check:_ OpenAPI document exposes no PUT or PATCH on the batches resource; a test attempting a direct ORM update of a cost field is rejected (illustrative: a SQLAlchemy validator or a DB trigger — the lead chooses).
- [ ] Undo of a bake follows the same current-balance rule as any entry: it is rejected only if reversing would drive the batch's Kitchen on-hand negative, so units that left and came back do not block it. A voided bake's batch is excluded from stock and recipe cost history. _Automated check:_ bake, move units out of Kitchen, assert undo is rejected; move them back, assert undo succeeds and stock matches the pre-bake snapshot.

## Locations

- [ ] Kitchen, Sold, Waste, Sampled, and Production exist after migration and cannot be deleted, renamed, or deactivated through the API. _Automated check:_ attempting to deactivate a built-in location is rejected.
- [ ] A user can create, rename, and deactivate a stand or a market. Deactivating a location with units on hand is rejected with the on-hand listed (on-hand must be zero to deactivate). An inactive stand or market rejects new visits and manual moves into it and is hidden as a destination in the visit and manual-move pickers. Moves out of an inactive location remain allowed so stock restored there by undo can be recovered, and a location can be reactivated at any time. There is no API route that deletes any location, built-in or user-created; user locations are deactivate-only. _Automated check:_ OpenAPI document contains no DELETE on the locations resource; ORM relationships from location to movement carry no cascading delete; a visit at, or a manual move into, an inactive location returns 422; a manual move out of an inactive location succeeds; undo into an inactive location still succeeds when the balance check passes; reactivating a location succeeds.
- [ ] Location create accepts kind `stand` or `market` only; kind is immutable on update. _Automated check:_ a create request naming kind `production`, `kitchen`, `sold`, `waste`, or `sampled` returns 422; an update request attempting to change kind on any location returns 422.

## Ledger, stock, and FIFO

- [ ] There is no API route that updates or deletes a movement or an entry, and no API route that updates (other than undo) or deletes a visit or a batch. Voiding via undo is the only lifecycle change to an entry, and it never removes or edits the original entry's movements. A recipe or size referenced by any batch or movement, and an ingredient referenced by any recipe line, cannot be deleted either; there is no DELETE route for recipes, sizes, or ingredients, only deactivate-only or restrict-on-reference behavior, and this no-cascade check covers recipe, size, and ingredient the same as entry, visit, batch, location, and movement. _Automated check:_ OpenAPI document contains no PUT, PATCH, or DELETE on the movements, entries, visits, or batches resources — undo is its own endpoint, not an entry update; a test voids an entry and asserts its original movement rows are unchanged in the database; no ORM relationship among entry, visit, batch, location, movement, recipe, and size cascades deletes; the OpenAPI document contains no DELETE on the recipes or sizes resources.
- [ ] On-hand per location, recipe, size, and batch is computed from movements. _Automated check:_ after a sequence of movements, the stock endpoint equals an independent fold over the movement list.
- [ ] Any removal of units from a location takes from the batch with the earliest expiration first and may span batches. Recipe, size, and count are the only batch-selection fields the user provides; a manual move additionally names its source and destination locations. _Automated check:_ two batches with different expirations; removing more than the older batch holds drains it first and takes the remainder from the newer.
- [ ] WHEN a removal exceeds on-hand at that location, the whole request is rejected and the response names location, recipe, size, on-hand, and requested. No partial movement is written.
- [ ] Saving a visit is one transaction: every constraint for that visit type (non-negativity, counted ≤ on-hand, tossed + pulled ≤ counted, returned + tossed ≤ taken, FIFO availability for every removal) is checked before any movement row is written, and a rejected visit writes no rows at all. A visit's location must be an active stand or market; any other location kind, or an inactive stand or market, is rejected. _Automated check:_ a market visit with `returned + tossed > taken` is rejected and the database has zero Visit, Entry, and Movement rows for that submission, including the Kitchen-to-market `taken` movement; a visit posted against Kitchen, Production, Sold, Waste, Sampled, or an inactive stand/market returns 422.

## Stand visit

- [ ] The form lists every recipe and size currently on hand at the stand with inputs for counted, tossed, pulled to kitchen, and a separate list of kitchen stock with an input for added to stand, plus cash collected.
- [ ] WHEN the visit is saved, units missing since the last visit move to Sold for priced sizes and to Sampled for zero-price sizes, tossed units move to Waste, pulled units move to Kitchen, added units move from Kitchen to the stand, and all movements reference the visit.
- [ ] WHEN a counted value exceeds on-hand, the visit is rejected with the offending recipe and size named.
- [ ] WHEN tossed plus pulled exceeds counted for a size, the visit is rejected with that size named.
- [ ] A stand visit has no fee: the API rejects a non-zero fee for a stand visit and stores `fee_cents = 0`. _Automated check:_ posting a stand visit with a non-zero fee returns 422.
- [ ] The saved visit shows expected revenue, cash collected, and shrink (`shrink_cents = expected_revenue_cents − revenue_cents`, positive when short). Expected revenue is computed from size prices at save time and stored on the visit; a later price change never alters a previously saved visit's expected revenue. _Automated check:_ save a visit, change the size's price, reload the visit, and assert expected revenue is unchanged; assert shrink is positive for a visit where revenue is less than expected revenue.

## Market visit

- [ ] The form lists kitchen stock with an input for taken, then for each taken size inputs for returned and tossed, with sample-size returned prefilled to zero and editable, plus revenue total and fee.
- [ ] WHEN the visit is saved, taken units move from Kitchen to the market, missing units move to Sold or Sampled by the price rule, tossed units to Waste, returned units to Kitchen, and all movements reference the visit.
- [ ] WHEN returned plus tossed exceeds taken for a size, the visit is rejected with that size named.
- [ ] The saved visit shows expected revenue from units sold next to the entered revenue, computed from size prices at save time and stored on the visit as `expected_revenue_cents` so a later price change never alters it. The `expected_revenue_cents − revenue_cents` difference is shown but is not labeled shrink for a market visit.

## Profit

- [ ] Every saved visit shows profit equal to revenue minus fee minus the frozen cost of units sold, wasted, and sampled during it, with those three costs on separate lines. _Automated check:_ a fixture with known batch costs, a mixed visit, and an asserted profit in cents.
- [ ] The home screen lists past entries (bakes, visits, manual operations) with date and location, newest first, visits showing revenue and profit, and each non-voided entry with an undo action. A voided visit is listed as voided with no profit figure and is excluded from any profit or revenue totals.

## Home screen and expiration

- [ ] Stock is shown grouped by inventory location (Kitchen, each stand, each market), then recipe and size, with counts. Production, Sold, Waste, and Sampled are terminal locations and never appear in stock views. Batches expiring within seven days are highlighted; expired batches are flagged distinctly.
- [ ] A toss action on kitchen stock takes recipe, size, and count and records Waste by FIFO.
- [ ] Nothing moves to Waste without a user action.

## Corrections

- [ ] Undo targets one original entry (a bake, a visit, or a manual operation) and appends a reversal entry whose movements each carry `reverses_movement`, set to the exact original row's id, in reverse creation order, targeting the same batch as the original movement; the original entry is marked voided. The original movements remain in place. Stock afterward equals stock before the entry. _Automated check:_ stock snapshot before equals snapshot after undo.
- [ ] WHEN a later movement has already consumed, at the same inventory location (Kitchen, a stand, or a market), the batch a reversal into that location would need to restore, undo is rejected instead of driving on-hand negative there. Reversals whose source is Sold, Waste, or Sampled need no such check. _Automated check:_ a manual move drains a batch after a visit, then undo of that visit is rejected.
- [ ] WHEN an entry is already voided, undo of it is rejected, and a duplicate manual removal cannot be used to bypass that: undoing the same movement row twice is rejected by the uniqueness of `reverses_movement`, not by matching quantity or batch. _Automated check:_ two identical manual removals (same recipe, size, quantity, and resulting batch) produce two distinct movement rows; undoing the first succeeds once and a second undo of that same row is rejected while the second removal's row is untouched.
- [ ] WHEN undo is rejected for any reason, no reversal rows are written and nothing about the original entry changes: a non-voided entry stays unvoided and an already-voided entry stays voided. _Automated check:_ trigger a rejected undo and assert the movement table and the entry's voided flag are both unchanged.
- [ ] A manual movement form moves units between inventory locations, or from an inventory location to Waste, or to Sold or Sampled by the price rule (priced sizes to Sold, zero-price sizes to Sampled), with recipe, size, and count, by FIFO. Its destination may never be a market. Production's only outflow is the bake movement; Sold, Waste, and Sampled receive units from visits and manual removals and lose units only through undo. _Automated check:_ a manual move naming a market as the destination is rejected.
- [ ] A manual operation can be undone with the same rules as a visit: same batch, all or nothing, rejected if already undone. _Automated check:_ toss then undo restores the stock snapshot.

## Login and deployment

- [ ] WHEN not logged in, an unauthenticated request to an application route redirects to login and an unauthenticated request to an API route other than the login endpoint returns 401. The login page and the static asset bundle (the built JS/CSS and other Vite output it needs to render) stay public and are never redirected.
- [ ] Logging in with the configured password sets a signed session cookie with `HttpOnly`, `SameSite=Strict`, and `Secure` outside local development. A wrong password does not set a cookie. `SameSite=Strict` on this JSON-only API is the CSRF control; no separate CSRF token is required.
- [ ] `docker compose up` on a clean machine starts one container serving the app on a documented port with the SQLite file on a named volume, and the login page loads.
- [ ] Deployment notes document the backup command and where the backup goes. Human verification: the user runs the backup command once against the deployed instance and confirms a copy exists.
- [ ] Every screen is usable on a 375 px wide viewport without horizontal scrolling. Human verification: the user opens each screen on a phone.

## Money

- [ ] Every money, weight, and quantity field in the domain, ORM, and API schema is exactly `int`; no field anywhere is `float`, `Decimal`, or a numeric string. _Automated check:_ pyright strict passes; a test enumerates every SQLAlchemy column and Pydantic field whose name ends in `_cents`, `_weight`, `_count`, or `quantity` and asserts the exact type is `int` (Integer), and separately asserts no column or field anywhere is `float` or `Decimal`; a test asserts the OpenAPI document declares every such field as `integer`.
- [ ] Every quantity field (counted, tossed, pulled, added, taken, returned, count made per size) and every money input field (ingredient price, sale price, fee, revenue) is rejected if negative. Derived money values (profit, the expected-versus-actual cash difference) are signed and may be negative. _Automated check:_ Pydantic schemas declare the input fields with a non-negative constraint; a test posts a negative value for one field from each family and asserts a 422 response; a fixture with fee exceeding revenue asserts a negative profit is returned, not rejected.

## Research and decision gates

- **Hosting target** (VPS with Caddy or an AWS Lightsail instance with an attached block disk; AWS Lightsail Container Service and AWS App Runner are rejected because neither offers a persistent disk for SQLite). Not required for acceptance; the Compose criterion above is sufficient. Must be decided before the first real deployment.

## Deliberately excluded

Per the brief's out-of-scope section: Square API, Found import, ingredient stock, price history, unit conversion, multi-user, editing or deleting history, labor and mileage costing, offline or in-market use. An agent must not count these as required or build adapters for them.
