"""Assistant settings expose exactly their reviewed current non-secret values."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.application.assistant_queries import read_assistant_preferences
from src.domains.agents.application.assistant_schemas import AssistantPreferenceRead
from src.domains.auth.preference_commands import ASSISTANT_PREFERENCE_SOURCES
from src.domains.users.models import User

pytestmark = pytest.mark.unit


async def test_all_assistant_fields_are_current_and_no_private_column_is_projected() -> None:
    values = {
        "memory_enabled": False,
        "health_metrics_agents_enabled": True,
        "execution_mode": "react",
        "use_last_known_location": False,
        "voice_enabled": False,
        "voice_mode_enabled": True,
        "voice_stt_mode": "local",
        "tokens_display_enabled": True,
        "login_notifications_enabled": False,
        "onboarding_completed": True,
        "debug_panel_enabled": False,
        "response_display_mode": "html_cards",
    }
    actor = User(
        id=uuid4(), is_active=True, deleted_at=None, hashed_password="planted-secret", **values
    )
    db = AsyncMock()
    db.scalar.side_effect = [None, actor]
    projection = await read_assistant_preferences(db, actor.id, AssistantPreferenceRead())
    assert projection.values == values
    assert set(projection.values) == set(ASSISTANT_PREFERENCE_SOURCES)
    assert "planted-secret" not in projection.model_dump_json()


async def test_selected_flags_do_not_omit_explicit_false_values() -> None:
    actor = User(id=uuid4(), is_active=True, deleted_at=None, memory_enabled=False)
    db = AsyncMock()
    db.scalar.side_effect = [None, actor]
    result = await read_assistant_preferences(
        db, actor.id, AssistantPreferenceRead(fields=["memory_enabled"])
    )
    assert result.values == {"memory_enabled": False}
