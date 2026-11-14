"""``title_waiting_discussion``: the turn's door to an annex's automatic title.

Called by the turn once its request is archived, in a short transaction of its
own — the change is said to the open tabs as a METADATA signal, the path a
rename takes, which the archive's own « message added » signal would otherwise
absorb. It is a convenience of the turn, never a gate on it: nothing readable
opens no session, and a failure is logged by its facts and swallowed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.conversations import auto_title
from src.domains.conversations.auto_title import title_waiting_discussion

pytestmark = pytest.mark.unit

CONVERSATION_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def _fresh_worker() -> None:
    """Each test is a worker that has offered nothing yet."""
    auto_title._OFFERED.clear()


def _context(session: Any, opened: list[Any]) -> Any:
    @asynccontextmanager
    async def get_db_context() -> AsyncIterator[Any]:
        opened.append(session)
        yield session

    return get_db_context


async def test_a_readable_message_is_offered_as_the_title_on_its_own_session() -> None:
    session, opened = MagicMock(), []
    service = MagicMock(settle_waiting_title=AsyncMock(return_value=True))
    with (
        patch.object(auto_title, "get_db_context", _context(session, opened)),
        patch.object(auto_title, "ConversationCatalogueService", return_value=service) as built,
    ):
        await title_waiting_discussion(CONVERSATION_ID, "  Plan my trip to Lisbon\nwith two stops ")

    assert opened == [session]
    built.assert_called_once_with(session)
    service.settle_waiting_title.assert_awaited_once_with(CONVERSATION_ID, "Plan my trip to Lisbon")


@pytest.mark.parametrize("message", ["", " \n ", "​"])
async def test_a_message_with_nothing_readable_opens_no_session(message: str) -> None:
    opened: list[Any] = []
    with patch.object(auto_title, "get_db_context", _context(MagicMock(), opened)):
        await title_waiting_discussion(CONVERSATION_ID, message)

    assert opened == []


async def test_a_failure_never_reaches_the_turn_and_logs_no_content() -> None:
    service = MagicMock(settle_waiting_title=AsyncMock(side_effect=RuntimeError("secret words")))
    with (
        patch.object(auto_title, "get_db_context", _context(MagicMock(), [])),
        patch.object(auto_title, "ConversationCatalogueService", return_value=service),
        patch.object(auto_title, "logger") as log,
    ):
        await title_waiting_discussion(CONVERSATION_ID, "Plan my trip to Lisbon")

    log.warning.assert_called_once()
    logged = str(log.warning.call_args)
    assert "RuntimeError" in logged
    # Facts only (ADR-317): neither the error's text nor the person's words.
    assert "secret words" not in logged and "Lisbon" not in logged


class TestADiscussionIsOfferedItsTitleOnce:
    """A discussion never goes back to waiting: a title is taken or typed once.

    Asking the catalogue again at every request typed in an annex would spend a
    transaction, on the turn's latency path, to hear the same « no ».
    """

    async def _offer(self, opened: list[Any], conversation_id: uuid.UUID, message: str) -> None:
        service = MagicMock(settle_waiting_title=AsyncMock(return_value=False))
        with (
            patch.object(auto_title, "get_db_context", _context(MagicMock(), opened)),
            patch.object(auto_title, "ConversationCatalogueService", return_value=service),
        ):
            await title_waiting_discussion(conversation_id, message)

    async def test_the_second_request_of_a_discussion_opens_no_session(self) -> None:
        opened: list[Any] = []

        await self._offer(opened, CONVERSATION_ID, "Plan my trip")
        await self._offer(opened, CONVERSATION_ID, "And book the hotel")

        assert len(opened) == 1

    async def test_another_discussion_is_still_offered_its_own(self) -> None:
        opened: list[Any] = []

        await self._offer(opened, CONVERSATION_ID, "Plan my trip")
        await self._offer(opened, uuid.uuid4(), "Compare two phones")

        assert len(opened) == 2

    async def test_a_message_with_nothing_readable_leaves_the_discussion_waiting(self) -> None:
        opened: list[Any] = []

        await self._offer(opened, CONVERSATION_ID, " ")
        await self._offer(opened, CONVERSATION_ID, "Now a real question")

        assert len(opened) == 1

    async def test_a_failed_offer_is_made_again_at_the_next_request(self) -> None:
        opened: list[Any] = []
        broken = MagicMock(settle_waiting_title=AsyncMock(side_effect=RuntimeError("down")))
        with (
            patch.object(auto_title, "get_db_context", _context(MagicMock(), opened)),
            patch.object(auto_title, "ConversationCatalogueService", return_value=broken),
        ):
            await title_waiting_discussion(CONVERSATION_ID, "Plan my trip")

        await self._offer(opened, CONVERSATION_ID, "Plan my trip")

        assert len(opened) == 2

    async def test_what_the_worker_remembers_is_bounded(self) -> None:
        opened: list[Any] = []
        for _ in range(auto_title._OFFERED_MAX):
            await self._offer(opened, uuid.uuid4(), "Hello")
        await self._offer(opened, CONVERSATION_ID, "Hello")

        assert len(auto_title._OFFERED) == auto_title._OFFERED_MAX
        # The oldest left to make room: asked once more, it is simply told no again.
        assert CONVERSATION_ID in auto_title._OFFERED
