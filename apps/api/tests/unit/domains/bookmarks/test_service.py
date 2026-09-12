"""What keeping an answer means (ADR-282).

A bookmark is a COPY taken at the click: the answer, the request that produced
it, and the answer's date. What this pins:

- only the caller's own, VISIBLE, assistant, non-empty message can be kept;
- the request is the last visible user message before the answer — and a
  proactive notification, which answers no request, keeps none;
- the toggle is idempotent: keeping twice returns the existing bookmark;
- the cap is enforced on creation and never on a bookmark that already exists;
- removing by message id is what the bubble's second click does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import PROACTIVE_MESSAGE_TYPE_PREFIX
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.domains.bookmarks.errors import BookmarkLimitReachedError
from src.domains.bookmarks.service import BookmarkService

pytestmark = pytest.mark.unit

MODULE = "src.domains.bookmarks.service"


def _message(**overrides: object) -> MagicMock:
    message = MagicMock()
    message.id = uuid4()
    message.conversation_id = uuid4()
    message.role = "assistant"
    message.content = "**Réservé** : salle B, 14 h."
    message.message_metadata = {}
    message.created_at = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(message, key, value)
    return message


def _request(content: str = "Réserve la salle B à 14 h") -> MagicMock:
    request = MagicMock()
    request.content = content
    return request


@pytest.fixture
def repositories() -> tuple[MagicMock, MagicMock]:
    """The bookmark repository and the message reads, both stubbed."""
    bookmarks = MagicMock()
    bookmarks.get_by_message = AsyncMock(return_value=None)
    bookmarks.count_for_user = AsyncMock(return_value=0)
    bookmarks.owned_assistant_message = AsyncMock(return_value=_message())
    bookmarks.preceding_user_message = AsyncMock(return_value=_request())
    bookmarks.add = AsyncMock(side_effect=lambda bookmark: bookmark)
    bookmarks.get_for_user = AsyncMock(return_value=None)
    bookmarks.delete = AsyncMock()
    bookmarks.delete_by_message = AsyncMock(return_value=True)
    settings = MagicMock()
    settings.bookmarks_max_per_user = 3
    return bookmarks, settings


def _service(repositories: tuple[MagicMock, MagicMock]) -> BookmarkService:
    bookmarks, settings = repositories
    with (
        patch(f"{MODULE}.BookmarkRepository", return_value=bookmarks),
        patch(f"{MODULE}.settings", settings),
    ):
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return BookmarkService(db)


class TestKeepingAnAnswer:
    async def test_it_copies_the_answer_the_request_and_the_date(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        bookmarks, settings = repositories
        message = bookmarks.owned_assistant_message.return_value
        user_id = uuid4()

        with patch(f"{MODULE}.settings", settings):
            bookmark, created = await _service(repositories).keep(user_id, message.id)

        assert created is True
        assert bookmark.user_id == user_id
        assert bookmark.message_id == message.id
        assert bookmark.conversation_id == message.conversation_id
        assert bookmark.content == message.content
        assert bookmark.request_content == "Réserve la salle B à 14 h"
        assert bookmark.answered_at == message.created_at

    async def test_the_request_is_the_last_visible_user_message_before_the_answer(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        bookmarks, settings = repositories
        message = bookmarks.owned_assistant_message.return_value

        with patch(f"{MODULE}.settings", settings):
            await _service(repositories).keep(uuid4(), message.id)

        bookmarks.preceding_user_message.assert_awaited_once_with(message)

    async def test_a_proactive_notification_answers_no_request(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        """The user's last words before a notification did not produce it."""
        bookmarks, settings = repositories
        bookmarks.owned_assistant_message.return_value = _message(
            message_metadata={"type": f"{PROACTIVE_MESSAGE_TYPE_PREFIX}heartbeat"}
        )

        with patch(f"{MODULE}.settings", settings):
            bookmark, _ = await _service(repositories).keep(uuid4(), uuid4())

        assert bookmark.request_content is None
        bookmarks.preceding_user_message.assert_not_awaited()

    async def test_keeping_twice_returns_the_existing_bookmark(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        bookmarks, settings = repositories
        existing = MagicMock()
        bookmarks.get_by_message.return_value = existing
        # Even at the cap: the toggle asked for a state, not for a row.
        bookmarks.count_for_user.return_value = 3

        with patch(f"{MODULE}.settings", settings):
            bookmark, created = await _service(repositories).keep(uuid4(), uuid4())

        assert bookmark is existing
        assert created is False
        bookmarks.add.assert_not_awaited()


class TestTwoClicksInFlight:
    async def test_the_loser_of_the_race_returns_the_winners_row(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        """The partial unique index lets one row through; the other click asked
        for a state, and that row is the state."""
        from sqlalchemy.exc import IntegrityError

        bookmarks, settings = repositories
        winner = MagicMock()
        bookmarks.add = AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception("dup")))
        bookmarks.get_by_message = AsyncMock(side_effect=[None, winner])
        service = _service(repositories)
        service.db.rollback = AsyncMock()

        with patch(f"{MODULE}.settings", settings):
            bookmark, created = await service.keep(uuid4(), uuid4())

        assert bookmark is winner
        assert created is False
        service.db.rollback.assert_awaited_once()
        service.db.commit.assert_not_awaited()


class TestWhatCannotBeKept:
    async def test_a_message_that_is_not_the_callers_is_not_found(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        """Not « forbidden »: saying the row exists would leak that it does."""
        bookmarks, settings = repositories
        bookmarks.owned_assistant_message.return_value = None

        with patch(f"{MODULE}.settings", settings), pytest.raises(ResourceNotFoundError):
            await _service(repositories).keep(uuid4(), uuid4())

    async def test_an_empty_answer_is_refused(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        """An image-only bubble has nothing to keep — the chat hides its share
        menu for the same reason."""
        bookmarks, settings = repositories
        bookmarks.owned_assistant_message.return_value = _message(content="   ")

        with patch(f"{MODULE}.settings", settings), pytest.raises(ValidationError):
            await _service(repositories).keep(uuid4(), uuid4())

    async def test_the_cap_refuses_a_new_bookmark(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        bookmarks, settings = repositories
        bookmarks.count_for_user.return_value = 3

        with patch(f"{MODULE}.settings", settings), pytest.raises(BookmarkLimitReachedError):
            await _service(repositories).keep(uuid4(), uuid4())

        bookmarks.add.assert_not_awaited()


class TestRemoving:
    async def test_removing_a_foreign_or_unknown_id_is_not_found(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        bookmarks, settings = repositories
        bookmarks.get_for_user.return_value = None

        with patch(f"{MODULE}.settings", settings), pytest.raises(ResourceNotFoundError):
            await _service(repositories).remove(uuid4(), uuid4())

    async def test_removing_by_message_reports_whether_anything_went(
        self, repositories: tuple[MagicMock, MagicMock]
    ) -> None:
        bookmarks, settings = repositories
        bookmarks.delete_by_message.return_value = False
        user_id, message_id = uuid4(), uuid4()

        with patch(f"{MODULE}.settings", settings):
            removed = await _service(repositories).remove_by_message(user_id, message_id)

        assert removed is False
        bookmarks.delete_by_message.assert_awaited_once_with(user_id, message_id)
