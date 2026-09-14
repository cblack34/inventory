"""SQLAlchemy models, engine factory, and Alembic-backed persistence.

Import direction is db -> domain only: this package imports from
``inventory.domain``, never the reverse (see
``tests/domain/test_purity.py``).
"""
