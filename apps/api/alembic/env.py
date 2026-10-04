"""
Alembic environment configuration.
"""

from sqlalchemy import engine_from_config, pool

from alembic import context

# Logging is configured by this import, before any application module: the
# container's entrypoint runs the migrations, so what `import_all_models()`
# logs reaches the container log — and before this import it did so under
# structlog's defaults (console rendering, DEBUG lines at LOG_LEVEL=INFO, no
# PII filter; measured in production 2026-10-03). Alembic's own `fileConfig`
# is gone with it: it would replace the root handler this configuration
# installed, and disable every logger created before it.
from src.infrastructure.observability import logging_bootstrap  # noqa: F401
from src.core.config import settings

# CRITICAL: Import ALL domain models so they are registered in Base.metadata
# Without these imports, Alembic's autogenerate will miss tables and migrations may fail
# Uses the centralized registry as single source of truth (DRY)
from src.infrastructure.database.models import Base
from src.infrastructure.database.registry import import_all_models

import_all_models()

# this is the Alembic Config object
config = context.config

# Get database URL from settings
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

# Object-exclusion policy (runtime/bridge tables, un-round-trippable indexes) is
# the single source of truth in schema_drift, shared with the structural-drift
# guard so the two never diverge (audit F042). server-default comparison is off
# there for the same reason: server defaults are migration-managed here.
from src.infrastructure.database.schema_drift import include_object  # noqa: E402


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

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
        compare_type=True,
        compare_server_default=False,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=False,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
