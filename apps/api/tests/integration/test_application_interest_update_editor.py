"""Draft modifications reread owned facts and cannot forge comparison or actor fields."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_repository import (
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_feedback import prepare_interest_feedback
from src.domains.agents.application.interest_feedback_schemas import InterestFeedbackSelection
from src.domains.agents.application.interest_reactivation import prepare_interest_reactivation
from src.domains.agents.application.interest_reactivation_schemas import InterestReactivateRequest
from src.domains.agents.application.interest_update import prepare_interest_update
from src.domains.agents.application.interest_update_schemas import InterestUpdateRequest
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("attack", ["valid", "actor", "comparison"])
@pytest.mark.parametrize("operation", ["update", "feedback", "reactivate"])
async def test_interest_update_editor_revalidates_source_and_retains_single_use_identity(
    async_session: AsyncSession, test_user: User, attack: str, operation: str
) -> None:
    row = UserInterest(
        user_id=test_user.id,
        topic="Original topic",
        category="science",
        positive_signals=3,
        negative_signals=1,
        status="dormant" if operation == "reactivate" else "active",
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    identity, owner = row.id, test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    selected = {
        "interest_id": str(identity),
        "changes": {"topic": "Revised topic", "negative_signals": 0},
    }
    if operation == "feedback":
        selected = {"interest_id": str(identity), "feedback": "thumbs_down"}
    elif operation == "reactivate":
        selected = {"interest_id": str(identity)}
    if attack != "valid":
        selected["user_id" if attack == "actor" else "expected"] = str(uuid4())
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(
        content=json.dumps({"intent": selected, "remove_fields": []})
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
        if operation == "reactivate":
            old = await prepare_interest_reactivation(
                async_session, owner, InterestReactivateRequest(interest_id=identity)
            )
        else:
            old = (
                await prepare_interest_feedback(
                    async_session,
                    owner,
                    InterestFeedbackSelection(interest_id=identity, feedback="thumbs_up"),
                )
                if operation == "feedback"
                else await prepare_interest_update(
                    async_session,
                    owner,
                    InterestUpdateRequest(
                        interest_id=identity, changes={"topic": "First proposal"}
                    ),
                )
            )
        draft_id = "draft-" + str(old.command_id)
        await save_command(async_session, old, draft_id)
        if attack == "valid":
            revised = ApplicationActionDraftContent.model_validate(
                await DraftModificationService().modify(
                    old.model_dump(mode="json"),
                    "Change le sujet et efface les signaux négatifs",
                    "application_action",
                    user_language="fr",
                    run_id=draft_id,
                )
            )
            if operation == "reactivate":
                assert revised.after["interest_to_reactivate"]["status"] == "active"
            else:
                field = "interest_feedback" if operation == "feedback" else "interest_configuration"
                assert revised.after[field]["configuration"]["negative_signals"] == (
                    3 if operation == "feedback" else 0
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
    await async_session.refresh(row)
    assert row.topic == "Original topic" and row.negative_signals == 1
    command = await get_command(async_session, old.command_id, owner)
    assert command is not None and matches_command(command, revised, draft_id)
    assert revised.command_id == old.command_id
    if attack == "valid":
        assert not matches_command(command, old, draft_id)
