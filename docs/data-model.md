# Data Model

Domain concepts and the rules that bind them. Names and shapes are **illustrative guidance, not mandated implementation**; the rules are authoritative. Money is integer cents everywhere. Weights are integer grams or tenths of an ounce, the lead's choice, but one unit project-wide.

## Concepts

| Concept | Owned facts | Notes |
| --- | --- | --- |
| Ingredient | name, unit label (free text), current price per unit | Shared across recipes. No price history. |
| Recipe | name, shelf life in days, ingredient lines (ingredient, quantity), sizes | Cost per size is computed on read, never stored. |
| Size | recipe, name, portion weight, sale price, typical yield count | Price zero is legal and means "given away." No sample flag. |
| Batch | recipe, baked date, expires date, total cost, per-size unit cost, count made per size | Cost fields are written once at bake and never updated. |
| Location | name, kind | Kinds: `kitchen`, `stand`, `market`, `sold`, `waste`, `sampled`. Kitchen, Sold, Waste, Sampled are singleton built-ins created by migration and undeletable. Stands and markets are user rows. |
| Movement | batch, size, from location, to location, quantity, timestamp, optional visit | Append-only. No update or delete. |
| Visit | location, date, revenue, fee, voided flag, notes | Only stand and market locations have visits. For a stand visit, revenue is the cash collected and fee is zero. |

Derived, never stored: on-hand per (location, recipe, size, batch) equals the sum of movements in minus movements out.

## Batch cost and per-size split

At bake time:

- `batch_cost = Σ over recipe lines (quantity × ingredient.current_price)`, rounded to cents once at the end.
- `total_weight = Σ over sizes (count_made × portion_weight)`.
- `unit_cost(size) = batch_cost × portion_weight / total_weight`, rounded to cents.
- The rounded per-size unit costs multiplied by counts will not sum exactly to `batch_cost`. Assign the remainder in cents to the size with the largest total weight so `Σ (unit_cost × count_made) == batch_cost` holds exactly. Test this.

A batch with zero total weight (nothing made) is rejected.

## FIFO allocation

Any operation that removes units of a (location, recipe, size) takes from the batch with the earliest `expires` date first, then earliest `baked` date, then lowest id. It may span batches. If the requested quantity exceeds on-hand at that location, reject the whole operation and report on-hand versus requested. Never create negative stock.

## Visit settlement

Given the location's derived on-hand per (recipe, size) immediately before the visit:

**Stand visit** input: counted per size, tossed per size, cash collected, pulled-to-kitchen per size, added-from-kitchen per size.

1. `missing = on_hand − counted`. Reject if negative.
2. For each size: if `price > 0`, move `missing` to Sold; else move `missing` to Sampled. FIFO.
3. Move `tossed` to Waste. FIFO from the counted remainder.
4. Move `pulled` to Kitchen. Move `added` from Kitchen to the stand.
5. `expected_cash = Σ (missing × price)`. Show alongside `cash collected`. The difference is shrink; store nothing extra for it.

**Market visit** input: taken-from-kitchen per size, returned per size, tossed per size, revenue total, fee.

1. Move `taken` from Kitchen to the market location. FIFO.
2. `missing = taken − returned − tossed`. Reject if negative.
3. Sold or Sampled by the price rule, as above. Move `tossed` to Waste. Move `returned` to Kitchen.
4. `expected_revenue = Σ (missing × price)`. Show alongside the entered revenue.

Sample returns prefill to zero in the market form because sample packaging does not survive an event. It is a prefill, not a rule.

## Profit

For a visit: `profit = revenue − fee − cost_of(Sold) − cost_of(Waste) − cost_of(Sampled)`, where each cost is the sum of `unit_cost × quantity` over the movements that visit created into that destination. Present the three cost lines separately so waste and giveaways are visible.

## Corrections

"Undo last visit" appends, for every movement the visit created, a movement of the same quantity in the opposite direction with the same batch, tagged to a new correction record or to the same visit with a reversal marker, and marks the visit voided. The original movements remain. A manual movement form allows any from and to location including moving out of Sold, Waste, or Sampled back to a real location for other corrections.

## Expiration

A batch is expiring soon when `expires − today ≤ 7 days` and expired when `expires < today`. The home screen highlights both and offers "toss" on kitchen stock. Nothing auto-moves to Waste.
