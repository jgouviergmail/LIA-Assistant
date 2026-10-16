"""Interest creation is exact HITL; source embedding costs happen only after approval."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import UsageLimitExceededError
from src.domains.agents.application import interest_creation
from src.domains.agents.application.command_repository import (
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_create_schemas import InterestCreateConfiguration
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools import application_interest_tools
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from src.infrastructure.llm.embedding_context import get_embedding_context
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "normal",
        "quota",
        "late_disabled",
        "late_expiry",
        "duplicate_before",
        "duplicate_during",
        "commit_unknown",
    ],
)
async def test_interest_creation_is_absent_before_exact_confirmation(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    tool = getattr(application_interest_tools, "create_lia_interest_tool", None)
    assert tool is not None, "Manual interest creation needs its native HITL action"
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    test_user.interests_enabled = False
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    prior_context = get_embedding_context()
    calls: list[str] = []

    async def budget(user_id: UUID, *, layer: str) -> None:
        assert user_id == owner and layer == "application_interest"
        if scenario == "quota":
            raise UsageLimitExceededError(limit_name="cycle_cost")

    async def insert_duplicate() -> None:
        async_session.add(
            UserInterest(
                user_id=owner,
                topic="Explicit owned interest",
                category="science",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        await async_session.commit()

    async def source_provider(text: str) -> None:
        context = get_embedding_context()
        assert context is not None and context.user_id == str(owner)
        calls.append(text)
        if scenario == "late_disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario == "late_expiry":
            clock = Mock(wraps=datetime)
            clock.now.return_value = datetime.now(UTC) + timedelta(days=1)
            monkeypatch.setattr(interest_creation, "datetime", clock)
        elif scenario == "duplicate_during":
            await insert_duplicate()
        return None

    provider = AsyncMock(side_effect=source_provider)
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    with (
        installed_runtime_context(user_id=owner, deps=object(), language="fr"),
        patch("src.domains.agents.tools.application_interest_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.interests.helpers.generate_interest_embedding", provider),
        patch("src.domains.agents.application.interest_embeddings.enforce_usage_limit", budget),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        output = await tool.coroutine(
            configuration={"topic": "Explicit owned interest", "category": "science"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore(), language="fr"),
        )
        assert output.success and output.metadata["requires_confirmation"]
        provider.assert_not_called()
        if scenario == "duplicate_before":
            await insert_duplicate()
        elif scenario == "commit_unknown":
            source_create = interest_creation.create_managed_interest

            async def uncertain_create(*args, **kwargs):
                row = await source_create(*args, **kwargs)
                source_commit = async_session.commit

                async def lost_ack():
                    await source_commit()
                    monkeypatch.setattr(async_session, "commit", source_commit)
                    raise SQLAlchemyError("Lost commit acknowledgement")

                monkeypatch.setattr(async_session, "commit", lost_ack)
                return row

            monkeypatch.setattr(interest_creation, "create_managed_interest", uncertain_create)
        item = next(iter(output.registry_updates.values()))
        content = item.payload["content"]
        identity = UUID(content["command_id"])
        assert await async_session.get(UserInterest, identity) is None
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, owner, object())
        provider.assert_not_called()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        request = {
            "draft_id": item.id,
            "draft_type": "application_action",
            "draft_content": content,
        }
        result = await draft_executor._execute_confirmed_draft(
            request, {"configurable": {"thread_id": "interest-create"}}, "interest-create", "fr"
        )
        assert result.success is (scenario == "normal")
        row = await async_session.scalar(select(UserInterest).where(UserInterest.id == identity))
        assert (row is not None) is (scenario in {"normal", "commit_unknown"})
        if row is not None:
            assert (
                row.user_id == owner
                and row.topic == "Explicit owned interest"
                and row.category == "science"
            )
        assert calls == (
            [] if scenario in {"quota", "duplicate_before"} else ["Explicit owned interest"]
        )
        assert get_embedding_context() == prior_context
        if scenario != "normal":
            assert (
                draft_refusal_code(result)
                == {
                    "quota": "USAGE_LIMIT_EXCEEDED",
                    "late_disabled": "CAPABILITY_DISABLED",
                    "late_expiry": "EXPIRED",
                    "duplicate_before": "STALE_STATE",
                    "duplicate_during": "STALE_STATE",
                    "commit_unknown": "COMPLETION_UNKNOWN",
                }[scenario]
            )
        await async_session.refresh(test_user)
        assert test_user.interests_enabled is False
        replay = await draft_executor._execute_confirmed_draft(
            request, {"configurable": {"thread_id": "interest-create"}}, "interest-create", "fr"
        )
        assert not replay.success and provider.await_count == len(calls)


@pytest.mark.parametrize("attack", ["valid", "actor", "minted_id"])
async def test_interest_creation_editor_retains_identity_without_writing_or_spending(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    import json

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    configuration = {"topic": "Revised topic", "category": "technology"}
    if attack != "valid":
        configuration["user_id" if attack == "actor" else "id"] = str(uuid4())
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(
        content=json.dumps({"intent": configuration, "remove_fields": []})
    )
    with (
        installed_runtime_context(user_id=owner, language="fr"),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
        patch(
            "src.domains.interests.helpers.generate_interest_embedding", new_callable=AsyncMock
        ) as provider,
    ):
        old = await interest_creation.prepare_interest_creation(
            async_session,
            owner,
            InterestCreateConfiguration(topic="Original topic", category="science"),
        )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        if attack == "valid":
            revised = ApplicationActionDraftContent.model_validate(
                await DraftModificationService().modify(
                    old.model_dump(mode="json"),
                    "Change le sujet",
                    "application_action",
                    user_language="fr",
                    run_id=draft_id,
                )
            )
        else:
            with pytest.raises(CommandRejected, match="INVALID_INPUT"):
                await DraftModificationService().modify(
                    old.model_dump(mode="json"),
                    "Change le sujet",
                    "application_action",
                    user_language="fr",
                    run_id=draft_id,
                )
            revised = old
        provider.assert_not_called()
    assert await async_session.get(UserInterest, old.command_id) is None
    command = await get_command(async_session, old.command_id, owner)
    assert command is not None and matches_command(command, revised, draft_id)
    assert revised.command_id == old.command_id
    if attack == "valid":
        assert revised.after["interest_to_create"]["configuration"] == configuration
        assert not matches_command(command, old, draft_id)


async def test_manual_ui_creation_reuses_source_defaults_independently_of_native_switch(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.constants import (
        INTEREST_INITIAL_NEGATIVE_SIGNALS,
        INTEREST_INITIAL_POSITIVE_SIGNALS,
    )
    from src.domains.interests.router import create_interest
    from src.domains.interests.schemas import InterestCreate

    monkeypatch.setattr(settings, "application_tools_enabled", False)
    owner = test_user.id
    test_user.interests_enabled = False
    await async_session.commit()
    with patch(
        "src.domains.interests.router.generate_interest_embedding",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = await create_interest(
            InterestCreate(topic="Manual source topic", category="science"),
            test_user,
            async_session,
        )
    assert response.positive_signals == INTEREST_INITIAL_POSITIVE_SIGNALS
    assert (
        response.negative_signals == INTEREST_INITIAL_NEGATIVE_SIGNALS
        and response.status == "active"
    )
    assert response.topic == "Manual source topic" and response.category == "science"
    row = await async_session.get(UserInterest, response.id)
    assert row is not None and row.user_id == owner and row.embedding is None
