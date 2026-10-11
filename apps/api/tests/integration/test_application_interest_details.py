"""Source explanation and live provenance are explicit, owned and free of learning writes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.tools import application_interest_tools
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.interests.explainability_router import (
    get_interest_explanation,
    get_interest_provenance,
)
from src.domains.interests.models import UserInterest
from src.domains.shared.provenance import ProvenanceOutcome, ProvenanceReference
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["live", "deleted", "foreign", "unknown", "disabled", "late_disabled"]
)
async def test_interest_details_reuse_source_formula_and_private_live_provenance(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    tool = getattr(application_interest_tools, "get_lia_interest_details_tool", None)
    assert tool is not None, "Interest explanation and provenance need their native explicit read"
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner, identity = test_user.id, uuid4()
    test_user.interests_enabled = False
    conversation = Conversation(
        user_id=owner,
        title="Own source",
        message_count=0,
        total_tokens=0,
        deleted_at=datetime.now(UTC) if scenario == "deleted" else None,
    )
    async_session.add(conversation)
    await async_session.flush()
    message = ConversationMessage(
        conversation_id=conversation.id, role="user", content="Untrusted saved signal"
    )
    interest = UserInterest(
        id=identity,
        user_id=test_superuser.id if scenario == "foreign" else owner,
        topic="Owned topic",
        category="science",
        positive_signals=3,
        negative_signals=0,
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add_all([message, interest])
    await async_session.flush()
    async_session.add(
        ProvenanceReference(
            user_id=owner,
            interest_id=identity,
            conversation_id=conversation.id,
            message_id=message.id,
            outcome=ProvenanceOutcome.ORIGIN.value,
        )
    )
    await async_session.commit()
    if scenario == "unknown":
        identity = uuid4()
    if scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    source_resolve = ProvenanceRepository.resolve_for

    async def withdraw(repository, **kwargs):
        result = await source_resolve(repository, **kwargs)
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        return result

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=owner),
        patch("src.domains.agents.tools.application_interest_tools.get_db_context", session),
    ):
        if scenario == "late_disabled":
            monkeypatch.setattr(ProvenanceRepository, "resolve_for", withdraw)
        output = await tool.coroutine(
            selection={"interest_id": str(identity)},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert output.success is (scenario in {"live", "deleted"})
    if output.success:
        expected_explanation = await get_interest_explanation(identity, test_user, async_session)
        expected_provenance = await get_interest_provenance(identity, test_user, async_session)
        assert output.structured_data["explanation"] == expected_explanation.model_dump(mode="json")
        assert output.structured_data["provenance"] == expected_provenance.model_dump(mode="json")
        assert expected_provenance.references[0].is_tombstone is (scenario == "deleted")
        assert "embedding" not in str(output.structured_data)
    else:
        assert output.error_code == (
            "CAPABILITY_DISABLED" if scenario in {"disabled", "late_disabled"} else "NOT_FOUND"
        )
        assert "Untrusted saved signal" not in str(output)
        if scenario in {"foreign", "unknown"}:
            with pytest.raises(ResourceNotFoundError):
                await get_interest_explanation(identity, test_user, async_session)
            with pytest.raises(ResourceNotFoundError):
                await get_interest_provenance(identity, test_user, async_session)
    await async_session.refresh(test_user)
    await async_session.refresh(interest)
    assert test_user.interests_enabled is False and interest.positive_signals == 3
