"""Text-family renderers: csv (BOM + neutralization), md, txt (ADR-226)."""

import csv
import io

import pytest

from src.domains.document_generation.renderers import (
    DOCUMENT_EXTENSIONS,
    DOCUMENT_MIME_TYPES,
    render_document,
)
from src.domains.document_generation.schemas import (
    DocumentType,
    SectionBlock,
    SectionedContent,
    TableSheet,
    TabularContent,
)


def _tabular() -> TabularContent:
    return TabularContent(
        filename_stem="llm-models",
        title="LLM models",
        sheets=[
            TableSheet(
                name="Models",
                headers=["model", "provider"],
                rows=[["Fable 5", "Anthropic"], ["=HYPERLINK(1)", "évil"]],
            )
        ],
    )


def _sectioned() -> SectionedContent:
    return SectionedContent(
        filename_stem="alsace",
        title="L'Alsace",
        blocks=[
            SectionBlock(kind="heading", level=2, text="Géographie"),
            SectionBlock(kind="paragraph", text="Plaine du Rhin."),
            SectionBlock(kind="bullets", items=["Strasbourg", "Colmar"]),
            SectionBlock(
                kind="table",
                table=TableSheet(name="Villes", headers=["ville"], rows=[["Mulhouse"]]),
            ),
        ],
    )


@pytest.mark.unit
class TestCsvRenderer:
    """csv: Excel-compatible BOM, quoting via the stdlib writer, neutralization."""

    def test_has_bom_and_neutralized_formula(self) -> None:
        data = render_document(DocumentType.CSV, _tabular())
        assert data[:3] == b"\xef\xbb\xbf"  # utf-8-sig (probe 2026-08-17)
        text = data.decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(text)))
        assert reader[0] == ["model", "provider"]
        assert reader[1] == ["Fable 5", "Anthropic"]
        assert reader[2][0] == "'=HYPERLINK(1)"  # neutralized

    def test_csv_requires_tabular_content(self) -> None:
        with pytest.raises(ValueError, match="TabularContent"):
            render_document(DocumentType.CSV, _sectioned())


@pytest.mark.unit
class TestMarkdownRenderer:
    """md: every block kind renders, title owns '#'."""

    def test_renders_every_block_kind(self) -> None:
        text = render_document(DocumentType.MD, _sectioned()).decode("utf-8")
        assert "# L'Alsace" in text
        assert "## Géographie" in text
        assert "- Strasbourg" in text
        assert "| ville |" in text
        assert "| Mulhouse |" in text

    def test_level_one_heading_is_shifted_below_title(self) -> None:
        content = SectionedContent(
            filename_stem="x",
            title="T",
            blocks=[SectionBlock(kind="heading", level=1, text="H")],
        )
        text = render_document(DocumentType.MD, content).decode("utf-8")
        assert "## H" in text  # the title owns '#'


@pytest.mark.unit
class TestTxtRenderer:
    """txt: plain and complete, no markdown syntax leaks."""

    def test_is_plain_and_complete(self) -> None:
        text = render_document(DocumentType.TXT, _sectioned()).decode("utf-8")
        for fragment in ("L'Alsace", "Géographie", "Plaine du Rhin.", "Strasbourg", "Mulhouse"):
            assert fragment in text
        assert "|" not in text.splitlines()[0]
        assert "#" not in text


@pytest.mark.unit
class TestFormatMaps:
    """Metadata maps stay total over DocumentType."""

    def test_mime_and_extension_maps_are_total(self) -> None:
        assert set(DOCUMENT_MIME_TYPES) == set(DocumentType)
        assert set(DOCUMENT_EXTENSIONS) == set(DocumentType)


@pytest.mark.unit
class TestMarkdownStructureSurvivesTheData:
    """A pipe is markdown's column separator: a cell carrying one splits the
    row, and every later cell lands under the wrong header."""

    def test_a_pipe_in_a_cell_does_not_add_a_column(self) -> None:
        content = SectionedContent(
            filename_stem="x",
            title="T",
            blocks=[
                SectionBlock(
                    kind="table",
                    table=TableSheet(
                        name="t", headers=["a|b", "c"], rows=[["1|2", "3"], ["4", "5"]]
                    ),
                )
            ],
        )
        lines = render_document(DocumentType.MD, content).decode("utf-8").splitlines()
        rows = [line for line in lines if line.startswith("|")]
        # Header, rule and two data rows, each with exactly two cells.
        assert len(rows) == 4
        for row in rows:
            assert row.count("|") - row.count(r"\|") == 3

    def test_a_newline_in_a_cell_stays_on_one_row(self) -> None:
        content = SectionedContent(
            filename_stem="x",
            title="T",
            blocks=[
                SectionBlock(
                    kind="table",
                    table=TableSheet(name="t", headers=["a", "b"], rows=[["x\ny", "z"]]),
                )
            ],
        )
        lines = render_document(DocumentType.MD, content).decode("utf-8").splitlines()
        assert len([line for line in lines if line.startswith("|")]) == 3


@pytest.mark.unit
class TestAPlainTextRuleMatchesWhatItUnderlines:
    """Four ideographs are eight columns wide: a rule of four dashes under them
    reads as a typo in the one format that has no typography to fall back on."""

    ZH = "季度报告"

    def test_the_title_rule_follows_the_display_width(self) -> None:
        content = SectionedContent(
            filename_stem="x",
            title=self.ZH,
            blocks=[SectionBlock(kind="paragraph", text="corps")],
        )
        lines = render_document(DocumentType.TXT, content).decode("utf-8").splitlines()
        assert lines[0] == self.ZH
        assert len(lines[1]) == 2 * len(self.ZH)

    def test_a_latin_rule_is_unchanged(self) -> None:
        content = SectionedContent(
            filename_stem="x", title="Titre", blocks=[SectionBlock(kind="paragraph", text="c")]
        )
        lines = render_document(DocumentType.TXT, content).decode("utf-8").splitlines()
        assert lines[1] == "=" * len("Titre")
