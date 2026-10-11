"""Readonly owners are withdrawn before a disabled or failed restart."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import read_gateway
from src.infrastructure.meeting_reads import configure_meeting_reads, get_meeting_reads
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_owner(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    previous = configure_meeting_reads(read_gateway.SavedMeetingReads())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            read_gateway, "SavedMeetingReads", MagicMock(side_effect=RuntimeError("broken owner"))
        )
    try:
        if failure:
            with pytest.raises(RuntimeError, match="broken owner"):
                registries.init_meeting_reads()
        else:
            registries.init_meeting_reads()
        with pytest.raises(AuthorizationError):
            get_meeting_reads()
    finally:
        configure_meeting_reads(previous)
