"""pdf: key figures, pictures, a cover, sources and links (ADR-274).

The oracle is PyMuPDF reading the result back: the words where they stand, the
fills a band paints, the images a page embeds and in what encoding, the links a
reader clicks.
"""

from dataclasses import replace

import pymupdf
import pytest

from src.core.config import settings
from src.core.document_preferences import DocumentPreferences
from src.domains.document_generation import typography
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.renderers.page_pictures import PAGE
from src.domains.document_generation.schemas import (
    DocumentType,
    Illustration,
    KeyFigure,
    SectionBlock,
    SectionedContent,
    Source,
    TableSheet,
)
from tests.helpers.document_pictures import synthetic_pictures

pytestmark = [pytest.mark.unit]

_COVER = Illustration(subject="A harbour at dawn", alt="Boats at rest in a harbour.")
_LONG_ADDRESS = (
    "https://www.example.org/reports/2026/annual-review/appendix-b/tables/"
    "regional-breakdown-of-revenue-and-costs?lang=en&format=full"
)


@pytest.fixture(autouse=True)
def _threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the long-document threshold: the test must not depend on a tunable."""
    monkeypatch.setattr(settings, "document_generation_toc_min_headings", 4)


def _render(content: SectionedContent, *, drawn: bool = True) -> pymupdf.Document:
    context = RenderContext(language="en", preferences=DocumentPreferences(images_allowed=drawn))
    if drawn:
        context = replace(context, pictures=synthetic_pictures(normalize_content(content, context)))
    data = render_document(DocumentType.PDF, content, context)
    return pymupdf.open(stream=data, filetype="pdf")


def _report(*blocks: SectionBlock, **fields: object) -> SectionedContent:
    return SectionedContent(filename_stem="r", title="Report", blocks=list(blocks), **fields)  # type: ignore[arg-type]


def _long(**fields: object) -> SectionedContent:
    parts = [
        block
        for part in range(1, 5)
        for block in (
            SectionBlock(kind="heading", level=1, text=f"Part {part}"),
            SectionBlock(kind="paragraph", text="Lorem ipsum dolor sit amet. " * 40),
        )
    ]
    return _report(*parts, **fields)


def _text(document: pymupdf.Document) -> str:
    return "".join(page.get_text() for page in document)


def _hex(color: tuple[float, float, float]) -> str:
    return "".join(f"{round(channel * 255):02X}" for channel in color)


def _jpegs(document: pymupdf.Document) -> list[tuple[int, int]]:
    """(page number, xref) of every JPEG the document embeds."""
    found: list[tuple[int, int]] = []
    for number, page in enumerate(document, start=1):
        for image in page.get_images(full=True):
            if document.extract_image(image[0])["ext"] == "jpeg":
                found.append((number, image[0]))
    return found


def _uri_links(document: pymupdf.Document) -> list[dict[str, object]]:
    return [
        link for page in document for link in page.get_links() if link["kind"] == pymupdf.LINK_URI
    ]


class TestTheBandOfKeyFigures:
    def test_the_figures_stand_in_shaded_tiles_of_one_width(self) -> None:
        figures = [KeyFigure(value=v, label=f"what {v} measures") for v in ("42%", "+18%", "$1.2M")]
        document = _render(_report(SectionBlock(kind="figures", figures=figures)))
        page = document[0]
        text = page.get_text()
        for figure in figures:
            assert figure.value in text and figure.label in text
        tiles = [
            drawing["rect"]
            for drawing in page.get_drawings()
            if drawing.get("fill") and _hex(drawing["fill"]) == typography.BAND
        ]
        assert len(tiles) == 3
        assert max(t.width for t in tiles) - min(t.width for t in tiles) < 0.5
        assert all(tiles[0].y0 == pytest.approx(t.y0) for t in tiles)

    def test_every_value_stands_on_one_line_inside_its_tile(self) -> None:
        # No value is part of another: each is found once, on one line or not at all.
        values = ("€1,234,567", "9", "12 days", "+18%")
        figures = [KeyFigure(value=value) for value in values]
        page = _render(_report(SectionBlock(kind="figures", figures=figures)))[0]
        tiles = [
            d["rect"]
            for d in page.get_drawings()
            if d.get("fill") and _hex(d["fill"]) == typography.BAND
        ]
        for value in values:
            (where,) = page.search_for(value)
            assert any(tile.contains(where) for tile in tiles), value


class TestPictures:
    def test_a_picture_is_embedded_as_its_jpeg_in_a_numbered_figure(self) -> None:
        chart = SectionBlock(
            kind="chart",
            caption="Revenue",
            table=TableSheet(
                name="r", headers=["Region", "Revenue"], rows=[["North", "10"], ["South", "12"]]
            ),
        )
        picture = SectionBlock(
            kind="illustration",
            illustration=Illustration(subject="A harbour", alt="Boats."),
            caption="The harbour",
        )
        document = _render(_report(chart, picture, illustration=_COVER))
        text = _text(document)
        assert "Figure 1 — Revenue" in text
        assert "Figure 2 — The harbour" in text
        assert len(_jpegs(document)) == 2  # the cover's and the block's, neither re-encoded

    def test_a_picture_keeps_its_whole_room_even_at_a_page_s_end(self) -> None:
        filler = [SectionBlock(kind="paragraph", text="Lorem ipsum dolor sit amet. " * 14)] * 5
        picture = SectionBlock(kind="illustration", illustration=Illustration(subject="A harbour"))
        document = _render(_report(*filler, picture))
        ((number, xref),) = _jpegs(document)
        (rect,) = document[number - 1].get_image_rects(xref)
        assert rect.height == pytest.approx(rect.width / PAGE.aspect, abs=0.5)
        assert rect.width == pytest.approx(PAGE.width_in * 72, abs=0.5)

    def test_a_picture_nobody_drew_leaves_no_trace(self) -> None:
        picture = SectionBlock(
            kind="illustration", illustration=Illustration(subject="A harbour"), caption="Port"
        )
        document = _render(_report(SectionBlock(kind="paragraph", text="x"), picture), drawn=False)
        assert not _jpegs(document)
        assert "Figure" not in _text(document)


class TestTheCover:
    def test_a_long_document_opens_on_an_unstamped_cover(self) -> None:
        document = _render(_long(illustration=_COVER, subtitle="For the board"))
        cover, contents = document[0].get_text(), document[1].get_text()
        assert "Report" in cover and "For the board" in cover
        assert "Page 1 of" not in cover
        assert _jpegs(document)[0][0] == 1
        assert "Contents" in contents and f"Page 2 of {document.page_count}" in contents

    def test_the_contents_numbers_still_point_at_their_pages(self) -> None:
        document = _render(_long())
        for _level, title, page in document.get_toc():
            assert title in document[page - 1].get_text(), (title, page)
        assert any(link["kind"] == pymupdf.LINK_GOTO for link in document[1].get_links())

    def test_a_short_document_is_stamped_from_its_first_page(self) -> None:
        document = _render(_report(SectionBlock(kind="paragraph", text="x"), illustration=_COVER))
        assert f"Page 1 of {document.page_count}" in document[0].get_text()


class TestSourcesAndLinks:
    def test_the_sources_close_the_document_each_a_link(self) -> None:
        sources = [
            Source(title="Annual report", url="https://example.org/report"),
            Source(title="A book"),
        ]
        document = _render(
            _report(SectionBlock(kind="paragraph", text="See [1]."), sources=sources)
        )
        last = document[-1].get_text()
        assert "Sources" in last
        assert "[1]" in last and "Annual report — https://example.org/report" in last
        assert "[2]" in last and "A book" in last
        assert [link["uri"] for link in _uri_links(document)] == ["https://example.org/report"]

    def test_an_address_in_the_text_opens_when_clicked(self) -> None:
        text = "See [the agency](https://example.org/a_b) for details."
        document = _render(_report(SectionBlock(kind="paragraph", text=text)))
        assert "the agency (https://example.org/a_b)" in _text(document)
        (link,) = _uri_links(document)
        assert link["uri"] == "https://example.org/a_b"
        (where,) = document[0].search_for("https://example.org/a_b")
        assert link["from"].intersects(where)

    def test_a_wrapped_address_is_one_link_per_line(self) -> None:
        sources = [Source(title=_LONG_ADDRESS, url=_LONG_ADDRESS)]
        document = _render(_report(SectionBlock(kind="paragraph", text="x"), sources=sources))
        links = _uri_links(document)
        assert len(links) == 2
        assert {link["uri"] for link in links} == {_LONG_ADDRESS}
        first, second = (link["from"] for link in links)
        assert second.y0 > first.y1 - 0.5  # the second line, below the first
