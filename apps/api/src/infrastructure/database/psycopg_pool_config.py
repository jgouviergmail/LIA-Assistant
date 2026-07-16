"""Shared psycopg (libpq) configuration for the LangGraph PostgreSQL pools.

The checkpointer (``domains/conversations/checkpointer.py``) and the LangGraph
Store (``domains/agents/context/store.py``) each open a psycopg
``AsyncConnectionPool``. Both historically duplicated the conninfo resolution
(``settings.database_url`` → psycopg form) and the connection kwargs, and
neither bounded connection ESTABLISHMENT: without ``connect_timeout``, a
connect whose TCP handshake stalls (e.g. a freshly published Docker port on
Windows that black-holes the SYN) is left to kernel-level TCP behavior instead
of a policy we control. This module centralizes both concerns (single source
of truth, one timeout policy).

Note: the frozen-run incident at ``checkpointer_initializing`` was NOT a
connect issue — it was the savers' ``CREATE INDEX CONCURRENTLY`` migrations
deadlocking against an open test transaction; see
``tests/conftest.py::_provision_langgraph_tables`` for that fix.

``set_psycopg_url_override`` additionally gives tests an EXPLICIT injection
point for the pools' database URL, independent of the ``settings`` object —
mirroring ``reset_checkpointer`` / ``reset_tool_context_store`` as the
test-only escape hatches of those singletons.
"""

from typing import Any

from psycopg.rows import dict_row

from src.core.config import settings

# Test-only URL override (see set_psycopg_url_override). None in production.
_psycopg_url_override: str | None = None


def resolve_psycopg_url() -> str:
    """Resolve the libpq/psycopg connection URL for the LangGraph pools.

    Returns:
        The explicit override when one is injected (tests), otherwise
        ``settings.database_url`` converted from the asyncpg SQLAlchemy form
        (``postgresql+asyncpg://``) to the plain psycopg form
        (``postgresql://``).
    """
    if _psycopg_url_override is not None:
        return _psycopg_url_override
    return str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")


def set_psycopg_url_override(url: str | None) -> None:
    """Inject (or clear, with ``None``) an explicit URL for the LangGraph pools.

    WARNING: Test-only. Production code must never call this — the pools
    resolve their URL from settings. Test fixtures use it to guarantee the
    checkpointer/store pools target the test database regardless of how the
    settings object is composed.

    Args:
        url: psycopg-form URL (``postgresql://…``), or ``None`` to clear.
    """
    global _psycopg_url_override
    _psycopg_url_override = url


def psycopg_pool_kwargs() -> dict[str, Any]:
    """Connection kwargs shared by the checkpointer and Store pools.

    ``autocommit``/``prepare_threshold``/``row_factory`` mirror upstream
    ``AsyncPostgresSaver.from_conn_string`` requirements (setup migrations run
    autocommit; the savers require ``dict_row``). ``connect_timeout`` bounds
    the establishment of ONE connection: a stalled connect fails after N
    seconds and is retried by the pool (or surfaces as a loud ``PoolTimeout``)
    instead of being left to kernel TCP behavior.

    Returns:
        A fresh dict per call (callers must never share a mutable one).
    """
    return {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
        "connect_timeout": settings.database_connect_timeout,
    }
