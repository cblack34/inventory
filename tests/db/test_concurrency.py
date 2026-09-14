"""Pins serialized removals: two concurrent over-removals, exactly one succeeds.

See `docs/data-model.md`, "Visit settlement" ("every entry that moves
stock ... runs in a serialized write transaction (`BEGIN IMMEDIATE` on
SQLite, with a busy timeout)") and `docs/acceptance.md`, "Ledger, stock,
and FIFO". Runs against the file-backed `engine` fixture, never
`:memory:`, and uses a `threading.Barrier` so both threads open their
write transaction at the same instant rather than racing to start.
"""

import threading
from datetime import UTC, datetime

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.engine import make_session_factory, write_engine
from inventory.db.stock import load_stock
from inventory.db.transaction import write_transaction
from inventory.db.writes import BakeRequest, ManualMove, record_bake, record_manual_move
from inventory.domain.ledger import InsufficientStock
from tests.db.seed import SingleSizeRecipe

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_two_concurrent_manual_removals_over_on_hand_exactly_one_succeeds(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    session_factory = make_session_factory(write_engine(engine))
    with write_transaction(session_factory) as session:
        record_bake(
            session,
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=_NOW.date(),
                expires=_NOW.date(),
                counts={single_size_recipe.size_id: 10},
            ),
            now=_NOW,
        )

    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        kitchen_id = locations.kitchen_id
        waste_id = locations.waste_id

    barrier = threading.Barrier(2)
    outcomes: list[BaseException | None] = [None, None]

    def remove_six(index: int) -> None:
        barrier.wait()
        try:
            with write_transaction(session_factory) as session:
                record_manual_move(
                    session,
                    ManualMove(
                        from_location_id=kitchen_id,
                        to_location_id=waste_id,
                        size_id=single_size_recipe.size_id,
                        quantity=6,
                    ),
                    now=_NOW,
                )
        except Exception as exc:
            outcomes[index] = exc

    threads = [threading.Thread(target=remove_six, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    successes = [outcome for outcome in outcomes if outcome is None]
    failures = [outcome for outcome in outcomes if outcome is not None]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], InsufficientStock)

    with Session(engine) as session:
        stock, _batches = load_stock(session)

    remaining = sum(
        quantity
        for (location_id, size_id, _batch_id), quantity in stock.items()
        if location_id == kitchen_id and size_id == single_size_recipe.size_id
    )
    assert remaining == 4
