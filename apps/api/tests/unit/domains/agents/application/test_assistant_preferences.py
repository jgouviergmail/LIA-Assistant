"""Non-secret assistant settings preserve the native API validators and CAS."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import ResourceConflictError
from src.domains.auth.preference_commands import (
    AssistantPreferencePatch,
    update_assistant_preferences,
)
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"memory_enabled": None},
        {"memory_enabled": 1},
        {"execution_mode": "invented"},
        {"response_display_mode": "invented"},
        {"voice_stt_mode": "invented"},
        {"api_key": "planted-secret"},
    ],
)
def test_assistant_patch_rejects_ambiguous_invalid_and_secret_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AssistantPreferencePatch.model_validate(payload)


async def test_unchanged_assistant_consent_does_not_repeat_an_effect() -> None:
    actor = User(id=uuid4(), memory_enabled=False, is_active=True, deleted_at=None)
    db = AsyncMock()
    db.scalar.return_value = actor
    receipt = PreferenceWriteReceipt()
    await update_assistant_preferences(
        db,
        actor.id,
        AssistantPreferencePatch(memory_enabled=False),
        expected={"memory_enabled": False},
        receipt=receipt,
    )
    assert receipt.committed and receipt.no_op
    db.commit.assert_not_awaited()


async def test_intervening_consent_change_cannot_be_overwritten_by_an_old_approval() -> None:
    actor = User(id=uuid4(), memory_enabled=False, is_active=True, deleted_at=None)
    db = AsyncMock()
    db.scalar.return_value = actor
    with pytest.raises(ResourceConflictError):
        await update_assistant_preferences(
            db,
            actor.id,
            AssistantPreferencePatch(memory_enabled=False),
            expected={"memory_enabled": True},
            receipt=PreferenceWriteReceipt(),
        )
    db.commit.assert_not_awaited()


async def test_remote_stt_unavailable_is_refused_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = User(id=uuid4(), voice_stt_mode="local", is_active=True, deleted_at=None)
    db = AsyncMock()
    db.scalar.return_value = actor
    monkeypatch.setattr("src.domains.auth.preference_commands.stt_remote_available", lambda: False)
    with pytest.raises(ValueError):
        await update_assistant_preferences(
            db,
            actor.id,
            AssistantPreferencePatch(voice_stt_mode="remote"),
            expected={"voice_stt_mode": "local"},
            receipt=PreferenceWriteReceipt(),
        )
    assert actor.voice_stt_mode == "local"
    db.commit.assert_not_awaited()
