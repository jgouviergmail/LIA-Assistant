"""A connector-card unlink freezes an owned local connection before confirmation."""

from importlib import import_module
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.users.models import User
from tests.unit.domains.connectors.test_removal_commands import connector

pytestmark = pytest.mark.unit


async def test_preparation_never_deletes_or_revokes_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = import_module("src.domains.agents.application.connection_operations")
    schemas = import_module("src.domains.agents.application.connection_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    saved = connector(actor)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, saved]
    content = await operations.prepare_connector_unlink_content(
        db, actor.id, schemas.ConnectorUnlinkRequest(connector_id=saved.id)
    )
    assert content.operation_id == "connector_connection.unlink"
    assert content.before == content.intent
    assert content.after == {"connector_to_disconnect": None}
    assert (
        "private-token" not in content.model_dump_json()
        and "private_key" not in content.model_dump_json()
    )
    db.commit.assert_not_awaited()
    db.delete.assert_not_awaited()


async def test_saved_card_read_does_not_serve_private_grant_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = import_module("src.domains.agents.application.connection_operations")
    schemas = import_module("src.domains.agents.application.connection_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    first, second = connector(actor), connector(actor)
    first.oauth_grant_id = uuid4()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, actor, 2]
    db.scalars.return_value = MagicMock()
    db.scalars.return_value.all.return_value = [first, second]
    result = await operations.read_connector_connections(
        db, actor.id, schemas.ConnectorConnectionsRead(limit=1)
    )
    assert result.total == 2 and result.next_cursor == first.id
    assert len(result.connectors) == 1
    assert "oauth_grant_id" not in result.model_dump_json()
    assert (
        "private-token" not in result.model_dump_json()
        and "private_key" not in result.model_dump_json()
    )


def test_only_a_selector_is_accepted_without_any_role_or_credential() -> None:
    schemas = import_module("src.domains.agents.application.connection_schemas")
    for forbidden in ("actor_id", "status", "metadata", "api_key"):
        with pytest.raises(ValidationError):
            schemas.ConnectorUnlinkRequest.model_validate(
                {"connector_id": str(uuid4()), forbidden: "untrusted"}
            )


def test_disconnect_preview_names_the_service_and_does_not_claim_provider_revocation() -> None:
    from src.domains.agents.application.connection_schemas import ConnectorConnectionUnlinkPatch
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.connectors.removal_commands import connector_removal_snapshot

    actor = User(id=uuid4())
    saved = connector(actor)
    saved.oauth_grant_id = uuid4()
    snapshot = connector_removal_snapshot(saved)
    content = _preference_content(
        actor.id,
        ConnectorConnectionUnlinkPatch(connector_to_disconnect=snapshot),
        {"connector_to_disconnect": snapshot.model_dump(mode="json")},
    )
    lines = render_application_preview(
        content.model_dump(mode="json"),
        {
            "application_field_connector_to_disconnect": "Connection",
            "application_connector_unlink": "Local unlink; provider consent is retained",
            "application_before": "Before",
            "application_after": "After",
            "application_expiry": "Expires",
            "application_unavailable": "Unavailable",
        },
        lambda value: value or "",
    )
    text = str(lines)
    assert "Gmail" in text and "reader@example.test" in text
    assert "provider consent is retained" in text
    assert str(saved.oauth_grant_id) not in text


def test_future_connection_card_fields_require_a_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import create_model

    from src.domains.agents.application import connection_schemas as schemas

    schemas.assert_connection_projection_coverage()
    future = create_model(
        "FutureConnectionCard", __base__=schemas.ConnectorResponse, device_label=(str | None, None)
    )
    monkeypatch.setattr(schemas, "ConnectorResponse", future)
    with pytest.raises(AssertionError, match="projection review"):
        schemas.assert_connection_projection_coverage()


def test_modifier_prompt_contains_only_the_public_connection_selector() -> None:
    from src.domains.agents.application.connection_schemas import ConnectorConnectionUnlinkPatch
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.connectors.removal_commands import connector_removal_snapshot

    actor = User(id=uuid4())
    saved = connector(actor)
    saved.oauth_grant_id = uuid4()
    snapshot = connector_removal_snapshot(saved)
    content = _preference_content(
        actor.id,
        ConnectorConnectionUnlinkPatch(connector_to_disconnect=snapshot),
        {"connector_to_disconnect": snapshot.model_dump(mode="json")},
    )
    text = str(
        build_application_edit_prompt(
            content.model_dump(mode="json"), "Choisis une autre connexion"
        )
    )
    assert "connector_id" in text and str(saved.id) in text
    assert "oauth_grant_id" not in text and "updated_at" not in text
    assert str(saved.oauth_grant_id) not in text and "reader@example.test" not in text
