"""RenderContext: for whom, where, and how much apparatus (ADR-274).

The content says what a document contains; the context says for whom (the
reader's language, their timezone) and where (the deployment's page size), and
whether the long-document apparatus may switch itself on. A caller that already
shapes its document — meeting minutes — pins ``structure="plain"``.
"""

from datetime import UTC, datetime

import pytest

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.document_generation.context import (
    RenderContext,
    build_render_context,
    default_render_context,
)

pytestmark = [pytest.mark.unit]


class TestTheContextIsBuiltFromThePersonAndTheDeployment:
    def test_language_is_normalised_and_the_page_comes_from_settings(self, monkeypatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "document_generation_page_size", "letter")
        context = build_render_context(
            language="zh",
            timezone="Asia/Shanghai",
            generated_at=datetime(2026, 9, 8, 23, 30, tzinfo=UTC),
        )
        assert context.language == "zh-CN"  # backend canon, never "zh"
        assert context.page_size == "letter"
        assert context.structure == "auto"

    def test_the_date_line_is_read_in_the_readers_own_timezone(self) -> None:
        """23:30 UTC is already the 9th in Shanghai: the server's date is not theirs."""
        context = build_render_context(
            language="en",
            timezone="Asia/Shanghai",
            generated_at=datetime(2026, 9, 8, 23, 30, tzinfo=UTC),
        )
        assert "9" in context.date_line and "2026" in context.date_line

    def test_a_missing_timezone_falls_back_to_the_central_default(self) -> None:
        context = build_render_context(
            language="fr", timezone="", generated_at=datetime(2026, 9, 8, tzinfo=UTC)
        )
        assert context.timezone == DEFAULT_USER_DISPLAY_TIMEZONE

    def test_a_caller_may_pin_a_plain_structure(self) -> None:
        context = build_render_context(
            language="fr",
            timezone="Europe/Paris",
            generated_at=datetime(2026, 9, 8, tzinfo=UTC),
            structure="plain",
        )
        assert context.structure == "plain"


class TestTheContextDegradesSafely:
    def test_no_generated_at_means_no_date_line(self) -> None:
        """Minutes carry their own dates: the renderer must not stamp another."""
        assert RenderContext(language="fr").date_line == ""

    def test_the_default_context_states_nothing_of_its_own(self) -> None:
        context = default_render_context()
        assert context.generated_at is None
        assert context.language
        assert context.page_size in ("a4", "letter")
        assert context.structure == "auto"

    def test_labels_go_through_the_document_label_table(self) -> None:
        assert RenderContext(language="de").label("documents.column_label", n=2) == "Spalte 2"
        assert RenderContext(language="zh-CN").label("documents.toc_heading") == "目录"

    def test_the_context_is_immutable(self) -> None:
        """A renderer must never rewrite the reader's facts mid-document."""
        context = RenderContext(language="fr")
        with pytest.raises((AttributeError, TypeError)):
            context.language = "en"  # type: ignore[misc]
