"""initial

Creates the ten tables in `docs/schema.md`, seeds the five built-in
locations (Kitchen, Production, Sold, Waste, Sampled), and creates the
two `BEFORE UPDATE` triggers that freeze `batch.total_cost_cents` and
`batch_size.unit_cost_cents` at the database (see `docs/data-model.md`,
non-negotiable 2 and "Batch").

Revision ID: 0001
Revises:
Create Date: 2026-09-13 23:05:53.776339

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Built-in locations seeded by this migration; looked up by `kind`
# elsewhere (see `inventory.db.builtins`), never by the ids assigned here.
_BUILTIN_LOCATIONS = (
    ("Kitchen", "kitchen"),
    ("Production", "production"),
    ("Sold", "sold"),
    ("Waste", "waste"),
    ("Sampled", "sampled"),
)

_BATCH_COST_TRIGGER = """
    CREATE TRIGGER batch_cost_frozen
    BEFORE UPDATE OF total_cost_cents ON batch
    BEGIN
        SELECT RAISE(ABORT, 'batch cost is frozen');
    END;
"""

_BATCH_SIZE_COST_TRIGGER = """
    CREATE TRIGGER batch_size_cost_frozen
    BEFORE UPDATE OF unit_cost_cents ON batch_size
    BEGIN
        SELECT RAISE(ABORT, 'batch cost is frozen');
    END;
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("voided", sa.Boolean(), nullable=False),
        sa.Column("reverses_entry_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("kind IN ('bake','visit','manual','reversal')", name="ck_entry_kind"),
        sa.ForeignKeyConstraint(["reverses_entry_id"], ["entry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reverses_entry_id"),
    )
    op.create_table(
        "ingredient",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unit_label", sa.String(), nullable=False),
        sa.Column("current_price_cents", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("current_price_cents >= 0", name="ck_ingredient_price"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "location",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(collation="NOCASE"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('kitchen','stand','market','production','sold','waste','sampled')",
            name="ck_location_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "recipe",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("shelf_life_days", sa.Integer(), nullable=False),
        sa.CheckConstraint("shelf_life_days >= 0", name="ck_recipe_shelf_life"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("baked", sa.Date(), nullable=False),
        sa.Column("expires", sa.Date(), nullable=False),
        sa.Column("total_cost_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("expires >= baked", name="ck_batch_expires_after_baked"),
        sa.ForeignKeyConstraint(["entry_id"], ["entry.id"]),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id"),
    )
    op.create_table(
        "recipe_line",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_recipe_line_quantity"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredient.id"]),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "size",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(collation="NOCASE"), nullable=False),
        sa.Column("portion_weight_g", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("typical_yield_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("portion_weight_g > 0", name="ck_size_portion_weight"),
        sa.CheckConstraint("price_cents >= 0", name="ck_size_price"),
        sa.CheckConstraint("typical_yield_count >= 0", name="ck_size_typical_yield"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recipe_id", "name", name="uq_size_recipe_name"),
    )
    op.create_table(
        "visit",
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("revenue_cents", sa.Integer(), nullable=False),
        sa.Column("fee_cents", sa.Integer(), nullable=False),
        sa.Column("expected_revenue_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("fee_cents >= 0", name="ck_visit_fee"),
        sa.CheckConstraint("revenue_cents >= 0", name="ck_visit_revenue"),
        sa.ForeignKeyConstraint(["entry_id"], ["entry.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["location.id"]),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    op.create_table(
        "batch_size",
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("size_id", sa.Integer(), nullable=False),
        sa.Column("count_made", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("count_made >= 1", name="ck_batch_size_count_made"),
        sa.ForeignKeyConstraint(["batch_id"], ["batch.id"]),
        sa.ForeignKeyConstraint(["size_id"], ["size.id"]),
        sa.PrimaryKeyConstraint("batch_id", "size_id"),
    )
    op.create_table(
        "movement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("size_id", sa.Integer(), nullable=False),
        sa.Column("from_location_id", sa.Integer(), nullable=False),
        sa.Column("to_location_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reverses_movement_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("quantity >= 1", name="ck_movement_quantity"),
        sa.ForeignKeyConstraint(["batch_id"], ["batch.id"]),
        sa.ForeignKeyConstraint(["entry_id"], ["entry.id"]),
        sa.ForeignKeyConstraint(["from_location_id"], ["location.id"]),
        sa.ForeignKeyConstraint(["reverses_movement_id"], ["movement.id"]),
        sa.ForeignKeyConstraint(["size_id"], ["size.id"]),
        sa.ForeignKeyConstraint(["to_location_id"], ["location.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reverses_movement_id"),
    )

    location_table = sa.table(
        "location",
        sa.column("name", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("active", sa.Boolean()),
    )
    op.bulk_insert(
        location_table,
        [{"name": name, "kind": kind, "active": True} for name, kind in _BUILTIN_LOCATIONS],
    )

    op.execute(_BATCH_COST_TRIGGER)
    op.execute(_BATCH_SIZE_COST_TRIGGER)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER batch_size_cost_frozen")
    op.execute("DROP TRIGGER batch_cost_frozen")

    op.drop_table("movement")
    op.drop_table("batch_size")
    op.drop_table("visit")
    op.drop_table("size")
    op.drop_table("recipe_line")
    op.drop_table("batch")
    op.drop_table("recipe")
    op.drop_table("location")
    op.drop_table("ingredient")
    op.drop_table("entry")
