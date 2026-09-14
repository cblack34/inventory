# Schema

Proposed persisted schema for the persistence slice, derived from [`data-model.md`](data-model.md). The data model is authoritative; this diagram is the descriptive shape the SQLAlchemy models and the initial Alembic migration follow. Money is integer cents (`_cents`), weights integer grams (`_g`).

```mermaid
erDiagram
    ingredient {
        int id PK
        text name
        text unit_label
        int current_price_cents
        bool active
    }
    recipe {
        int id PK
        text name
        int shelf_life_days
    }
    recipe_line {
        int id PK
        int recipe_id FK
        int ingredient_id FK
        int quantity
    }
    size {
        int id PK
        int recipe_id FK
        text name "unique per recipe, case-insensitive"
        int portion_weight_g "> 0"
        int price_cents ">= 0; zero means given away"
        int typical_yield_count
    }
    location {
        int id PK
        text name "unique, case-insensitive"
        text kind "kitchen|stand|market|production|sold|waste|sampled"
        bool active "stands and markets only"
    }
    entry {
        int id PK
        text kind "bake|visit|manual|reversal"
        datetime created_at
        bool voided
        int reverses_entry_id FK "unique, nullable; reversal only"
    }
    batch {
        int id PK
        int recipe_id FK
        int entry_id FK "the bake entry, unique"
        date baked
        date expires ">= baked"
        int total_cost_cents "frozen; BEFORE UPDATE trigger raises"
    }
    batch_size {
        int batch_id PK, FK
        int size_id PK, FK
        int count_made
        int unit_cost_cents "frozen; BEFORE UPDATE trigger raises"
    }
    movement {
        int id PK
        int entry_id FK
        int batch_id FK
        int size_id FK
        int from_location_id FK
        int to_location_id FK
        int quantity ">= 1"
        int reverses_movement_id FK "unique, nullable; reversal rows only"
    }
    visit {
        int entry_id PK, FK
        int location_id FK "stand or market"
        int revenue_cents
        int fee_cents "0 for a stand"
        int expected_revenue_cents "computed at save"
    }

    recipe ||--o{ recipe_line : "has"
    ingredient ||--o{ recipe_line : "priced by"
    recipe ||--o{ size : "yields"
    recipe ||--o{ batch : "baked as"
    batch ||--|{ batch_size : "cost per size"
    size ||--o{ batch_size : ""
    entry ||--o| batch : "bake creates"
    entry ||--o| visit : "visit is"
    entry ||--o{ movement : "owns"
    entry o|--o| entry : "reversal undoes"
    batch ||--o{ movement : "units of"
    size ||--o{ movement : ""
    location ||--o{ movement : "from"
    location ||--o{ movement : "to"
    location ||--o{ visit : "at"
    movement o|--o| movement : "reversal targets"
```

## What the diagram cannot show

- **Nothing derived is stored.** There is no on-hand column; stock is always the fold over `movement`. Recipe cost per size is computed on read from current ingredient prices.
- **No deletes.** No ORM relationship cascades and no route deletes a row in any table. `ingredient` and user-created `location` rows carry `active`; every other row is permanent. Voiding an `entry` is the only lifecycle change, and it never edits or removes the entry's movements.
- **Built-ins by migration.** Kitchen, Production, Sold, Waste, and Sampled are rows created by the initial migration and cannot be renamed, deactivated, or deleted through the API.
- **Frozen cost.** A `BEFORE UPDATE` trigger on `batch.total_cost_cents` and `batch_size.unit_cost_cents` raises, so no write path (ORM, Core, or raw SQL) can change a recorded cost.
- **One transaction per write.** Recording a bake, visit, manual move, or undo loads on-hand, calls the domain planner, and appends `entry`, `movement`, and `visit` rows under `BEGIN IMMEDIATE` with a busy timeout, or writes nothing.
- **Per-size cost is a table.** `batch_size` holds `count_made` and `unit_cost_cents` per (batch, size) because a recipe yields several sizes; `batch.total_cost_cents` remains the authoritative record of what the batch cost, and the per-size sum may differ from it by the bounded rounding remainder.
