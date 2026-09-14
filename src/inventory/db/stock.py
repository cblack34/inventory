"""Read helpers over an open `Session`: derived stock and frozen unit costs.

Both fold or select straight from the ledger tables; neither writes
anything. See `docs/data-model.md`, "Concepts" (on-hand is derived, never
stored) and `inventory.domain.ledger` for the fold and ordering rules this
module feeds into.
"""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Batch, BatchSize
from inventory.db.models import Movement as MovementRow
from inventory.domain.ledger import BatchOrder, OnHand, on_hand
from inventory.domain.ledger import Movement as LedgerMovement


def load_stock(session: Session) -> tuple[OnHand, dict[int, BatchOrder]]:
    """Fold every movement row into on-hand, plus every batch's FIFO order.

    Every movement counts, voided entry or not: a voided entry's own
    reversal rows already net it back to zero, so filtering by `voided`
    here would double-subtract that entry's stock. Only inventory
    locations (Kitchen, stands, markets) appear in the on-hand result;
    see `inventory.db.builtins`.
    """
    builtins = load_builtin_locations(session)
    rows = session.execute(select(MovementRow)).scalars().all()
    movements = [
        LedgerMovement(
            id=row.id,
            batch_id=row.batch_id,
            size_id=row.size_id,
            from_location_id=row.from_location_id,
            to_location_id=row.to_location_id,
            quantity=row.quantity,
        )
        for row in rows
    ]
    stock = on_hand(movements, builtins.locations.inventory_location_ids)

    batch_rows = session.execute(select(Batch.id, Batch.baked, Batch.expires)).all()
    batches = {
        row.id: BatchOrder(batch_id=row.id, expires=row.expires, baked=row.baked)
        for row in batch_rows
    }
    return stock, batches


def unit_costs(session: Session, batch_ids: Collection[int]) -> dict[tuple[int, int], int]:
    """Frozen per-`(batch_id, size_id)` unit costs for the given batch ids."""
    if not batch_ids:
        return {}
    rows = session.execute(
        select(BatchSize.batch_id, BatchSize.size_id, BatchSize.unit_cost_cents).where(
            BatchSize.batch_id.in_(batch_ids)
        )
    ).all()
    return {(row.batch_id, row.size_id): row.unit_cost_cents for row in rows}
