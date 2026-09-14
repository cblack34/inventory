"""Pure domain rules: money math, ledger, FIFO, settlement, profit, expiration.

Nothing in this package imports FastAPI, SQLAlchemy, or any IO. A test imports
every submodule in a fresh subprocess and fails if either framework loads.
Weights are integer grams (``_g``); money is integer cents (``_cents``).
"""


class DomainError(Exception):
    """Base for every rule violation the domain raises.

    The API layer maps subclasses to HTTP responses in one place.
    """
