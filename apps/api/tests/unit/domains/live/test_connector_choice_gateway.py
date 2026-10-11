"""Live listings reuse source contracts and keep excluded models explicit and paged."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.live.schemas import LiveModelsResponse, LiveVoicesResponse
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def test_switching_to_an_unconfigured_model_requires_an_explicit_voice() -> None:
    from src.domains.live.model_settings import LiveModelSettings, write_models

    owner = import_module("src.domains.live.connector_preference_gateway")
    connector = Connector(
        id=uuid4(),
        user_id=uuid4(),
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        connector_metadata=write_models(
            {},
            "saved",
            LiveModelSettings(voice="Kore", idle_timeout_seconds=60, session_max_minutes=10),
        ),
    )
    with pytest.raises(owner.LiveConnectorSettingsRefused) as refused:
        owner.settings_for_native_change(connector, {"model": "not_configured"})
    assert refused.value.code == "INVALID_INPUT"
    requested = owner.settings_for_native_change(
        connector, {"model": "not_configured", "voice": "Puck"}
    )
    assert requested.voice == "Puck"
    assert owner.settings_for_native_change(connector, {"voice": "Puck"}).model == "saved"


async def test_inactive_owner_cannot_list_provider_models(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = import_module("src.domains.live.connector_preference_gateway")
    db = AsyncMock(spec=AsyncSession)
    actor = User(id=uuid4(), is_active=False, deleted_at=None)
    db.scalar.return_value = actor
    service = AsyncMock()
    monkeypatch.setattr(owner, "LiveConnectorService", lambda _db: service)
    with pytest.raises(AuthorizationError):
        await owner.SavedLiveConnectorPreferences().options(
            db, actor.id, "models", None, language="fr"
        )
    service.list_models.assert_not_awaited()


async def test_models_without_declared_tariffs_remain_visible_without_being_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = import_module("src.domains.live.connector_preference_gateway")
    db = AsyncMock(spec=AsyncSession)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    db.scalar.return_value = actor
    service = AsyncMock()
    service.list_models.return_value = LiveModelsResponse(
        models=[], default_model="default", unpriced=["unknown"]
    )
    monkeypatch.setattr(owner, "LiveConnectorService", lambda _db: service)
    result = await owner.SavedLiveConnectorPreferences().options(
        db, actor.id, "models", None, language="fr"
    )
    assert result.choices == [
        {"name": "unknown", "selectable": False, "reason": "undeclared_tariff"}
    ]
    assert result.details["unpriced_total"] == 1
    assert "unpriced" not in result.details
    service.list_models.assert_awaited_once_with(actor, language="fr")
    service.sample_voice.assert_not_awaited()


async def test_portal_voice_listing_remains_empty_with_its_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = import_module("src.domains.live.connector_preference_gateway")
    db = AsyncMock(spec=AsyncSession)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    db.scalar.return_value = actor
    service = AsyncMock()
    service.list_voices.return_value = LiveVoicesResponse(
        provider="elevenlabs", voices=[], provenance="portal"
    )
    monkeypatch.setattr(owner, "LiveConnectorService", lambda _db: service)
    result = await owner.SavedLiveConnectorPreferences().options(
        db, actor.id, "voices", "elevenlabs", language="fr"
    )
    assert result.choices == [] and result.details["provenance"] == "portal"
    service.list_voices.assert_awaited_once_with(actor, provider_id="elevenlabs", language="fr")
    service.sample_voice.assert_not_awaited()


@pytest.mark.parametrize(
    "failure,expected",
    [("rate_limit", "RATE_LIMIT_EXCEEDED"), ("timeout", "TIMEOUT"), ("sdk", "EXTERNAL_API_ERROR")],
)
async def test_provider_failures_are_finite_and_do_not_disclose_vendor_content(
    monkeypatch: pytest.MonkeyPatch, failure: str, expected: str
) -> None:
    import httpx

    owner = import_module("src.domains.live.connector_preference_gateway")
    db = AsyncMock(spec=AsyncSession)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    db.scalar.return_value = actor
    service = AsyncMock()
    request = httpx.Request("GET", "https://provider.example.test/private-key")
    if failure == "rate_limit":
        error = httpx.HTTPStatusError(
            "private-credential", request=request, response=httpx.Response(429, request=request)
        )
    elif failure == "timeout":
        error = httpx.ReadTimeout("private-credential", request=request)
    else:
        error = RuntimeError("private-credential SDK failure")
    service.list_models.side_effect = error
    monkeypatch.setattr(owner, "LiveConnectorService", lambda _db: service)
    with pytest.raises(owner.LiveConnectorSettingsRefused) as refused:
        await owner.SavedLiveConnectorPreferences().options(
            db, actor.id, "models", None, language="fr"
        )
    assert refused.value.code == expected
    assert "private" not in str(refused.value)
