"""Pydantic v2 schemas for batches, movements, reversals, visits, entries, stock.

Every input model forbids unknown keys and validates strictly (no `"1"`
for an `int` field, no `1.5` either), matching
`inventory.api.schemas.catalog`. `counts` on a bake is a list of
`{size_id, count}` items rather than `dict[int, int]`: a JSON object's
keys always arrive as strings, and `strict=True` makes Pydantic reject
a string key for an `int`-keyed dict outright, so the wire shape has to
be a list; `BatchCreate.counts_by_size` converts it to the mapping
`inventory.db.writes.BakeRequest` wants. `VisitCreate` is a
discriminated union on `kind`: a stand payload carrying `fee_cents`, or
any payload carrying an unrecognized key, is rejected by
`extra="forbid"` before the discriminator is even consulted. Money
fields end in `_cents`, matching `inventory.db.models`.
"""

from datetime import UTC, date, datetime
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inventory.api.schemas.ids import Id
from inventory.db.models import Batch
from inventory.db.models import Visit as VisitRow
from inventory.domain.visits import Profit

# --- Batches ------------------------------------------------------------------


class BakeCountItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    size_id: Id
    count: int = Field(ge=0)


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    recipe_id: Id
    # `strict=False` overrides the model-level `strict=True` for these two
    # fields only: JSON has no date type, and pydantic's *strict* mode --
    # unlike its default lenient mode -- refuses to parse an ISO 8601
    # string into a `date` even when it arrived as a JSON body, so a
    # strict `date` field would reject every legal request. Money and
    # quantity fields stay strict; only the wire representation of a date
    # needs the carve-out.
    baked: date = Field(strict=False)
    expires: date = Field(strict=False)
    counts: list[BakeCountItem] = Field(min_length=1)

    @field_validator("counts")
    @classmethod
    def _reject_duplicate_sizes(cls, counts: list[BakeCountItem]) -> list[BakeCountItem]:
        seen: set[int] = set()
        for item in counts:
            if item.size_id in seen:
                msg = f"size_id {item.size_id} appears more than once in counts"
                raise ValueError(msg)
            seen.add(item.size_id)
        return counts

    def counts_by_size(self) -> dict[int, int]:
        """`counts` as `BakeRequest` wants it; size ids are unique by validation."""
        return {item.size_id: item.count for item in self.counts}


class BatchSizeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    size_id: int
    count_made: int
    unit_cost_cents: int


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipe_id: int
    entry_id: int
    baked: date
    expires: date
    total_cost_cents: int
    sizes: list[BatchSizeRead]

    @classmethod
    def from_model(cls, batch: Batch) -> BatchRead:
        return cls(
            id=batch.id,
            recipe_id=batch.recipe_id,
            entry_id=batch.entry_id,
            baked=batch.baked,
            expires=batch.expires,
            total_cost_cents=batch.total_cost_cents,
            sizes=[BatchSizeRead.model_validate(size) for size in batch.batch_sizes],
        )


# --- Movements ------------------------------------------------------------------


class MovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    from_location_id: Id
    to_location_id: Id
    size_id: Id
    quantity: int = Field(ge=1)


# --- Reversals ------------------------------------------------------------------


class ReversalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entry_id: Id


class ReversalRead(BaseModel):
    entry_id: int
    reverses_entry_id: int


# --- Visits ---------------------------------------------------------------------


class StandRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    size_id: Id
    counted: int = Field(ge=0)
    tossed: int = Field(ge=0)
    pulled: int = Field(ge=0)
    added: int = Field(ge=0)


class MarketRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    size_id: Id
    taken: int = Field(ge=0)
    returned: int = Field(ge=0)
    tossed: int = Field(ge=0)


class StandVisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["stand"]
    location_id: Id
    rows: list[StandRowIn] = Field(default_factory=list[StandRowIn])
    revenue_cents: int = Field(ge=0)


class MarketVisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["market"]
    location_id: Id
    rows: list[MarketRowIn] = Field(default_factory=list[MarketRowIn])
    revenue_cents: int = Field(ge=0)
    fee_cents: int = Field(ge=0)


VisitCreate = Annotated[StandVisitCreate | MarketVisitCreate, Field(discriminator="kind")]


class ProfitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sold_cost_cents: int
    waste_cost_cents: int
    sampled_cost_cents: int
    profit_cents: int


class VisitRead(BaseModel):
    entry_id: int
    kind: Literal["stand", "market"]
    location_id: int
    revenue_cents: int
    fee_cents: int
    expected_revenue_cents: int
    difference_cents: int
    profit: ProfitRead | None

    @classmethod
    def from_row(
        cls, *, entry_id: int, kind: str, visit_row: VisitRow, profit: Profit | None
    ) -> VisitRead:
        """Build a `VisitRead`; `profit` is `None` for a voided visit.

        `difference_cents = expected_revenue_cents - revenue_cents`
        (`docs/data-model.md`, "Visit settlement"): positive when the
        visit came up short, whatever the caller calls that difference
        for its own visit type.
        """
        return cls(
            entry_id=entry_id,
            kind=cast(Literal["stand", "market"], kind),
            location_id=visit_row.location_id,
            revenue_cents=visit_row.revenue_cents,
            fee_cents=visit_row.fee_cents,
            expected_revenue_cents=visit_row.expected_revenue_cents,
            difference_cents=visit_row.expected_revenue_cents - visit_row.revenue_cents,
            profit=ProfitRead.model_validate(profit) if profit is not None else None,
        )


# --- Entries --------------------------------------------------------------------


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_id: int
    kind: str
    created_at: datetime
    voided: bool
    location_id: int | None
    revenue_cents: int | None
    profit_cents: int | None

    @field_validator("created_at")
    @classmethod
    def _created_at_as_utc(cls, value: datetime) -> datetime:
        """Attach `tzinfo=UTC` to a naive `created_at`.

        SQLite's `DateTime` column round-trips a `datetime` as naive
        (`inventory.api.deps.now` always writes UTC, but the driver
        drops the offset), so the JSON response would otherwise carry
        an ambiguous, offset-less timestamp instead of `+00:00`/`Z`.
        """
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# --- Stock ----------------------------------------------------------------------


class BatchStockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    expires: date
    quantity: int
    state: Literal["expired", "expiring_soon", "ok"]


class SizeStockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    size_id: int
    size_name: str
    recipe_id: int
    recipe_name: str
    quantity: int
    batches: list[BatchStockRead]


class StockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    location_id: int
    name: str
    kind: str
    sizes: list[SizeStockRead]
