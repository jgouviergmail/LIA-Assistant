"""Confirmation exceptions are reviewed capabilities, never HTTP-method guesses."""

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "operation, intent, expected",
    [
        ("preferences.update", {"color_theme": "forest"}, False),
        ("preferences.update", {"font_size": 17}, False),
        ("preferences.update", {"image_generation_enabled": False}, False),
        ("habit_settings.update", {"habits_enabled": False}, False),
        ("psyche_settings.update", {"psyche_display_avatar": False}, False),
        ("journal_settings.update", {"journals_enabled": False}, False),
        ("journal_settings.update", {"journal_max_total_chars": 1000}, True),
        ("interest_settings.update", {"interests_enabled": False}, False),
        ("heartbeat_preferences.update", {"heartbeat_enabled": False}, False),
        ("assistant_preferences.update", {"tokens_display_enabled": True}, False),
        ("assistant_preferences.update", {"voice_mode_enabled": True}, True),
        ("assistant_preferences.update", {"voice_mode_enabled": False}, False),
        (
            "assistant_preferences.update",
            {"voice_mode_enabled": True, "tokens_display_enabled": False},
            True,
        ),
        ("assistant_preferences.update", {"voice_stt_mode": "remote"}, True),
        (
            "assistant_preferences.update",
            {"tokens_display_enabled": True, "voice_stt_mode": "remote"},
            True,
        ),
        ("assistant_preferences.update", {"login_notifications_enabled": False}, True),
        ("meeting_device.control", {"device_recording": {"action": "start"}}, True),
        ("knowledge_space.delete", {}, True),
        ("future_settings.update", {"enabled": True}, True),
    ],
)
def test_risk_based_confirmation(operation, intent, expected):
    from src.domains.agents.application.confirmation_policy import requires_confirmation

    assert requires_confirmation(operation, intent) is expected
