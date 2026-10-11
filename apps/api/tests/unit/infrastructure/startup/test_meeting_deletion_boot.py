"""A disabled or failed boot cannot retain an earlier deletion owner."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import deletion_gateway
from src.infrastructure.meeting_deletions import configure_meeting_deletions, get_meeting_deletions
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_deletion_owner(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    previous = configure_meeting_deletions(deletion_gateway.SavedMeetingDeletions())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            deletion_gateway,
            "SavedMeetingDeletions",
            MagicMock(side_effect=RuntimeError("Controlled boot failure")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError):
                registries.init_meeting_deletions()
        else:
            registries.init_meeting_deletions()
        with pytest.raises(AuthorizationError):
            get_meeting_deletions()
    finally:
        configure_meeting_deletions(previous)
