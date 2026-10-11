"""Preparation freezes a concrete, bounded change without modifying the account."""

from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.schemas import PreferencePatch
from src.domains.auth.preference_commands import AssistantPreferencePatch
from src.domains.users.models import User

pytestmark = pytest.mark.unit


async def test_assistant_consent_preview_is_exact_without_toggling_the_account() -> None:
    prepare = import_module("src.domains.agents.application.preparation").prepare_assistant_content
    actor = User(
        id=uuid4(), is_active=True, is_superuser=False, memory_enabled=True, deleted_at=None
    )
    db = AsyncMock()
    db.scalar.side_effect = ["true", actor]
    content = await prepare(db, actor.id, AssistantPreferencePatch(memory_enabled=False))
    assert content.operation_id == "assistant_preferences.update"
    assert content.before == {"memory_enabled": True}
    assert content.after == {"memory_enabled": False}
    assert actor.memory_enabled is True
    db.commit.assert_not_awaited()


async def test_preparation_freezes_current_before_after_without_user_write() -> None:
    prepare = import_module("src.domains.agents.application.preparation").prepare_preference_content
    actor = User(id=uuid4(), is_active=True, is_superuser=False, font_size=16, deleted_at=None)
    db = AsyncMock()
    db.scalar.side_effect = ["true", actor]
    content = await prepare(db, actor.id, PreferencePatch(font_size=17))
    assert content.actor_id == actor.id
    assert content.before == {"font_size": 16}
    assert content.after == {"font_size": 17}
    assert content.intent == {"font_size": 17}
    assert actor.font_size == 16
    db.commit.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.parametrize("current,step,target", [(16, 1, 17), (16, -1, 15), (19, 1, 20)])
def test_relative_font_size_is_the_actual_ui_one_pixel_step(
    current: int, step: int, target: int
) -> None:
    resolve = import_module("src.domains.agents.application.preparation").font_step_patch
    assert resolve(current, step).font_size == target


@pytest.mark.parametrize("current,step", [(20, 1), (14, -1), (16, 2), (16, True)])
def test_font_adjustment_never_silently_clamps_or_coerces(current: int, step: object) -> None:
    resolve = import_module("src.domains.agents.application.preparation").font_step_patch
    with pytest.raises((ValidationError, ValueError)):
        resolve(current, step)
