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
from src.core.i18n_dates import format_elapsed, format_short_stamp
from src.core.i18n_proactive import ProactiveMessages
from src.infrastructure.scheduler.reminder_notification import (
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
    """Wording of "how long ago the reminder was set".

    Two languages when this lived in the scheduler as
    ``if language == "fr": ... else: <English>``. It now reads the central
    six-language table, so the four other readers get their own words — see
    ``TestEverySupportedLanguageIsAnswered`` below.
    """

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
        assert format_elapsed(elapsed, "fr") == expected_fr

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
        assert format_elapsed(elapsed, "en") == expected_en

    def test_a_day_boundary_reads_as_yesterday_not_as_hours(self) -> None:
        """`timedelta.days` truncates: 25 h is one day, not 25 hours."""
        assert format_elapsed(timedelta(hours=25), "en") == "yesterday"

    def test_two_days_is_plural_but_one_day_is_yesterday(self) -> None:
        assert format_elapsed(timedelta(days=2), "en") == "2 days ago"


class TestFormatCreationDatetime:
    """The creation timestamp, rendered in the USER's timezone.

    The zone conversion is part of the function, not a caller's preparation:
    splitting them would let a caller stamp a UTC instant as if it were local.
    """

    def test_utc_instant_is_converted_to_the_user_timezone(self) -> None:
        """13:30 UTC is 15:30 in Paris in July — the user reads their own clock."""
        created = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)

        assert format_short_stamp(created, "Europe/Paris", "fr") == "le 15/07 à 15:30"

    def test_a_timezone_shift_can_move_the_date(self) -> None:
        """23:30 UTC is already the next day in Tokyo."""
        created = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)

        assert format_short_stamp(created, "Asia/Tokyo", "fr") == "le 16/07 à 08:30"

    def test_english_uses_month_first_and_a_twelve_hour_clock(self) -> None:
        created = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)

        result = format_short_stamp(created, "Europe/Paris", "en")

        assert result.startswith("on 07/15 at ")
        assert "03:30 PM" in result

    def test_utc_user_sees_the_stored_instant(self) -> None:
        created = datetime(2026, 1, 2, 9, 5, tzinfo=UTC)

        assert format_short_stamp(created, "UTC", "fr") == "le 02/01 à 09:05"


class TestEverySupportedLanguageIsAnswered:
    """The reason these moved: four readers out of six were served English.

    A German, Spanish, Italian or Chinese user received an English fragment
    inside a message otherwise composed in their own language — and, on the
    fallback path, an entire English notification. The rule CLAUDE.md states
    names this case explicitly ("LLM scaffolding around versioned prompts").
    """

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_elapsed_wording_exists_and_is_not_the_english_one(self, language: str) -> None:
        rendered = format_elapsed(timedelta(days=3), language)
        assert rendered
        if language != "en":
            assert rendered != format_elapsed(timedelta(days=3), "en"), language

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_the_stamp_exists_for_every_language(self, language: str) -> None:
        created = datetime(2026, 7, 15, 13, 30, tzinfo=UTC)
        assert format_short_stamp(created, "Europe/Paris", language)

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_the_fallback_notification_is_never_english_by_default(self, language: str) -> None:
        """This one is the notification BODY, not prompt scaffolding."""
        body = ProactiveMessages.reminder_fallback_body("le 15/07", "appeler le medecin", language)
        assert "appeler le medecin" in body
        if language != "en":
            assert "It's time!" not in body, language

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_the_neutral_persona_speaks_the_readers_language(self, language: str) -> None:
        from src.core.i18n_dates import neutral_persona

        voice = neutral_persona(language)
        assert voice
        if language != "en":
            assert voice != neutral_persona("en"), language

    def test_the_frontend_spelling_of_chinese_is_normalized(self) -> None:
        """`zh` from the browser must reach the `zh-CN` row, not the fallback.

        The defect ADR-131 exists for, reproduced three times in this file's
        history.
        """
        assert format_elapsed(timedelta(days=3), "zh") == format_elapsed(timedelta(days=3), "zh-CN")
        assert format_elapsed(timedelta(days=3), "zh") != format_elapsed(timedelta(days=3), "en")


class TestTheMessageKnowsWhetherItRepeats:
    """A recurring reminder must not cite the day it was set up.

    The prompt ordered it unconditionally: "Mention when the request was made".
    For a reminder firing every morning, created three months ago, the model
    was instructed to open with "you asked me three months ago to…" on EVERY
    occurrence. The scheduling rule has no branch on "is this recurring"; this
    wording does, and legitimately.
    """

    def test_a_single_occurrence_still_cites_the_request(self) -> None:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        block = load_prompt("reminder_origin_once", version="v1").format(
            created_at_text="le 27/12 à 15:30", elapsed_text="hier"
        )
        assert "le 27/12 à 15:30" in block
        assert "hier" in block
        assert "ONCE" in block

    def test_a_recurring_occurrence_is_forbidden_from_citing_it(self) -> None:
        from src.core.recurrence import RecurrenceSpec, describe
        from src.domains.agents.prompts.prompt_loader import load_prompt

        spec = RecurrenceSpec.model_validate(
            {
                "freq": "daily",
                "interval": 1,
                "anchor_date": "2026-06-01",
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
            }
        )
        block = load_prompt("reminder_origin_recurring", version="v1").format(
            schedule_human=describe(spec, "fr")
        )
        assert "Do NOT mention when the reminder was set up" in block
        # The schedule replaces the origin: the reader hears WHAT repeats.
        assert describe(spec, "fr") in block

    def test_the_two_blocks_never_say_the_same_thing(self) -> None:
        """A guard against someone "simplifying" them back into one."""
        from src.domains.agents.prompts.prompt_loader import load_prompt

        once = load_prompt("reminder_origin_once", version="v1")
        recurring = load_prompt("reminder_origin_recurring", version="v1")
        assert once != recurring
        assert "{created_at_text}" in once
        assert "{created_at_text}" not in recurring


class TestTheFallbackDoesNotContradictTheVersionedPrompt:
    """A fallback is a safety net, not a second prompt with its own opinions.

    `reminder_origin_recurring.txt` forbids naming when the reminder was set
    up: the reader configured the schedule once and hears from it every time
    it comes round, so "you asked me three months ago" is right for a post-it
    and wrong on the ninetieth morning. The inline fallback said exactly that,
    unconditionally — so losing one file would not merely degrade the wording,
    it would reintroduce the defect the lot removed, on every recurring
    reminder, with nothing to reveal it.

    The rule lives in the versioned fragment; the fallback must DEFER to it
    (`{origin_context}`) rather than restate it.
    """

    def test_the_fallback_defers_to_the_origin_fragment(self) -> None:
        from src.infrastructure.scheduler.reminder_notification import FALLBACK_REMINDER_PROMPT

        assert "{origin_context}" in FALLBACK_REMINDER_PROMPT
        for forbidden in ("asked for this reminder", "{elapsed_text}", "{created_at_text}"):
            assert forbidden not in FALLBACK_REMINDER_PROMPT, (
                f"the fallback states {forbidden!r}, which "
                "`reminder_origin_recurring.txt` forbids on a recurring occurrence"
            )

    def test_the_versioned_fragment_still_carries_the_rule(self) -> None:
        """If the rule moved, this test must be the thing that notices."""
        from src.domains.agents.prompts.prompt_loader import load_prompt

        recurring = load_prompt("reminder_origin_recurring", version="v1")
        assert "Do NOT mention when the reminder was set up" in recurring

    def test_reader_written_content_is_a_VALUE_not_part_of_the_template(self) -> None:
        """A reminder saying "payer la facture {montant}" must not break the job.

        The fallback interpolated the reader's own words into the template
        string, and the result was then passed to `.format()` — so a brace in
        a reminder's content became a placeholder nobody could fill.
        Measured 2026-09-06: `KeyError: 'montant'`, which the per-reminder
        handler turns into three retries and an abandoned occurrence. The
        versioned prompt never had the problem, because there the content is a
        keyword argument. The fallback must be shaped the same way.
        """
        from src.infrastructure.scheduler.reminder_notification import FALLBACK_REMINDER_PROMPT

        rendered = FALLBACK_REMINDER_PROMPT.format(
            persona_prompt="P",
            original_message="orig",
            reminder_content="payer la facture {montant} EUR",
            elapsed_text="e",
            created_at_text="c",
            trigger_text="t",
            memory_section="m",
            user_language="fr",
            psyche_context="p",
            origin_context="- origin -",
        )
        assert "{montant}" in rendered
        assert "- origin -" in rendered
