"""Every connection of the application engine starts bounded (audit AC-028, ADR-304).

A session lives no longer than the queries it serves; until now nothing on the server
said so. A lock wait could last as long as its holder, and a transaction left open
across a network call stayed open for as long as the call took — 863 s once, on
production (ADR-304). The application engine now hands PostgreSQL two bounds at
connect time, and counts each time one of them ends a statement or a session.
"""

from __future__ import annotations

import ast
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, ExceptionContext
from sqlalchemy.exc import DBAPIError

from src.core.config import settings
from src.infrastructure.database import server_bounds
from src.infrastructure.database.server_bounds import bound_reached, engine_server_settings

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[4]


class _DriverError(Exception):
    """What the driver raises: its SQLSTATE is the only fact the counter may read."""

    def __init__(self, sqlstate: str | None) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class _Context(ExceptionContext):
    """What SQLAlchemy hands ``handle_error``: the facts the counter reads, nothing else."""

    def __init__(
        self,
        connection: Connection | None,
        *,
        sqlstate: str | None,
        is_disconnect: bool,
        is_pre_ping: bool,
    ) -> None:
        driver_error = _DriverError(sqlstate)
        self.original_exception = driver_error
        self.sqlalchemy_exception = DBAPIError("SELECT 1", None, driver_error)
        self.connection = connection
        self.is_disconnect = is_disconnect
        self.is_pre_ping = is_pre_ping


@pytest.fixture
def connection() -> Iterator[Connection]:
    """A real connection: its ``info`` and its invalidation behave as the engine's do."""
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as conn:
            yield conn
    finally:
        engine.dispose()


def _context(
    connection: Connection | None = None,
    *,
    sqlstate: str | None = None,
    is_disconnect: bool = False,
    is_pre_ping: bool = False,
    idle_for_ms: float | None = None,
) -> _Context:
    """The context of a failure on ``connection``, idle for ``idle_for_ms`` when given."""
    if connection is not None and idle_for_ms is not None:
        connection.info[server_bounds.IDLE_SINCE_KEY] = time.monotonic() - idle_for_ms / 1000
    return _Context(
        connection, sqlstate=sqlstate, is_disconnect=is_disconnect, is_pre_ping=is_pre_ping
    )


def _invalidated_in_its_transaction(connection: Connection) -> Connection:
    """A disconnect mid-transaction: reading its ``info`` now raises ``PendingRollbackError``."""
    connection.begin()
    connection.invalidate()
    return connection


class TestTheBoundsTheEngineSends:
    def test_every_enabled_bound_is_sent_in_milliseconds(self) -> None:
        assert engine_server_settings() == {
            "lock_timeout": str(settings.database_lock_timeout_ms),
            "idle_in_transaction_session_timeout": str(
                settings.database_idle_in_transaction_timeout_ms
            ),
        }

    @pytest.mark.parametrize(
        ("field", "parameter"),
        [
            ("database_lock_timeout_ms", "lock_timeout"),
            ("database_idle_in_transaction_timeout_ms", "idle_in_transaction_session_timeout"),
        ],
    )
    def test_a_disabled_bound_is_not_sent(
        self, monkeypatch: pytest.MonkeyPatch, field: str, parameter: str
    ) -> None:
        """0 disables: the server's own setting is left as it is, never overridden by 0."""
        monkeypatch.setattr(settings, field, 0)

        assert parameter not in engine_server_settings()


class TestWhichBoundEndedAStatement:
    @pytest.mark.parametrize(
        ("sqlstate", "bound"),
        [
            ("55P03", "lock_timeout"),
            ("57014", "statement_timeout"),
            ("25P03", "idle_in_transaction_timeout"),
            ("23505", None),
            ("40P01", None),
        ],
    )
    def test_a_refusal_names_its_bound_by_its_sqlstate(
        self, sqlstate: str, bound: str | None
    ) -> None:
        assert bound_reached(_context(sqlstate=sqlstate)) == bound

    def test_a_disconnect_after_an_idle_span_past_the_bound_is_the_idle_bound(
        self, connection: Connection
    ) -> None:
        """asyncpg reports the server's end of an idle transaction as a bare disconnect,
        with no SQLSTATE (measured): the span the engine kept tells it apart."""
        past = settings.database_idle_in_transaction_timeout_ms * 1.5

        assert (
            bound_reached(_context(connection, is_disconnect=True, idle_for_ms=past))
            == "idle_in_transaction_timeout"
        )

    def test_a_disconnect_after_a_short_span_names_no_bound(self, connection: Connection) -> None:
        short = settings.database_idle_in_transaction_timeout_ms / 10

        assert bound_reached(_context(connection, is_disconnect=True, idle_for_ms=short)) is None

    def test_a_disconnect_found_by_the_pool_s_ping_names_no_bound(
        self, connection: Connection
    ) -> None:
        """A pooled connection is in no transaction: no idle bound ever ends it."""
        past = settings.database_idle_in_transaction_timeout_ms * 1.5
        context = _context(connection, is_disconnect=True, is_pre_ping=True, idle_for_ms=past)

        assert bound_reached(context) is None

    def test_an_invalidated_connection_is_never_read(self, connection: Connection) -> None:
        """Reading ``info`` revalidates a connection: after a disconnect inside a transaction
        it raises ``PendingRollbackError`` — the caller's rollback did (caught on PostgreSQL)."""
        invalidated = _invalidated_in_its_transaction(connection)

        assert bound_reached(_context(invalidated, is_disconnect=True)) is None

    def test_forgetting_an_invalidated_connection_reads_nothing(
        self, connection: Connection
    ) -> None:
        server_bounds._forget_idle(_invalidated_in_its_transaction(connection))

        assert connection.invalidated

    def test_a_disabled_idle_bound_names_no_disconnect(
        self, monkeypatch: pytest.MonkeyPatch, connection: Connection
    ) -> None:
        monkeypatch.setattr(settings, "database_idle_in_transaction_timeout_ms", 0)

        assert (
            bound_reached(_context(connection, is_disconnect=True, idle_for_ms=3_600_000)) is None
        )


class TestTheEnginesThatCarryTheBounds:
    def test_the_application_engine_counts_every_bound_it_reaches(self) -> None:
        from src.infrastructure.database.session import engine

        assert event.contains(engine.sync_engine, "handle_error", server_bounds._count)

    def test_the_application_engine_sends_its_bounds(self) -> None:
        """The module-level engine's connect arguments carry ``engine_server_settings()``."""
        tree = ast.parse(
            (_API / "src" / "infrastructure" / "database" / "session.py").read_text(
                encoding="utf-8"
            )
        )
        sent = [
            keyword.value
            for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "create_async_engine"
            for keyword in call.keywords
            if keyword.arg == "connect_args"
        ]

        assert len(sent) == 1 and isinstance(sent[0], ast.Dict)
        pairs = dict(zip(sent[0].keys, sent[0].values, strict=True))
        settings_keys = [k for k in pairs if isinstance(k, ast.Constant)]
        assert any(k.value == "server_settings" for k in settings_keys)
        value = next(
            v
            for k, v in pairs.items()
            if isinstance(k, ast.Constant) and k.value == "server_settings"
        )
        assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
        assert value.func.id == "engine_server_settings"

    def test_the_migration_engine_runs_unbounded(self) -> None:
        """A migration may hold a lock longer than any request should wait for one."""
        tree = ast.parse((_API / "alembic" / "env.py").read_text(encoding="utf-8"))
        names = {
            node.id if isinstance(node, ast.Name) else node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Name | ast.Attribute)
        }
        keywords = {node.arg for node in ast.walk(tree) if isinstance(node, ast.keyword)}

        assert "engine_server_settings" not in names
        assert "server_settings" not in keywords
