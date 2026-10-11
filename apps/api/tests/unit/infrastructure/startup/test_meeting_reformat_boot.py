"""A disabled or failed restart withdraws any earlier reformat owner."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import reformat_gateway
from src.infrastructure.meeting_reformat import configure_meeting_reformat, get_meeting_reformat
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_reformat_owner(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    previous = configure_meeting_reformat(reformat_gateway.SavedMeetingReformat())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            reformat_gateway,
            "SavedMeetingReformat",
            MagicMock(side_effect=RuntimeError("Controlled boot failure")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError):
                registries.init_meeting_reformat()
        else:
            registries.init_meeting_reformat()
        with pytest.raises(AuthorizationError):
            get_meeting_reformat()
    finally:
        configure_meeting_reformat(previous)
