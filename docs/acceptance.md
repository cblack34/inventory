# Final Acceptance and Verification

The active scope is complete when every criterion below holds and every required command passes. Tactical replanning may derive additional slice checks but may not weaken or replace this contract.

## Run and verify

```bash
make check
make e2e
```

Both exit zero on the completed spine. `make check` covers ruff, pyright, pytest, Biome, tsc, vitest, and the production frontend build. `make e2e` builds the frontend, starts the API against a temporary SQLite file, and runs the Playwright smoke test. Their definitions live only in the `Makefile`.

## Ingredients and recipes

- [ ] An ingredient has a name, a free-text unit label, and a current price in cents. Editing the price on the ingredient changes the computed cost of every recipe that uses it.
- [ ] A recipe has a name, shelf life in days, ingredient lines with quantities, and one or more sizes each with portion weight, sale price in cents, and typical yield count. A size with price zero is accepted.
- [ ] The recipe screen shows the computed cost per size from current ingredient prices and typical yield. _Automated check:_ API returns per-size cost that matches the cost-split rule in `data-model.md` for a recipe with three sizes of different weights.

## Bake

- [ ] Recording a bake requires a recipe, date, and actual count per size, with expiration prefilled as date plus shelf life and editable.
- [ ] WHEN a bake is recorded, the batch stores total cost and per-size unit cost computed from ingredient prices at that moment, and a movement per size moves the counted units from Production to Kitchen. _Automated check:_ `|Σ (unit_cost × count_made) − batch_cost| ≤ number of sizes` cents (exact equality is not achievable for every yield; see [`data-model.md`](data-model.md)).
- [ ] WHEN an ingredient price changes after a bake, that batch's stored costs are unchanged. _Automated check:_ non-negotiable 2.
- [ ] WHEN all counts are zero, the bake is rejected.

## Locations

- [ ] Kitchen, Sold, Waste, Sampled, and Production exist after migration and cannot be deleted or renamed through the API.
- [ ] A user can create, rename, and deactivate a stand or a market. Deactivating a location with units on hand is rejected with the on-hand listed.

## Ledger, stock, and FIFO

- [ ] There is no API route that updates or deletes a movement, and no API route that deletes a visit. Voiding via "undo last visit" is the only lifecycle change to a visit, and it never removes or edits the visit's original movements. _Automated check:_ OpenAPI document contains no PUT, PATCH, or DELETE on the movements resource and no DELETE on the visits resource; a test voids a visit and asserts its original movement rows are unchanged in the database; ORM relationships from visit and batch to movement carry no cascading delete.
- [ ] On-hand per location, recipe, size, and batch is computed from movements. _Automated check:_ after a sequence of movements, the stock endpoint equals an independent fold over the movement list.
- [ ] Any removal of units from a location takes from the batch with the earliest expiration first and may span batches. The request carries recipe, size, and count only. _Automated check:_ two batches with different expirations; removing more than the older batch holds drains it first and takes the remainder from the newer.
- [ ] WHEN a removal exceeds on-hand at that location, the whole request is rejected and the response names location, recipe, size, on-hand, and requested. No partial movement is written.

## Stand visit

- [ ] The form lists every recipe and size currently on hand at the stand with inputs for counted, tossed, pulled to kitchen, and a separate list of kitchen stock with an input for added to stand, plus cash collected.
- [ ] WHEN the visit is saved, units missing since the last visit move to Sold for priced sizes and to Sampled for zero-price sizes, tossed units move to Waste, pulled units move to Kitchen, added units move from Kitchen to the stand, and all movements reference the visit.
- [ ] WHEN a counted value exceeds on-hand, the visit is rejected with the offending recipe and size named.
- [ ] WHEN tossed plus pulled exceeds counted for a size, the visit is rejected with that size named.
- [ ] The saved visit shows expected cash, actual cash, and the difference.

## Market visit

- [ ] The form lists kitchen stock with an input for taken, then for each taken size inputs for returned and tossed, with sample-size returned prefilled to zero and editable, plus revenue total and fee.
- [ ] WHEN the visit is saved, taken units move from Kitchen to the market, missing units move to Sold or Sampled by the price rule, tossed units to Waste, returned units to Kitchen, and all movements reference the visit.
- [ ] WHEN returned plus tossed exceeds taken for a size, the visit is rejected with that size named.
- [ ] The saved visit shows expected revenue from units sold next to the entered revenue.

## Profit

- [ ] Every saved visit shows profit equal to revenue minus fee minus the frozen cost of units sold, wasted, and sampled during it, with those three costs on separate lines. _Automated check:_ a fixture with known batch costs, a mixed visit, and an asserted profit in cents.
- [ ] The home screen lists past visits with date, location, revenue, and profit, newest first.

## Home screen and expiration

- [ ] Stock is shown grouped by location, then recipe and size, with counts. Batches expiring within seven days are highlighted; expired batches are flagged distinctly.
- [ ] A toss action on kitchen stock takes recipe, size, and count and records Waste by FIFO.
- [ ] Nothing moves to Waste without a user action.

## Corrections

- [ ] "Undo last visit" appends a reversing movement for every movement the visit created, marks the visit voided, and leaves the original movements in place. Stock afterward equals stock before the visit. _Automated check:_ stock snapshot before equals snapshot after undo.
- [ ] A manual movement form accepts any from and to location, including out of Sold, Waste, or Sampled, with recipe, size, and count, by FIFO.

## Login and deployment

- [ ] WHEN not logged in, every route except the login page redirects to login and every API route except the login endpoint returns 401.
- [ ] Logging in with the configured password sets a signed session cookie. A wrong password does not.
- [ ] `docker compose up` on a clean machine starts one container serving the app on a documented port with the SQLite file on a named volume, and the login page loads.
- [ ] Deployment notes document the backup command and where the backup goes. Human verification: the user runs the backup command once against the deployed instance and confirms a copy exists.
- [ ] Every screen is usable on a 375 px wide viewport without horizontal scrolling. Human verification: the user opens each screen on a phone.

## Money

- [ ] No money field in the domain, ORM, or API schema is a float. _Automated check:_ pyright passes with money types declared as `int`; a test asserts the OpenAPI document declares every field ending in `_cents` as integer.
- [ ] Every quantity field (counted, tossed, pulled, added, taken, returned, count made per size) and every money field (price, fee, revenue) is rejected if negative. _Automated check:_ Pydantic schemas declare these fields with a non-negative constraint; a test posts a negative value for one field from each family and asserts a 422 response.

## Research and decision gates

- **Hosting target** (VPS with Caddy or AWS Lightsail Containers). Not required for acceptance; the Compose criterion above is sufficient. Must be decided before the first real deployment.

## Deliberately excluded

Per the brief's out-of-scope section: Square API, Found import, ingredient stock, price history, unit conversion, multi-user, editing or deleting history, labor and mileage costing, offline or in-market use. An agent must not count these as required or build adapters for them.
