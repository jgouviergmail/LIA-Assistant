"""
Tests for ToolDependencies concurrency safety.

Validates that asyncio.Lock prevents SQLAlchemy race conditions when
multiple tools execute in parallel (e.g., HITL approval of multiple actions).
"""

import asyncio
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
