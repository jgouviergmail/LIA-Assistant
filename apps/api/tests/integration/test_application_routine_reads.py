"""Native reads expose the Studio contract, never the private condition ledger."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.agents.application.routine_queries import read_routines
from src.domains.agents.application.routine_read_schemas import RoutineRead
from src.domains.agents.tools.application_routine_tools import (
    get_lia_routines_tool,
    public_routine_read,
)
from src.domains.agents.tools.automation_tools import list_scheduled_actions_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import extract_data_block
from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("view", ["settings", "week"])
async def test_routine_read_reuses_the_owner_ui_contract_and_excludes_private_facts(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    view: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    source = ScheduledActionService(async_session)
    timed = await source.create(
        test_user.id,
        ScheduledActionCreate(
            title="Morning",
            action_prompt="Read the weather",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        ),
        "Europe/Paris",
    )
    watched = await source.create(
        test_user.id,
        ScheduledActionCreate(
            title="Inbox",
            action_prompt="Summarize matching mail",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="mail_match", query="receipt"),
            requires_approval=True,
        ),
        "Europe/Paris",
    )
    watched.condition_state = {"private_fact": "never-in-context"}
    await async_session.commit()
    result = await read_routines(
        async_session, test_user.id, RoutineRead.model_validate({"view": view})
    )
    data = result.model_dump(mode="json")
    assert "never-in-context" not in str(data)
    assert "condition_state" not in str(data)
    assert timed.is_enabled and watched.is_enabled
    public = public_routine_read(result)
    output = UnifiedToolOutput.data_success(
        message="Routine data",
        structured_data=public,
        metadata={"application_routine_cursor": True},
    )
    block = extract_data_block(output, 1)
    assert block is not None
    assert block.truncated
    assert block.shown == 1
    parsed = json.loads(block.text)
    key = "scheduled_actions" if view == "settings" else "actions"
    assert len(parsed[key]) == 1
    assert parsed["next_cursor"] == parsed[key][-1]["id"]
    assert "never-in-context" not in block.text
    if view == "settings":
        assert data["settings"]["total"] == 2
        routines = {row["id"]: row for row in data["settings"]["scheduled_actions"]}
        assert routines[str(watched.id)]["requires_approval"] is True
        assert routines[str(watched.id)]["condition_config"]["query"] == "receipt"
        assert routines[str(timed.id)]["action_prompt"] == "Read the weather"
        assert routines[str(timed.id)]["times_of_day"] == ["09:00"]
        assert routines[str(timed.id)]["week_slots"]
        assert data["settings"]["condition_check_minutes"]
    else:
        assert len(data["week"]["actions"]) == 2
        assert data["week"]["generated_at"]
    first = await read_routines(
        async_session, test_user.id, RoutineRead.model_validate({"view": view, "limit": 1})
    )
    assert first.returned_count == 1 and first.next_cursor is not None
    second = await read_routines(
        async_session,
        test_user.id,
        RoutineRead.model_validate({"view": view, "limit": 1, "after_id": str(first.next_cursor)}),
    )
    assert second.returned_count == 1 and second.next_cursor is None
    first_ids = [item["id"] for item in public_routine_read(first)[key]]
    second_ids = [item["id"] for item in public_routine_read(second)[key]]
    assert set(first_ids + second_ids) == {str(timed.id), str(watched.id)}


async def test_routine_read_refuses_absent_target_and_disabled_platform(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    with pytest.raises(ResourceNotFoundError):
        await read_routines(async_session, test_user.id, RoutineRead(routine_id=uuid4()))
    monkeypatch.setattr(settings, "application_tools_enabled", False)
    with pytest.raises(AuthorizationError):
        await read_routines(async_session, test_user.id, RoutineRead())


@pytest.mark.parametrize("legacy", [True, False])
@pytest.mark.parametrize("intervention", ["none", "off", "inactive"])
async def test_native_and_legacy_routine_reads_require_fresh_application_authority(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", intervention != "off")
    actor_id = test_user.id
    if intervention == "inactive":
        test_user.is_active = False
        await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_routine_tools.get_db_context", session),
        patch("src.domains.agents.tools.automation_tools.get_db_context", session),
    ):
        runtime = make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        result = (
            await list_scheduled_actions_tool.coroutine(runtime=runtime, locale="fr")
            if legacy
            else await get_lia_routines_tool.coroutine(runtime=runtime)
        )
    assert result.success is (intervention == "none")
    if intervention == "off":
        assert result.error_code == "CAPABILITY_DISABLED"
    elif intervention == "inactive":
        assert result.error_code == "FORBIDDEN"


@pytest.mark.parametrize("view", ["settings", "week"])
async def test_routine_page_and_selector_cannot_read_another_account(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    view: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    foreign = await ScheduledActionService(async_session).create(
        test_superuser.id,
        ScheduledActionCreate(
            title="Foreign routine",
            action_prompt="Foreign confidential instruction",
            recurrence=RecurrenceSpec(
                freq="daily",
                times=DailyTimes(mode="at", at=(TimeOfDay(hour=9, minute=0),)),
                anchor_date=date(2026, 9, 1),
            ),
        ),
        "Europe/Paris",
    )
    await async_session.commit()
    result = await read_routines(
        async_session,
        test_user.id,
        RoutineRead.model_validate({"view": view, "after_id": str(foreign.id)}),
    )
    assert result.returned_count == 0 and result.total_available == 0
    assert "Foreign confidential instruction" not in str(public_routine_read(result))
    with pytest.raises(ResourceNotFoundError):
        await read_routines(
            async_session,
            test_user.id,
            RoutineRead.model_validate({"view": view, "routine_id": str(foreign.id)}),
        )
