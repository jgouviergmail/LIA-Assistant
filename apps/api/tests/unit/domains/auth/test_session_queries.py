"""Session metadata is shared with the UI; unknown current identity is never guessed."""

from datetime import UTC, datetime
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.infrastructure.cache.session_store import SessionStore, UserSession

pytestmark = pytest.mark.unit


async def test_native_pages_unknown_current_session_without_cookie_or_attestation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.auth.session_queries")
    user = User(id=uuid4(), is_active=True)
    now = datetime.now(UTC)
    sessions = [
        UserSession(
            session_id=f"private-cookie-{index}",
            user_id=str(user.id),
            created_at=now,
            fcm_token_id="private-attestation",
        )
        for index in range(3)
    ]
    sessions.sort(key=lambda item: item.display_id, reverse=True)
    store = AsyncMock(spec=SessionStore)
    store.list_user_sessions.return_value = sessions
    monkeypatch.setattr(
        module, "device_names_by_token_id", AsyncMock(return_value={"private-attestation": "Phone"})
    )
    db = AsyncMock(spec=AsyncSession)
    first = await module.read_device_sessions(db, user, store, limit=1)
    second = await module.read_device_sessions(db, user, store, limit=1, cursor=first.next_cursor)
    assert first.total == 3 and first.sessions[0].id == sessions[0].display_id
    assert second.sessions[0].id == sessions[1].display_id
    assert first.current_session_known is False and first.sessions[0].current is None
    public = first.model_dump(mode="json")
    assert "private-cookie" not in str(public) and "private-attestation" not in str(public)
    assert first.sessions[0].device_name == "Phone"
    with pytest.raises(ValueError):
        await module.read_device_sessions(db, user, store, cursor="f" * 16)


def test_new_device_metadata_fields_require_native_review(monkeypatch: pytest.MonkeyPatch) -> None:
    module = import_module("src.domains.auth.session_queries")
    module.assert_device_session_projection_coverage()
    monkeypatch.setattr(
        module,
        "DeviceSessionResponse",
        create_model(
            "FutureSession", __base__=module.DeviceSessionResponse, sensitive=(str, "private")
        ),
    )
    with pytest.raises(AssertionError, match="review"):
        module.assert_device_session_projection_coverage()


@pytest.mark.parametrize(
    "payload",
    [
        {"cursor": "private-cookie"},
        {"limit": True},
        {"limit": 51},
        {"current_session_id": "private"},
    ],
)
def test_native_session_query_refuses_unbounded_or_forged_context(
    payload: dict[str, object],
) -> None:
    module = import_module("src.domains.agents.application.session_schemas")
    with pytest.raises(ValidationError):
        module.DeviceSessionsRead.model_validate(payload)
