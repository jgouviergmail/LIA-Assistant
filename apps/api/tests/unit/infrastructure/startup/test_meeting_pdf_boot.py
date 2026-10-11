"""Restart never retains a previous minutes renderer after disable/failure."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import pdf_gateway
from src.infrastructure.meeting_pdf import configure_meeting_pdf, get_meeting_pdf
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_owner(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    previous = configure_meeting_pdf(pdf_gateway.SavedMeetingPDF())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            pdf_gateway, "SavedMeetingPDF", MagicMock(side_effect=RuntimeError("broken renderer"))
        )
    try:
        if failure:
            with pytest.raises(RuntimeError, match="broken renderer"):
                registries.init_meeting_pdf()
        else:
            registries.init_meeting_pdf()
        with pytest.raises(AuthorizationError):
            get_meeting_pdf()
    finally:
        configure_meeting_pdf(previous)
