"""A disabled or failed boot cannot retain an earlier retry owner."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import retry_gateway
from src.infrastructure.meeting_retry import configure_meeting_retry, get_meeting_retry
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_retry_owner(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    previous = configure_meeting_retry(retry_gateway.SavedMeetingRetry())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            retry_gateway,
            "SavedMeetingRetry",
            MagicMock(side_effect=RuntimeError("Controlled boot failure")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError):
                registries.init_meeting_retry()
        else:
            registries.init_meeting_retry()
        with pytest.raises(AuthorizationError):
            get_meeting_retry()
    finally:
        configure_meeting_retry(previous)
