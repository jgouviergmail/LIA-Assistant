"""A disabled or failed restart cannot retain a previous transcript writer."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import transcript_gateway
from src.infrastructure.meeting_transcripts import (
    configure_meeting_transcripts,
    get_meeting_transcripts,
)
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_owner(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    previous = configure_meeting_transcripts(transcript_gateway.SavedMeetingTranscripts())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            transcript_gateway,
            "SavedMeetingTranscripts",
            MagicMock(side_effect=RuntimeError("broken owner")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError, match="broken owner"):
                registries.init_meeting_transcripts()
        else:
            registries.init_meeting_transcripts()
        with pytest.raises(AuthorizationError):
            get_meeting_transcripts()
    finally:
        configure_meeting_transcripts(previous)
