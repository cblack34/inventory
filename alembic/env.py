import os
from logging.config import fileConfig

from sqlalchemy import URL, engine_from_config, pool

from alembic import context
from inventory.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `DB`, when set, is an absolute path to the SQLite file to migrate; it
# overrides `alembic.ini`'s `sqlalchemy.url`. Tests instead call
# `Config.set_main_option("sqlalchemy.url", ...)` directly on a
# programmatic `Config`, which `config.get_main_option` below picks up
# without needing the environment variable at all.
_db_path = os.environ.get("DB")
if _db_path:
    url = URL.create("sqlite+pysqlite", database=_db_path)
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))

# Model metadata, for `alembic check` / `--autogenerate` drift comparison.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Uses a plain engine built straight from `sqlalchemy.url`, deliberately
    without this project's `inventory.db.engine.make_engine` and its
    `BEGIN IMMEDIATE` event hooks: Alembic drives its own transaction via
    `context.begin_transaction()`, and layering a `begin`-event override
    that issues `BEGIN IMMEDIATE` underneath that would fight Alembic for
    control of the transaction boundary. A migration runs once,
    single-threaded, with nothing else contending for the write lock, so
    the serialization that `make_engine` provides buys nothing here.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
