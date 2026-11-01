"""The routine form's route writes the pre-approval apart from the routine (spec D9).

The routine's own changes reach the shared service as the shared schema states
them — never carrying the pre-approval — and the pre-approval is written by its
own strict method only when the form SENT it: an edit that leaves the field out
leaves the stored servers alone.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.scheduled_actions import router as router_module
from src.domains.scheduled_actions.schemas import (
    ScheduledActionFormCreate,
    ScheduledActionFormUpdate,
    ScheduledActionUpdate,
)
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def _service() -> MagicMock:
    action = SimpleNamespace(id=uuid4())
    return MagicMock(
        create=AsyncMock(return_value=action),
        update=AsyncMock(return_value=action),
        set_mcp_preapproval=AsyncMock(return_value=action),
    )


_NEW_ROUTINE: dict[str, Any] = {
    "title": "Tidy",
    "action_prompt": "Archive the notes older than a month",
    "recurrence": {
        "freq": "daily",
        "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
        "anchor_date": "2026-10-19",
    },
}


async def _create(service: MagicMock, payload: dict[str, Any]) -> None:
    user = User(id=uuid4(), email="form@test.local", hashed_password="x")
    db = MagicMock(commit=AsyncMock(), refresh=AsyncMock())
    with (
        patch.object(router_module, "ScheduledActionService", return_value=service),
        patch.object(router_module, "_action_to_response", return_value=None),
    ):
        await router_module.create_scheduled_action(
            ScheduledActionFormCreate.model_validate(payload), user=user, db=db
        )


async def _update(service: MagicMock, payload: dict[str, Any]) -> None:
    user = User(id=uuid4(), email="form@test.local", hashed_password="x")
    db = MagicMock(commit=AsyncMock(), refresh=AsyncMock())
    with (
        patch.object(router_module, "ScheduledActionService", return_value=service),
        patch.object(router_module, "_action_to_response", return_value=None),
    ):
        await router_module.update_scheduled_action(
            uuid4(), ScheduledActionFormUpdate.model_validate(payload), user=user, db=db
        )


class TestTheFormRoute:
    async def test_the_routine_changes_never_carry_the_preapproval(self) -> None:
        service = _service()

        await _update(service, {"title": "Tidy", "mcp_preapproved_servers": ["notes"]})

        (_action_id, _user_id, changes), _ = service.update.await_args
        assert type(changes) is ScheduledActionUpdate
        assert changes.model_dump(exclude_unset=True) == {"title": "Tidy"}
        service.set_mcp_preapproval.assert_awaited_once()
        assert service.set_mcp_preapproval.await_args.args[2] == ["notes"]

    async def test_an_edit_without_the_field_leaves_it_alone(self) -> None:
        service = _service()

        await _update(service, {"title": "Tidy"})

        service.set_mcp_preapproval.assert_not_awaited()

    async def test_an_explicit_null_clears_it(self) -> None:
        service = _service()

        await _update(service, {"mcp_preapproved_servers": None})

        assert service.set_mcp_preapproval.await_args.args[2] is None


class TestTheFormCreatesARoutine:
    async def test_a_new_routine_stores_the_servers_its_form_ticked(self) -> None:
        service = _service()

        await _create(service, {**_NEW_ROUTINE, "mcp_preapproved_servers": ["notes"]})

        service.create.assert_awaited_once()
        service.set_mcp_preapproval.assert_awaited_once()
        assert service.set_mcp_preapproval.await_args.args[2] == ["notes"]

    async def test_a_new_routine_without_a_tick_writes_nothing_more(self) -> None:
        service = _service()

        await _create(service, _NEW_ROUTINE)

        service.create.assert_awaited_once()
        service.set_mcp_preapproval.assert_not_awaited()
