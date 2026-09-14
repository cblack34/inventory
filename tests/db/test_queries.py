"""Pins `stock_by_location` and `history`.

See `docs/acceptance.md`, "Home screen and expiration", "Profit", and
"Corrections", and `docs/data-model.md`, "Expiration" and "Profit".
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.queries import history, stock_by_location
from inventory.db.stock import load_stock
from inventory.db.visits import MarketVisit, record_market_visit
from inventory.db.writes import BakeRequest, ManualMove, record_bake, record_manual_move, undo
from inventory.domain.visits import MarketRow
from tests.db.seed import BakeFixture, SingleSizeRecipe, StandAndMarket

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_stock_by_location_excludes_terminal_locations_and_reports_per_batch_expiry_states(
    engine: Engine,
    single_size_recipe: SingleSizeRecipe,
    bake_fixture: BakeFixture,
    stand_and_market: StandAndMarket,
) -> None:
    today = date(2026, 1, 10)
    expired_batch_expires = date(2026, 1, 5)
    expiring_soon_expires = date(2026, 1, 12)

    # Two batches of the size under test, left completely untouched so
    # Kitchen's per-batch quantities stay exactly as baked.
    with Session(engine) as session:
        record_bake(
            session,
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=date(2025, 12, 1),
                expires=expired_batch_expires,
                counts={single_size_recipe.size_id: 4},
            ),
            now=_NOW,
        )
        record_bake(
            session,
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=date(2026, 1, 8),
                expires=expiring_soon_expires,
                counts={single_size_recipe.size_id: 6},
            ),
            now=_NOW,
        )
        session.commit()

    # A second, unrelated recipe supplies the activity that lands units in
    # Sold, Sampled, and Waste, per the acceptance wording this also pins
    # ("after a bake, a visit, and a toss") -- kept off the size above so
    # FIFO removals never touch the batches whose states are being checked.
    with Session(engine) as session:
        record_bake(
            session,
            BakeRequest(
                recipe_id=bake_fixture.recipe_id,
                baked=_NOW.date(),
                expires=_NOW.date() + timedelta(days=30),
                counts={bake_fixture.large_id: 4, bake_fixture.small_id: 4},
            ),
            now=_NOW,
        )
        session.commit()

        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        waste_id = load_builtin_locations(session).locations.waste_id
        record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=waste_id,
                size_id=bake_fixture.large_id,
                quantity=1,
            ),
            now=_NOW,
        )
        session.commit()

        record_market_visit(
            session,
            MarketVisit(
                market_id=stand_and_market.market_id,
                rows=[
                    MarketRow(size_id=bake_fixture.large_id, taken=2, returned=1, tossed=0),
                    MarketRow(size_id=bake_fixture.small_id, taken=2, returned=1, tossed=0),
                ],
                revenue_cents=100,
                fee_cents=0,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        result = stock_by_location(session, today)

    assert {location.kind for location in result} <= {"kitchen", "stand", "market"}

    kitchen = next(location for location in result if location.kind == "kitchen")
    target_size_id = single_size_recipe.size_id
    size_stocks = [
        size_stock for size_stock in kitchen.sizes if size_stock.size_id == target_size_id
    ]
    assert len(size_stocks) == 1
    size_stock = size_stocks[0]

    states_by_quantity = {batch.quantity: batch.state for batch in size_stock.batches}
    assert states_by_quantity[4] == "expired"
    assert states_by_quantity[6] == "expiring_soon"


def test_history_lists_newest_first_and_a_voided_visit_has_no_profit_figure(
    engine: Engine, single_size_recipe: SingleSizeRecipe, stand_and_market: StandAndMarket
) -> None:
    with Session(engine) as session:
        record_bake(
            session,
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=_NOW.date(),
                expires=_NOW.date() + timedelta(days=30),
                counts={single_size_recipe.size_id: 10},
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        stock_before_visit, _batches = load_stock(session)

        market_row = MarketRow(size_id=single_size_recipe.size_id, taken=10, returned=3, tossed=1)
        visit_entry_id = record_market_visit(
            session,
            MarketVisit(
                market_id=stand_and_market.market_id,
                rows=[market_row],
                revenue_cents=600,
                fee_cents=0,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        undo(session, entry_id=visit_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session:
        stock_after_undo, _batches = load_stock(session)

    assert stock_after_undo == stock_before_visit

    with Session(engine) as session:
        entries = history(session)

    # Newest first: the reversal entry (created after the visit) leads.
    assert entries[0].kind == "reversal"

    visit_history = next(entry for entry in entries if entry.entry_id == visit_entry_id)
    assert visit_history.voided is True
    assert visit_history.profit_cents is None
    assert visit_history.location_id == stand_and_market.market_id
