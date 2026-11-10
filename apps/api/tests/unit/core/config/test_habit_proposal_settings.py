"""The proposal bars are settings, composed into ``Settings`` (ADR-375)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
def test_the_proposal_bars_are_composed_with_their_defaults() -> None:
    assert settings.habits_proposal_routine_gap_hours == 2.0
    assert settings.habits_proposal_manual_min_runs == 3
    assert settings.habits_proposal_manual_min_days == 3
    assert settings.habits_proposal_failure_streak == 3
    assert settings.habits_proposal_window_min_days == 5
    assert settings.habits_proposal_window_min_cells == 8
    assert settings.habits_proposal_window_min_share == 0.25
    assert settings.habits_proposal_window_max_extension_hours == 3
    assert settings.habits_proposal_silent_min_notifications == 20
    assert settings.habits_proposal_connector_min_days == 3
    assert settings.habits_proposal_mute_after_refusals == 3
    assert settings.habits_proposal_snooze_days == 14
    assert settings.habits_proposal_resurface_days == 90


@pytest.mark.unit
def test_the_chat_card_bounds_are_settings_with_their_defaults() -> None:
    """At most one proposal under a chat answer per gap, each one again only
    after the repeat delay (ADR-375 lot 3)."""
    from src.core.config.habits import HabitsSettings

    declared = HabitsSettings.model_construct()
    assert declared.habits_proposal_chat_gap_hours == 24
    assert declared.habits_proposal_chat_repeat_days == 7
