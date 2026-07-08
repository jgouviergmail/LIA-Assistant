"""Unit tests for VoiceCommentService prompt datetime resolution.

The datetime injected into the voice prompt is SPOKEN to the user as "the
current time": it must be resolved in the user's preferred timezone (or the
central ``DEFAULT_USER_DISPLAY_TIMEZONE``), never in the server clock frame
(datetime doctrine, ``core/time_utils.py``). These tests pin that contract on
``_resolve_prompt_datetime``, the single resolution point used by
``stream_voice_comment``.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.voice.service import (
    _PROMPT_DATETIME_FALLBACK_FORMAT,
    _resolve_prompt_datetime,
)

# Fixed instant for deterministic assertions: 2026-07-08 12:00 UTC.
_FIXED_UTC_INSTANT = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


@pytest.fixture
def frozen_now_in_timezone(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Freeze ``now_in_timezone`` (as imported by voice.service) on a fixed instant.

    Mirrors the real contract: the instant is converted to the requested
    timezone, ``None`` falling back to ``DEFAULT_USER_DISPLAY_TIMEZONE``.
    """

    def _frozen(user_timezone: str | None = None) -> datetime:
        tz = ZoneInfo(user_timezone or DEFAULT_USER_DISPLAY_TIMEZONE)
        return _FIXED_UTC_INSTANT.astimezone(tz)

    monkeypatch.setattr("src.domains.voice.service.now_in_timezone", _frozen)
    return _FIXED_UTC_INSTANT


class TestResolvePromptDatetime:
    """The spoken 'current time' respects the user's preference timezone."""

    def test_provided_datetime_is_passed_through_verbatim(self) -> None:
        """Callers pre-format the datetime in the user's timezone — no rewrite."""
        provided = "2026-07-08T15:30:00+02:00"
        assert _resolve_prompt_datetime(provided, "America/New_York") == provided

    def test_fallback_uses_user_preference_timezone(self, frozen_now_in_timezone: datetime) -> None:
        """Without a provided datetime, the user's timezone drives the spoken time.

        At 12:00 UTC, a New York user (EDT, UTC-4 in July) must hear 08:00 —
        not the 12:00 server/UTC time the legacy naive ``datetime.now()``
        fallback produced.
        """
        result = _resolve_prompt_datetime(None, "America/New_York")
        assert result == "2026-07-08 08:00"
        assert result != _FIXED_UTC_INSTANT.strftime(_PROMPT_DATETIME_FALLBACK_FORMAT)

    def test_empty_string_triggers_the_fallback(self, frozen_now_in_timezone: datetime) -> None:
        """Empty string behaves like None (legacy falsy check preserved)."""
        assert _resolve_prompt_datetime("", "America/New_York") == "2026-07-08 08:00"

    def test_fallback_without_timezone_uses_central_default(
        self, frozen_now_in_timezone: datetime
    ) -> None:
        """No user timezone → the central default, never a naive server time."""
        result = _resolve_prompt_datetime(None, None)
        expected = _FIXED_UTC_INSTANT.astimezone(ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)).strftime(
            _PROMPT_DATETIME_FALLBACK_FORMAT
        )
        assert result == expected
