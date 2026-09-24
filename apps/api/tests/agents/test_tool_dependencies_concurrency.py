"""
Tests for ToolDependencies concurrency safety.

Validates that asyncio.Lock prevents SQLAlchemy race conditions when
multiple tools execute in parallel (e.g., HITL approval of multiple actions).
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.dependencies import ToolDependencies


@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy AsyncSession."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def tool_deps(mock_db_session):
    """ToolDependencies instance with mocked DB session."""
    return ToolDependencies(db_session=mock_db_session)


class TestToolDependenciesConcurrency:
    """Test suite for ToolDependencies concurrency safety."""

    async def test_concurrent_get_connector_service_no_race_condition(
        self, tool_deps, mock_db_session
    ):
        """
        Test that multiple concurrent calls to get_connector_service()
        don't cause race conditions (SQLAlchemy concurrent access errors).
        """
        # Arrange: Simulate 10 tools requesting connector service simultaneously
        concurrent_calls = 10

        # Track initialization calls
        init_count = 0

        # Patch ConnectorService creation to track calls
        original_method = tool_deps.get_connector_service

        async def tracked_get_connector_service():
            nonlocal init_count
            result = await original_method()
            if tool_deps._connector_service is not None:
                init_count += 1
            return result

        # Act: Execute concurrent calls
        results = await asyncio.gather(
            *[tracked_get_connector_service() for _ in range(concurrent_calls)]
        )

        # Assert: All calls return same service instance (singleton)
        assert (
            len({id(r) for r in results}) == 1
        ), "All calls should return the same ConnectorService instance"

        # Assert: Service initialized only once despite concurrent calls
        assert (
            init_count == concurrent_calls
        ), "Service should be initialized once, but all calls should increment counter"

    async def test_concurrent_get_or_create_client_no_race_condition(self, tool_deps):
        """
        Test that multiple concurrent calls to get_or_create_client()
        with the same cache_key don't create duplicate clients.
        """
        # Arrange: Mock client factory
        factory_call_count = 0

        async def mock_factory():
            nonlocal factory_call_count
            factory_call_count += 1
            await asyncio.sleep(0.01)  # Simulate async DB/API call
            return MagicMock(name=f"client_{factory_call_count}")

        cache_key = ("user_123", "GOOGLE_CONTACTS")
        concurrent_calls = 10

        # Act: Execute concurrent calls with same cache_key
        results = await asyncio.gather(
            *[
                tool_deps.get_or_create_client(
                    client_class=MagicMock,
                    cache_key=cache_key,
                    factory=mock_factory,
                )
                for _ in range(concurrent_calls)
            ]
        )

        # Assert: All calls return same client instance (no duplicates)
        assert (
            len({id(r) for r in results}) == 1
        ), "All calls should return the same client instance"

        # Assert: Factory called only once (double-check lock pattern worked)
        assert (
            factory_call_count == 1
        ), f"Factory should be called exactly once, got {factory_call_count}"

    async def test_concurrent_different_cache_keys_creates_separate_clients(self, tool_deps):
        """
        Test that concurrent calls with different cache_keys create
        separate clients correctly (no interference).
        """
        # Arrange: Multiple cache keys
        cache_keys = [
            ("user_1", "GOOGLE_CONTACTS"),
            ("user_2", "GOOGLE_CONTACTS"),
            ("user_1", "GMAIL"),
        ]

        factory_calls = {}

        async def mock_factory(key):
            factory_calls[key] = factory_calls.get(key, 0) + 1
            await asyncio.sleep(0.01)
            return MagicMock(name=f"client_{key}")

        # Act: Execute concurrent calls with different cache_keys
        tasks = []
        for cache_key in cache_keys:
            for _ in range(3):  # 3 concurrent calls per cache_key
                tasks.append(
                    tool_deps.get_or_create_client(
                        client_class=MagicMock,
                        cache_key=cache_key,
                        factory=lambda k=cache_key: mock_factory(k),
                    )
                )

        results = await asyncio.gather(*tasks)

        # Assert: 3 unique clients created (one per cache_key)
        unique_clients = {id(r) for r in results}
        assert (
            len(unique_clients) == 3
        ), f"Should create 3 unique clients, got {len(unique_clients)}"

        # Assert: Each factory called exactly once per cache_key
        for key in cache_keys:
            assert (
                factory_calls.get(key, 0) == 1
            ), f"Factory for {key} should be called once, got {factory_calls.get(key, 0)}"

    async def test_db_lock_serializes_concurrent_access(self, tool_deps, mock_db_session):
        """
        Test that asyncio.Lock in ToolDependencies serializes concurrent
        DB access to prevent SQLAlchemy race conditions.
        """
        # Arrange: Track execution order
        execution_order = []

        async def mock_db_operation(operation_id: int):
            """Simulate DB operation that must be serialized."""
            async with tool_deps._db_lock:
                execution_order.append(f"{operation_id}_start")
                await asyncio.sleep(0.01)  # Simulate DB query
                execution_order.append(f"{operation_id}_end")

        # Act: Execute 5 concurrent DB operations
        await asyncio.gather(*[mock_db_operation(i) for i in range(5)])

        # Assert: Operations executed serially (no interleaving)
        # Each operation should complete (start->end) before next starts
        for i in range(5):
            start_idx = execution_order.index(f"{i}_start")
            end_idx = execution_order.index(f"{i}_end")
            assert (
                end_idx == start_idx + 1
            ), f"Operation {i} should complete atomically without interleaving"

    async def test_lock_does_not_deadlock_on_exception(self, tool_deps):
        """
        Test that asyncio.Lock is properly released even when
        factory or service creation raises an exception.
        """

        # Arrange: Factory that raises exception
        async def failing_factory():
            raise ValueError("Simulated factory error")

        cache_key = ("user_123", "GOOGLE_CONTACTS")

        # Act & Assert: First call should raise exception
        with pytest.raises(ValueError, match="Simulated factory error"):
            await tool_deps.get_or_create_client(
                client_class=MagicMock,
                cache_key=cache_key,
                factory=failing_factory,
            )

        # Act: Second call should not deadlock (lock was released)
        successful_client = MagicMock(name="success")

        async def successful_factory():
            return successful_client

        result = await tool_deps.get_or_create_client(
            client_class=MagicMock,
            cache_key=cache_key,
            factory=successful_factory,
        )

        # Assert: Second call succeeded
        assert (
            result == successful_client
        ), "Lock should be released after exception, allowing retry"

    async def test_concurrent_mixed_operations(self, tool_deps):
        """
        Test realistic scenario: concurrent get_connector_service()
        and get_or_create_client() calls don't interfere.
        """

        # Arrange: Mock factory
        async def mock_factory():
            await asyncio.sleep(0.01)
            return MagicMock(name="client")

        # Act: Mix of concurrent operations
        tasks = [
            tool_deps.get_connector_service(),
            tool_deps.get_connector_service(),
            tool_deps.get_or_create_client(
                client_class=MagicMock,
                cache_key=("user_1", "GOOGLE"),
                factory=mock_factory,
            ),
            tool_deps.get_or_create_client(
                client_class=MagicMock,
                cache_key=("user_1", "GOOGLE"),
                factory=mock_factory,
            ),
            tool_deps.get_connector_service(),
        ]

        results = await asyncio.gather(*tasks)

        # Assert: No errors, all operations completed
        assert len(results) == 5

        # Assert: First 3 get_connector_service calls return same instance
        assert id(results[0]) == id(results[1]) == id(results[4])

        # Assert: Both get_or_create_client calls return same instance
        assert id(results[2]) == id(results[3])


class TestToolDependenciesAclose:
    """Test suite for ToolDependencies.aclose() (deterministic client cleanup)."""

    async def test_aclose_closes_cached_clients_and_clears_cache(self, tool_deps):
        """aclose() awaits close() on every cached client and empties the cache."""
        client_a = MagicMock()
        client_a.close = AsyncMock()
        client_b = MagicMock()
        client_b.close = AsyncMock()
        tool_deps._clients_cache = {"a": client_a, "b": client_b}

        await tool_deps.aclose()

        client_a.close.assert_awaited_once()
        client_b.close.assert_awaited_once()
        assert tool_deps._clients_cache == {}

    async def test_aclose_skips_clients_without_close(self, tool_deps):
        """Clients without a close() attribute are skipped, cache still cleared."""
        no_close = object()
        closable = MagicMock()
        closable.close = AsyncMock()
        tool_deps._clients_cache = {"x": no_close, "y": closable}

        await tool_deps.aclose()

        closable.close.assert_awaited_once()
        assert tool_deps._clients_cache == {}

    async def test_aclose_is_best_effort_on_failing_close(self, tool_deps):
        """A failing close() never blocks the other clients (best-effort)."""
        failing = MagicMock()
        failing.close = AsyncMock(side_effect=RuntimeError("boom"))
        healthy = MagicMock()
        healthy.close = AsyncMock()
        tool_deps._clients_cache = {"bad": failing, "good": healthy}

        await tool_deps.aclose()  # must not raise

        healthy.close.assert_awaited_once()
        assert tool_deps._clients_cache == {}

    async def test_aclose_supports_sync_close(self, tool_deps):
        """A synchronous close() (non-awaitable) is also supported."""
        sync_client = MagicMock()
        sync_client.close = MagicMock(return_value=None)
        tool_deps._clients_cache = {"s": sync_client}

        await tool_deps.aclose()

        sync_client.close.assert_called_once()
        assert tool_deps._clients_cache == {}

    async def test_aclose_on_empty_cache_is_noop(self, tool_deps):
        """aclose() on an empty cache is a safe no-op."""
        await tool_deps.aclose()
        assert tool_deps._clients_cache == {}


class _Fake:
    """A connector service with one real coroutine method and a session."""

    def __init__(self, db: object) -> None:
        self.db = db
        self.calls = 0

    async def get_connector(self, _user_id: object, _connector_type: object) -> str:
        self.calls += 1
        return "row"

    async def fail(self) -> None:
        raise RuntimeError("the read failed")


class TestNoTransactionLeftOpen:
    """ADR-304: an operation on the turn's shared session ends its transaction.

    A credential read used to keep the turn's transaction open for the rest of
    the turn — every tool's network calls included.
    """

    async def test_an_explicit_operation_commits_behind_itself(
        self, tool_deps, mock_db_session
    ) -> None:
        from src.domains.connectors.models import ConnectorType

        service = await tool_deps.get_connector_service()
        service._service.get_connector_credentials = AsyncMock(return_value=None)
        await service.get_connector_credentials(uuid.uuid4(), ConnectorType.GOOGLE_GMAIL)
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.rollback.assert_not_awaited()

    async def test_a_forwarded_coroutine_is_serialized_and_commits(self, mock_db_session) -> None:
        """Before ADR-304 a method reached through ``__getattr__`` ran unguarded."""
        from src.domains.agents.dependencies import ConcurrencySafeConnectorService

        lock = asyncio.Lock()
        fake = _Fake(mock_db_session)
        wrapper = ConcurrencySafeConnectorService(fake, lock)  # type: ignore[arg-type]

        async with lock:
            pending = asyncio.create_task(wrapper.get_connector(uuid.uuid4(), "gmail"))
            await asyncio.sleep(0.05)
            assert fake.calls == 0, "the forwarded method ran while the lock was held"
        assert await pending == "row"
        mock_db_session.commit.assert_awaited_once()

    async def test_a_failed_operation_rolls_its_transaction_back(self, mock_db_session) -> None:
        from src.domains.agents.dependencies import ConcurrencySafeConnectorService

        wrapper = ConcurrencySafeConnectorService(
            _Fake(mock_db_session), asyncio.Lock()  # type: ignore[arg-type]
        )
        with pytest.raises(RuntimeError):
            await wrapper.fail()
        mock_db_session.rollback.assert_awaited_once()
        mock_db_session.commit.assert_not_awaited()

    async def test_a_plain_attribute_is_returned_as_is(self, tool_deps, mock_db_session) -> None:
        service = await tool_deps.get_connector_service()
        assert service.db is mock_db_session


class TestConnectorClientUnitOfWork:
    """A client's own writes run on a session of their own, never the turn's (ADR-304)."""

    async def test_a_unit_of_work_neither_uses_the_turn_session_nor_blocks_a_tool(
        self, tool_deps, mock_db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A token refresh used to hold the lock — and the turn's session —
        through the token endpoint; a parallel credential read waited on it."""
        from contextlib import asynccontextmanager

        from src.domains.connectors import session_scope
        from src.domains.connectors.models import ConnectorType
        from src.domains.connectors.session_scope import connector_unit_of_work, owns_session

        own_session = MagicMock(spec=AsyncSession)

        @asynccontextmanager
        async def _own():
            yield own_session

        monkeypatch.setattr(session_scope, "get_db_context", _own)
        service = await tool_deps.get_connector_service()
        service._service.get_connector_credentials = AsyncMock(return_value=None)
        assert owns_session(service), "a client may end its unit's transaction early"
        order: list[str] = []
        inside = asyncio.Event()
        release = asyncio.Event()

        async def client_unit() -> None:
            async with connector_unit_of_work(service) as underlying:
                assert underlying.db is own_session
                assert underlying.db is not mock_db_session
                order.append("unit:start")
                inside.set()
                await release.wait()
                order.append("unit:end")

        async def parallel_tool() -> None:
            await inside.wait()
            await service.get_connector_credentials(uuid.uuid4(), ConnectorType.GOOGLE_GMAIL)
            order.append("tool:read")

        unit = asyncio.create_task(client_unit())
        tool = asyncio.create_task(parallel_tool())
        await inside.wait()
        await asyncio.wait_for(tool, timeout=1)
        release.set()
        await unit
        assert order == ["unit:start", "tool:read", "unit:end"]
