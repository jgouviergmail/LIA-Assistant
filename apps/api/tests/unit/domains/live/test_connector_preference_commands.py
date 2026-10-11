"""Live connector settings refresh actor authority before any provider probe."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.live.connector_preference_commands import (
    connector_preference_snapshot,
    update_live_connector_settings,
)
from src.domains.live.connector_service import LiveConnectorService
from src.domains.live.model_settings import LiveModelSettings, write_models
from src.domains.live.preferences import LivePreferences
from src.domains.live.schemas import LiveConnectorSettings
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


async def test_operator_refusal_after_owner_locks_stops_native_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "live_enabled", True)
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        live_preferences=LivePreferences(provider="gemini").model_dump(),
    )
    connector = Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        credentials_encrypted="private-key",
        connector_metadata=write_models(
            {},
            "model",
            LiveModelSettings(voice="Kore", idle_timeout_seconds=60, session_max_minutes=10),
        ),
    )
    expected = connector_preference_snapshot(actor, connector, "gemini")
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, connector, "false"]
    service = LiveConnectorService(db)
    service.connector_of = AsyncMock(return_value=connector)
    service.api_key_of = AsyncMock(return_value="private-key")
    service._check_choice = AsyncMock()
    with pytest.raises(AuthorizationError):
        await service.update_connector_settings(
            actor,
            "gemini",
            LiveConnectorSettings(
                model="model", voice="Puck", idle_timeout_seconds=60, session_max_minutes=10
            ),
            language="fr",
            expected=expected,
        )
    service.api_key_of.assert_not_awaited()
    service._check_choice.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_deactivated_actor_cannot_probe_or_write_live_connector_settings() -> None:
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    current = User(id=actor.id, is_active=False, deleted_at=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = current
    service = LiveConnectorService(db)
    service.connector_of = AsyncMock(
        return_value=Connector(
            id=uuid4(),
            user_id=actor.id,
            connector_type=ConnectorType.GEMINI_LIVE,
            status=ConnectorStatus.ACTIVE,
            connector_metadata={},
        )
    )
    service.api_key_of = AsyncMock(return_value="private-key")
    service.connector_response = lambda *_args, **_kwargs: None
    service._check_choice = AsyncMock()
    with pytest.raises(AuthorizationError):
        await service.update_connector_settings(
            actor,
            "gemini",
            LiveConnectorSettings(
                model="model",
                voice="voice",
                idle_timeout_seconds=60,
                session_max_minutes=10,
            ),
            language="fr",
        )
    service.connector_of.assert_not_awaited()
    service._check_choice.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("intervention", ["credential", "metadata", "provider", "inactive"])
async def test_changed_connector_state_is_refused_before_a_provider_probe(
    intervention: str,
) -> None:
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        live_preferences=LivePreferences(provider="gemini").model_dump(),
    )
    connector = Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        connector_metadata={},
        credentials_encrypted="first-key",
    )
    expected = connector_preference_snapshot(actor, connector, "gemini")
    if intervention == "credential":
        connector.credentials_encrypted = "rotated-key"
    if intervention == "metadata":
        connector.connector_metadata = {"model": "another"}
    if intervention == "provider":
        actor.live_preferences = LivePreferences(provider="openai").model_dump()
    if intervention == "inactive":
        connector.status = ConnectorStatus.INACTIVE
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, connector]
    validate = AsyncMock()
    with pytest.raises(ResourceConflictError):
        await update_live_connector_settings(
            db,
            actor.id,
            "gemini",
            LiveConnectorSettings(
                model="model",
                voice="voice",
                idle_timeout_seconds=60,
                session_max_minutes=10,
            ),
            locate=AsyncMock(return_value=connector),
            validate=validate,
            expected=expected,
        )
    validate.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_unchanged_live_connector_settings_do_not_probe_the_provider_or_write() -> None:
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        live_preferences=LivePreferences(provider="gemini").model_dump(),
    )
    desired = LiveConnectorSettings(
        model="model", voice="voice", idle_timeout_seconds=60, session_max_minutes=10
    )
    connector = Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        credentials_encrypted="key",
        connector_metadata=write_models(
            {}, "model", LiveModelSettings(**desired.model_dump(exclude={"model"}))
        ),
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [actor, connector]
    validate = AsyncMock()
    receipt = PreferenceWriteReceipt()
    result = await update_live_connector_settings(
        db,
        actor.id,
        "gemini",
        desired,
        locate=AsyncMock(return_value=connector),
        validate=validate,
        receipt=receipt,
    )
    assert result is connector and receipt.committed and receipt.no_op
    validate.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_model_switch_resolution_restores_that_models_saved_settings_and_keeps_connector_budget() -> (
    None
):
    from src.domains.live.connector_preference_gateway import settings_for_native_change

    first = LiveConnectorSettings(
        model="first",
        voice="Kore",
        idle_timeout_seconds=60,
        session_max_minutes=10,
        session_budget_eur=2.5,
    )
    remembered = LiveModelSettings(
        voice="Puck", thinking_level="high", idle_timeout_seconds=120, session_max_minutes=0
    )
    connector = Connector(
        connector_type=ConnectorType.GEMINI_LIVE,
        connector_metadata=write_models(
            write_models({}, "second", remembered),
            "first",
            LiveModelSettings(**first.model_dump(exclude={"model"})),
        ),
    )
    connector.connector_metadata["session_budget_eur"] = 2.5
    resolved = settings_for_native_change(connector, {"model": "second"})
    assert resolved == LiveConnectorSettings(
        model="second", session_budget_eur=2.5, **remembered.model_dump()
    )
