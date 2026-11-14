"""The writing-style routes read and forget the AUTHENTICATED account's style (ADR-383)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.writing_style.router import router
from src.domains.writing_style.schemas import WritingStyleResponse

pytestmark = pytest.mark.unit
USER_ID = uuid.uuid4()
SERVICE = "src.domains.writing_style.router.WritingStyleService"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(id=USER_ID)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


def test_the_style_shown_is_the_authenticated_accounts(client: TestClient) -> None:
    shown = WritingStyleResponse(enabled=True, profile="Signs « Seb ».", mails_read=12)
    with patch(SERVICE) as service:
        service.return_value.read = AsyncMock(return_value=shown)

        response = client.get("/writing-style")

    assert response.status_code == 200
    assert response.json()["profile"] == "Signs « Seb »."
    service.return_value.read.assert_awaited_once_with(USER_ID)


def test_forgetting_answers_no_content(client: TestClient) -> None:
    with patch(SERVICE) as service:
        service.return_value.forget = AsyncMock(return_value=False)

        response = client.delete("/writing-style")

    assert response.status_code == 204
    service.return_value.forget.assert_awaited_once_with(USER_ID)


def test_the_switch_is_saved_as_a_shared_preference_and_the_state_answered(
    client: TestClient,
) -> None:
    """One vocabulary for the screen and the assistant (``AssistantPreferencePatch``)."""
    with (
        patch(SERVICE) as service,
        patch("src.domains.writing_style.router.update_assistant_preferences", AsyncMock()) as save,
    ):
        service.return_value.read = AsyncMock(return_value=WritingStyleResponse(enabled=False))

        response = client.patch("/writing-style", json={"writing_style_enabled": False})

    assert response.status_code == 200 and response.json()["enabled"] is False
    _db, user_id, saved = save.await_args.args
    assert user_id == USER_ID and saved.writing_style_enabled is False
    assert saved.model_fields_set == {"writing_style_enabled"}


def test_the_switch_takes_a_boolean_only(client: TestClient) -> None:
    with patch("src.domains.writing_style.router.update_assistant_preferences") as save:
        response = client.patch("/writing-style", json={"writing_style_enabled": "maybe"})

    assert response.status_code == 422
    save.assert_not_called()
