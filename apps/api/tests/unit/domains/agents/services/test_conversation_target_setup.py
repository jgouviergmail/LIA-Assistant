"""An orchestration setup must not re-resolve an already admitted target as Main."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.agents.services.conversation_orchestrator import ConversationOrchestrator
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.conversations.models import Conversation
from src.domains.conversations.service import ConversationService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("kind", list(ConversationKind))
async def test_setup_uses_the_exact_admitted_identity_and_account_preferences(
    kind: ConversationKind,
) -> None:
    target = ConversationRef(uuid4(), uuid4(), kind, 7, uuid4())
    unrelated_main = Conversation(
        id=uuid4(),
        user_id=target.owner_id,
        runtime_id=uuid4(),
        kind=ConversationKind.MAIN,
        revision=0,
    )
    orchestrator = ConversationOrchestrator()
    db = AsyncMock(spec=AsyncSession)
    grants = (["contacts"], frozenset({"google_contacts"}))
    previous = TokenSummaryDTO.zero()
    with (
        patch.object(
            ConversationService, "get_or_create_conversation", new_callable=AsyncMock
        ) as factory,
        patch.object(
            orchestrator, "_get_user_connector_grants", new_callable=AsyncMock
        ) as read_grants,
        patch.object(
            orchestrator, "_get_previous_tokens_from_db", new_callable=AsyncMock
        ) as read_previous,
    ):
        factory.return_value = unrelated_main
        read_grants.return_value = grants
        read_previous.return_value = previous
        context = await orchestrator.setup_conversation(target, "session", "run", db)
        assert context.target is target
        assert context.conversation_id == target.id
        assert context.tracking_context.conversation_id == target.id
        assert context.tracking_context.user_id == target.owner_id
        assert context.oauth_scopes == grants[0]
        assert context.active_connector_types == grants[1]
        assert context.previous_tokens_summary == previous
        read_grants.assert_awaited_once_with(target.owner_id, db)
        read_previous.assert_awaited_once_with("run", db)
        factory.assert_not_awaited()
