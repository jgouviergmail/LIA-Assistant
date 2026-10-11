"""A disabled or failed restart cannot retain the previous template writer."""

from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.meetings import template_gateway
from src.infrastructure.meeting_templates import configure_meeting_templates, get_meeting_templates
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [False, True])
def test_restart_withdraws_previous_owner(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    previous = configure_meeting_templates(template_gateway.SavedMeetingTemplates())
    monkeypatch.setattr(settings, "meetings_enabled", failure)
    if failure:
        monkeypatch.setattr(
            template_gateway,
            "SavedMeetingTemplates",
            MagicMock(side_effect=RuntimeError("broken owner")),
        )
    try:
        if failure:
            with pytest.raises(RuntimeError, match="broken owner"):
                registries.init_meeting_templates()
        else:
            registries.init_meeting_templates()
        with pytest.raises(AuthorizationError):
            get_meeting_templates()
    finally:
        configure_meeting_templates(previous)
