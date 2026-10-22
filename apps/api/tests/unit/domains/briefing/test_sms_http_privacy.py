"""Private SMS previews must never enter browser or intermediary HTTP caches."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.session_dependencies import get_current_active_session
from src.domains.briefing.router import router
from src.domains.briefing.schemas import (
    BriefingResponse,
    CardSection,
    CardStatus,
    SmsData,
    TextSection,
)
from src.domains.briefing.service import BriefingService, build_briefing_windows
from src.domains.users.models import User
from tests.unit.domains.briefing.test_llm import _bundle_with_weather, _weather_section

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "method,path", [("GET", "/cards"), ("POST", "/refresh-cards"), ("POST", "/refresh")]
)
async def test_sms_card_http_responses_are_not_cacheable(monkeypatch, method, path):
    now = datetime.now(UTC)
    data = SmsData(
        total=1,
        window_total=1,
        window_start=now,
        as_of=now,
        latest_at=now,
        items=[
            {
                "id": uuid4(),
                "sender": "Alice",
                "display_name": "Alice",
                "received_at": now,
                "date_kind": "received",
                "body_excerpt": "PRIVATE_HTTP_PREVIEW",
                "body_truncated": False,
            }
        ],
    )
    cards = _bundle_with_weather(_weather_section()).model_copy(
        update={"sms": CardSection(status=CardStatus.OK, data=data, generated_at=now)}
    )
    monkeypatch.setattr(BriefingService, "build_cards", AsyncMock(return_value=cards))
    monkeypatch.setattr(
        BriefingService,
        "build_today",
        AsyncMock(
            return_value=BriefingResponse(
                cards=cards,
                windows=build_briefing_windows(),
                greeting=TextSection(text="Hello", generated_at=now),
            )
        ),
    )
    app = FastAPI()
    app.include_router(router)
    user = User(
        id=uuid4(),
        email="sms-http@example.test",
        full_name="SMS Test",
        language="fr",
        timezone="Europe/Paris",
        is_active=True,
        briefing_preferences={},
    )
    app.dependency_overrides[get_current_active_session] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(
            method,
            f"/briefing{path}",
            **({"json": {"sections": ["sms"]}} if method == "POST" else {}),
        )
    assert response.status_code == 200 and "PRIVATE_HTTP_PREVIEW" in response.text
    assert "no-store" in response.headers.get("cache-control", "")
