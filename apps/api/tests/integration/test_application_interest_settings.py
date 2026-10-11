"""Confirmed interest settings preserve source constraints, fresh rights and newer edits."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application import interest_settings
from src.domains.agents.application.command_repository import (
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_settings_schemas import InterestSettingsPatch
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools import application_interest_tools
from src.domains.users.models import User
from tests.helpers.application_pending_proposal import pending_proposal
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "normal",
        "overnight",
        "noop",
        "stale",
        "unrelated",
        "disabled",
        "actor_off",
        "replay",
        "late_disabled",
        "late_actor_off",
        "late_expiry",
        "unknown_commit",
        "timezone",
    ],
)
async def test_existing_pending_settings_keep_exact_confirmation_and_current_source_state(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    tool = getattr(application_interest_tools, "update_lia_interest_settings_tool", None)
    assert tool is not None, "Interest notification settings need their native HITL action"
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    test_user.interests_enabled = True
    test_user.interests_notify_start_hour = 8
    test_user.interests_notify_end_hour = 22
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue = asyncio.Queue()
    desired = {"interests_enabled": scenario == "noop"}
    if scenario in {"overnight", "timezone"}:
        desired = {"interests_notify_start_hour": 22, "interests_notify_end_hour": 6}
    original_fence = interest_settings.interest_settings_fence
    checks = 0

    async def withdrawing_fence(db, actor_id, draft):
        nonlocal checks
        checks += 1
        if checks == 3:
            if scenario == "late_disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif scenario == "late_actor_off":
                await db.execute(update(User).where(User.id == owner).values(is_active=False))
            elif scenario == "late_expiry":
                clock = Mock(wraps=datetime)
                clock.now.return_value = draft.expires_at + timedelta(seconds=1)
                monkeypatch.setattr(interest_settings, "datetime", clock)
        await original_fence(db, actor_id, draft)

    original_write = interest_settings.update_interest_settings

    async def source_write(db, *args, **kwargs):
        if scenario != "unknown_commit":
            return await original_write(db, *args, **kwargs)
        commit = db.commit

        async def lost_ack():
            await commit()
            raise SQLAlchemyError("Lost commit acknowledgement")

        with patch.object(db, "commit", side_effect=lost_ack):
            return await original_write(db, *args, **kwargs)

    with (
        patch("src.domains.agents.tools.application_interest_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        patch.object(interest_settings, "interest_settings_fence", withdrawing_fence),
        patch.object(interest_settings, "update_interest_settings", source_write),
        installed_runtime_context(
            user_id=owner, deps=object(), language="fr", side_channel_queue=queue
        ),
    ):
        output = await pending_proposal(
            async_session,
            owner,
            InterestSettingsPatch.model_validate(desired),
            "update_lia_interest_settings_tool",
            interest_settings.prepare_interest_settings,
        )
        assert output.success and output.metadata["requires_confirmation"]
        await async_session.refresh(test_user)
        assert test_user.interests_enabled and test_user.interests_notify_start_hour == 8
        assert queue.empty()
        item = next(iter(output.registry_updates.values()))
        if scenario == "stale":
            await async_session.execute(
                update(User).where(User.id == owner).values(interests_enabled=False)
            )
            await async_session.commit()
        elif scenario == "unrelated":
            await async_session.execute(update(User).where(User.id == owner).values(font_size=18))
            await async_session.commit()
        elif scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario == "actor_off":
            await async_session.execute(
                update(User).where(User.id == owner).values(is_active=False)
            )
            await async_session.commit()
        elif scenario == "timezone":
            await async_session.execute(
                update(User).where(User.id == owner).values(timezone="Asia/Tokyo")
            )
            await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        request = {
            "draft_id": item.id,
            "draft_type": "application_action",
            "draft_content": item.payload["content"],
        }
        result = await draft_executor._execute_confirmed_draft(
            request, {"configurable": {"thread_id": "interest-settings"}}, "interest-settings", "fr"
        )
        assert result.success is (
            scenario
            not in {
                "stale",
                "disabled",
                "actor_off",
                "late_disabled",
                "late_actor_off",
                "late_expiry",
                "unknown_commit",
                "timezone",
            }
        )
        if scenario in {"late_disabled", "late_actor_off", "late_expiry", "unknown_commit"}:
            assert (
                result.error
                == {
                    "late_disabled": "CAPABILITY_DISABLED",
                    "late_actor_off": "FORBIDDEN",
                    "late_expiry": "EXPIRED",
                    "unknown_commit": "COMPLETION_UNKNOWN",
                }[scenario]
            )
        if scenario == "replay":
            replay = await draft_executor._execute_confirmed_draft(
                request,
                {"configurable": {"thread_id": "interest-settings"}},
                "interest-settings",
                "fr",
            )
            assert not replay.success
    await async_session.refresh(test_user)
    if scenario == "overnight":
        assert (test_user.interests_notify_start_hour, test_user.interests_notify_end_hour) == (
            22,
            6,
        )
    elif scenario == "timezone":
        assert result.error == "STALE_STATE"
        assert (test_user.interests_notify_start_hour, test_user.interests_notify_end_hour) == (
            8,
            22,
        )
    else:
        assert test_user.interests_enabled is (
            scenario
            in {"noop", "disabled", "actor_off", "late_disabled", "late_actor_off", "late_expiry"}
        )
    if scenario == "unrelated":
        assert test_user.font_size == 18
    if scenario == "stale":
        assert result.error == "STALE_STATE"
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(scenario in {"normal", "overnight", "unrelated", "replay"})
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["interests"]
        assert set(hints[0].metadata["change"]["changed_fields"]) == set(desired)


@pytest.mark.parametrize("attack", ["valid", "actor", "unknown_field"])
async def test_interest_setting_editor_replaces_approval_but_never_writes_settings(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    modification = {"interests_notify_start_hour": 22, "interests_notify_end_hour": 6}
    if attack != "valid":
        modification["actor_id" if attack == "actor" else "unreviewed_setting"] = str(uuid4())
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(
        content=json.dumps({"intent": modification, "remove_fields": []})
    )
    with (
        installed_runtime_context(user_id=owner, language="fr"),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        old = await interest_settings.prepare_interest_settings(
            async_session, owner, InterestSettingsPatch(interests_enabled=False)
        )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        if attack == "valid":
            revised_content = await DraftModificationService().modify(
                old.model_dump(mode="json"),
                "Notifie entre 22h et 6h",
                "application_action",
                user_language="fr",
                run_id=draft_id,
            )
        else:
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await DraftModificationService().modify(
                    old.model_dump(mode="json"),
                    "Notifie entre 22h et 6h",
                    "application_action",
                    user_language="fr",
                    run_id=draft_id,
                )
            revised_content = old.model_dump(mode="json")
    revised = ApplicationActionDraftContent.model_validate(revised_content)
    await async_session.refresh(test_user)
    assert test_user.interests_enabled
    command = await get_command(async_session, old.command_id, owner)
    assert command is not None and matches_command(command, revised, draft_id)
    if attack == "valid":
        assert revised.after == {**old.after, **modification} and not matches_command(
            command, old, draft_id
        )
    else:
        assert revised == old


@pytest.mark.parametrize(
    "change", [{}, {"interests_notify_start_hour": 0}, {"interests_enabled": None}]
)
async def test_source_ui_settings_use_fresh_sparse_values(
    async_session: AsyncSession, test_user: User, change: dict[str, object]
) -> None:
    from src.domains.interests.router import update_settings
    from src.domains.interests.schemas import InterestSettingsUpdate

    owner = test_user.id
    await async_session.commit()
    await async_session.execute(
        update(User)
        .where(User.id == owner)
        .values(interests_enabled=False)
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    response = await update_settings(
        InterestSettingsUpdate.model_validate(change), test_user, async_session
    )
    assert not response.interests_enabled
    if change.get("interests_notify_start_hour") == 0:
        assert response.interests_notify_start_hour == 0
