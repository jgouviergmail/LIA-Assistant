"""Unit tests for message pagination's HTTP contract."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationKind, ConversationRef


def test_the_history_page_searches_nothing_of_its_own() -> None:
    """Words are searched through ONE door, ``GET /me/search`` (lot 12).

    The page's former ``search`` filter read one discussion; the history field
    now searches every discussion of the account, and a second door would be
    the second reading of « which messages hold these words ».
    """
    from src.domains.conversations.router import get_conversation_messages

    assert "search" not in inspect.signature(get_conversation_messages).parameters


@pytest.mark.asyncio
async def test_router_has_more_true_when_service_returns_limit_plus_one():
    """When service returns ``limit + 1`` rows, router exposes has_more=True
    and truncates the response to ``limit``."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    base_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    # Service returns limit+1 = 4 rows (DESC, newest first)
    fake_messages = [
        {
            "id": uuid4(),
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"m{i}",
            "message_metadata": None,
            "created_at": base_dt - timedelta(minutes=i),
            "tokens_in": None,
            "tokens_out": None,
            "tokens_cache": None,
            "cost_eur": None,
            "google_api_requests": None,
        }
        for i in range(4)
    ]
    fake_user = MagicMock(id=uuid4())
    fake_conv = ConversationRef(fake_user.id, uuid4(), ConversationKind.MAIN, 0, uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=fake_messages)

    with (
        patch.object(router_module, "ConversationService", return_value=service_mock),
        patch.object(
            router_module.ConversationCatalogueService,
            "resolve_target",
            AsyncMock(return_value=fake_conv),
        ),
    ):
        response = await get_conversation_messages(
            selection=ConversationSelection(),
            limit=3,
            before=None,
            current_user=fake_user,
            db=MagicMock(),
        )

    assert response.has_more is True
    assert len(response.messages) == 3  # Truncated from 4
    # next_cursor = created_at of the oldest item in the returned page (index 2)
    assert response.next_cursor == fake_messages[2]["created_at"]


@pytest.mark.asyncio
async def test_router_has_more_false_when_service_returns_under_limit():
    """When the service returns fewer rows than ``limit``, no more pages exist:
    has_more=False and next_cursor=None."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    base_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    fake_messages = [
        {
            "id": uuid4(),
            "role": "user",
            "content": f"m{i}",
            "message_metadata": None,
            "created_at": base_dt - timedelta(minutes=i),
            "tokens_in": None,
            "tokens_out": None,
            "tokens_cache": None,
            "cost_eur": None,
            "google_api_requests": None,
        }
        for i in range(2)
    ]
    fake_user = MagicMock(id=uuid4())
    fake_conv = ConversationRef(fake_user.id, uuid4(), ConversationKind.MAIN, 0, uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=fake_messages)

    with (
        patch.object(router_module, "ConversationService", return_value=service_mock),
        patch.object(
            router_module.ConversationCatalogueService,
            "resolve_target",
            AsyncMock(return_value=fake_conv),
        ),
    ):
        response = await get_conversation_messages(
            selection=ConversationSelection(),
            limit=5,
            before=None,
            current_user=fake_user,
            db=MagicMock(),
        )

    assert response.has_more is False
    assert response.next_cursor is None
    assert len(response.messages) == 2


@pytest.mark.asyncio
async def test_router_requests_limit_plus_one_from_service():
    """Router asks the service for ``limit + 1`` rows to detect has_more without
    a second COUNT query — contract relied on by the pagination implementation."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    fake_user = MagicMock(id=uuid4())
    fake_conv = ConversationRef(fake_user.id, uuid4(), ConversationKind.MAIN, 0, uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=[])

    with (
        patch.object(router_module, "ConversationService", return_value=service_mock),
        patch.object(
            router_module.ConversationCatalogueService,
            "resolve_target",
            AsyncMock(return_value=fake_conv),
        ),
    ):
        await get_conversation_messages(
            selection=ConversationSelection(),
            limit=50,
            before=None,
            current_user=fake_user,
            db=MagicMock(),
        )

    call = service_mock.get_messages_with_tokens_auto.call_args
    # All args forwarded as kwargs — assert the limit was bumped by one
    assert call.kwargs["limit"] == 51


@pytest.mark.asyncio
async def test_router_propagates_before_cursor_to_service():
    """The ``before`` query param is forwarded to the service as
    ``before_created_at`` so the keyset filter applies."""
    from src.domains.conversations import router as router_module
    from src.domains.conversations.router import get_conversation_messages

    cursor = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
    fake_user = MagicMock(id=uuid4())
    fake_conv = ConversationRef(fake_user.id, uuid4(), ConversationKind.MAIN, 0, uuid4())

    service_mock = MagicMock()
    service_mock.get_active_conversation = AsyncMock(return_value=fake_conv)
    service_mock.get_messages_with_tokens_auto = AsyncMock(return_value=[])

    with (
        patch.object(router_module, "ConversationService", return_value=service_mock),
        patch.object(
            router_module.ConversationCatalogueService,
            "resolve_target",
            AsyncMock(return_value=fake_conv),
        ),
    ):
        await get_conversation_messages(
            selection=ConversationSelection(),
            limit=50,
            before=cursor,
            current_user=fake_user,
            db=MagicMock(),
        )

    call = service_mock.get_messages_with_tokens_auto.call_args
    assert call.kwargs["before_created_at"] == cursor
