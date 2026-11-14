"""Tests for ProactiveMessages i18n (zh-CN regression, ADR-131)."""

import pytest

from src.core.constants import SUPPORTED_LANGUAGES
from src.core.i18n_proactive import ProactiveMessages

# Iterate the table itself rather than a hand-maintained list: a new task type
# must be covered by the guards below the day it is added, not the day someone
# remembers to extend a tuple. (``scheduled_action`` was added in 2026-07 and
# would have slipped through the previous hardcoded list.)
ALL_TASK_TYPES = sorted(ProactiveMessages._TITLES)


@pytest.mark.unit
class TestProactiveMessages:
    def test_interest_title_all_six_languages(self) -> None:
        for language, expected in [
            ("fr", "Pour toi"),
            ("en", "For you"),
            ("es", "Para ti"),
            ("de", "Für dich"),
            ("it", "Per te"),
            ("zh-CN", "为你推荐"),
        ]:
            assert ProactiveMessages.notification_title("interest", language) == expected

    @pytest.mark.parametrize("task_type", ALL_TASK_TYPES)
    def test_zh_cn_regression_no_english_fallback(self, task_type: str) -> None:
        """User.language is backend-canonical zh-CN; the old table was keyed 'zh'."""
        title = ProactiveMessages.notification_title(task_type, "zh-CN")
        assert title != ProactiveMessages.notification_title(task_type, "en")

    @pytest.mark.parametrize("task_type", ALL_TASK_TYPES)
    def test_every_task_type_covers_all_supported_languages(self, task_type: str) -> None:
        """No task type may fall back to English for a supported language.

        Completeness guard in the spirit of ``assert_registry_completeness``:
        a partially translated entry degrades silently in production.
        """
        missing = [
            lang for lang in SUPPORTED_LANGUAGES if lang not in ProactiveMessages._TITLES[task_type]
        ]
        assert not missing, f"{task_type} is missing translations for {missing}"

    def test_scheduled_action_title_is_localized(self) -> None:
        """Regression: the executor used its own inline table keyed "zh"."""
        assert ProactiveMessages.notification_title("scheduled_action", "fr") == "Action planifiée"
        assert ProactiveMessages.notification_title("scheduled_action", "zh-CN") == "计划操作"

    def test_unknown_language_resolves_to_the_configured_default(self) -> None:
        """The accessor now normalizes, so an unsupported code lands on the default.

        It used to key the table on the RAW code and fall through to English.
        That made the accessor safe only for callers who had already
        canonicalized — the discipline whose failure produced this module's
        founding bug. It normalizes internally now, matching what
        ``HitlMessages`` does (normalize, then an English belt-and-braces
        ``.get``), so an unsupported language answers with the configured
        default language rather than English.
        """
        from src.core.config import settings

        assert ProactiveMessages.notification_title(
            "interest", "xx"
        ) == ProactiveMessages.notification_title("interest", settings.default_language)

    @pytest.mark.parametrize("spelling", ["zh", "zh_CN", "zh-cn", "ZH-CN"])
    def test_every_chinese_spelling_reaches_the_canonical_entry(self, spelling: str) -> None:
        """Callers hold raw locales; none of them may degrade to English."""
        assert ProactiveMessages.notification_title("interest", spelling) == "为你推荐"

    def test_a_regional_variant_resolves_to_its_base_language(self) -> None:
        assert ProactiveMessages.notification_title("interest", "fr-FR") == "Pour toi"
        assert ProactiveMessages.notification_title("interest", "en_US") == "For you"

    def test_unknown_task_type_generic_title(self) -> None:
        assert ProactiveMessages.notification_title("nope", "en") == "Notification"

    def test_sources_label_six_languages(self) -> None:
        labels = {
            ProactiveMessages.sources_label(lang)
            for lang in ("fr", "en", "es", "de", "it", "zh-CN")
        }
        # fr/en share "Sources"; the other four are distinct translations.
        assert len(labels) == 5
        assert ProactiveMessages.sources_label("zh-CN") == "来源"

    def test_sources_label_unknown_language_falls_back(self) -> None:
        assert ProactiveMessages.sources_label("xx") == "Sources"


ROUTINES_URL = "https://lia.example/dashboard/settings?section=scheduled-actions"


@pytest.mark.unit
class TestRoutineNoticeBodies:
    """What a routine tells its owner when it did NOT run as planned."""

    @pytest.mark.parametrize("kind", sorted(ProactiveMessages._ROUTINE_NOTICE_BODIES))
    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_a_notice_names_the_routine_and_links_to_its_screen(
        self, kind: str, language: str
    ) -> None:
        body = ProactiveMessages.routine_notice_body(
            kind, "Morning briefing", language, routines_url=ROUTINES_URL, max_failures=5
        )

        assert "Morning briefing" in body
        assert f"]({ROUTINES_URL})" in body
        # Every placeholder the template names was produced.
        assert "{" not in body and "}" not in body

    @pytest.mark.parametrize("kind", ["failed", "disabled"])
    def test_a_failure_notice_states_the_enforced_threshold(self, kind: str) -> None:
        body = ProactiveMessages.routine_notice_body(
            kind, "Morning briefing", "en", routines_url=ROUTINES_URL, max_failures=7
        )

        assert "7" in body

    @pytest.mark.parametrize("kind", sorted(ProactiveMessages._ROUTINE_NOTICE_BODIES))
    def test_chinese_is_not_served_the_english_sentence(self, kind: str) -> None:
        zh, en = (
            ProactiveMessages.routine_notice_body(
                kind, "T", language, routines_url=ROUTINES_URL, max_failures=5
            )
            for language in ("zh-CN", "en")
        )

        assert zh != en

    def test_a_title_holding_braces_is_quoted_as_written(self) -> None:
        body = ProactiveMessages.routine_notice_body(
            "failed", "Report {week}", "en", routines_url=ROUTINES_URL, max_failures=5
        )

        assert "Report {week}" in body

    def test_an_unknown_kind_says_nothing_rather_than_a_placeholder(self) -> None:
        assert (
            ProactiveMessages.routine_notice_body(
                "nope", "T", "en", routines_url=ROUTINES_URL, max_failures=5
            )
            == ""
        )
