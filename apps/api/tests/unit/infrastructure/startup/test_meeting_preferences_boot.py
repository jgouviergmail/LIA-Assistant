"""Disabled or failed owners cannot retain a previous gateway binding."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import preference_gateway
from src.infrastructure.meeting_preferences import (
    configure_meeting_preferences,
    get_meeting_preferences,
)
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_gateway(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    previous = configure_meeting_preferences(preference_gateway.SavedMeetingPreferences())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            preference_gateway,
            "SavedMeetingPreferences",
            MagicMock(side_effect=RuntimeError("broken owner")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError, match="broken owner"):
                registries.init_meeting_preferences()
        else:
            registries.init_meeting_preferences()
        with pytest.raises(AuthorizationError):
            get_meeting_preferences()
    finally:
        configure_meeting_preferences(previous)
