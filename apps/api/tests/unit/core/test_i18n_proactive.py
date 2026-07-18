"""Tests for ProactiveMessages i18n (zh-CN regression, ADR-131)."""

import pytest

from src.core.i18n_proactive import ProactiveMessages


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

    def test_zh_cn_regression_no_english_fallback(self) -> None:
        """User.language is backend-canonical zh-CN; the old table was keyed 'zh'."""
        for task_type in ("interest", "birthday", "event", "summary", "heartbeat"):
            title = ProactiveMessages.notification_title(task_type, "zh-CN")
            assert title != ProactiveMessages.notification_title(task_type, "en")

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
