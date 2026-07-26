"""Reminder notification: the strings a user actually receives.

A reminder that fires is one of the few things LIA sends unprompted, so its
push title and body are read by the user before anything else. Two of the
helpers below were written as inline tables in Python — the pattern the
systemic i18n rule forbids — and one of them reproduced, verbatim, the defect
[ADR-131] was created to fix: keying the table on ``"zh"`` while
``User.language`` is backend-canonical ``"zh-CN"``, so Chinese users silently
received the English title.

The notification path is otherwise LLM-driven and DB-bound; these are the pure
functions that decide what the user reads, and they are testable directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.core.constants import SUPPORTED_LANGUAGES
from src.core.i18n_proactive import ProactiveMessages
from src.infrastructure.scheduler.reminder_notification import (
    format_creation_datetime,
    format_elapsed_time,
    get_localized_title,
    truncate_for_notification,
)

pytestmark = pytest.mark.unit


class TestLocalizedTitle:
    """The push notification title."""

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_every_supported_language_gets_its_own_title(self, language: str) -> None:
        """No supported language may silently fall back to English.

        ``SUPPORTED_LANGUAGES`` is the source of truth (``fr, en, es, de, it,
        zh-CN``), so iterating it makes a newly supported language fail here
        the day it is declared — not the day a user complains.
        """
        title = get_localized_title(language)

        assert title
        if language != "en":
            assert title != get_localized_title("en"), (
                f"{language} falls back to the English title — the table is "
                "either missing the key or keyed on a different spelling"
            )

    def test_chinese_is_keyed_on_the_backend_canonical_code(self) -> None:
        """The ADR-131 regression, at a second site.

        ``User.language`` holds ``zh-CN`` (see the column comment on
        ``users.language``). A table keyed ``"zh"`` therefore never matches and
        every Chinese user gets English.
        """
        assert get_localized_title("zh-CN") == "提醒"

    def test_frontend_spelling_is_normalized_rather_than_dropped(self) -> None:
        """`zh` is the FRONTEND spelling; it must not degrade to English."""
        assert get_localized_title("zh") == get_localized_title("zh-CN")

    def test_unknown_language_resolves_to_the_configured_default(self) -> None:
        """`normalize_language` is the contract: unsupported → default language.

        Not English: the chokepoint answers with the configured default, which
        is what every other localized surface does.
        """
        from src.core.i18n import DEFAULT_LANGUAGE

        assert get_localized_title("kl") == get_localized_title(DEFAULT_LANGUAGE)

    def test_a_regional_variant_resolves_to_its_base_language(self) -> None:
        assert get_localized_title("fr-FR") == get_localized_title("fr")
        assert get_localized_title("en_US") == get_localized_title("en")

    def test_title_comes_from_the_central_table(self) -> None:
        """One table for every proactive surface, not one per scheduler.

        The reminder title used to live in an inline dict inside the scheduler,
        which is how it drifted from the centralized one.
        """
        for language in SUPPORTED_LANGUAGES:
            assert get_localized_title(language) == ProactiveMessages.notification_title(
                "reminder", language
            )


class TestTruncateForNotification:
    """FCM bodies are length-bounded; the cut must stay inside the bound."""

    def test_short_text_is_returned_verbatim(self) -> None:
        assert truncate_for_notification("Court", 150) == "Court"

    def test_text_at_the_exact_limit_is_not_truncated(self) -> None:
        text = "x" * 150
        assert truncate_for_notification(text, 150) == text

    def test_longer_text_is_cut_to_the_limit_including_the_ellipsis(self) -> None:
        result = truncate_for_notification("x" * 200, 150)

        assert len(result) == 150
        assert result.endswith("...")

    def test_the_kept_prefix_is_the_original_text(self) -> None:
        result = truncate_for_notification("abcdefghij", 8)

        assert result == "abcde..."
        assert len(result) == 8


class TestFormatElapsedTime:
    """Wording of "how long ago the reminder was set"."""

    @pytest.mark.parametrize(
        "elapsed,expected_fr",
        [
            (timedelta(days=3), "il y a 3 jours"),
            (timedelta(days=1), "hier"),
            (timedelta(hours=2), "il y a 2 heures"),
            (timedelta(hours=1), "il y a 1 heure"),
            (timedelta(minutes=5), "il y a 5 minutes"),
            (timedelta(minutes=1), "il y a 1 minute"),
            (timedelta(seconds=10), "il y a quelques instants"),
        ],
    )
    def test_french_wording_including_the_singular_forms(
        self, elapsed: timedelta, expected_fr: str
    ) -> None:
        assert format_elapsed_time(elapsed, "fr") == expected_fr

    @pytest.mark.parametrize(
        "elapsed,expected_en",
        [
            (timedelta(days=3), "3 days ago"),
            (timedelta(days=1), "yesterday"),
            (timedelta(hours=2), "2 hours ago"),
            (timedelta(hours=1), "1 hour ago"),
            (timedelta(minutes=5), "5 minutes ago"),
            (timedelta(minutes=1), "1 minute ago"),
            (timedelta(seconds=10), "just now"),
        ],
    )
    def test_english_wording_including_the_singular_forms(
        self, elapsed: timedelta, expected_en: str
    ) -> None:
        assert format_elapsed_time(elapsed, "en") == expected_en

    def test_a_day_boundary_reads_as_yesterday_not_as_hours(self) -> None:
        """`timedelta.days` truncates: 25 h is one day, not 25 hours."""
        assert format_elapsed_time(timedelta(hours=25), "en") == "yesterday"

    def test_two_days_is_plural_but_one_day_is_yesterday(self) -> None:
        assert format_elapsed_time(timedelta(days=2), "en") == "2 days ago"


class TestFormatCreationDatetime:
    """The creation timestamp, rendered in the USER's timezone."""

    def test_utc_instant_is_converted_to_the_user_timezone(self) -> None:
        """13:30 UTC is 15:30 in Paris in July — the user reads their own clock."""
        created = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)

        assert format_creation_datetime(created, "Europe/Paris", "fr") == "le 15/07 à 15:30"

    def test_a_timezone_shift_can_move_the_date(self) -> None:
        """23:30 UTC is already the next day in Tokyo."""
        created = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)

        assert format_creation_datetime(created, "Asia/Tokyo", "fr") == "le 16/07 à 08:30"

    def test_english_uses_month_first_and_a_twelve_hour_clock(self) -> None:
        created = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)

        result = format_creation_datetime(created, "Europe/Paris", "en")

        assert result.startswith("on 07/15 at ")
        assert "03:30 PM" in result

    def test_utc_user_sees_the_stored_instant(self) -> None:
        created = datetime(2026, 1, 2, 9, 5, tzinfo=UTC)

        assert format_creation_datetime(created, "UTC", "fr") == "le 02/01 à 09:05"
