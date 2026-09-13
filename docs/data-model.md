# Data Model

Domain concepts and the rules that bind them. Names and shapes are **illustrative guidance, not mandated implementation**; the rules are authoritative. Money is integer cents everywhere. Every money input — ingredient price, size sale price, visit fee, visit revenue — is a non-negative integer; reject the request otherwise. Derived money values (profit, the expected-versus-actual cash difference) are signed integers; a loss or a shortfall is a legitimate negative value. Weights are integer grams or tenths of an ounce, the lead's choice, but one unit project-wide. Every quantity a user enters (recipe ingredient-line quantity, counted, tossed, pulled, added, taken, returned, count made per size) is a non-negative integer; reject the request otherwise.

## Concepts

| Concept | Owned facts | Notes |
| --- | --- | --- |
| Ingredient | name, unit label (free text), current price per unit, active flag | Shared across recipes. No price history. Ingredients are never deleted, only deactivated. |
| Recipe | name, shelf life in days, ingredient lines (ingredient, quantity), sizes | Cost per size is computed on read, never stored. |
| Size | recipe, name, portion weight, sale price, typical yield count | Price zero is legal and means "given away." No sample flag. |
| Batch | recipe, bake entry, baked date, expires date, total cost, per-size unit cost, count made per size | Cost fields are written once at bake and never updated. The batch references its bake entry; if that entry is voided, the batch is excluded from stock, batch cost reports, and profit. |
| Location | name, kind, active flag (stands and markets only) | Inventory kinds: `kitchen`, `stand`, `market`. Terminal kinds: `production`, `sold`, `waste`, `sampled`. Kitchen, Production, Sold, Waste, and Sampled are singleton built-ins created by migration; they cannot be deleted, renamed, or deactivated. Stands and markets are user rows. Terminal locations hold no stock and never appear in on-hand, stock views, or FIFO. Production is the source of every bake movement, so every movement has two real ends; its only outflow is to Kitchen. Sold, Waste, and Sampled gain units from visits and manual removals and lose units only through undo. An inactive stand or market rejects new visits and manual moves into it and is hidden from those forms; undo may still reverse into it, since the balance check in Corrections governs on-hand, not activity. |
| Entry | kind (`bake`, `visit`, `manual`, or `reversal`), timestamp, voided flag, reverses entry (required for `reversal`, null otherwise, unique) | Every movement belongs to exactly one entry; there is no "movement with no entry" case. A `bake` entry is created when a batch is recorded and owns that batch's Production-to-Kitchen movement rows. A `manual` entry is one user operation from the manual movement form and may contain several movement rows, one per batch FIFO selected. A `reversal` entry is what undo appends; it references the entry it undoes, so a reversal is auditable even when the original entry created no movements. See Corrections. |
| Movement | entry, batch, size, from location, to location, quantity, timestamp, reverses movement (optional, unique) | Append-only. No update or delete. No route deletes an entry or a movement; voiding an entry is the only lifecycle change, and undo appends a reversal entry rather than removing any row. `reverses_movement` is set only on a reversal entry's rows and is unique, so a given original movement can be targeted by at most one reversal. |
| Visit | entry, location, revenue, fee, expected_revenue_cents, notes | A visit is an entry with revenue, fee, expected_revenue_cents, and location; only stand and market locations have visits. For a stand visit, revenue is the cash collected and fee is zero. `expected_revenue_cents` is computed from each size's price at save time and stored on the visit, so a later price change never alters a saved visit's numbers. |

All money facts in the table above are integer cents and are named with a `_cents` suffix in code (for example `current_price_cents`, `total_cost_cents`, `revenue_cents`); the table uses plain words for readability.

Derived, never stored: on-hand per (location, recipe, size, batch) equals the sum of movements in minus movements out. On-hand is defined only for inventory locations (Kitchen, stands, markets); Production, Sold, Waste, and Sampled are terminal and excluded from stock views, on-hand, and FIFO.

## Recipe cost estimate and batch cost split

On the recipe screen, before any bake exists: `recipe_cost = Σ over recipe lines (quantity × ingredient.current_price)`, `typical_total_weight = Σ over sizes (typical_yield_count × portion_weight)`, and estimated `unit_cost(size) = round_half_up(recipe_cost × portion_weight / typical_total_weight)`. This is a live estimate, recomputed on read, never stored. Saving a recipe whose typical total weight is zero is rejected, so the estimate always has a denominator.

At bake time, using actual counts:

- `batch_cost = Σ over recipe lines (quantity × ingredient.current_price)`, rounded to cents once at the end.
- `total_weight = Σ over sizes (count_made × portion_weight)`.
- `unit_cost(size) = round_half_up(batch_cost × portion_weight / total_weight)` to cents. Round half up everywhere, never banker's rounding, so recipe estimates and bake costs agree.
- Recording a bake creates a `bake` entry and writes one movement per size from Production to Kitchen for `count_made` units, referencing that entry, the same way every other transfer is written; there is no batch-only special case in the ledger.
- Rounding per size means `Σ (unit_cost × count_made)` will not always equal `batch_cost` exactly — with integer per-size unit costs, no remainder assignment can force an exact match for every yield. Example: a 101-cent batch split into two equal-weight sizes of two units each gives 25.25 cents per unit, which rounds half up to 25, so the four units total 100 cents. No integer unit cost can total 101 across four units, so exactness is impossible here regardless of rounding rule. Do not chase exactness with a remainder trick. Instead bound the drift. Each unit's rounding error is at most half a cent, so `|Σ (unit_cost × count_made) − batch_cost| ≤ ceil(total_units / 2)` cents, where `total_units = Σ count_made`. Round half up so the bound is exact, not banker's rounding. `batch_cost` stays the authoritative record of what the batch cost; `unit_cost` per size drives movement costing and profit and is internally consistent even when it does not reconcile to the cent against `batch_cost`. Test the bound, not equality.

A batch with zero total weight (nothing made) is rejected.

## FIFO allocation

Any operation that removes units of a (location, recipe, size) takes from the batch with the earliest `expires` date first, then earliest `baked` date, then lowest id. It may span batches. If the requested quantity exceeds on-hand at that location, reject the whole operation and report on-hand versus requested. Never create negative stock.

## Visit settlement

Given the location's derived on-hand per (recipe, size) immediately before the visit, saving a visit is a single transaction: every constraint below for that visit type — non-negativity, counted ≤ on-hand, tossed + pulled ≤ counted, returned + tossed ≤ taken, and FIFO availability for every removal — is checked before any movement row is written. A rejected visit writes nothing, so a bad payload can never leave partial ledger rows or deplete Kitchen. Every entry that moves stock out of any inventory location (visit, manual transfer, manual removal, undo) runs in a serialized write transaction (`BEGIN IMMEDIATE` on SQLite, with a busy timeout) so the availability read and the append happen under one write lock; two concurrent removals of the same stock cannot both pass validation.

**Stand visit** input: counted per size, tossed per size, cash collected, pulled-to-kitchen per size, added-from-kitchen per size.

1. `missing = on_hand − counted`. Reject if negative. Reject if `tossed + pulled > counted` for any size, since both come out of the counted remainder that stays at the stand.
2. For each size: if `price > 0`, move `missing` to Sold; else move `missing` to Sampled. FIFO.
3. Move `tossed` to Waste. FIFO from the counted remainder.
4. Move `pulled` to Kitchen. Move `added` from Kitchen to the stand.
5. `expected_revenue_cents = Σ (missing × price)`, computed from current prices at save time and persisted on the visit. Show alongside `revenue_cents` (the cash collected). `shrink_cents = expected_revenue_cents − revenue_cents`; positive means cash came up short.

**Market visit** input: taken-from-kitchen per size, returned per size, tossed per size, revenue total, fee.

1. `missing = taken − returned − tossed`. Reject if negative.
2. Move `taken` from Kitchen to the market location. FIFO.
3. Sold or Sampled by the price rule, as above. Move `tossed` to Waste. Move `returned` to Kitchen.
4. `expected_revenue_cents = Σ (missing × price)`, computed from current prices at save time and persisted on the visit. Show alongside the entered `revenue_cents`. The same `expected_revenue_cents − revenue_cents` difference shown for a stand visit applies here; it is not called shrink for a market visit.

Sample returns prefill to zero in the market form because sample packaging does not survive an event. It is a prefill, not a rule.

## Profit

For a visit: `profit = revenue − fee − cost_of(Sold) − cost_of(Waste) − cost_of(Sampled)`, where each cost is the sum of `unit_cost × quantity` over the movements that visit created into that destination. Present the three cost lines separately so waste and giveaways are visible. A voided visit shows no profit figure in history and is excluded from any profit or revenue totals; its original movements remain for audit but no longer count toward those numbers.

## Corrections

Undo targets one original entry — a bake, a visit, or a manual operation — and appends a new entry of kind `reversal`. For every movement the original entry created, in reverse creation order, the reversal entry gets one movement of the same quantity and the same batch from the original destination back to the original origin, and that reversal movement's `reverses_movement` is set to the exact original row's id. Targeting the original batch is the one exception to FIFO, which governs user-initiated removals only. `reverses_movement` is unique, so at most one reversal movement can ever point at a given original row: two otherwise-identical manual removals still produce two distinct movement rows, undo targets the id, not the data, and undoing the same row twice is rejected by that constraint rather than by matching quantities or batches. Undo is all or nothing: if any reversal whose source is an inventory location would drive that batch's on-hand negative there, because a later movement already consumed it, the whole undo is rejected, no rows are written, and the original entry stays unvoided. Reversals out of Sold, Waste, or Sampled need no balance check, since the original entry's own movement put the units there. Undo of an already-voided entry is rejected. Original movements are never edited or deleted. Undoing a bake entry reverses its Production-to-Kitchen movements per size under these same rules; because Production is never depleted, the balance check applies only on the Kitchen side. Voiding a bake excludes its batch from stock, batch cost reports, and profit, the same way a voided visit is excluded from profit totals.

A manual movement form moves units between inventory locations by FIFO, or removes them from an inventory location to Waste, or to Sold or Sampled by the same price rule a visit uses. A manual transfer's source and destination must differ, and its destination must be an active inventory location and may never be a market; a manual removal's destination is Waste, Sold, or Sampled. User-initiated moves into a market happen only through a market visit's `taken` step, and a visit returns, tosses, or sells everything it took, so no stock is left at a market between visits for a manual move to disturb. Reversal entries are exempt; undoing a market visit legitimately moves units back into the market. A manual operation can be undone with the same rules as a visit.

## Expiration

A batch is expiring soon when `0 ≤ expires − today ≤ 7 days` and expired when `expires < today`; the two states are distinct, so an already-expired batch is not also flagged as expiring soon. The home screen highlights both and offers "toss" on kitchen stock. Nothing auto-moves to Waste.
