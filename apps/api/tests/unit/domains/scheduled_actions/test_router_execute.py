"""« Run now » hands the tick the reservation it took (point 19).

The manual run reserves the routine under a fresh token and fires the run in
the background. Without that token, nothing could tell this run from the next
tick's once the recovery had freed a long run: both would run, and the late one
would settle over the other's state.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.scheduled_actions import router as router_module
from src.domains.users.models import User

pytestmark = pytest.mark.unit


async def test_the_manual_run_carries_the_token_it_reserved_under() -> None:
    action = SimpleNamespace(id=uuid4(), execution_token=uuid4())
    service = MagicMock(reserve_manual_execution=AsyncMock(return_value=action))
    run = AsyncMock(return_value="")
    fired: list[Any] = []

    def _fire(coroutine: Any, *, name: str) -> None:
        fired.append(name)
        coroutine.close()  # the double owns the coroutine it was handed

    user = User(id=uuid4(), email="manual-run@test.local", hashed_password="x")
    with (
        patch.object(router_module, "ScheduledActionService", return_value=service),
        patch.object(router_module, "safe_fire_and_forget", _fire),
        patch("src.infrastructure.scheduler.scheduled_action_executor.execute_single_action", run),
    ):
        await router_module.execute_scheduled_action(
            action.id, user=user, db=MagicMock(commit=AsyncMock())
        )

    run.assert_called_once_with(
        action_id=action.id, user_id=user.id, execution_token=action.execution_token
    )
    assert len(fired) == 1
