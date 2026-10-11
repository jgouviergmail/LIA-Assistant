"""Channel proposals freeze one current owned binding without credentials or business writes."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.channels.models import UserChannelBinding
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def test_frozen_binding_refuses_an_unsupported_channel_kind() -> None:
    from src.domains.channels.preference_commands import ChannelBindingSnapshot

    with pytest.raises(ValidationError):
        ChannelBindingSnapshot(
            id=uuid4(),
            channel_type="invented-provider",
            channel_user_id="chat",
            channel_username=None,
            is_active=True,
        )


def test_channel_editor_offers_only_the_selector_and_desired_state() -> None:
    from src.domains.agents.application.channel_schemas import ChannelBindingUpdatePatch
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.channels.preference_commands import ChannelBindingSnapshot

    snapshot = ChannelBindingSnapshot(
        id=uuid4(),
        channel_type="telegram",
        channel_user_id="private-chat-id",
        channel_username="@reader",
        is_active=False,
    )
    draft = _preference_content(
        uuid4(),
        ChannelBindingUpdatePatch(channel_binding=snapshot),
        {"channel_binding": snapshot.model_dump(mode="json")},
    )
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Active plutôt ce canal")
    )
    assert "private-chat-id" not in prompt
    assert "channel_user_id" not in prompt
    assert "channel_username" not in prompt
    assert "binding_id" in prompt and "enabled" in prompt


@pytest.mark.parametrize(
    "payload",
    [
        {"binding_id": "invalid", "enabled": False},
        {"binding_id": str(uuid4()), "enabled": "false"},
        {"binding_id": str(uuid4()), "enabled": False, "user_id": str(uuid4())},
    ],
)
def test_public_change_refuses_a_model_actor_and_coerced_values(payload: object) -> None:
    schemas = import_module("src.domains.agents.application.channel_schemas")
    with pytest.raises(ValidationError):
        schemas.ChannelBindingUpdateRequest.model_validate(payload)


async def test_channel_preparation_freezes_identity_and_desired_state_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operations = import_module("src.domains.agents.application.channel_operations")
    schemas = import_module("src.domains.agents.application.channel_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "channels_enabled", True)
    actor = User(id=uuid4(), is_active=True, deleted_at=None)
    binding = UserChannelBinding(
        id=uuid4(),
        user_id=actor.id,
        channel_type="telegram",
        channel_user_id="private-chat-id",
        channel_username="@reader",
        is_active=True,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, None, actor, binding]
    content = await operations.prepare_channel_binding_content(
        db, actor.id, schemas.ChannelBindingUpdateRequest(binding_id=binding.id, enabled=False)
    )
    assert content.operation_id == "channel_binding.update"
    assert content.before["channel_binding"]["id"] == str(binding.id)
    assert content.before["channel_binding"]["is_active"] is True
    assert content.after["channel_binding"]["is_active"] is False
    assert content.after == content.intent
    assert binding.is_active is True
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("off", ["deployment", "operator"])
async def test_channel_ceiling_is_checked_before_reading_binding_identity(
    monkeypatch: pytest.MonkeyPatch, off: str
) -> None:
    operations = import_module("src.domains.agents.application.channel_operations")
    schemas = import_module("src.domains.agents.application.channel_schemas")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "channels_enabled", off != "deployment")
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = [None, "false"]
    with pytest.raises(AuthorizationError):
        await operations.prepare_channel_binding_content(
            db, uuid4(), schemas.ChannelBindingUpdateRequest(binding_id=uuid4(), enabled=False)
        )
    assert db.scalar.await_count == (1 if off == "deployment" else 2)
    db.commit.assert_not_awaited()
