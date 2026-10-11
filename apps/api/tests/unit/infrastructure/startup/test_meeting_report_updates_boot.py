"""A disabled or failed restart cannot retain the preceding sparse writer."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import report_update_gateway
from src.infrastructure.meeting_report_updates import (
    configure_meeting_report_updates,
    get_meeting_report_updates,
)
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_owner(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    previous = configure_meeting_report_updates(report_update_gateway.SavedMeetingReportUpdates())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            report_update_gateway,
            "SavedMeetingReportUpdates",
            MagicMock(side_effect=RuntimeError("broken owner")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError, match="broken owner"):
                registries.init_meeting_report_updates()
        else:
            registries.init_meeting_report_updates()
        with pytest.raises(AuthorizationError):
            get_meeting_report_updates()
    finally:
        configure_meeting_report_updates(previous)
