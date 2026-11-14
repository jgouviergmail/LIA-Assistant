"""PDF renderer: HTML -> Story -> paged PDF; text extraction is the oracle (ADR-226)."""

import io
import unicodedata

import pymupdf
import pytest

from src.domains.document_generation import typography
from src.domains.document_generation.renderers import RENDERERS, render_document
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    TableSheet,
)


def _content() -> SectionedContent:
    return SectionedContent(
        filename_stem="alsace",
        title="Rapport Alsace",
        blocks=[
            SectionBlock(kind="heading", level=2, text="Villes"),
            SectionBlock(kind="paragraph", text="Texte avec accents éàü & <balise>."),
            SectionBlock(kind="bullets", items=["Strasbourg", "Colmar"]),
            SectionBlock(
                kind="table",
                table=TableSheet(name="V", headers=["ville"], rows=[["Mulhouse"]]),
            ),
        ],
    )


@pytest.mark.unit
class TestPdfRenderer:
    """Round-trip via PyMuPDF extraction — the RAG PDF reader is the oracle."""

    def test_round_trip_text(self) -> None:
        data = render_document(DocumentType.PDF, _content())
        document = pymupdf.open(stream=data, filetype="pdf")
        text = "".join(page.get_text() for page in document)
        document.close()
        for fragment in (
            "Rapport Alsace",
            "Villes",
            "éàü & <balise>",  # html.escape round-trips literally in extraction
            "Strasbourg",
            "Colmar",
            "Mulhouse",
        ):
            assert fragment in text

    def test_long_content_paginates(self) -> None:
        blocks = [
            SectionBlock(kind="paragraph", text=f"Paragraphe {i} — " + "texte " * 60)
            for i in range(60)
        ]
        content = SectionedContent(filename_stem="long", title="Long", blocks=blocks)
        data = render_document(DocumentType.PDF, content)
        document = pymupdf.open(stream=data, filetype="pdf")
        assert document.page_count > 1  # the Story loop actually paginates
        document.close()

    def test_requires_sectioned_content(self) -> None:
        from src.domains.document_generation.schemas import TabularContent

        tabular = TabularContent(
            filename_stem="x",
            title="T",
            sheets=[TableSheet(name="S", headers=["a"], rows=[["1"]])],
        )
        with pytest.raises(ValueError, match="SectionedContent"):
            render_document(DocumentType.PDF, tabular)


@pytest.mark.unit
class TestRendererRegistryCompleteness:
    """ADR-085: the registry covers every DocumentType, or the module refuses to import."""

    def test_registry_is_complete(self) -> None:
        assert set(RENDERERS) == set(DocumentType)


def _craft_document(structure: str = "auto") -> bytes:
    """A long document: contents, numbering, a table crossing pages, CJK."""
    from src.domains.document_generation.context import RenderContext

    blocks: list[SectionBlock] = []
    for part in range(1, 7):
        blocks.append(SectionBlock(kind="heading", level=1, text=f"Partie {part}"))
        blocks.append(SectionBlock(kind="paragraph", text="Lorem ipsum dolor sit amet. " * 60))
        blocks.append(SectionBlock(kind="heading", level=2, text=f"Détail {part}"))
        blocks.append(SectionBlock(kind="numbered", items=["une étape", "deux étapes"]))
    blocks.append(SectionBlock(kind="quote", text="Une citation mise en exergue."))
    blocks.append(SectionBlock(kind="callout", text="Point d'attention — " + "mots " * 200))
    rows = [[f"Ville {i}", str(100000 + i * 1234), f"{(i % 7) - 3:.1f}"] for i in range(80)]
    blocks.append(
        SectionBlock(
            kind="table",
            caption="Chiffres clés",
            table=TableSheet(
                name="t", headers=["Ville", "Population", "Croissance (%)"], rows=rows
            ),
        )
    )
    blocks.append(SectionBlock(kind="heading", level=2, text="中文测试"))
    blocks.append(SectionBlock(kind="paragraph", text="这是一个中文段落。"))
    content = SectionedContent(filename_stem="r", title="Rapport", subtitle="Comité", blocks=blocks)
    context = RenderContext(language="fr", structure=structure)  # type: ignore[arg-type]
    return render_document(DocumentType.PDF, content, context)


#: Below this height a rectangle is a rule, not a background.
_MIN_FILL_PT = 4.0
#: At or below this width it is a border (the callout's left rule is 2 pt).
_BORDER_WIDTH_PT = 3.0
#: A background envelops its LINE, so the vertical tolerance is a line box —
#: measured, not guessed: at one line box the shipped recipe leaves 0 empty
#: fills and the dangerous one 42, while a flat 4 pt reports 27 false ones.
_FILL_TOLERANCE_X_PT = 2.0
_FILL_TOLERANCE_Y_PT = typography.PDF_BODY_PT * typography.PDF_LINE_HEIGHT


@pytest.mark.unit
class TestPdfCraft:
    """What a reader gets: a running head, exact page numbers, bookmarks."""

    def test_header_and_footer_on_every_page_and_metadata(self) -> None:
        """Every page but the cover, which carries neither (a long document opens on one)."""
        document = pymupdf.open(stream=_craft_document(), filetype="pdf")
        total = document.page_count
        assert total >= 4
        for number, page in enumerate(document, start=1):
            text = page.get_text()
            assert "Rapport" in text
            assert (f"Page {number} / {total}" in text) is (number > 1)
        assert document.metadata["title"] == "Rapport"
        assert document.metadata["subject"] == "Comité"
        document.close()

    def test_the_contents_page_numbers_are_the_real_ones(self) -> None:
        """We paginate this document ourselves, so its numbers are exact."""
        document = pymupdf.open(stream=_craft_document(), filetype="pdf")
        assert "Sommaire" in document[1].get_text()  # after the cover
        outline = document.get_toc()
        assert [entry[1] for entry in outline][:2] == ["1 Partie 1", "1.1 Détail 1"]
        for _level, title, page in outline:
            assert title in document[page - 1].get_text(), (title, page)
        document.close()

    def test_the_contents_entries_link_to_their_pages(self) -> None:
        document = pymupdf.open(stream=_craft_document(), filetype="pdf")
        links = [link for link in document[1].get_links() if link["kind"] == pymupdf.LINK_GOTO]
        assert links
        document.close()

    def test_a_plain_structure_has_no_contents_and_no_numbers(self) -> None:
        document = pymupdf.open(stream=_craft_document(structure="plain"), filetype="pdf")
        assert "Sommaire" not in document[0].get_text()
        assert "1 Partie 1" not in document[0].get_text()
        assert "Partie 1" in document[0].get_text()
        document.close()

    def test_no_phantom_fill_on_a_continuation_page(self) -> None:
        """Every painted background covers actual text.

        MuPDF repaints a header rectangle at the top of every continuation page
        when a ``th`` carries a background under ``border-collapse`` — measured
        2026-09-08, and falsified: the shipped recipe leaves 0 such rectangle
        where the dangerous one leaves 44. Thin rectangles are borders, not
        backgrounds, and a cell's fill overshoots its glyphs by its padding,
        hence the 4 pt tolerance.
        """
        document = pymupdf.open(stream=_craft_document(), filetype="pdf")
        for page in list(document)[1:]:
            for drawing in page.get_drawings():
                fill = drawing.get("fill")
                rect = drawing["rect"]
                if fill is None or min(fill) > 0.99:
                    continue
                if rect.height < _MIN_FILL_PT or rect.width <= _BORDER_WIDTH_PT:
                    continue
                clip = pymupdf.Rect(
                    rect.x0 - _FILL_TOLERANCE_X_PT,
                    rect.y0 - _FILL_TOLERANCE_Y_PT,
                    rect.x1 + _FILL_TOLERANCE_X_PT,
                    rect.y1 + _FILL_TOLERANCE_Y_PT,
                )
                assert page.get_text("text", clip=clip).strip(), (page.number, rect, fill)
        document.close()

    def test_cjk_and_every_block_kind_render(self) -> None:
        # MuPDF renders typographic ligatures, so "Chiffres" comes back as
        # "Chiﬀres": every text oracle over a PDF normalises first.
        text = unicodedata.normalize(
            "NFKC",
            "".join(
                page.get_text() for page in pymupdf.open(stream=_craft_document(), filetype="pdf")
            ),
        )
        assert "中文测试" in text and "这是一个中文段落" in text
        assert "Une citation mise en exergue." in text
        assert "Point d'attention" in text
        assert "Tableau 1 — Chiffres clés" in text

    def test_the_page_size_follows_the_context(self) -> None:
        from src.domains.document_generation.context import RenderContext

        content = SectionedContent(
            filename_stem="x", title="T", blocks=[SectionBlock(kind="paragraph", text="p")]
        )
        letter = pymupdf.open(
            stream=render_document(
                DocumentType.PDF, content, RenderContext(language="en", page_size="letter")
            ),
            filetype="pdf",
        )
        assert round(letter[0].rect.width) == 612
        letter.close()


@pytest.mark.unit
class TestWideTablesStayOnThePage:
    """MuPDF honours neither ``width: 100%`` nor ``table-layout: fixed`` once a
    table has many columns: it sizes them from their content and runs off the
    sheet. Measured 2026-09-08 — 12 columns reach 714 pt on a 595 pt page.

    The oracle reads the table's RULES, not its text: the text alone stops at
    the last glyph and hides the overflow.
    """

    @staticmethod
    def _table_document(columns: int) -> bytes:
        from src.domains.document_generation.context import RenderContext

        content = SectionedContent(
            filename_stem="t",
            title="Tableau",
            blocks=[
                SectionBlock(
                    kind="table",
                    table=TableSheet(
                        name="t",
                        headers=[
                            f"Colonne numéro {c} avec un intitulé long" for c in range(columns)
                        ],
                        rows=[[f"valeur {r}.{c}" for c in range(columns)] for r in range(6)],
                    ),
                )
            ],
        )
        return render_document(DocumentType.PDF, content, RenderContext(language="fr"))

    @pytest.mark.parametrize("columns", [3, 6, 8, 10, 12, 14, 16])
    def test_no_table_rule_crosses_the_right_margin(self, columns: int) -> None:
        from src.domains.document_generation import typography

        document = pymupdf.open(stream=self._table_document(columns), filetype="pdf")
        _left, _top, right_margin, _bottom = typography.PDF_MARGIN_PT
        for page in document:
            edge = page.rect.width - right_margin
            widest = max(
                (drawing["rect"].x1 for drawing in page.get_drawings()),
                default=0.0,
            )
            assert widest <= edge + 1, f"{columns} columns: rules reach {widest:.0f} > {edge:.0f}"
        document.close()

    def test_the_ladder_only_shrinks_what_must_shrink(self) -> None:
        """The shrink is a remedy, not a habit: few columns keep the base size."""
        from src.domains.document_generation import typography

        assert typography.pdf_table_class(3) == ""
        assert typography.pdf_table_class(8) == ""
        assert typography.pdf_table_class(10) == "wide"
        assert typography.pdf_table_class(12) == "xwide"
        assert typography.pdf_table_class(16) == "xxwide"

    def test_the_stated_limit_is_where_the_measurement_put_it(self) -> None:
        """Beyond it nothing fits — 20 columns overflow even at 5 pt — and the
        constant says so instead of the renderer pretending otherwise."""
        from src.domains.document_generation import typography

        assert typography.PDF_TABLE_MAX_FITTING_COLUMNS == 16


@pytest.mark.unit
class TestTheStampsAreReadableInEveryLanguage:
    """Helvetica has no ideograph: the running head of a Chinese report was
    stamped as "······" and its footer as "· 1 ··· 1 ·", on every page, while
    the BODY was fine — the Story embeds its own CJK fallback. Measured
    2026-09-08; no test saw it, because a PDF with a garbage header still
    opens."""

    TITLE = "季度业绩报告"

    def _stamped(self, language: str, title: str) -> tuple[str, str]:
        content = SectionedContent(
            filename_stem="x",
            title=title,
            blocks=[SectionBlock(kind="paragraph", text="corps")],
        )
        from src.domains.document_generation.context import RenderContext

        data = render_document(DocumentType.PDF, content, RenderContext(language=language))
        with pymupdf.open(stream=data, filetype="pdf") as document:
            page = document[0]
            header = page.get_textbox(pymupdf.Rect(0, 0, page.rect.width, 40))
            footer = page.get_textbox(
                pymupdf.Rect(0, page.rect.height - 40, page.rect.width, page.rect.height)
            )
        return header.strip(), footer.strip()

    def test_a_chinese_running_head_carries_its_ideographs(self) -> None:
        header, footer = self._stamped("zh-CN", self.TITLE)
        assert self.TITLE in header
        assert "·" not in header
        assert "1" in footer and "·" not in footer

    def test_a_latin_running_head_is_unchanged(self) -> None:
        header, footer = self._stamped("fr", "Rapport trimestriel")
        assert "Rapport trimestriel" in header
        assert "Page 1 / 1" in footer


@pytest.mark.unit
class TestTheStampsStandUpright:
    """The running head and the footer were drawn UPSIDE DOWN on every page of every
    PDF (found 2026-11-13 by looking at a rendered page): the Story's page content
    flips the y axis with a ``cm`` it never closes, and the stamps were appended
    under it — their position compensated, their glyphs mirrored. Text extraction
    reads them in order and in place, so no test saw it. The oracle here is the
    glyph's own box: an upright glyph stands mostly ABOVE its baseline."""

    @staticmethod
    def _stamp_glyphs(language: str, title: str) -> list[tuple[float, float, float]]:
        from src.domains.document_generation.context import RenderContext

        content = SectionedContent(
            filename_stem="x", title=title, blocks=[SectionBlock(kind="paragraph", text="corps")]
        )
        data = render_document(DocumentType.PDF, content, RenderContext(language=language))
        glyphs: list[tuple[float, float, float]] = []
        with pymupdf.open(stream=data, filetype="pdf") as document:
            page = document[0]
            for trace in page.get_texttrace():
                if trace["size"] != typography.PDF_STAMP_PT:
                    continue
                for _unicode, _glyph, origin, bbox in trace["chars"]:
                    if bbox[3] - bbox[1] > 0:
                        glyphs.append((origin[1], bbox[1], bbox[3]))
        return glyphs

    @pytest.mark.parametrize(("language", "title"), [("fr", "Rapport"), ("zh-CN", "季度报告")])
    def test_every_stamped_glyph_stands_above_its_baseline(self, language: str, title: str) -> None:
        glyphs = self._stamp_glyphs(language, title)
        assert glyphs, "the stamps were not found"
        for baseline, top, bottom in glyphs:
            assert baseline - top > bottom - baseline, (baseline, top, bottom)


@pytest.mark.unit
class TestALayoutThatNeverEndsIsRefused:
    """PyMuPDF's Story can loop forever: a floated picture straddling a page end is
    never placed, and ``place()`` answers ``more`` on every page in a three-page
    cycle (measured 2026-11-13: 778, 155, 68 pt filled, again and again). No signal
    tells such a cycle from a long table, so the loop is bounded by a page count no
    document reaches — a worker thread must never spin on a render."""

    @staticmethod
    def _looping_html() -> tuple[str, object]:
        from PIL import Image

        image = Image.new("RGB", (1536, 1024), (30, 80, 140))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG")
        archive = pymupdf.Archive()
        archive.add(buffer.getvalue(), "cover.jpg")
        chart = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">'
            '<rect width="640" height="360" fill="#1F5AA6"/></svg>'
        )
        archive.add(chart.encode(), "chart.svg")
        html = (
            "<h1>Quarterly review</h1>"
            '<table style="width:100%"><tr><td>2.5</td><td>+18</td><td>94</td></tr></table>'
            "<p>" + "Lorem ipsum dolor sit amet. " * 12 + "</p>"
            '<img src="chart.svg" style="width: 100%"/><p>caption</p>'
            '<img src="cover.jpg" style="width: 40%; float: right"/>'
            "<p>" + "Text " * 60 + "</p>"
            '<h2 style="page-break-before: always">Next</h2><p>after</p>'
        )
        return html, archive

    def test_a_cycling_story_raises_instead_of_spinning(self, monkeypatch) -> None:
        from src.domains.document_generation.renderers import pdf_layout

        html, archive = self._looping_html()
        monkeypatch.setattr(typography, "PDF_MAX_PAGES", 12)
        with pytest.raises(pdf_layout.DocumentLayoutError):
            pdf_layout.lay_out(html, "", "a4", archive=archive)

    def test_the_bound_sits_far_above_the_longest_document_a_slot_can_write(self) -> None:
        """100 000 output tokens of prose is ~55 000 words, ~120 A4 pages; a table
        of that budget, ~115. The bound leaves twice that and still stops a cycle
        before it holds hundreds of megabytes on the production board."""
        assert 250 <= typography.PDF_MAX_PAGES <= 400
