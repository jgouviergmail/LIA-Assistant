"""PDF renderer: HTML -> Story -> paged PDF; text extraction is the oracle (ADR-226)."""

import unicodedata

import fitz
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
        document = fitz.open(stream=data, filetype="pdf")
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
        document = fitz.open(stream=data, filetype="pdf")
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
        document = fitz.open(stream=_craft_document(), filetype="pdf")
        total = document.page_count
        assert total >= 4
        for number, page in enumerate(document, start=1):
            text = page.get_text()
            assert "Rapport" in text
            assert f"Page {number} / {total}" in text
        assert document.metadata["title"] == "Rapport"
        assert document.metadata["subject"] == "Comité"
        document.close()

    def test_the_contents_page_numbers_are_the_real_ones(self) -> None:
        """We paginate this document ourselves, so its numbers are exact."""
        document = fitz.open(stream=_craft_document(), filetype="pdf")
        assert "Sommaire" in document[0].get_text()
        outline = document.get_toc()
        assert [entry[1] for entry in outline][:2] == ["1 Partie 1", "1.1 Détail 1"]
        for _level, title, page in outline:
            assert title in document[page - 1].get_text(), (title, page)
        document.close()

    def test_the_contents_entries_link_to_their_pages(self) -> None:
        document = fitz.open(stream=_craft_document(), filetype="pdf")
        links = [link for link in document[0].get_links() if link["kind"] == fitz.LINK_GOTO]
        assert links
        document.close()

    def test_a_plain_structure_has_no_contents_and_no_numbers(self) -> None:
        document = fitz.open(stream=_craft_document(structure="plain"), filetype="pdf")
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
        document = fitz.open(stream=_craft_document(), filetype="pdf")
        for page in list(document)[1:]:
            for drawing in page.get_drawings():
                fill = drawing.get("fill")
                rect = drawing["rect"]
                if fill is None or min(fill) > 0.99:
                    continue
                if rect.height < _MIN_FILL_PT or rect.width <= _BORDER_WIDTH_PT:
                    continue
                clip = fitz.Rect(
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
                page.get_text() for page in fitz.open(stream=_craft_document(), filetype="pdf")
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
        letter = fitz.open(
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

        document = fitz.open(stream=self._table_document(columns), filetype="pdf")
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
        with fitz.open(stream=data, filetype="pdf") as document:
            page = document[0]
            header = page.get_textbox(fitz.Rect(0, 0, page.rect.width, 40))
            footer = page.get_textbox(
                fitz.Rect(0, page.rect.height - 40, page.rect.width, page.rect.height)
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
