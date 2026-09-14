"""Pins `record_stand_visit`, `record_market_visit`, and `visit_profit`.

See `docs/acceptance.md`, "Stand visit", "Market visit", "Profit", and
`docs/data-model.md`, "Visit settlement" and "Profit".
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Entry, Location, Size
from inventory.db.models import Movement as MovementRow
from inventory.db.models import Visit as VisitRow
from inventory.db.visits import (
    EntryIsNotAVisitError,
    InvalidQuantityError,
    InvalidVisitLocationError,
    MarketVisit,
    StandVisit,
    record_market_visit,
    record_stand_visit,
    visit_profit,
)
from inventory.db.writes import BakeRequest, ManualMove, record_bake, record_manual_move, undo
from inventory.domain.ledger import InsufficientStock
from inventory.domain.visits import MarketOverTakenError, MarketRow, StandRow
from tests.db.seed import BakeFixture, SingleSizeRecipe, StandAndMarket

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
_BAKED = _NOW.date()
_EXPIRES = _BAKED + timedelta(days=30)


def _row_counts(session: Session) -> tuple[int, int, int]:
    entry_count = session.execute(select(func.count()).select_from(Entry)).scalar_one()
    visit_count = session.execute(select(func.count()).select_from(VisitRow)).scalar_one()
    movement_count = session.execute(select(func.count()).select_from(MovementRow)).scalar_one()
    return entry_count, visit_count, movement_count


def _bake(session: Session, recipe_id: int, counts: dict[int, int]) -> None:
    record_bake(
        session,
        BakeRequest(recipe_id=recipe_id, baked=_BAKED, expires=_EXPIRES, counts=counts),
        now=_NOW,
    )
    session.commit()


def _transfer(session: Session, *, size_id: int, to_location_id: int, quantity: int) -> None:
    kitchen_id = load_builtin_locations(session).locations.kitchen_id
    record_manual_move(
        session,
        ManualMove(
            from_location_id=kitchen_id,
            to_location_id=to_location_id,
            size_id=size_id,
            quantity=quantity,
        ),
        now=_NOW,
    )
    session.commit()


def test_stand_visit_routes_priced_size_to_sold_and_zero_price_size_to_sampled(
    engine: Engine, bake_fixture: BakeFixture, stand_and_market: StandAndMarket
) -> None:
    stand_id = stand_and_market.stand_id
    with Session(engine) as session:
        _bake(session, bake_fixture.recipe_id, {bake_fixture.large_id: 5, bake_fixture.small_id: 5})
        _transfer(session, size_id=bake_fixture.large_id, to_location_id=stand_id, quantity=3)
        _transfer(session, size_id=bake_fixture.small_id, to_location_id=stand_id, quantity=3)

    with Session(engine) as session:
        entry_id = record_stand_visit(
            session,
            StandVisit(
                stand_id=stand_and_market.stand_id,
                rows=[
                    StandRow(size_id=bake_fixture.large_id, counted=2, tossed=0, pulled=0, added=0),
                    StandRow(size_id=bake_fixture.small_id, counted=2, tossed=0, pulled=0, added=0),
                ],
                revenue_cents=300,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        movements = (
            session.execute(select(MovementRow).where(MovementRow.entry_id == entry_id))
            .scalars()
            .all()
        )
        assert all(movement.entry_id == entry_id for movement in movements)

        sold = [movement for movement in movements if movement.to_location_id == locations.sold_id]
        sampled = [
            movement for movement in movements if movement.to_location_id == locations.sampled_id
        ]
        assert [(movement.size_id, movement.quantity) for movement in sold] == [
            (bake_fixture.large_id, 1)
        ]
        assert [(movement.size_id, movement.quantity) for movement in sampled] == [
            (bake_fixture.small_id, 1)
        ]

        visit_row = session.get_one(VisitRow, entry_id)
        assert visit_row.fee_cents == 0


def test_record_market_visit_rejects_over_taken_and_writes_nothing(
    engine: Engine, single_size_recipe: SingleSizeRecipe, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session:
        _bake(session, single_size_recipe.recipe_id, {single_size_recipe.size_id: 10})

    with Session(engine) as session:
        before = _row_counts(session)
        with pytest.raises(MarketOverTakenError):
            record_market_visit(
                session,
                MarketVisit(
                    market_id=stand_and_market.market_id,
                    rows=[
                        MarketRow(size_id=single_size_recipe.size_id, taken=5, returned=4, tossed=3)
                    ],
                    revenue_cents=0,
                    fee_cents=0,
                ),
                now=_NOW,
            )
        session.rollback()

    with Session(engine) as session:
        assert _row_counts(session) == before
        market_movements = (
            session.execute(
                select(MovementRow).where(MovementRow.to_location_id == stand_and_market.market_id)
            )
            .scalars()
            .all()
        )
        assert market_movements == []


def test_visit_locations_are_rejected_for_wrong_kind_terminal_or_inactive(
    engine: Engine, single_size_recipe: SingleSizeRecipe, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session:
        _bake(session, single_size_recipe.recipe_id, {single_size_recipe.size_id: 10})

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        waste_id = load_builtin_locations(session).locations.waste_id

        with pytest.raises(InvalidVisitLocationError):
            record_stand_visit(
                session, StandVisit(stand_id=kitchen_id, rows=[], revenue_cents=0), now=_NOW
            )
        with pytest.raises(InvalidVisitLocationError):
            record_stand_visit(
                session, StandVisit(stand_id=waste_id, rows=[], revenue_cents=0), now=_NOW
            )
        with pytest.raises(InvalidVisitLocationError):
            record_market_visit(
                session,
                MarketVisit(
                    market_id=stand_and_market.stand_id, rows=[], revenue_cents=0, fee_cents=0
                ),
                now=_NOW,
            )
        with pytest.raises(InvalidVisitLocationError):
            record_stand_visit(
                session,
                StandVisit(stand_id=stand_and_market.market_id, rows=[], revenue_cents=0),
                now=_NOW,
            )


def test_visit_against_an_inactive_stand_is_rejected(
    engine: Engine, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session:
        location = session.get_one(Location, stand_and_market.stand_id)
        location.active = False
        session.commit()

    with Session(engine) as session, pytest.raises(InvalidVisitLocationError):
        record_stand_visit(
            session,
            StandVisit(stand_id=stand_and_market.stand_id, rows=[], revenue_cents=0),
            now=_NOW,
        )


def test_record_stand_visit_rejects_negative_revenue(
    engine: Engine, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session, pytest.raises(InvalidQuantityError):
        record_stand_visit(
            session,
            StandVisit(stand_id=stand_and_market.stand_id, rows=[], revenue_cents=-1),
            now=_NOW,
        )


def test_record_market_visit_rejects_negative_fee(
    engine: Engine, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session, pytest.raises(InvalidQuantityError):
        record_market_visit(
            session,
            MarketVisit(
                market_id=stand_and_market.market_id, rows=[], revenue_cents=0, fee_cents=-1
            ),
            now=_NOW,
        )


def test_expected_revenue_is_frozen_against_a_later_price_change_and_shrink_is_positive(
    engine: Engine, single_size_recipe: SingleSizeRecipe, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session:
        _bake(session, single_size_recipe.recipe_id, {single_size_recipe.size_id: 10})
        _transfer(
            session,
            size_id=single_size_recipe.size_id,
            to_location_id=stand_and_market.stand_id,
            quantity=5,
        )

    with Session(engine) as session:
        entry_id = record_stand_visit(
            session,
            StandVisit(
                stand_id=stand_and_market.stand_id,
                rows=[
                    StandRow(
                        size_id=single_size_recipe.size_id,
                        counted=3,
                        tossed=0,
                        pulled=0,
                        added=0,
                    )
                ],
                revenue_cents=150,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        visit_row = session.get_one(VisitRow, entry_id)
        assert visit_row.expected_revenue_cents == 200
        assert visit_row.fee_cents == 0
        shrink_cents = visit_row.expected_revenue_cents - visit_row.revenue_cents
        assert shrink_cents == 50

        size = session.get_one(Size, single_size_recipe.size_id)
        size.price_cents = 999
        session.commit()

    with Session(engine) as session:
        visit_row = session.get_one(VisitRow, entry_id)
        assert visit_row.expected_revenue_cents == 200


def test_visit_profit_reports_three_separate_cost_lines_and_goes_negative_when_fee_exceeds_revenue(
    engine: Engine, bake_fixture: BakeFixture, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session:
        counts = {bake_fixture.large_id: 10, bake_fixture.small_id: 10}
        _bake(session, bake_fixture.recipe_id, counts)

    with Session(engine) as session:
        entry_id = record_market_visit(
            session,
            MarketVisit(
                market_id=stand_and_market.market_id,
                rows=[
                    MarketRow(size_id=bake_fixture.large_id, taken=10, returned=2, tossed=1),
                    MarketRow(size_id=bake_fixture.small_id, taken=10, returned=3, tossed=0),
                ],
                revenue_cents=500,
                fee_cents=2000,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        profit = visit_profit(session, entry_id)

    assert profit.sold_cost_cents == 560
    assert profit.waste_cost_cents == 80
    assert profit.sampled_cost_cents == 140
    assert profit.profit_cents == -2280


def test_visit_profit_rejects_an_entry_with_no_visit_row(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    with Session(engine) as session:
        record_bake(
            session,
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=_BAKED,
                expires=_EXPIRES,
                counts={single_size_recipe.size_id: 5},
            ),
            now=_NOW,
        )
        session.commit()
        bake_entry_id = session.execute(
            select(MovementRow.entry_id).where(MovementRow.size_id == single_size_recipe.size_id)
        ).scalar_one()

    with Session(engine) as session, pytest.raises(EntryIsNotAVisitError):
        visit_profit(session, bake_entry_id)


def test_manual_move_that_drains_a_batch_after_a_visit_blocks_its_undo(
    engine: Engine, single_size_recipe: SingleSizeRecipe, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session:
        _bake(session, single_size_recipe.recipe_id, {single_size_recipe.size_id: 10})
        _transfer(
            session,
            size_id=single_size_recipe.size_id,
            to_location_id=stand_and_market.stand_id,
            quantity=6,
        )

    with Session(engine) as session:
        stand_visit_entry_id = record_stand_visit(
            session,
            StandVisit(
                stand_id=stand_and_market.stand_id,
                rows=[
                    StandRow(
                        size_id=single_size_recipe.size_id,
                        counted=6,
                        tossed=0,
                        pulled=6,
                        added=0,
                    )
                ],
                revenue_cents=0,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        before = _row_counts(session)
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        waste_id = load_builtin_locations(session).locations.waste_id
        record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=waste_id,
                size_id=single_size_recipe.size_id,
                quantity=10,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        before_undo = _row_counts(session)
        with pytest.raises(InsufficientStock):
            undo(session, entry_id=stand_visit_entry_id, now=_NOW)
        session.rollback()

    with Session(engine) as session:
        assert _row_counts(session) == before_undo
        assert before_undo != before  # the drain itself did write rows
        assert session.get_one(Entry, stand_visit_entry_id).voided is False
