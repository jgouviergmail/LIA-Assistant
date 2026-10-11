"""Disabled or failed boot never retains an earlier minutes sender."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import email_gateway
from src.infrastructure.meeting_email import configure_meeting_email, get_meeting_email
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_email_owner(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    previous = configure_meeting_email(email_gateway.SavedMeetingEmail())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            email_gateway,
            "SavedMeetingEmail",
            MagicMock(side_effect=RuntimeError("Controlled boot failure")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError):
                registries.init_meeting_email()
        else:
            registries.init_meeting_email()
        with pytest.raises(AuthorizationError):
            get_meeting_email()
    finally:
        configure_meeting_email(previous)
