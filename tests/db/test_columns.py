"""Pins non-negotiable 4 (money is never a float) for the ORM layer, and the
"no deletes" rule from `docs/schema.md` for every relationship and
foreign key among the ten mapped tables.
"""

from sqlalchemy import Float, Integer, Numeric, Table
from sqlalchemy.orm import RelationshipProperty

from inventory.db.models import Base

# Every column name the data model calls out as money, weight, or a
# quantity a user enters (see `docs/data-model.md` and `docs/acceptance.md`
# "Money"). Update this set when a money, weight, or quantity column is
# added to `inventory.db.models`.
_INTEGER_COLUMN_SUFFIXES = ("_cents", "_g")
_INTEGER_COLUMN_NAMES = {
    "quantity",
    "count_made",
    "typical_yield_count",
    "shelf_life_days",
}


def _all_columns() -> list[tuple[str, str, object]]:
    columns: list[tuple[str, str, object]] = []
    for mapper in Base.registry.mappers:
        # Every mapped class here uses `__tablename__`, so `local_table` is
        # always the plain `Table` (never `None`, never a joined/derived
        # `FromClause`); the assertion narrows the type for `.name` below.
        table = mapper.local_table
        assert isinstance(table, Table)
        columns.extend((table.name, column.name, column.type) for column in mapper.columns)
    return columns


def test_pinned_money_weight_and_quantity_columns_are_integer() -> None:
    offenders: list[str] = []
    for table_name, column_name, column_type in _all_columns():
        is_pinned = column_name.endswith(_INTEGER_COLUMN_SUFFIXES) or (
            column_name in _INTEGER_COLUMN_NAMES
        )
        if is_pinned and not isinstance(column_type, Integer):
            offenders.append(f"{table_name}.{column_name}: {column_type!r}")
    assert offenders == []


def test_no_column_anywhere_is_float_or_numeric() -> None:
    offenders = [
        f"{table_name}.{column_name}: {column_type!r}"
        for table_name, column_name, column_type in _all_columns()
        if isinstance(column_type, Float | Numeric)
    ]
    assert offenders == []


def test_no_relationship_cascades_deletes() -> None:
    offenders: list[str] = []
    for mapper in Base.registry.mappers:
        for relationship_property in mapper.relationships:
            assert isinstance(relationship_property, RelationshipProperty)
            cascade = relationship_property.cascade
            if "delete" in cascade or "delete-orphan" in cascade:
                offenders.append(f"{mapper.class_.__name__}.{relationship_property.key}")
    assert offenders == []


def test_no_foreign_key_cascades_deletes() -> None:
    offenders: list[str] = []
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        assert isinstance(table, Table)
        offenders.extend(
            f"{table.name}.{foreign_key.parent.name}"
            for foreign_key in table.foreign_keys
            if foreign_key.ondelete is not None and foreign_key.ondelete.upper() == "CASCADE"
        )
    assert offenders == []
