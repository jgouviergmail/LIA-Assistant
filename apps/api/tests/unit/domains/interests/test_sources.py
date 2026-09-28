"""Tests for notification source hyperlinks (ADR-131)."""

import pytest

from src.core.i18n_drafts import label_separator
from src.core.i18n_proactive import ProactiveMessages
from src.domains.interests.sources import build_sources_block
from src.infrastructure.proactive.notification import markdown_links_to_plain


@pytest.mark.unit
class TestBuildSourcesBlock:
    def test_builds_markdown_links_with_domain_labels(self) -> None:
        block = build_sources_block(
            ["https://www.lemonde.fr/article-123", "https://arxiv.org/abs/2501.1"],
            language="fr",
            max_links=3,
        )
        assert "[lemonde.fr](https://www.lemonde.fr/article-123)" in block
        assert "[arxiv.org](https://arxiv.org/abs/2501.1)" in block
        assert block.startswith("\n\n")
        assert "Sources" in block

    def test_caps_and_dedupes(self) -> None:
        urls = [f"https://site{n}.com/x" for n in range(5)] + ["https://site0.com/x"]
        block = build_sources_block(urls, language="en", max_links=2)
        assert block.count("](") == 2

    def test_invalid_urls_skipped_and_empty_cases(self) -> None:
        assert build_sources_block([], "fr", 3) == ""
        assert build_sources_block(["not-a-url", "ftp://x/y"], "fr", 3) == ""
        assert build_sources_block(["https://ok.com/a"], "fr", 0) == ""

    def test_zh_cn_label(self) -> None:
        block = build_sources_block(["https://ok.com/a"], language="zh-CN", max_links=3)
        assert "来源" in block

    @pytest.mark.parametrize("language", ["fr", "en", "zh-CN"])
    def test_the_label_joins_the_links_with_the_reader_s_punctuation(self, language: str) -> None:
        """A French no-break space, an English colon, a full-width Chinese one."""
        block = build_sources_block(["https://ok.com/a"], language=language, max_links=3)
        label = ProactiveMessages.sources_label(language)

        assert block == f"\n\n{label}{label_separator(language)}[ok.com](https://ok.com/a)"


@pytest.mark.unit
class TestMarkdownLinksToPlain:
    def test_converts_links_for_push_channels(self) -> None:
        text = (
            "Great read.\n\nSources : [lemonde.fr](https://lemonde.fr/a)"
            " · [arxiv.org](https://arxiv.org/b)"
        )
        plain = markdown_links_to_plain(text)
        assert "[" not in plain
        assert "](" not in plain
        assert "lemonde.fr (https://lemonde.fr/a)" in plain
        assert "arxiv.org (https://arxiv.org/b)" in plain

    def test_plain_text_untouched(self) -> None:
        assert markdown_links_to_plain("no links here") == "no links here"
