"""Chinese language-code normalization tests (audit wave 2, zh).

The system has two legitimate spellings for Chinese: ``zh`` (frontend
locales/URLs) and ``zh-CN`` (backend ``User.language``, ``SUPPORTED_LANGUAGES``,
i18n table keys). The single chokepoint is
``utils/i18n_location.normalize_language`` — every consumer must accept BOTH
spellings and reach the ``zh-CN``-keyed tables.

Criterion: a user whose language arrives as "zh" OR "zh-CN" receives Chinese
in labels (contacts) and in text summaries.
"""

import pytest

from src.domains.agents.formatters.text_summary import (
    DOMAIN_LABELS,
    generate_text_summary_for_items,
)
from src.domains.agents.tools.labels import (
    translate_field_type,
    translate_relation_type,
)
from src.domains.agents.utils.i18n_location import normalize_language


class TestNormalizeLanguageChokepoint:
    """normalize_language maps every Chinese variant to zh-CN."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("zh", "zh-CN"),
            ("zh-CN", "zh-CN"),
            ("zh_CN", "zh-CN"),
            ("zh-TW", "zh-CN"),
            ("ZH", "zh-CN"),
            ("fr", "fr"),
            ("fr-FR", "fr"),
            ("en_US", "en"),
        ],
    )
    def test_normalization(self, raw: str, expected: str):
        assert normalize_language(raw) == expected

    def test_unsupported_language_falls_back(self):
        # Fallback must be a supported language (settings-driven default)
        assert normalize_language("xx") in ("fr", "en", "es", "de", "it", "zh-CN")


class TestLabelsChineseReachable:
    """tools/labels.py: 'zh' and 'zh-CN' both reach the zh-CN tables."""

    @pytest.mark.parametrize("locale", ["zh", "zh-CN", "zh_CN"])
    def test_field_type_translated_to_chinese(self, locale: str):
        assert translate_field_type("home", locale) == "住宅"
        assert translate_field_type("work", locale) == "工作"

    @pytest.mark.parametrize("locale", ["zh", "zh-CN"])
    def test_relation_type_translated_to_chinese(self, locale: str):
        assert translate_relation_type("spouse", locale) == "配偶"


class TestTextSummaryChineseReachable:
    """formatters/text_summary.py: 'zh' and 'zh-CN' both reach Chinese labels."""

    def test_domain_labels_keyed_on_canonical_zh_cn(self):
        assert "zh-CN" in DOMAIN_LABELS, (
            "DOMAIN_LABELS must be keyed on the canonical backend code zh-CN "
            "(normalize_language output), not on the frontend spelling zh"
        )
        assert "zh" not in DOMAIN_LABELS, (
            "Remove the zh key — inputs are normalized to zh-CN via "
            "normalize_language (single chokepoint)"
        )

    @pytest.mark.parametrize("language", ["zh", "zh-CN"])
    def test_summary_uses_chinese_labels(self, language: str):
        summary = generate_text_summary_for_items(
            items=[{}],  # one item with no serializable payload
            domain="contacts",
            user_language=language,
        )
        # No summaries → "<count> <other-label>" with the Chinese 'other' label
        assert "项目" in summary, f"Expected Chinese label for language={language!r}"
