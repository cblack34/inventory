"""SQLAlchemy 2.0 models for the ten tables in `docs/schema.md`.

The data model (`docs/data-model.md`) is authoritative; this module is the
implementation of its descriptive shape. Money is integer cents (`_cents`
suffix), weight is integer grams (`_g` suffix); every column mapped here
is `Integer` for money, weight, and quantity fields (`inventory.db` has no
`Float` or `Numeric` column anywhere — see `tests/db/test_columns.py`).

No relationship here cascades a delete (no `cascade="all, delete"`, no
`delete-orphan`, no `ondelete="CASCADE"` on any foreign key): nothing in
this schema is ever deleted, only appended or (for `active` flags and the
`voided` flag) flipped. See "No deletes" in `docs/schema.md`.

Enum-like columns (`location.kind`, `entry.kind`) are plain `String` with
a `CHECK` constraint listing the allowed values, not a SQLAlchemy `Enum`
type, to keep the SQLite column simple (a plain TEXT column with a
CHECK, matching what a raw `CREATE TABLE` in the migration renders).
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for every mapped class in this package."""


_LOCATION_KINDS = "'kitchen','stand','market','production','sold','waste','sampled'"
_ENTRY_KINDS = "'bake','visit','manual','reversal'"

# Case-insensitive uniqueness (location name globally, size name per recipe)
# is declared at the column type via SQLite's NOCASE collation rather than a
# functional index, so it is plain column metadata that Alembic's
# autogenerate/`compare_metadata` compares like any other column -- a
# `text(...)`-expression unique index is not reflected the same way and
# would not round-trip cleanly through `alembic check`.
_NocaseString = String(collation="NOCASE")


class Ingredient(Base):
    """A shared, priced ingredient. Never deleted, only deactivated."""

    __tablename__ = "ingredient"
    __table_args__ = (CheckConstraint("current_price_cents >= 0", name="ck_ingredient_price"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    unit_label: Mapped[str] = mapped_column(String, nullable=False)
    current_price_cents: Mapped[int] = mapped_column(nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)

    recipe_lines: Mapped[list["RecipeLine"]] = relationship(back_populates="ingredient")


class Recipe(Base):
    """A permanent recipe: name, shelf life, ingredient lines, sizes."""

    __tablename__ = "recipe"
    __table_args__ = (CheckConstraint("shelf_life_days >= 0", name="ck_recipe_shelf_life"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    shelf_life_days: Mapped[int] = mapped_column(nullable=False)

    lines: Mapped[list["RecipeLine"]] = relationship(back_populates="recipe")
    sizes: Mapped[list["Size"]] = relationship(back_populates="recipe")
    batches: Mapped[list["Batch"]] = relationship(back_populates="recipe")


class RecipeLine(Base):
    """One ingredient and quantity within a recipe."""

    __tablename__ = "recipe_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredient.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="lines")
    ingredient: Mapped[Ingredient] = relationship(back_populates="recipe_lines")


class Size(Base):
    """A yield of a recipe: name, portion weight, sale price, typical yield."""

    __tablename__ = "size"
    __table_args__ = (
        UniqueConstraint("recipe_id", "name", name="uq_size_recipe_name"),
        CheckConstraint("portion_weight_g > 0", name="ck_size_portion_weight"),
        CheckConstraint("price_cents >= 0", name="ck_size_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id"), nullable=False)
    name: Mapped[str] = mapped_column(_NocaseString, nullable=False)
    portion_weight_g: Mapped[int] = mapped_column(nullable=False)
    price_cents: Mapped[int] = mapped_column(nullable=False)
    typical_yield_count: Mapped[int] = mapped_column(nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="sizes")
    batch_sizes: Mapped[list["BatchSize"]] = relationship(back_populates="size")


class Location(Base):
    """A kitchen, stand, market, or one of the four terminal built-ins."""

    __tablename__ = "location"
    __table_args__ = (CheckConstraint(f"kind IN ({_LOCATION_KINDS})", name="ck_location_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(_NocaseString, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)


class Entry(Base):
    """One user operation (`bake`, `visit`, `manual`, or `reversal`)."""

    __tablename__ = "entry"
    __table_args__ = (CheckConstraint(f"kind IN ({_ENTRY_KINDS})", name="ck_entry_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    voided: Mapped[bool] = mapped_column(nullable=False, default=False)
    reverses_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("entry.id"), nullable=True, unique=True
    )

    batch: Mapped["Batch | None"] = relationship(back_populates="entry", uselist=False)
    visit: Mapped["Visit | None"] = relationship(back_populates="entry", uselist=False)
    movements: Mapped[list["Movement"]] = relationship(back_populates="entry")


class Batch(Base):
    """A bake: recipe, bake entry, dates, and the frozen total cost."""

    __tablename__ = "batch"
    __table_args__ = (CheckConstraint("expires >= baked", name="ck_batch_expires_after_baked"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id"), nullable=False)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entry.id"), nullable=False, unique=True)
    baked: Mapped[date] = mapped_column(nullable=False)
    expires: Mapped[date] = mapped_column(nullable=False)
    # Frozen at bake time; a `BEFORE UPDATE OF total_cost_cents` trigger
    # (migration 0001) raises on any attempt to change this column, so no
    # write path -- ORM, Core, or raw SQL -- can move it after the fact.
    total_cost_cents: Mapped[int] = mapped_column(nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="batches")
    entry: Mapped[Entry] = relationship(back_populates="batch")
    batch_sizes: Mapped[list["BatchSize"]] = relationship(back_populates="batch")


class BatchSize(Base):
    """Per-(batch, size) count made and frozen unit cost."""

    __tablename__ = "batch_size"

    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"), primary_key=True)
    size_id: Mapped[int] = mapped_column(ForeignKey("size.id"), primary_key=True)
    count_made: Mapped[int] = mapped_column(nullable=False)
    # Frozen at bake time; a `BEFORE UPDATE OF unit_cost_cents` trigger
    # (migration 0001) raises on any attempt to change this column.
    unit_cost_cents: Mapped[int] = mapped_column(nullable=False)

    batch: Mapped[Batch] = relationship(back_populates="batch_sizes")
    size: Mapped[Size] = relationship(back_populates="batch_sizes")


class Movement(Base):
    """One append-only ledger row: `quantity` units, one batch and size, two locations."""

    __tablename__ = "movement"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_movement_quantity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entry.id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"), nullable=False)
    size_id: Mapped[int] = mapped_column(ForeignKey("size.id"), nullable=False)
    from_location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), nullable=False)
    to_location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    reverses_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("movement.id"), nullable=True, unique=True
    )

    entry: Mapped[Entry] = relationship(back_populates="movements")


class Visit(Base):
    """A stand or market visit: the entry's revenue, fee, and expected revenue."""

    __tablename__ = "visit"
    __table_args__ = (
        CheckConstraint("revenue_cents >= 0", name="ck_visit_revenue"),
        CheckConstraint("fee_cents >= 0", name="ck_visit_fee"),
    )

    entry_id: Mapped[int] = mapped_column(ForeignKey("entry.id"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), nullable=False)
    revenue_cents: Mapped[int] = mapped_column(nullable=False)
    fee_cents: Mapped[int] = mapped_column(nullable=False)
    expected_revenue_cents: Mapped[int] = mapped_column(nullable=False)

    entry: Mapped[Entry] = relationship(back_populates="visit")
