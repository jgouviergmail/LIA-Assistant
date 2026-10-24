"""The PostgreSQL bounds every connection of the application engine starts with (AC-028).

A session lives no longer than the queries it serves (ADR-304), and until now nothing
on the server said so: a lock wait lasted as long as its holder, and a transaction left
open across a network call stayed open for as long as the call took — 863 s once, in
production. The application engine now hands PostgreSQL two bounds at connect time
(``engine_server_settings``): ``lock_timeout`` and ``idle_in_transaction_session_timeout``.
They are connection DEFAULTS, so a transaction's own ``SET LOCAL`` still tightens one
for itself — the OAuth refresh door does. The migration engine (a migration may hold a
lock longer than any request should wait for one) and the LangGraph pools do not carry
them.

Each time a bound ends a statement or a session the engine counts it
(``db_bound_reached_total{bound}``), from ``handle_error`` — which sees every failure of
the engine, not only those of the repositories. A refusal is read from its SQLSTATE,
never from its message. The end of an idle transaction is the exception: asyncpg reports
it as a bare disconnect with NO SQLSTATE (measured on PostgreSQL 16 — the server's
25P03 never reaches the client), so the engine keeps, per connection, when its
transaction last went idle, and a disconnect that follows an idle span past the bound
is that bound.
"""

from __future__ import annotations

import time
from typing import Final, Literal

import structlog
from sqlalchemy import event
from sqlalchemy.engine import Connection, ExceptionContext
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import ConnectionPoolEntry

from src.core.config import settings
from src.infrastructure.database.errors import database_error_fields
from src.infrastructure.observability.metrics_database import db_bound_reached_total

logger = structlog.get_logger(__name__)

DatabaseBound = Literal["lock_timeout", "idle_in_transaction_timeout", "statement_timeout"]

#: The refusals a bound ends a statement with (PostgreSQL appendix A).
_BOUND_BY_SQLSTATE: Final[dict[str, DatabaseBound]] = {
    "55P03": "lock_timeout",  # lock_not_available
    "57014": "statement_timeout",  # query_canceled
    # idle_in_transaction_session_timeout — when a driver does report it (asyncpg does not).
    "25P03": "idle_in_transaction_timeout",
}

#: Where a connection keeps when its transaction last went idle (``Connection.info``).
IDLE_SINCE_KEY: Final = "lia_idle_in_transaction_since"


def engine_server_settings() -> dict[str, str]:
    """The bounds the application engine's connections start with, in milliseconds.

    Returns:
        PostgreSQL settings for asyncpg's ``server_settings``; a bound set to 0 is left
        out, so the server keeps its own setting rather than being told 0.
    """
    bounds = {
        "lock_timeout": settings.database_lock_timeout_ms,
        "idle_in_transaction_session_timeout": settings.database_idle_in_transaction_timeout_ms,
    }
    return {name: str(value) for name, value in bounds.items() if value > 0}


def install_bound_counter(engine: AsyncEngine) -> None:
    """Count every statement or session one of the engine's bounds ends.

    Args:
        engine: The engine whose connections carry ``engine_server_settings``.
    """
    sync = engine.sync_engine
    event.listen(sync, "after_cursor_execute", _note_idle)
    event.listen(sync, "commit", _forget_idle)
    event.listen(sync, "rollback", _forget_idle)
    event.listen(sync.pool, "checkin", _forget_idle_on_checkin)
    event.listen(sync, "handle_error", _count)


def bound_reached(context: ExceptionContext) -> DatabaseBound | None:
    """Which bound, if any, ended the statement or the session ``context`` reports.

    Args:
        context: What SQLAlchemy hands ``handle_error``.

    Returns:
        The bound — read from the server's SQLSTATE, or, for a bare disconnect, from the
        idle span the engine kept — or None when no bound is the cause.
    """
    sqlstate = database_error_fields(_failure_of(context)).get("sqlstate")
    if sqlstate in _BOUND_BY_SQLSTATE:
        return _BOUND_BY_SQLSTATE[sqlstate]
    # A pooled connection is in no transaction: its ping never meets the idle bound.
    connection = context.connection
    if not context.is_disconnect or context.is_pre_ping or connection is None:
        return None
    if connection.invalidated:  # reading ``info`` would revalidate it
        return None
    since = connection.info.get(IDLE_SINCE_KEY)
    bound_ms = settings.database_idle_in_transaction_timeout_ms
    if since is None or bound_ms <= 0:
        return None
    return "idle_in_transaction_timeout" if (time.monotonic() - since) * 1000 >= bound_ms else None


def _note_idle(conn: Connection, *_statement: object) -> None:
    """A statement ended: an open transaction is idle from now on."""
    if conn.in_transaction():
        conn.info[IDLE_SINCE_KEY] = time.monotonic()


def _forget_idle(conn: Connection) -> None:
    """The transaction ended: nothing is idle in it any more.

    An invalidated connection is left untouched — its record is discarded with it,
    and reading ``info`` would try to revalidate it, which a rollback after a
    disconnect must never be made to do (it raised ``PendingRollbackError``).
    """
    if not conn.invalidated:
        conn.info.pop(IDLE_SINCE_KEY, None)


def _forget_idle_on_checkin(
    _dbapi_connection: object, connection_record: ConnectionPoolEntry
) -> None:
    """A connection back in the pool holds no transaction, whatever ended it."""
    connection_record.info.pop(IDLE_SINCE_KEY, None)


def _count(context: ExceptionContext) -> None:
    bound = bound_reached(context)
    if bound is None:
        return
    db_bound_reached_total.labels(bound=bound).inc()
    logger.warning(
        "database_bound_reached", bound=bound, **database_error_fields(_failure_of(context))
    )


def _failure_of(context: ExceptionContext) -> BaseException:
    """The failure as SQLAlchemy wraps it, else as the driver raised it."""
    return context.sqlalchemy_exception or context.original_exception
