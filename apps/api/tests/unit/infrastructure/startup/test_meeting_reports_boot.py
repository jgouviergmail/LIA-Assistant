"""A disabled or failed restart withdraws a previous report restoration owner."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import report_gateway
from src.infrastructure.meeting_reports import configure_meeting_reports, get_meeting_reports
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_owner(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    previous = configure_meeting_reports(report_gateway.SavedMeetingReports())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            report_gateway,
            "SavedMeetingReports",
            MagicMock(side_effect=RuntimeError("broken owner")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError, match="broken owner"):
                registries.init_meeting_reports()
        else:
            registries.init_meeting_reports()
        with pytest.raises(AuthorizationError):
            get_meeting_reports()
    finally:
        configure_meeting_reports(previous)
