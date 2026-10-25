"""
Unit tests for FastAPI dependency injection utilities.

Phase: Session 11 - Tests Quick Wins (core/dependencies)
Created: 2025-11-20

Focus: Database session dependency injection
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from src.core.dependencies import get_db
from src.infrastructure.database import session as session_module


class TestGetDb:
    """Tests for get_db() async generator dependency."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """Test that get_db yields a database session."""
        with patch("src.core.dependencies.get_db_session") as mock_get_db_session:
            # Mock the get_db_session generator
            mock_session = AsyncMock()

            async def mock_generator():
                yield mock_session

            mock_get_db_session.return_value = mock_generator()

            # Call get_db
            async for session in get_db():
                # Verify we got the mocked session
                assert session is mock_session
                break  # Only check first yielded value

    @pytest.mark.asyncio
    async def test_get_db_delegates_to_get_db_session(self):
        """Test that get_db delegates to get_db_session."""
        with patch("src.core.dependencies.get_db_session") as mock_get_db_session:
            # Mock the get_db_session generator
            mock_session = AsyncMock()

            async def mock_generator():
                yield mock_session

            mock_get_db_session.return_value = mock_generator()

            # Call get_db and consume generator
            async for _ in get_db():
                break

            # Verify get_db_session was called
            mock_get_db_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_is_async_generator(self):
        """Test that get_db is an async generator."""
        with patch("src.core.dependencies.get_db_session") as mock_get_db_session:
            # Mock the get_db_session generator
            mock_session = AsyncMock()

            async def mock_generator():
                yield mock_session

            mock_get_db_session.return_value = mock_generator()

            # get_db should return an async generator
            result = get_db()

            # Check it's an async generator
            assert hasattr(result, "__aiter__")
            assert hasattr(result, "__anext__")

            # Clean up
            async for _ in result:
                break

    @pytest.mark.asyncio
    async def test_get_db_propagates_session_from_get_db_session(self):
        """Test that get_db propagates the exact session from get_db_session."""
        with patch("src.core.dependencies.get_db_session") as mock_get_db_session:
            # Create a specific mock session to track
            specific_mock_session = AsyncMock()
            specific_mock_session.session_id = "test_session_123"

            async def mock_generator():
                yield specific_mock_session

            mock_get_db_session.return_value = mock_generator()

            # Call get_db
            async for session in get_db():
                # Verify it's the exact same session object
                assert session is specific_mock_session
                assert session.session_id == "test_session_123"
                break

    @pytest.mark.asyncio
    async def test_get_db_handles_multiple_iterations(self):
        """Test that get_db can be iterated multiple times (creates new generator each time)."""
        with patch("src.core.dependencies.get_db_session") as mock_get_db_session:
            # Mock the get_db_session generator
            call_count = 0

            def create_generator():
                nonlocal call_count
                call_count += 1

                async def mock_generator():
                    yield AsyncMock()

                return mock_generator()

            mock_get_db_session.side_effect = create_generator

            # First iteration
            async for _ in get_db():
                break

            # Second iteration
            async for _ in get_db():
                break

            # Verify get_db_session was called twice (once per generator)
            assert mock_get_db_session.call_count == 2


class TestGetDbForwardsTheRouteOutcome:
    """A route's outcome reaches the session behind ``get_db`` (2026-10-25).

    ``get_db`` delegated to ``get_db_session`` with ``async for``: an exception
    FastAPI throws into ``get_db`` at its ``yield`` stopped the loop and never
    reached the session helper — its rollback branch (the rollback, its metric,
    its classified log) ran for none of the routes depending on it, and the
    session's close waited for the garbage collector to finalize the abandoned
    generator. Driven here the way FastAPI drives a ``yield`` dependency.
    """

    @pytest.mark.asyncio
    async def test_a_route_failure_rolls_back_and_closes_before_the_dependency_exits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()
        monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: session)

        with pytest.raises(ValueError, match="the route failed"):
            async with asynccontextmanager(get_db)():
                raise ValueError("the route failed")

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_route_success_commits_and_closes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()
        monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: session)

        async with asynccontextmanager(get_db)() as db:
            assert db is session

        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        session.close.assert_awaited_once()
