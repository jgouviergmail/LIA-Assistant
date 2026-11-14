"""md and txt: key figures, sources, the callout's label — and no picture (ADR-274)."""

import pytest

from src.core.document_preferences import DocumentPreferences
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    DocumentType,
    Illustration,
    KeyFigure,
    SectionBlock,
    SectionedContent,
    Source,
)

pytestmark = [pytest.mark.unit]


def _report(*blocks: SectionBlock, **fields: object) -> SectionedContent:
    return SectionedContent(filename_stem="r", title="Report", blocks=list(blocks), **fields)  # type: ignore[arg-type]


def _render(doc_type: DocumentType, content: SectionedContent, language: str = "en") -> str:
    # Pictures allowed on purpose: a text file must write nothing of one even then.
    context = RenderContext(language=language, preferences=DocumentPreferences(images_allowed=True))
    return render_document(doc_type, content, context).decode("utf-8")


_FIGURES = SectionBlock(
    kind="figures", figures=[KeyFigure(value="42%", label="of the market"), KeyFigure(value="3")]
)
_SOURCES = [
    Source(title="Annual [2026] report", url="https://example.org/report_(final)"),
    Source(title="A book"),
    Source(title="https://example.org/data", url="https://example.org/data"),
]


class TestKeyFigures:
    def test_markdown_lists_each_figure_value_first(self) -> None:
        lines = _render(DocumentType.MD, _report(_FIGURES)).splitlines()
        assert "- **42%** — of the market" in lines
        assert "- **3**" in lines

    def test_plain_text_lists_them_without_markup(self) -> None:
        lines = _render(DocumentType.TXT, _report(_FIGURES)).splitlines()
        assert "  * 42% — of the market" in lines
        assert "  * 3" in lines

    def test_the_word_order_is_the_reader_s(self) -> None:
        assert "- **42%**：of the market" in _render(DocumentType.MD, _report(_FIGURES), "zh-CN")


class TestPictures:
    def test_a_picture_writes_nothing_and_leaves_no_blank_behind(self) -> None:
        picture = SectionBlock(
            kind="illustration", illustration=Illustration(subject="A harbour"), caption="Port"
        )
        content = _report(
            SectionBlock(kind="paragraph", text="Before."),
            picture,
            SectionBlock(kind="paragraph", text="After."),
            illustration=Illustration(subject="A cover"),
        )
        for doc_type in (DocumentType.MD, DocumentType.TXT):
            text = _render(doc_type, content)
            assert "Port" not in text and "Figure" not in text
            assert "Before.\n\nAfter." in text


class TestSources:
    def test_markdown_numbers_the_sources_each_a_link(self) -> None:
        text = _render(
            DocumentType.MD,
            _report(SectionBlock(kind="paragraph", text="See [1]."), sources=_SOURCES),
        )
        assert text.endswith(
            "## Sources\n\n"
            "1. [Annual \\[2026\\] report](<https://example.org/report_(final)>)\n"
            "2. A book\n"
            "3. <https://example.org/data>\n"
        )

    def test_plain_text_spells_each_address_out(self) -> None:
        text = _render(
            DocumentType.TXT,
            _report(SectionBlock(kind="paragraph", text="See [1]."), sources=_SOURCES),
        )
        assert text.endswith(
            "Sources\n-------\n"
            "[1] Annual [2026] report — https://example.org/report_(final)\n"
            "[2] A book\n"
            "[3] https://example.org/data\n"
        )

    def test_the_heading_and_the_entry_speak_the_reader_s_language(self) -> None:
        text = _render(
            DocumentType.TXT,
            _report(SectionBlock(kind="paragraph", text="x"), sources=_SOURCES),
            "de",
        )
        assert "Quellen\n-------" in text

    def test_no_source_no_heading(self) -> None:
        assert "Sources" not in _render(
            DocumentType.MD, _report(SectionBlock(kind="paragraph", text="x"))
        )


class TestTheCallout:
    @pytest.mark.parametrize(
        ("language", "label"),
        [("en", "Note."), ("fr", "À noter :"), ("de", "Hinweis:"), ("zh-CN", "提示：")],
    )
    def test_the_callout_is_labelled_in_the_reader_s_language(
        self, language: str, label: str
    ) -> None:
        text = _render(
            DocumentType.MD, _report(SectionBlock(kind="callout", text="Mind the gap.")), language
        )
        assert f"> **{label}** Mind the gap." in text.splitlines()
