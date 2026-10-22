"""« Not now » pauses for the hours its label promised when the opening was published."""

import pytest

from src.core.config import settings
from src.core.field_names import FIELD_DISCUSSION_PAUSE_HOURS
from src.domains.conversations.models import ConversationMessage
from src.domains.proactive_discussions.openings import promised_pause_hours

pytestmark = pytest.mark.unit


def _opening(metadata: dict[str, object] | None) -> ConversationMessage:
    return ConversationMessage(role="assistant", content="Fiction", message_metadata=metadata)


def test_the_published_promise_wins_over_a_setting_changed_since():
    promised = settings.discussion_pause_hours + 1
    assert promised_pause_hours(_opening({FIELD_DISCUSSION_PAUSE_HOURS: promised})) == promised


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {FIELD_DISCUSSION_PAUSE_HOURS: 0},
        {FIELD_DISCUSSION_PAUSE_HOURS: True},
        {FIELD_DISCUSSION_PAUSE_HOURS: "12"},
    ],
)
def test_an_opening_without_a_readable_promise_pauses_for_the_configured_hours(metadata):
    assert promised_pause_hours(_opening(metadata)) == settings.discussion_pause_hours
