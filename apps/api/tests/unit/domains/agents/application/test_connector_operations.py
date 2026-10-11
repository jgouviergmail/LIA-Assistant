"""Non-secret connector proposals use canonical existing schemas and exact identity."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.users.models import User

pytestmark = pytest.mark.unit


async def test_proposal_sanitizes_before_preview_and_never_changes_encrypted_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = import_module("src.domains.agents.application.connector_operations")
    schemas = import_module("src.domains.agents.application.connector_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    connector = Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=ConnectorStatus.ACTIVE,
        credentials_encrypted="never-a-model-key",
        preferences_encrypted=encrypt_data('{"default_calendar_name":"Before"}'),
    )
    original = connector.preferences_encrypted
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, connector]
    content = await operations.prepare_connector_preference_content(
        db,
        actor.id,
        schemas.ConnectorPreferenceUpdateRequest(
            connector_id=connector.id, preferences={"default_calendar_name": ' After\n"{name}" '}
        ),
    )
    assert content.before["connector_preferences"]["preferences"] == {
        "default_calendar_name": "Before"
    }
    assert content.after["connector_preferences"]["preferences"] == {
        "default_calendar_name": "Aftername"
    }
    assert connector.preferences_encrypted == original
    assert "never-a-model-key" not in content.model_dump_json()
    assert "credentials" not in content.model_dump_json()
    db.commit.assert_not_awaited()


def test_a_new_preference_field_requires_an_explicit_nonsecret_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import create_model

    from src.domains.connectors.preferences.registry import CONNECTOR_PREFERENCES_REGISTRY

    schemas = import_module("src.domains.agents.application.connector_schemas")
    existing = CONNECTOR_PREFERENCES_REGISTRY["google_calendar"]
    future = create_model("NewPreferences", __base__=existing, api_key=(str | None, None))
    monkeypatch.setitem(CONNECTOR_PREFERENCES_REGISTRY, "google_calendar", future)
    with pytest.raises(AssertionError, match="review"):
        schemas.assert_connector_preference_coverage()
