# Acceptance audit — final

Audited at `finish/api` HEAD `b6227ce` (worktree at
`.claude/worktrees/finish-api`), 2026-09-15. Every criterion in
`docs/acceptance.md` is traced below to the test(s) or code that pin it.
`make check` and `make e2e` were not run; the two facts about their
contents (below) were confirmed by reading the `Makefile` directly, and a
handful of tests were opened in full to confirm they assert what the
criterion claims rather than merely mentioning a token.

Extended on `finish/audit` HEAD `1310c98` (worktree at
`.claude/worktrees/finish-audit`), 2026-09-15: the five gaps this first
pass left as narrower-than-described automated checks each got a pinning
test (`tests/db/test_undo.py`, `tests/api/test_startup.py`,
`tests/api/test_ledger_openapi.py`, `tests/domain/test_no_floats.py`),
and their rows below now read `none`. `make check` exited 0 on that head
(464 tests, up from 458), and again on the leaf's final head 0235836 and
its successor after three Copilot passes (470 tests); `make e2e` was not
run for this docs-and-tests leaf (CI ran it green on every head).

Extended a third time addressing Copilot's review on
`cblack34/inventory#53`: the Money row below closed the three remaining
coverage gaps that review found (`EntryRead.revenue_cents`/`profit_cents`
missing from `tests/api/test_ledger_openapi.py`'s enumeration,
`VisitPlan.expected_revenue_cents` and `_Leg.quantity` missing from
`tests/domain/test_no_floats.py`'s, and no test walking Pydantic
`model_fields` directly — added as
`tests/api/test_pydantic_money_fields.py`).

Row/section count: the table below traces **47 criterion rows across
the 11 product sections that carry one** (Ingredients and recipes
through Money; `Run and verify` and `Gaps and human items` are prose,
not criterion tables), counted directly off the `|`-delimited rows
under each `##` heading. This leaf's own PR description instead
claimed "39 rows over 10 sections", which undercounts both figures;
that description is corrected separately.

## Run and verify

Both facts hold by inspection of the `Makefile`:

- `make check` = `check-python` (`ruff check`, `ruff format --check`,
  `pyright`, `pytest`) + `check-web` (Biome `lint`, `tsc` `typecheck`,
  `vitest` `test`, production `build`) + `check-types` (regenerates
  `openapi.json` from `app.openapi()`, runs `openapi-typescript`, diffs
  against the committed `src/web/src/api/types.ts`, fails on any diff).
  Every stage `docs/acceptance.md`'s "Run and verify" lists is present
  exactly once.
- `make e2e` = `npm run build` (frontend), `playwright install chromium`,
  `alembic upgrade head` against a fresh `mktemp -d` SQLite file, then
  `npm run test:e2e` (Playwright's own `webServer` starts
  `python -m inventory` against that same file via `DB=$tmp/e2e.db`).
  Matches "builds the frontend, starts the API against a temporary
  SQLite file, and runs the Playwright smoke test" exactly.

## Ingredients and recipes

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Ingredient: name, unit label, price; price edit re-costs every recipe using it | Automated | `tests/api/test_ingredients.py::test_patch_ingredient_price_changes_every_recipe_using_it` | none |
| Recipe: name, shelf life, lines, sizes; size price 0 accepted; portion weight > 0; total typical-yield weight 0 rejected | Automated | `tests/api/test_recipes.py::test_zero_typical_total_weight_is_rejected` (rejection, `urn:inventory:problem:zero-weight`); `tests/api/test_recipes.py::test_cost_estimate_pins_round_half_up_boundary` (asserts `sizes["Small"]["price_cents"] == 0`, i.e. zero price accepted); field bounds structural in `src/inventory/api/schemas/catalog.py` (`portion_weight_g: PositiveCount` = `ge=1`, `price_cents: Cents` = `ge=0`, `typical_yield_count: Count` = `ge=0`) via `src/inventory/api/schemas/numbers.py` | none |
| Recipe cost-per-size from current prices/typical yield; 200-cent/50-20-10/yield-2 fixture → 63/25/13; pins `round_half_up` vs. banker's `round()` | Automated | `tests/api/test_recipes.py::test_cost_estimate_pins_round_half_up_boundary` (API); `tests/domain/test_costing.py::TestSplitUnitCosts::test_recipe_estimate_matches_pinned_acceptance_numbers` and `TestRoundHalfUp::test_rounds_half_up_not_to_even` (domain, explicitly contrasts `round_half_up(125,2)==63` vs. Python `round()`→62) | none |

## Bake

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Bake requires recipe/date/counts; expiration prefilled date+shelf-life, editable; expires < baked → 422; historical dates allowed | Automated + Structural | `tests/api/test_batches.py::test_expires_before_baked_is_rejected`; `tests/db/test_writes_bake.py::test_record_bake_rejects_expires_before_baked_and_writes_nothing`; prefill in `src/web/src/features/bake/BakeForm.tsx` (`expires: addDays(baked, recipe.shelf_life_days) ?? baked`, zod `.refine` enforcing `expires >= baked`); `addDays` unit-tested in `src/web/src/lib/dates.test.ts` | none |
| Bake creates entry+batch (frozen cost) + one movement/size Production→Kitchen; zero-count size writes no row; drift bound `≤ ceil(units/2)`; 1010¢/20-unit single size → 51; 1000¢ three-size 200/100/50 @ 2/4/2 → 222/111/56 | Automated | `tests/domain/test_costing.py::TestSplitUnitCosts::test_bake_single_size_matches_pinned_acceptance_number` (→51), `test_bake_three_sizes_matches_pinned_acceptance_numbers` (→222/111/56, and explicitly asserts the naive equal-split-by-count answer of 125 each is wrong); `TestUnitCostDriftBound::test_matches_ceiling_of_half_total_units` and `test_drift_never_exceeds_bound`/`test_drift_bound_holds_over_a_grid` (bound pinned over a fixture grid); API-level echo in `tests/api/test_batches.py::test_bake_cost_split_pins_the_1000_cent_three_size_fixture`; zero-count skip in `tests/db/test_writes_bake.py::test_record_bake_skips_zero_count_sizes` | none |
| Ingredient price change after bake leaves batch cost unchanged (non-negotiable 2) | Automated | `tests/api/test_batches.py::test_ingredient_price_change_after_bake_leaves_batch_unchanged`; `tests/db/test_writes_bake.py::test_record_bake_batch_cost_is_frozen_against_a_later_price_change` | none |
| All-zero counts rejected | Automated | `tests/api/test_batches.py::test_all_zero_counts_is_rejected`, `test_empty_counts_is_rejected`; `tests/db/test_writes_bake.py::test_record_bake_rejects_all_zero_counts_and_writes_nothing` | none |
| Batch cost fields immutable: no PUT/PATCH on batches; `BEFORE UPDATE` DB trigger rejects raw `UPDATE` of a cost column | Automated + Structural | `tests/api/test_ledger_openapi.py::test_no_put_patch_or_delete_on_any_ledger_resource` (OpenAPI shape); `tests/db/test_triggers.py::test_raw_update_of_batch_total_cost_is_rejected` and `test_raw_update_of_batch_size_unit_cost_is_rejected` (raw `UPDATE`, trigger fires); `test_raw_update_of_a_non_cost_batch_column_succeeds` (control case, non-cost column still writable) | none |
| Undo of a bake: rejected only if it would drive Kitchen negative; units that left and returned don't block it; voided batch excluded from stock/cost/profit | Automated | `tests/db/test_undo.py::test_undo_of_a_bake_checks_kitchen_balance_sequentially` — bakes, moves 10 out to a stand, asserts undo raises `InsufficientStock`, moves the 10 back, asserts undo now succeeds and `stock_after == stock_before_bake` | none |

## Locations

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| 5 built-ins exist after migration, immutable via API | Automated | `tests/db/test_migration.py::test_migration_seeds_exactly_the_five_builtin_locations`; `tests/api/test_locations.py::test_rename_or_deactivate_a_builtin_is_rejected` (both renamed and deactivated return 422, `location_name` echoed) | none |
| Create/rename/deactivate stand or market; deactivate-with-stock rejected naming on-hand; inactive rejects new visits/moves-in, hidden as picker destination; moves-out of inactive still allowed; reactivation works; no DELETE anywhere on locations; no cascading FK/relationship delete | Automated + Structural | `tests/api/test_locations.py::test_deactivate_a_stand_with_stock_is_rejected_naming_on_hand`, `test_deactivate_an_empty_stand_succeeds_and_can_be_reactivated`; `tests/api/test_movements.py::test_move_into_an_inactive_stand_is_rejected`, `test_move_out_of_an_inactive_stand_succeeds`; `tests/db/test_writes_manual_move.py::test_manual_move_into_an_inactive_stand_is_rejected`, `test_manual_move_out_of_an_inactive_stand_succeeds`; `tests/db/test_undo.py::test_undo_of_a_manual_move_that_lands_in_a_now_inactive_stand_succeeds` (drains a stand to zero, deactivates it, undoes the drain, and asserts the reversal still lands there and stock is restored); `tests/api/test_visits.py::test_stand_visit_at_an_inactive_stand_is_rejected`; `tests/db/test_visits.py::test_visit_locations_are_rejected_for_every_invalid_target` (parametrized over `inactive_stand`/`inactive_market` among other invalid targets); no-DELETE in `tests/api/test_catalog_openapi.py::test_no_delete_on_any_catalog_resource`; no-cascade in `tests/db/test_columns.py::test_no_relationship_cascades_deletes` and `test_no_foreign_key_cascades_deletes` (walks every mapper/table, not just locations) | "Hidden as a destination in the visit and manual-move pickers" is frontend picker behavior — not directly grep-confirmed as filtering by `active`. (Undo landing in an inactive location is now pinned by `test_undo_of_a_manual_move_that_lands_in_a_now_inactive_stand_succeeds`, above.) See "Gaps" below. |
| Location create accepts only `stand`/`market`; kind immutable on update | Automated | `tests/api/test_locations.py::test_create_with_a_builtin_kind_is_rejected` (parametrized over all 5 built-in kinds); `test_patch_cannot_change_kind` | none |

## Ledger, stock, and FIFO

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| No PUT/PATCH/DELETE on movements, entries, visits, or batches; no DELETE on recipes, sizes, or ingredients (ingredients deactivate-only, recipes and sizes permanent); undo is its own endpoint; original movements unchanged after void; no cascades anywhere | Automated | `tests/api/test_ledger_openapi.py::test_no_put_patch_or_delete_on_any_ledger_resource`, `test_undo_is_its_own_post_endpoint_not_an_entry_update`; `tests/api/test_catalog_openapi.py::test_no_delete_on_any_catalog_resource`; `tests/db/test_undo.py::test_undo_of_a_manual_toss_restores_stock_and_voids_with_reverses_movement_id` (voids original entry, links reversal via `reverses_movement_id`, stock round-trips), `test_undo_leaves_the_original_movement_rows_byte_for_byte_unchanged` (snapshots every column of the original toss's movement rows and its entry's `created_at` before undo, diffs the same rows after undo, and asserts the reversal's movement rows are new ids disjoint from the original's); `tests/db/test_columns.py::test_no_relationship_cascades_deletes`/`test_no_foreign_key_cascades_deletes` | none |
| On-hand computed from movements, matches independent fold | Automated | `tests/api/test_stock.py::test_stock_matches_an_independent_fold_over_the_movements_made` (own hand-rolled fold over raw `Movement` rows, deliberately not calling the ledger's own `on_hand`); `tests/domain/test_ledger.py::test_on_hand_matches_independent_fold_and_excludes_terminal_locations` | none |
| FIFO by earliest expiration, may span batches; ordering-by-baked-date/id would fail | Automated | `tests/domain/test_ledger.py::test_allocate_fifo_drains_the_earlier_expiring_batch_first_even_when_baked_later`; `tests/db/test_writes_manual_move.py::test_manual_removal_drains_the_earlier_expiring_batch_first_across_two_bakes` | none |
| Removals serialized; 10 on hand, two threads remove 6, exactly one succeeds, never negative | Automated | `tests/db/test_concurrency.py::test_two_concurrent_manual_removals_over_on_hand_exactly_one_succeeds` (file-backed engine, `threading.Barrier`, exactly this fixture) | none |
| Over-on-hand removal: whole request rejected, names location/recipe/size/on-hand/requested; atomic (no Entry/Movement rows) | Automated | `tests/api/test_movements.py::test_move_exceeding_on_hand_returns_422_with_fields_and_writes_nothing`; `tests/db/test_writes_manual_move.py::test_manual_removal_exceeding_on_hand_raises_and_writes_nothing` | none |
| Visit saved as one transaction; every constraint checked before any row written; rejected visit writes zero rows; location must be active stand/market matching visit kind | Automated | `tests/db/test_visits.py::test_record_market_visit_rejects_over_taken_and_writes_nothing` (row counts unchanged, and explicitly asserts zero movements land at the market, including `taken`); `test_visit_locations_are_rejected_for_every_invalid_target` (parametrized over kitchen/production/sold/waste/sampled/inactive-stand/inactive-market/wrong-kind/nonexistent, crossed with stand/market); `tests/api/test_visits.py::test_stand_payload_against_a_market_is_rejected`, `test_market_payload_against_a_stand_is_rejected` | none |

## Stand visit

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Form: counted prefilled to on-hand, tossed/pulled/added inputs, cash; omitted (recipe,size) treated as untouched (counted = on-hand) | Automated + Structural | `tests/domain/test_visits.py::test_a_size_absent_from_rows_settles_as_counted_equals_on_hand` (`plan_stand_visit(STAND, [], context)` → no movements, zero expected revenue); form prefill in `src/web/src/features/visits/StandVisitForm.tsx`/`rows.ts`, unit-tested in `src/web/src/features/visits/rows.test.ts` (`buildStandRows` zero-fills absent sections) | none |
| Missing units → Sold (priced) / Sampled (zero-price); tossed → Waste; pulled → Kitchen; added Kitchen→stand; movements reference visit | Automated | `tests/api/test_visits.py::test_stand_visit_missing_priced_size_is_sold_and_zero_price_size_is_sampled`; `tests/domain/test_visits.py::test_missing_priced_size_sells_and_missing_zero_price_size_samples`, `test_added_allocates_from_kitchens_pre_visit_stock_never_units_just_pulled_back`; `tests/db/test_visits.py::test_stand_visit_routes_priced_size_to_sold_and_zero_price_size_to_sampled` | none |
| Counted > on-hand rejected naming recipe/size/on-hand/counted | Automated | `tests/api/test_visits.py::test_counted_exceeding_on_hand_is_rejected_naming_size_on_hand_and_counted`; `tests/domain/test_visits.py::test_counted_exceeding_on_hand_is_rejected_naming_size_on_hand_and_counted` | none |
| Tossed+pulled > counted rejected naming size | Automated | `tests/api/test_visits.py::test_tossed_plus_pulled_exceeding_counted_is_rejected_naming_the_size`; `tests/domain/test_visits.py::test_tossed_plus_pulled_exceeding_counted_is_rejected_naming_the_size` | none |
| No fee on stand visit; `extra='forbid'` blocks a smuggled field; `fee_cents` always 0 | Automated | `tests/api/test_visits.py::test_stand_payload_with_fee_cents_is_rejected`, `test_visit_payload_with_unknown_key_is_rejected` | none |
| Saved visit shows expected revenue/cash/shrink; expected revenue frozen at save, unaffected by later price change; shrink positive when short | Automated | `tests/api/test_visits.py::test_saved_visit_expected_revenue_unchanged_after_price_change_and_positive_difference`; `tests/db/test_visits.py::test_expected_revenue_is_frozen_against_a_later_price_change_and_shrink_is_positive` | none |

## Market visit

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Form: taken then returned/tossed per taken size; zero-price returned prefilled 0 (editable), priced returned no prefill (required); revenue + fee | Structural | `src/web/src/features/visits/MarketVisitForm.tsx`: `returned: meta.priceCents === 0 ? 0 : ""` and the code comment "the only signal that decides `returned`'s prefill" | No unit/e2e test exercises the actual prefill value in the rendered form (only the row-shaping helpers in `rows.test.ts` are unit-tested; the prefill itself is read by inspection of `MarketVisitForm.tsx`, not asserted by a test). |
| Taken Kitchen→market; missing→Sold/Sampled by price rule; tossed→Waste; returned→Kitchen; movements reference visit | Automated | `tests/api/test_reversals.py::test_undo_of_a_full_market_visit_restores_stock_and_voids_with_null_profit_in_history` (exercises taken/returned/tossed together); `tests/db/test_visits.py` market-routing assertions alongside `test_record_market_visit_rejects_over_taken_and_writes_nothing` | none |
| Returned+tossed > taken rejected naming size | Automated | `tests/domain/test_visits.py::test_returned_plus_tossed_exceeding_taken_is_rejected`; `tests/db/test_visits.py::test_record_market_visit_rejects_over_taken_and_writes_nothing` | none |
| Expected revenue shown next to entered revenue, frozen at save as `expected_revenue_cents`; difference shown, not labeled shrink | Automated + Structural | Freezing mechanism shared with stand visit, pinned by `tests/db/test_visits.py::test_expected_revenue_is_frozen_against_a_later_price_change_and_shrink_is_positive`; label difference ("not labeled shrink" for market) is a frontend copy choice — not independently automated-tested, checked by reading `VisitDetailPage.tsx` naming. | The "not labeled shrink for a market visit" half is a UI-copy assertion with no automated test; confirmed only by code reading. |

## Profit

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Profit = revenue − fee − frozen cost of sold/waste/sampled, three separate lines; fixture pins per-size `unit_cost` (not a `batch_cost` share) | Automated | `tests/domain/test_visits.py::test_profit_equals_revenue_minus_fee_minus_costs_of_sold_waste_sampled` — pins `unit_costs_cents` directly per (batch, size), mixed Sold/Waste/Sampled movements, asserts `Profit(sold_cost_cents=3*40, waste_cost_cents=1*40, sampled_cost_cents=2*10, profit_cents=1000-200-120-40-20)`; API echo in `tests/api/test_visits.py::test_visit_profit_equals_revenue_minus_fee_minus_costs_with_all_three_lines_present` | none |
| Home lists entries newest-first with date/location; visits show revenue+profit; undo action per non-voided entry; voided visit shows no profit and excluded from totals | Automated + Structural | `tests/api/test_entries.py::test_entries_list_newest_first_with_full_shape` (ordering, `kind`, `location_id`, `revenue_cents`, `profit_cents` per entry type); `test_entries_are_ordered_by_created_at_not_by_id`; `tests/api/test_reversals.py::test_undo_of_a_full_market_visit_restores_stock_and_voids_with_null_profit_in_history` (`voided=True`, `profit_cents is None`, `revenue_cents is None`); undo-button UI in `src/web/src/features/history/HistorySection.tsx` | The undo-action-per-entry UI and the "excluded from any profit or revenue **totals**" (i.e., a summed/aggregate figure, not just the per-entry null) are not covered by a vitest/Playwright test — confirmed only by reading `HistorySection.tsx`. If the home screen sums profit/revenue across entries anywhere, that aggregation path has no dedicated test excluding voided rows. |

## Home screen and expiration

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Stock grouped by location then recipe/size; Production/Sold/Waste/Sampled never in stock views; expired/expiring-soon per-batch, both markers coexist | Automated | `tests/api/test_stock.py::test_terminal_locations_never_appear_in_stock`; `test_size_row_with_one_expired_and_one_expiring_soon_batch_reports_both_states` (asserts both `states_by_quantity[3]=="expired"` and `[4]=="expiring_soon"` on the same size row); expiry rule pinned in `tests/domain/test_expiration.py` (`expiring_soon` 0–7 days, `expired` when `expires < today`) | none |
| Toss action: recipe/size/count, FIFO into Waste | Automated + Structural | Implemented as the generic manual-move endpoint with `to_location_id = waste`; FIFO-into-waste pinned by `tests/db/test_writes_manual_move.py` (waste destination cases) and undone in `tests/db/test_undo.py::test_undo_of_a_manual_toss_restores_stock_and_voids_with_reverses_movement_id`; dedicated UI in `src/web/src/features/stock/TossForm.tsx` | none |
| Nothing moves to Waste without a user action | Structural | `grep` of every write path to `waste_id` in `src/inventory` resolves to exactly two call sites: `src/inventory/domain/visits.py` (from a `tossed` field the user entered on a visit) and `src/inventory/db/writes.py`'s generic manual-move (a user-submitted API call); no scheduler/cron/background-task code exists anywhere in `src/inventory` (`grep -rl "BackgroundTasks\|APScheduler\|schedule\|cron"` returns nothing) | none |

## Corrections

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Undo targets one entry, appends reversal with `reverses_movement` = exact original row id, reverse creation order, same batch; original entry voided, original movements untouched; stock before == after; sequential balance check (taken checked only after sold/tossed/returned restore market on-hand) | Automated | `tests/api/test_reversals.py::test_undo_of_a_full_market_visit_restores_stock_and_voids_with_null_profit_in_history` (API); `tests/domain/test_ledger.py::test_sequential_undo_of_market_visit_succeeds_where_a_single_snapshot_would_reject_it` (explicitly the case a single-snapshot check would wrongly reject); `tests/db/test_undo.py::test_undo_of_a_manual_toss_restores_stock_and_voids_with_reverses_movement_id`, `test_undo_leaves_the_original_movement_rows_byte_for_byte_unchanged` (snapshots every column of the original's movement rows and entry `created_at` before undo, diffs after — the "original movements untouched" half of this row) | none |
| Reversal source is an inventory location and a later movement drained it → undo rejected, not negative on-hand; terminal-location sources need no check | Automated | `tests/api/test_reversals.py::test_manual_drain_after_a_visit_blocks_undo_of_that_visit_with_nothing_changed`; `tests/domain/test_ledger.py::test_undo_rejected_when_a_later_movement_outside_the_undo_drained_the_source`, `test_reversal_from_a_terminal_location_needs_no_balance_check` | none |
| Undo of an already-voided entry rejected; duplicate manual removal can't bypass — DB uniqueness on `reverses_movement`, not quantity/batch matching | Automated | `tests/api/test_reversals.py::test_undo_of_an_already_voided_entry_is_rejected`, `test_undo_of_a_reversal_is_rejected`; `tests/db/test_undo.py::test_two_identical_removals_produce_distinct_rows_and_undo_of_one_leaves_the_other` — explicitly attempts a raw second `INSERT` with the same `reverses_movement_id` inside `session.begin_nested()` and asserts `IntegrityError` (the DB constraint itself, not application logic) | none |
| Rejected undo writes no reversal rows; non-voided stays unvoided, already-voided stays voided | Automated | `tests/api/test_reversals.py::test_manual_drain_after_a_visit_blocks_undo_of_that_visit_with_nothing_changed` ("nothing changed" in the name); `tests/db/test_undo.py::test_undo_of_an_already_voided_entry_is_rejected` | none |
| Manual movement: inventory→inventory, →Waste, or →Sold/Sampled by price rule; never a market destination; Production's only outflow is bake; Sold/Waste/Sampled lose units only via undo | Automated | `tests/api/test_movements.py::test_move_to_a_market_destination_is_rejected`; `tests/db/test_writes_manual_move.py::test_manual_move_to_a_market_destination_is_rejected`, `test_manual_move_naming_sold_for_a_zero_price_size_lands_in_sampled` | none |
| Manual operation undoable with same rules as a visit: same batch, all-or-nothing, rejected if already undone | Automated | `tests/db/test_undo.py::test_undo_of_a_manual_toss_restores_stock_and_voids_with_reverses_movement_id`, `test_undo_of_an_already_voided_entry_is_rejected` (undo is one shared code path for every entry kind) | none |

## Login and deployment

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Unauthenticated app route → redirect to login; unauthenticated API (non-login) → 401; login page/static assets public; `/docs`,`/redoc`,`/openapi.json` disabled and 404 | Automated + Structural | `tests/api/test_unauthenticated.py::test_unauthenticated_app_route_redirects_to_login`, `test_unauthenticated_api_route_returns_401_problem`, `test_login_page_is_public`, `test_built_asset_is_public`, `test_openapi_json_stays_404`, `test_docs_and_redoc_stay_404`; `docs_url=None, redoc_url=None, openapi_url=None` in `src/inventory/app.py:59-61` | none |
| Login: `secrets.compare_digest`; signed cookie `HttpOnly`+`SameSite=Strict`+`Secure` (opt-out only via explicit dev var); wrong password sets no cookie; per-IP throttle after N failures with cooldown; explicit `Max-Age`; signed expiry claim checked every request; `SameSite=Strict` is the CSRF control, no separate token, every state change is POST, no state-changing GET | Automated + Structural | `secrets.compare_digest` call at `src/inventory/api/auth.py:190`; `tests/api/test_login.py::test_correct_password_sets_cookie_with_expected_attributes` (`httponly`, `samesite=strict`, `max-age=2592000`), `test_secure_flag_present_only_when_cookies_are_not_insecure`, `test_wrong_password_returns_401_and_sets_no_cookie`, `test_sixth_consecutive_failure_is_throttled_with_retry_after`, `test_tampered_cookie_is_treated_as_unauthenticated`; `tests/api/test_throttle.py` (bounded-memory throttle dict, retry-after rounding, concurrent-attempt ceiling); `tests/api/test_ledger_openapi.py::test_no_state_changing_get_anywhere_in_the_document` | none |
| App fails fast if `SHARED_PASSWORD`/`SESSION_SECRET` unset/empty, or secret < 32 bytes; no default anywhere in code or Compose | Automated + Structural | `tests/api/test_startup.py::test_missing_or_empty_required_variable_exits_nonzero_naming_it` (parametrized over `SHARED_PASSWORD` and `SESSION_SECRET`, each unset and empty — four subprocess runs), `test_short_session_secret_exits_nonzero_naming_it`, `test_overlong_shared_password_exits_nonzero_naming_it`; `src/inventory/settings.py` — no field default except `insecure_cookies`, `_secret_at_least_32_bytes` validator; `compose.yaml` secrets sourced only from `env_file: .env`, no inline default | none |
| `.env`-fed `docker compose up` starts one container, `alembic upgrade head` idempotent (never `create_all`), failed migration exits non-zero and server never starts, login page loads, authenticated read returns 200 | Structural (automated check is narrower) | `docker/entrypoint.sh` (`set -eu; uv run alembic upgrade head; exec uv run python -m inventory` — migration failure trips `set -e` before `exec`, so the server process never starts); `compose.yaml` (`env_file: .env`, no defaults, named volume `data`, port `127.0.0.1:8000:8000`, healthcheck via stdlib `urllib`); the acceptance text's own `_Automated check:_` clause is narrower than the bullet — only `tests/db/test_migration.py::test_migration_seeds_exactly_the_five_builtin_locations` is required, and that's what exists. | No test or CI job actually runs `docker compose up` end-to-end and hits the login page / an authenticated endpoint over HTTP against the built image; `.github/workflows/ci.yml` runs only `make check` and `make e2e` (which starts `python -m inventory` directly, not the container). This is consistent with the letter of the acceptance bullet's `_Automated check:_` clause (which only asks for the five-locations migration test), but the broader "compose up works end to end" claim in the same bullet is unverified by any test in this repo. |
| Deployment notes document backup command and destination | Human | `docs/deployment.md` lines ~90-103 (`sqlite3 "$DB" ".backup /backups/inventory.db"` documented, target `./backups/inventory.db` on the host). Acceptance requires the **owner** to run this once against the running instance and confirm a copy exists — that run is not something this audit can attest to. | none: the owner ran the documented backup command against a running instance on 2026-09-16 and confirmed the copy (reported in the implementation session; recorded in the finish slice delivery record). |
| Every screen usable at 375px without horizontal scroll | Human | No automated check exists or is claimed; acceptance itself calls this human verification (phone check). | Human verification pending: owner must open each screen on a phone. |

## Money

| Criterion (short) | Kind | Evidence | Gap |
|---|---|---|---|
| Every money/weight/quantity field is exactly `int` everywhere (SQLAlchemy, Pydantic, domain dataclasses); none is `float`/`Decimal`; OpenAPI declares each as `integer`; strict-int validation (`"1"`, `1.5` → 422) | Automated | SQLAlchemy: `tests/db/test_columns.py::test_pinned_money_weight_and_quantity_columns_are_integer` (asserts `isinstance(column_type, Integer)` for every pinned column name/suffix across all mapped tables) and `test_no_column_anywhere_is_float_or_numeric`; Domain dataclasses: `tests/domain/test_no_floats.py::test_no_domain_dataclass_field_is_float_or_decimal` (module walk over every `inventory.domain` submodule, asserts no field mentions `float`/`Decimal`, nested or not) and `test_enumerated_domain_dataclass_money_and_quantity_fields_are_exactly_int` (positive counterpart: an explicit field list per dataclass — including `VisitPlan.expected_revenue_cents` and `_Leg.quantity`, both added closing this leaf's third review pass — asserting `typing.get_type_hints(...)[field] is int`); OpenAPI-integer: `tests/api/test_catalog_openapi.py::test_every_catalog_money_weight_and_quantity_field_is_integer` (catalog resources) and `tests/api/test_ledger_openapi.py::test_every_ledger_money_weight_and_quantity_field_is_integer` (ledger resources — `BakeCountItem`, `BatchRead`/`BatchSizeRead`, `MovementCreate`, `StandRowIn`/`MarketRowIn`, `StandVisitCreate`/`MarketVisitCreate`, `VisitRead`, `ProfitRead`, `BatchStockRead`/`SizeStockRead`, and now `EntryRead.revenue_cents`/`profit_cents`, added the same pass), both hard-coded field lists rather than a suffix heuristic; direct Pydantic `model_fields` enumeration (the layer the OpenAPI checks above don't reach — they inspect generated JSON Schema, not the model class itself): `tests/api/test_pydantic_money_fields.py::test_enumerated_pydantic_money_weight_and_quantity_fields_are_exactly_int` (every money/weight/quantity field on every `BaseModel` in `inventory.api.schemas.catalog`, `inventory.api.schemas.ledger`, `inventory.api.auth`, and `inventory.app`, asserted `int` or `int \| None`: field names come from `model_fields`, types from `typing.get_type_hints`, which strips the `Annotated[int, Field(...)]` wrapper the `Cents`/`Count` aliases add) and `test_no_pydantic_model_field_is_float_or_decimal` (negative backstop over every field on every walked model); strict-int + negative rejection: `tests/api/test_numeric_bounds.py`, `tests/api/test_ledger_money.py`, `tests/api/test_recipes.py::test_strict_int_rejects_string_and_float_for_a_weight_field`/`test_strict_int_rejects_string_and_float_for_a_quantity_field`; pyright strict: `typeCheckingMode = "strict"` in `pyproject.toml`, run by `make check`'s `check-python` | none |
| Every quantity/money input field rejected if negative; profit/expected-vs-actual difference may be negative | Automated | `tests/api/test_ledger_money.py` (one field per family: bake count, stand-row counted, visit revenue, market fee); `tests/api/test_visits.py::test_fee_exceeding_revenue_gives_a_negative_profit_and_a_200`; `tests/domain/test_visits.py::test_fee_exceeding_revenue_gives_negative_profit_not_an_error` | none |

## Gaps and human items

The first pass above (`finish/api` HEAD `b6227ce`) flagged ten items. Five
were narrower-than-described automated checks and each now has a pinning
test, added on `finish/audit`: undo into an inactive location
(`tests/db/test_undo.py::test_undo_of_a_manual_move_that_lands_in_a_now_inactive_stand_succeeds`),
original movement rows unchanged after undo
(`tests/db/test_undo.py::test_undo_leaves_the_original_movement_rows_byte_for_byte_unchanged`),
`SESSION_SECRET` unset/empty at startup
(`tests/api/test_startup.py::test_missing_or_empty_required_variable_exits_nonzero_naming_it`),
the OpenAPI `integer` declaration for ledger-side fields
(`tests/api/test_ledger_openapi.py::test_every_ledger_money_weight_and_quantity_field_is_integer`),
and domain dataclass fields being positively `int`
(`tests/domain/test_no_floats.py::test_enumerated_domain_dataclass_money_and_quantity_fields_are_exactly_int`).
Their rows above now read `none` in the Gap column. What genuinely
remains:

1. **Locations — picker hiding.** "Hidden as a destination in the visit and manual-move pickers" for an inactive location is not confirmed by a frontend test; only backend rejection is tested. `src/web/src/features/movements/MovePage.tsx` and `src/web/src/features/visits/NewVisitPage.tsx` do filter on `active`, by inspection, but no vitest or Playwright assertion pins it.
2. **Market visit form — `returned` prefill.** Confirmed only by reading `MarketVisitForm.tsx`; no committed unit or e2e test asserts the rendered prefill value differs by size price. The web-entry slice's spine walkthrough (`docs/implementation/slices/web-entry.md`) did exercise this by hand — "priced `returned` empty and zero-price `returned` prefilled 0" is recorded in that slice's Verification note — but that walkthrough is not a test that runs in CI.
3. **Profit/home screen — aggregate totals.** Not a gap in the code: the home screen (`src/web/src/pages/HomePage.tsx`, `src/web/src/features/history/HistorySection.tsx`) never sums profit or revenue across entries at all — it only ever renders one entry's own `profit_cents`/`revenue_cents`, already `null` on a voided entry and already tested. The "aggregate totals excluding voided entries" concern the first pass raised presumes a feature (a summed total) that does not exist in the product, so there is nothing to write a test against.
4. **Deployment — `docker compose up` end-to-end.** No CI job or committed test builds/runs the container and hits the login page or an authenticated endpoint over HTTP; the acceptance bullet's own `_Automated check:_` clause is narrower (just the five-locations migration test) and that narrower check is fully met. The broader claim was exercised as a manual check during the deploy-local slice instead — `docs/implementation/slices/deploy-local.md`'s Verification note records a real `docker compose up -d --build` hitting `/login`, `/`, and `/api/v1/stock` before and after login, plus a negative start without `SESSION_SECRET` — but that run is not repeated automatically.
5. **Human items (as `docs/acceptance.md` itself designates them), not gaps in the code:** the owner ran the documented backup command once against a live instance and confirmed the copy on 2026-09-16; the remaining human item is opening every screen at 375px on a phone.

None of the above are missing behavior — each is either a one-time manual
walkthrough already recorded elsewhere rather than a committed test, a
concern about a feature that was never built, frontend behavior
confirmed only by reading the code, or a criterion `docs/acceptance.md`
itself flags as human verification.
