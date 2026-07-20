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

    def test_unknown_language_falls_back_to_english(self) -> None:
        assert ProactiveMessages.notification_title("interest", "xx") == "For you"

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
