"""Integration contract: the WHOLE process talks to the test database.

The session fixtures historically redirected only their own engine/session;
code under test going through the PROCESS singletons — the module-level
SQLAlchemy engine behind ``get_db_context()``/``get_db_session()``,
``settings.database_url``, the LangGraph checkpointer pool and the LangGraph
Store pool — still used the URL from ``.env.test`` (the developer database).
Those paths hide behind best-effort fallbacks, so tests stayed green while
validating against the WRONG database (silent false greens: ~35 s checkpointer
waits, ``relation "store" does not exist``, 21 s admin pricing calls through
``get_db_context()``).

These contracts pin two things:
1. Every process-wide DB entrypoint is redirected to the test database.
2. When the Testcontainers strategy is active, any residual connection to the
   developer database (loopback:5432) fails loudly instead of silently
   validating against dev data.
"""

from __future__ import annotations

import contextlib
import socket

import pytest
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_DEV_DB_PORT = 5432


class TestProcessDbRedirection:
    """All process-wide DB entrypoints point at the test database."""

    async def test_settings_database_url_points_at_test_db(self, test_database_url: str) -> None:
        """``settings.database_url`` (read lazily by checkpointer/store pools)."""
        from src.core.config import settings

        expected = make_url(test_database_url)
        actual = make_url(str(settings.database_url))
        assert (actual.host, actual.port, actual.database) == (
            expected.host,
            expected.port,
            expected.database,
        ), f"settings.database_url still points at {actual} instead of the test DB {expected}"

    async def test_global_engine_points_at_test_db(self, test_database_url: str) -> None:
        """The module-level engine behind get_db_context()/get_db_session()."""
        from src.infrastructure.database import session as db_session_module

        expected = make_url(test_database_url)
        actual = db_session_module.engine.url
        assert (actual.host, actual.port, actual.database) == (
            expected.host,
            expected.port,
            expected.database,
        ), f"global engine still points at {actual} instead of the test DB {expected}"

    async def test_get_db_context_reaches_test_db(
        self, async_session: AsyncSession, test_database_url: str
    ) -> None:
        """``get_db_context()`` (72 call sites: pricing cache, schedulers, tools…)
        actually executes against the test database, not the developer one."""
        from src.infrastructure.database.session import get_db_context

        expected_db = make_url(test_database_url).database
        async with get_db_context() as db:
            current = (await db.execute(text("SELECT current_database()"))).scalar()
        assert current == expected_db, (
            f"get_db_context() reached database '{current}' instead of the test "
            f"database '{expected_db}' — process engine not redirected"
        )


class TestLangGraphPersistenceOnTestDb:
    """Checkpointer and Store pools build their tables in the test database."""

    async def test_checkpointer_init_during_written_test_transaction(
        self, async_session: AsyncSession
    ) -> None:
        """Regression: LangGraph setup() must never deadlock against a test transaction.

        The saver/store migrations contain ``CREATE INDEX CONCURRENTLY``, which
        waits for every concurrent transaction holding an XID/snapshot on the
        database to finish. The ``async_session`` fixture keeps ONE outer
        transaction open for the whole test (F049 isolation); once the test has
        written/read enough state, a first-time in-test ``setup()`` waits on
        the test's transaction, which waits on setup() — the run froze at
        ``checkpointer_initializing``. Guarded by provisioning the LangGraph
        tables once per session in ``_db_schema_ready`` (no open transactions
        at that point), making in-test setup() a version check. ``wait_for``
        turns any regression into a loud 30 s failure instead of a frozen run.

        The body reproduces the empirically-established minimal trigger (the
        differential bisection): TWO writes with ``commit`` + ``refresh`` in
        the outer transaction — a single bare INSERT did NOT trigger the wait,
        this sequence froze it deterministically before the fix.
        """
        import asyncio

        from src.domains.conversations.checkpointer import get_checkpointer
        from src.domains.conversations.models import Conversation
        from src.domains.users.models import User

        user = User(
            email="deadlock-repro@example.com",
            hashed_password="hash",
            full_name="Deadlock Repro",
            is_active=True,
            is_verified=True,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        conversation = Conversation(
            id=user.id,
            user_id=user.id,
            title="Deadlock Repro",
            message_count=0,
            total_tokens=0,
        )
        async_session.add(conversation)
        await async_session.commit()
        await async_session.refresh(conversation)

        checkpointer = await asyncio.wait_for(get_checkpointer(), timeout=30)
        assert checkpointer is not None

    async def test_checkpointer_creates_tables_in_test_db(
        self, async_session: AsyncSession
    ) -> None:
        """get_checkpointer() connects to the test DB and setup() creates the
        checkpoint tables there (kills the ~35 s doomed dev-DB wait + fallback)."""
        from src.domains.conversations.checkpointer import get_checkpointer
        from src.infrastructure.database.session import get_db_context

        checkpointer = await get_checkpointer()
        assert checkpointer is not None
        async with get_db_context() as db:
            reg = (await db.execute(text("SELECT to_regclass('checkpoints')"))).scalar()
        assert reg is not None, "checkpoints table missing from the test database"

    async def test_store_creates_tables_in_test_db(self, async_session: AsyncSession) -> None:
        """get_tool_context_store() connects to the test DB and setup() creates
        the ``store`` relation (kills 'relation \"store\" does not exist')."""
        from src.domains.agents.context.store import get_tool_context_store
        from src.infrastructure.database.session import get_db_context

        store = await get_tool_context_store()
        assert store is not None
        async with get_db_context() as db:
            reg = (await db.execute(text("SELECT to_regclass('store')"))).scalar()
        assert reg is not None, "store table missing from the test database"


class TestDevDbGuard:
    """Testcontainers strategy active ⇒ developer DB (loopback:5432) unreachable."""

    def test_guard_predicate_targets_only_loopback_dev_port(self) -> None:
        """Deterministic predicate contract (holds under any DB strategy)."""
        from tests.integration.conftest import _is_dev_db_address

        assert _is_dev_db_address(("127.0.0.1", _DEV_DB_PORT))
        assert _is_dev_db_address(("localhost", _DEV_DB_PORT))
        assert _is_dev_db_address(("::1", _DEV_DB_PORT))
        # Never overblock: Redis, the container's random published port, unix
        # sockets and non-loopback hosts stay reachable.
        assert not _is_dev_db_address(("127.0.0.1", 6379))
        assert not _is_dev_db_address(("127.0.0.1", 49321))
        assert not _is_dev_db_address(("db.internal", _DEV_DB_PORT))
        assert not _is_dev_db_address("/var/run/docker.sock")

    def test_dev_db_connection_blocked_when_testcontainers_active(
        self, test_database_url: str
    ) -> None:
        from tests import conftest as root_conftest

        if not root_conftest._TESTCONTAINERS_ACTIVE:
            pytest.skip("external DB strategy — the dev-DB guard applies to Testcontainers runs")

        with pytest.raises(OSError, match="developer database"):
            with contextlib.closing(
                socket.create_connection(("127.0.0.1", _DEV_DB_PORT), timeout=2)
            ):
                pass  # pragma: no cover — connection must never be established

    def test_test_db_still_reachable_with_guard_active(self, test_database_url: str) -> None:
        """The guard never blocks the test database itself."""
        url = make_url(test_database_url)
        assert url.host is not None
        with contextlib.closing(
            socket.create_connection((url.host, url.port or _DEV_DB_PORT), timeout=5)
        ):
            pass
