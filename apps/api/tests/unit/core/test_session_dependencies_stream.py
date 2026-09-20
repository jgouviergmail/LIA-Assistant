"""The stream door of the authentication: a session of its own, closed before the route runs."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import src.core.session_dependencies as deps
from src.core.session_dependencies import (
    get_current_active_session_for_stream,
    get_current_session_for_stream,
)
from src.domains.users.models import User
from src.infrastructure.cache.session_store import UserSession

pytestmark = pytest.mark.unit

MODULE = "src.core.session_dependencies"


def _user(**overrides: Any) -> User:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "email": "user@example.com",
        "hashed_password": "hashed",
        "is_active": True,
        "is_verified": True,
        "is_superuser": False,
    }
    fields.update(overrides)
    return User(**fields)


def _store(session: UserSession | None) -> AsyncMock:
    store = AsyncMock()
    store.get_session = AsyncMock(return_value=session)
    store.touch_last_seen = AsyncMock()
    store.delete_session = AsyncMock()
    return store


class _Sessions:
    """A fake ``get_db_context``: counts what is open at any instant."""

    def __init__(self) -> None:
        self.open = 0
        self.opened = 0
        self.open_at_fetch: int | None = None

    @contextlib.asynccontextmanager
    async def __call__(self):  # noqa: ANN204
        self.open += 1
        self.opened += 1
        try:
            yield object()
        finally:
            self.open -= 1


async def test_the_stream_door_reads_the_account_on_its_own_session_then_closes_it() -> None:
    user = _user()
    sessions = _Sessions()
    repo = AsyncMock()

    async def _fetch(_user_id: uuid.UUID) -> User:
        sessions.open_at_fetch = sessions.open
        return user

    repo.get_user_minimal_for_session = _fetch
    with (
        patch(f"{MODULE}.get_db_context", sessions),
        patch(f"{MODULE}.UserRepository", return_value=repo),
    ):
        result = await get_current_session_for_stream(
            lia_session="s1",
            session_store=_store(UserSession(session_id="s1", user_id=str(user.id))),
        )
    assert result is user
    assert sessions.opened == 1
    assert sessions.open_at_fetch == 1  # the row was read on the door's session…
    assert sessions.open == 0  # …which is closed when the route receives the row


async def test_the_stream_door_refuses_like_the_request_door() -> None:
    """One authentication (`_authenticate`): the two doors cannot diverge."""
    sessions = _Sessions()
    with patch(f"{MODULE}.get_db_context", sessions):
        with pytest.raises(Exception) as no_cookie:
            await get_current_session_for_stream(lia_session=None, session_store=_store(None))
        with pytest.raises(Exception) as no_session:
            await get_current_session_for_stream(lia_session="gone", session_store=_store(None))
    assert getattr(no_cookie.value, "status_code", None) == 401
    assert getattr(no_session.value, "status_code", None) == 401
    assert sessions.open == 0


async def test_the_active_stream_door_refuses_an_inactive_or_deleted_account() -> None:
    for inactive in (_user(is_active=False), _user(deleted_at=datetime.now(UTC))):
        with pytest.raises(Exception) as refused:
            await get_current_active_session_for_stream(user=inactive)
        assert getattr(refused.value, "status_code", None) == 403
    active = _user()
    assert await get_current_active_session_for_stream(user=active) is active


def test_the_two_doors_share_one_authentication_and_one_active_check() -> None:
    """A rule added to one door reaches the other: both call the same functions."""
    import inspect

    request_door = inspect.getsource(deps.get_current_session)
    stream_door = inspect.getsource(deps.get_current_session_for_stream)
    assert "_authenticate(" in request_door and "_authenticate(" in stream_door
    assert "_ensure_active(" in inspect.getsource(deps.get_current_active_session)
    assert "_ensure_active(" in inspect.getsource(deps.get_current_active_session_for_stream)
