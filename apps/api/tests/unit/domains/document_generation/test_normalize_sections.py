"""A report's figures, pictures and sources in canonical form (ADR-274).

Repaired, never refused: a figure without its number goes, a page draws no
pictogram, a picture past the budget or without a subject goes, and a source
keeps its place — its position is its number in the text.
"""

import pytest

from src.core.config import settings
from src.core.document_preferences import DocumentIllustrations, DocumentPreferences
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.schemas import (
    Illustration,
    KeyFigure,
    SectionBlock,
    SectionedContent,
    Source,
)

pytestmark = [pytest.mark.unit]

_SCENE = Illustration(subject="  A harbour  at dawn ", alt=" Boats  at rest. ")


def _context(*, images: bool = True, never: bool = False) -> RenderContext:
    illustrations = DocumentIllustrations.NEVER if never else DocumentIllustrations.AUTO
    return RenderContext(
        language="en",
        preferences=DocumentPreferences(images_allowed=images, illustrations=illustrations),
    )


def _report(*blocks: SectionBlock, **fields: object) -> SectionedContent:
    return SectionedContent(
        filename_stem="r",
        title="Report",
        blocks=list(blocks) or [SectionBlock(kind="paragraph", text="Body.")],
        **fields,  # type: ignore[arg-type]
    )


def _normalize(content: SectionedContent, context: RenderContext | None = None) -> SectionedContent:
    result = normalize_content(content, context or _context())
    assert isinstance(result, SectionedContent)
    return result


def _picture(subject: str = "A chart room", caption: str = "") -> SectionBlock:
    return SectionBlock(
        kind="illustration", illustration=Illustration(subject=subject), caption=caption
    )


class TestKeyFigures:
    def test_figures_keep_their_number_and_lose_their_pictogram(self) -> None:
        block = SectionBlock(
            kind="figures",
            figures=[
                KeyFigure(value=" 42% ", label=" of  the market ", icon="target"),
                KeyFigure(value="  ", label="a label alone"),
            ],
        )
        (canonical,) = _normalize(_report(block)).blocks
        assert canonical.kind == "figures"
        assert canonical.figures == [KeyFigure(value="42%", label="of the market")]

    def test_figures_given_as_words_keep_their_words(self) -> None:
        block = SectionBlock(kind="figures", text="Revenue grew by 18% to $1.2M.")
        (canonical,) = _normalize(_report(block)).blocks
        assert (canonical.kind, canonical.text) == ("paragraph", "Revenue grew by 18% to $1.2M.")

    def test_figures_with_nothing_go(self) -> None:
        empty = SectionBlock(kind="figures", figures=[KeyFigure(value=" ")])
        assert [block.kind for block in _normalize(_report(empty)).blocks] == ["paragraph"]


class TestPictures:
    def test_a_picture_is_cleaned_and_keeps_its_caption(self) -> None:
        block = SectionBlock(kind="illustration", illustration=_SCENE, caption="  The port ")
        content = _normalize(_report(block))
        (canonical,) = content.blocks
        assert canonical.illustration == Illustration(
            subject="A harbour at dawn", alt="Boats at rest."
        )
        assert canonical.caption == "The port"

    def test_a_picture_without_a_subject_goes(self) -> None:
        block = SectionBlock(
            kind="illustration", illustration=Illustration(subject=" "), caption="c"
        )
        assert [b.kind for b in _normalize(_report(block, _picture())).blocks] == ["illustration"]

    def test_the_cover_comes_first_then_the_blocks_in_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "document_illustrations_max", 2)
        content = _normalize(
            _report(_picture("first"), _picture("second"), illustration=_SCENE, image_style=" ink ")
        )
        assert content.illustration is not None
        assert [b.illustration.subject for b in content.blocks if b.illustration] == ["first"]
        assert content.image_style == "ink"

    def test_no_budget_strips_every_picture_and_the_style(self) -> None:
        raw = _report(_picture(), illustration=_SCENE, image_style="ink")
        for context in (_context(images=False), _context(never=True)):
            content = _normalize(raw, context)
            assert content.illustration is None
            assert content.image_style == ""
            assert all(block.kind != "illustration" for block in content.blocks)

    def test_a_document_of_pictures_alone_still_shows_its_title(self) -> None:
        content = _normalize(_report(_picture()), _context(images=False))
        assert [(b.kind, b.text) for b in content.blocks] == [("paragraph", "Report")]


class TestSources:
    def test_every_source_keeps_its_place(self) -> None:
        sources = [
            Source(title=" Annual  report ", url=" https://example.org/report?y=2026 "),
            Source(title="An archive", url="ftp://example.org/file"),
            Source(title="", url="https://example.org/data"),
            Source(title="Somewhere", url="javascript:alert(1)"),
        ]
        content = _normalize(_report(sources=sources))
        assert content.sources == [
            Source(title="Annual report", url="https://example.org/report?y=2026"),
            Source(title="An archive", url=""),
            Source(title="https://example.org/data", url="https://example.org/data"),
            Source(title="Somewhere", url=""),
        ]

    @pytest.mark.parametrize(
        "address",
        [
            "example.org/page",
            "https://",
            "https://exa mple.org",
            "mailto:someone@example.org",
            "https://[::1",
            "data:text/html,hello",
        ],
    )
    def test_only_a_web_address_with_a_host_is_a_link(self, address: str) -> None:
        (source,) = _normalize(_report(sources=[Source(title="T", url=address)])).sources
        assert source.url == ""

    def test_an_empty_entry_in_the_middle_keeps_the_numbers_after_it(self) -> None:
        sources = [Source(title="A"), Source(title=" ", url=" "), Source(title="C")]
        content = _normalize(_report(sources=sources))
        assert [source.title for source in content.sources] == ["A", "", "C"]

    def test_empty_entries_at_the_end_go(self) -> None:
        sources = [Source(title="A"), Source(title=" "), Source(title="", url="nowhere")]
        assert [s.title for s in _normalize(_report(sources=sources)).sources] == ["A"]


class TestIdempotence:
    def test_normalizing_a_rich_report_twice_changes_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "document_illustrations_max", 2)
        raw = _report(
            SectionBlock(kind="figures", figures=[KeyFigure(value="42%", label="share", icon="x")]),
            _picture("first", " caption "),
            _picture("second"),
            SectionBlock(kind="paragraph", text="As shown in [1]."),
            illustration=_SCENE,
            image_style=" ink ",
            sources=[Source(title=" A ", url="https://example.org/a"), Source(title="B", url="x")],
        )
        once = _normalize(raw)
        assert _normalize(once) == once
