# Data Model

Domain concepts and the rules that bind them. Names and shapes are **illustrative guidance, not mandated implementation**; the rules are authoritative. Money is integer cents everywhere. Every money input — ingredient price, size sale price, visit fee, visit revenue — is a non-negative integer; reject the request otherwise. Derived money values (profit, the expected-versus-actual cash difference) are signed integers; a loss or a shortfall is a legitimate negative value. Weights are integer grams or tenths of an ounce, the lead's choice, but one unit project-wide. Every quantity a user enters (counted, tossed, pulled, added, taken, returned, count made per size) is a non-negative integer; reject the request otherwise.

## Concepts

| Concept | Owned facts | Notes |
| --- | --- | --- |
| Ingredient | name, unit label (free text), current price per unit | Shared across recipes. No price history. |
| Recipe | name, shelf life in days, ingredient lines (ingredient, quantity), sizes | Cost per size is computed on read, never stored. |
| Size | recipe, name, portion weight, sale price, typical yield count | Price zero is legal and means "given away." No sample flag. |
| Batch | recipe, baked date, expires date, total cost, per-size unit cost, count made per size | Cost fields are written once at bake and never updated. |
| Location | name, kind | Inventory kinds: `kitchen`, `stand`, `market`. Terminal kinds: `production`, `sold`, `waste`, `sampled`. Kitchen, Production, Sold, Waste, and Sampled are singleton built-ins created by migration; they cannot be deleted, renamed, or deactivated. Stands and markets are user rows. Terminal locations hold no stock and never appear in on-hand, stock views, or FIFO. Production is the source of every bake movement, so every movement has two real ends; its only outflow is to Kitchen. Sold, Waste, and Sampled gain units from visits and manual removals and lose units only through undo. |
| Movement | batch, size, from location, to location, quantity, timestamp, optional visit | Append-only. No update or delete. No route deletes a visit or a movement; voiding a visit is the only lifecycle change, and it appends reversing movements rather than removing any row. |
| Visit | location, date, revenue, fee, expected_revenue_cents, voided flag, notes | Only stand and market locations have visits. For a stand visit, revenue is the cash collected and fee is zero. `expected_revenue_cents` is computed from each size's price at save time and stored on the visit, so a later price change never alters a saved visit's numbers. |

Derived, never stored: on-hand per (location, recipe, size, batch) equals the sum of movements in minus movements out. On-hand is defined only for inventory locations (Kitchen, stands, markets); Production, Sold, Waste, and Sampled are terminal and excluded from stock views, on-hand, and FIFO.

## Batch cost and per-size split

At bake time:

- `batch_cost = Σ over recipe lines (quantity × ingredient.current_price)`, rounded to cents once at the end.
- `total_weight = Σ over sizes (count_made × portion_weight)`.
- `unit_cost(size) = round(batch_cost × portion_weight / total_weight)` to cents.
- Recording a bake writes one movement per size from Production to Kitchen for `count_made` units, the same way every other transfer is written; there is no batch-only special case in the ledger.
- Rounding per size means `Σ (unit_cost × count_made)` will not always equal `batch_cost` exactly — with integer per-size unit costs, no remainder assignment can force an exact match for every yield. Example: a 101-cent batch split into two equal-weight sizes of two units each prices each unit at 25 or 26 cents; the achievable totals are 100, 102, or 104 cents, never 101. Do not chase exactness with a remainder trick. Instead bound the drift. Each unit's rounding error is at most half a cent, so `|Σ (unit_cost × count_made) − batch_cost| ≤ ceil(total_units / 2)` cents, where `total_units = Σ count_made`. Round half up so the bound is exact, not banker's rounding. `batch_cost` stays the authoritative record of what the batch cost; `unit_cost` per size drives movement costing and profit and is internally consistent even when it does not reconcile to the cent against `batch_cost`. Test the bound, not equality.

A batch with zero total weight (nothing made) is rejected.

## FIFO allocation

Any operation that removes units of a (location, recipe, size) takes from the batch with the earliest `expires` date first, then earliest `baked` date, then lowest id. It may span batches. If the requested quantity exceeds on-hand at that location, reject the whole operation and report on-hand versus requested. Never create negative stock.

## Visit settlement

Given the location's derived on-hand per (recipe, size) immediately before the visit:

**Stand visit** input: counted per size, tossed per size, cash collected, pulled-to-kitchen per size, added-from-kitchen per size.

1. `missing = on_hand − counted`. Reject if negative. Reject if `tossed + pulled > counted` for any size, since both come out of the counted remainder that stays at the stand.
2. For each size: if `price > 0`, move `missing` to Sold; else move `missing` to Sampled. FIFO.
3. Move `tossed` to Waste. FIFO from the counted remainder.
4. Move `pulled` to Kitchen. Move `added` from Kitchen to the stand.
5. `expected_cash = Σ (missing × price)`, computed from current prices at save time and persisted on the visit as `expected_revenue_cents`. Show alongside `cash collected`. The difference is shrink; store nothing extra for it.

**Market visit** input: taken-from-kitchen per size, returned per size, tossed per size, revenue total, fee.

1. Move `taken` from Kitchen to the market location. FIFO.
2. `missing = taken − returned − tossed`. Reject if negative.
3. Sold or Sampled by the price rule, as above. Move `tossed` to Waste. Move `returned` to Kitchen.
4. `expected_revenue = Σ (missing × price)`, computed from current prices at save time and persisted on the visit as `expected_revenue_cents`. Show alongside the entered revenue.

Sample returns prefill to zero in the market form because sample packaging does not survive an event. It is a prefill, not a rule.

## Profit

For a visit: `profit = revenue − fee − cost_of(Sold) − cost_of(Waste) − cost_of(Sampled)`, where each cost is the sum of `unit_cost × quantity` over the movements that visit created into that destination. Present the three cost lines separately so waste and giveaways are visible. A voided visit shows no profit figure in history and is excluded from any profit or revenue totals; its original movements remain for audit but no longer count toward those numbers.

## Corrections

"Undo last visit" appends, for every movement the visit created and in reverse creation order, a movement of the same quantity and the same batch from the original destination back to the original origin, then marks the visit voided. Targeting the original batch is the one exception to FIFO, which governs user-initiated removals only. Undo is all or nothing: if any reversal whose source is an inventory location would drive that batch's on-hand negative there, because a later movement already consumed it, the whole undo is rejected, no rows are written, and the visit stays unvoided. Reversals out of Sold, Waste, or Sampled need no balance check, since the visit's own movement put the units there. Undo of an already-voided visit is rejected. Original movements are never edited or deleted.

A manual movement form moves units between inventory locations by FIFO, or removes them from an inventory location to Waste, or to Sold or Sampled by the same price rule a visit uses. A manual movement is a one-movement entry and can be undone with the same rules.

## Expiration

A batch is expiring soon when `expires − today ≤ 7 days` and expired when `expires < today`. The home screen highlights both and offers "toss" on kitchen stock. Nothing auto-moves to Waste.
