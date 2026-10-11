"""Live reflex writes refresh account state and preserve concurrent provider choice."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.live.preferences import LivePreferences
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


async def test_stale_reflex_confirmation_cannot_overwrite_a_new_provider_choice() -> None:
    owner = import_module("src.domains.live.preference_commands")
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        live_preferences=LivePreferences(provider="gemini").model_dump(),
    )
    previous = owner.live_preference_snapshot(actor)
    actor.live_preferences = LivePreferences(provider="openai").model_dump()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    with pytest.raises(ResourceConflictError):
        await owner.update_live_preferences(
            db, actor.id, LivePreferences(end_of_speech="calm"), expected=previous
        )
    db.commit.assert_not_awaited()
    assert actor.live_preferences["provider"] == "openai"


async def test_ui_reflex_save_preserves_the_fresh_provider_choice() -> None:
    owner = import_module("src.domains.live.preference_commands")
    actor = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        live_preferences=LivePreferences(provider="openai").model_dump(),
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    receipt = PreferenceWriteReceipt()
    result = await owner.update_live_preferences(
        db, actor.id, LivePreferences(end_of_speech="calm"), receipt=receipt
    )
    assert result.end_of_speech == "calm" and result.provider == "openai"
    assert receipt.committed and not receipt.no_op
    db.commit.assert_awaited_once()


async def test_inactive_account_is_refused_before_preferences_are_written() -> None:
    owner = import_module("src.domains.live.preference_commands")
    actor = User(id=uuid4(), is_active=False, deleted_at=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = actor
    with pytest.raises(AuthorizationError):
        await owner.update_live_preferences(db, actor.id, LivePreferences())
    db.commit.assert_not_awaited()
