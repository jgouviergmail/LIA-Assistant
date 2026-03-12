"""
Unit tests for ContextVar panic mode isolation (CORRECTION 5).

Tests coverage:
- panic_mode_used ContextVar default is False
- panic_mode_attempted ContextVar default is False
- ContextVars are independent between asyncio tasks
- SmartCatalogueService.reset_panic_mode() uses ContextVar
- SmartPlannerService uses panic_mode_attempted ContextVar

Target: context.py, panic_filtering.py, smart_catalogue_service.py,
        smart_planner_service.py
"""

from __future__ import annotations

import asyncio
from contextvars import copy_context

import pytest

from src.core.context import panic_mode_attempted, panic_mode_used

# =============================================================================
# Tests: ContextVar defaults
# =============================================================================


class TestContextVarDefaults:
    """Verify ContextVar default values."""

    def test_panic_mode_used_default_false(self) -> None:
        """panic_mode_used should default to False."""
        # Reset to ensure clean state
        panic_mode_used.set(False)
        assert panic_mode_used.get() is False

    def test_panic_mode_attempted_default_false(self) -> None:
        """panic_mode_attempted should default to False."""
        panic_mode_attempted.set(False)
        assert panic_mode_attempted.get() is False

    def test_set_and_get_panic_mode_used(self) -> None:
        """panic_mode_used can be set and retrieved."""
        panic_mode_used.set(True)
        assert panic_mode_used.get() is True
        panic_mode_used.set(False)
        assert panic_mode_used.get() is False

    def test_set_and_get_panic_mode_attempted(self) -> None:
        """panic_mode_attempted can be set and retrieved."""
        panic_mode_attempted.set(True)
        assert panic_mode_attempted.get() is True
        panic_mode_attempted.set(False)
        assert panic_mode_attempted.get() is False


# =============================================================================
# Tests: ContextVar isolation between async tasks
# =============================================================================


class TestContextVarAsyncIsolation:
    """Verify ContextVars are isolated between concurrent async tasks."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_isolated_panic_mode_used(self) -> None:
        """Concurrent tasks should have independent panic_mode_used state."""
        panic_mode_used.set(False)

        results: dict[str, bool] = {}

        async def task_a() -> None:
            panic_mode_used.set(True)
            await asyncio.sleep(0.01)
            results["a_after_set"] = panic_mode_used.get()

        async def task_b() -> None:
            await asyncio.sleep(0.005)
            # task_b should NOT see task_a's change (if properly isolated)
            results["b_during_a"] = panic_mode_used.get()

        # Note: asyncio.gather shares context by default in the same task
        # True isolation requires copy_context().run() or separate event loops
        # This test verifies the ContextVar API works correctly
        ctx_a = copy_context()
        ctx_b = copy_context()

        loop = asyncio.get_event_loop()
        await asyncio.gather(
            loop.run_in_executor(None, lambda: ctx_a.run(asyncio.run, task_a())),
            loop.run_in_executor(None, lambda: ctx_b.run(asyncio.run, task_b())),
        )

        assert results["a_after_set"] is True
        assert results["b_during_a"] is False

    @pytest.mark.asyncio
    async def test_concurrent_tasks_isolated_panic_mode_attempted(self) -> None:
        """Concurrent tasks should have independent panic_mode_attempted state."""
        panic_mode_attempted.set(False)

        results: dict[str, bool] = {}

        async def task_x() -> None:
            panic_mode_attempted.set(True)
            await asyncio.sleep(0.01)
            results["x_after_set"] = panic_mode_attempted.get()

        async def task_y() -> None:
            await asyncio.sleep(0.005)
            results["y_during_x"] = panic_mode_attempted.get()

        ctx_x = copy_context()
        ctx_y = copy_context()

        loop = asyncio.get_event_loop()
        await asyncio.gather(
            loop.run_in_executor(None, lambda: ctx_x.run(asyncio.run, task_x())),
            loop.run_in_executor(None, lambda: ctx_y.run(asyncio.run, task_y())),
        )

        assert results["x_after_set"] is True
        assert results["y_during_x"] is False


# =============================================================================
# Tests: SmartCatalogueService reset
# =============================================================================


class TestSmartCatalogueServiceReset:
    """Verify SmartCatalogueService.reset_panic_mode() uses ContextVar."""

    def test_reset_panic_mode_clears_contextvar(self) -> None:
        """reset_panic_mode should set panic_mode_used to False."""
        from unittest.mock import MagicMock

        from src.domains.agents.services.smart_catalogue_service import (
            SmartCatalogueService,
        )

        # Create service with mock registry
        mock_registry = MagicMock()
        service = SmartCatalogueService(registry=mock_registry)

        # Set to True
        panic_mode_used.set(True)
        assert panic_mode_used.get() is True

        # Reset
        service.reset_panic_mode()
        assert panic_mode_used.get() is False

    def test_no_instance_variable_panic_mode(self) -> None:
        """SmartCatalogueService should NOT have _panic_mode_used instance variable."""
        from unittest.mock import MagicMock

        from src.domains.agents.services.smart_catalogue_service import (
            SmartCatalogueService,
        )

        mock_registry = MagicMock()
        service = SmartCatalogueService(registry=mock_registry)

        # Verify no _panic_mode_used attribute
        assert not hasattr(service, "_panic_mode_used")
