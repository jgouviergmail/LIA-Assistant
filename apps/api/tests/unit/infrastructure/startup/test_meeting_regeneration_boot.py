"""A disabled or failed boot cannot retain an earlier regeneration owner."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import regeneration_gateway
from src.infrastructure.meeting_regeneration import (
    configure_meeting_regeneration,
    get_meeting_regeneration,
)
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_regeneration_owner(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    previous = configure_meeting_regeneration(regeneration_gateway.SavedMeetingRegeneration())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            regeneration_gateway,
            "SavedMeetingRegeneration",
            MagicMock(side_effect=RuntimeError("Controlled boot failure")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError):
                registries.init_meeting_regeneration()
        else:
            registries.init_meeting_regeneration()
        with pytest.raises(AuthorizationError):
            get_meeting_regeneration()
    finally:
        configure_meeting_regeneration(previous)
