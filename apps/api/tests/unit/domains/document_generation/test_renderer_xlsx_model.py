"""A workbook that stays alive: formulas, totals, inputs, summaries (ADR-274 amendment).

Two readers are the oracles: openpyxl reading the FORMULAS (what Excel will
recalculate) and reading the CACHED values (what a reader that never
recalculates shows). The cached values are compared with arithmetic written in
the test, never with the module that produced them.
"""

from __future__ import annotations

import io

import openpyxl
import pytest

from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.renderers import render_document
from src.domains.document_generation.schemas import (
    ColumnSpec,
    DocumentType,
    GroupSummary,
    SheetInput,
    TableSheet,
    TabularContent,
    WorkbookFigure,
)

pytestmark = [pytest.mark.unit]

ROWS = [
    ["North", "1000", "400"],
    ["South*", "800", "0"],
    ["North", "500", "450"],
    ["south", "300", "100"],
]


def _content(*specs: ColumnSpec, summary=None, inputs=(), headers=None, rows=None):
    return TabularContent(
        filename_stem="sales",
        title="Sales",
        sheets=[
            TableSheet(
                name="Sales",
                headers=headers or ["Region", "Revenue", "Cost"],
                rows=rows or [list(row) for row in ROWS],
                columns=list(specs),
                summary=summary,
            )
        ],
        inputs=list(inputs),
    )


def _books(content: TabularContent, language: str = "en"):
    data = render_document(DocumentType.XLSX, content, RenderContext(language=language))
    return (
        openpyxl.load_workbook(io.BytesIO(data)),
        openpyxl.load_workbook(io.BytesIO(data), data_only=True),
    )


class TestAComputedColumnIsALiveFormulaWithItsValue:
    def test_the_formula_and_the_cached_value(self) -> None:
        formulas, values = _books(
            _content(ColumnSpec(header="Margin", formula="{Revenue} - {Cost}", kind="amount"))
        )
        sheet, cache = formulas["Sales"], values["Sales"]
        assert sheet["D1"].value == "Margin"
        assert sheet["D2"].value == "=B2-C2"
        assert [cache.cell(row, 4).value for row in range(2, 6)] == [
            1000 - 400,
            800 - 0,
            500 - 450,
            300 - 100,
        ]

    def test_a_formula_that_can_fail_is_wrapped_and_cached_blank(self) -> None:
        formulas, values = _books(
            _content(ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}", kind="quantity"))
        )
        assert formulas["Sales"]["D3"].value == '=IFERROR(B3/C3,"")'
        assert values["Sales"]["D3"].value in ("", None)
        assert values["Sales"]["D2"].value == pytest.approx(1000 / 400)

    def test_an_input_is_a_named_cell_the_formulas_read(self) -> None:
        formulas, values = _books(
            _content(
                ColumnSpec(header="Net", formula="{Revenue} * (1 - {Tax rate})"),
                inputs=[SheetInput(name="Tax rate", value="25%", kind="percent")],
            ),
            language="fr",
        )
        assert formulas.sheetnames[0] == "Hypothèses"
        assert "Tax_rate" in formulas.defined_names
        assert formulas["Sales"]["D2"].value == "=B2*(1-Tax_rate)"
        assert values["Sales"]["D2"].value == pytest.approx(1000 * (1 - 0.25))
        assert values["Hypothèses"]["B2"].value == pytest.approx(0.25)

    @pytest.mark.parametrize("kind", ["code", "text"])
    def test_an_input_declared_as_a_text_is_still_the_number_its_formulas_read(
        self, kind: str
    ) -> None:
        """Proven 2026-11-14: written as a text, the named cell made Excel answer 1
        to ``IF(Year>5000,1,0)`` (a text is larger than any number) and skip it in
        ``MAX`` — where the cached values say 0 and 2026."""
        formulas, values = _books(
            _content(
                ColumnSpec(header="Late", formula="IF({Year} > 5000, 1, 0)"),
                ColumnSpec(header="Top", formula="MAX({Year}, {Revenue})"),
                inputs=[SheetInput(name="Year", value="2026", kind=kind)],
            )
        )
        named = formulas["Assumptions"]["B2"]
        assert (named.value, named.data_type) == (2026, "n")
        assert [values["Sales"].cell(2, column).value for column in (4, 5)] == [0, 2026]

    def test_a_total_no_float_holds_is_cached_as_nothing(self) -> None:
        """Two values Excel holds can add up past what a float holds: written as
        ``inf``, the cached total would make Excel repair the file."""
        from decimal import Decimal

        from src.domains.document_generation.renderers.xlsx_parts import cached

        assert cached(Decimal("9.9e307") * 2) == ""
        assert cached(Decimal("1.5")) == 1.5


class TestTotalsAndSummaries:
    def test_the_totals_row_caches_its_totals(self) -> None:
        formulas, values = _books(
            _content(
                ColumnSpec(header="Revenue", total="sum"),
                ColumnSpec(header="Cost", total="average"),
            )
        )
        totals_row = len(ROWS) + 2
        assert formulas["Sales"][f"B{totals_row}"].value == "=SUBTOTAL(109,[Revenue])"
        assert values["Sales"][f"B{totals_row}"].value == 1000 + 800 + 500 + 300
        assert values["Sales"][f"C{totals_row}"].value == pytest.approx((400 + 0 + 450 + 100) / 4)
        assert values["Sales"][f"A{totals_row}"].value == "Total"

    def test_a_summary_reads_the_data_and_matches_labels_exactly(self) -> None:
        """« South* » must not be a wildcard: its group holds its own row only."""
        formulas, values = _books(
            _content(summary=GroupSummary(by="Region", measures=["Revenue"], title="By region"))
        )
        assert formulas.sheetnames == ["Sales", "By region"]
        summary, cache = formulas["By region"], values["By region"]
        assert "SUMIFS(Sales!$B$2:$B$5,Sales!$A$2:$A$5" in summary["B2"].value
        assert '"~*"' in summary["B2"].value
        groups = {cache.cell(row, 1).value: cache.cell(row, 2).value for row in range(2, 5)}
        # A wildcard « South* » would also have summed the « south » row (1 100).
        assert groups == {"North": 1000 + 500, "south": 300, "South*": 800}

    def test_a_group_spelled_two_ways_is_one_group(self) -> None:
        """Excel's criteria ignore case; the cached sums must count the same rows."""
        formulas, values = _books(
            _content(
                summary=GroupSummary(by="Region", measures=["Revenue"]),
                rows=[["North", "1", "0"], ["north", "2", "0"], ["NORTH", "4", "0"]],
            )
        )
        title = formulas.sheetnames[1]
        assert values[title]["A2"].value == "North"
        assert values[title]["B2"].value == 1 + 2 + 4


class TestTheSheetIsReadable:
    def test_a_declared_amount_reads_in_the_reader_conventions(self) -> None:
        formulas, _values = _books(
            _content(ColumnSpec(header="Revenue", kind="amount", unit="EUR")), language="fr"
        )
        assert formulas["Sales"]["B2"].number_format.startswith('#,##0" €"')

    def test_a_closed_list_is_a_drop_down(self) -> None:
        formulas, _values = _books(
            _content(ColumnSpec(header="Region", choices=["North", "South"]))
        )
        validations = formulas["Sales"].data_validations.dataValidation
        assert validations and validations[0].type == "list"
        assert validations[0].formula1 == '"North,South"'

    def test_a_long_list_reads_a_hidden_sheet(self) -> None:
        choices = [f"Region number {index}, east" for index in range(20)]
        formulas, _values = _books(_content(ColumnSpec(header="Region", choices=choices)))
        hidden = [sheet.title for sheet in formulas.worksheets if sheet.sheet_state == "hidden"]
        assert hidden == ["Lists"]
        validation = formulas["Sales"].data_validations.dataValidation[0]
        assert validation.formula1 == "Lists!$A$1:$A$20"

    def test_a_choice_holding_a_quote_reads_the_hidden_sheet_too(self) -> None:
        """An inline list is ONE quoted text of the rule's formula: XlsxWriter writes
        a quote inside it bare (``"5" screen,7" screen"``), a formula Excel cannot
        read. Such a list is read from cells, where a quote is a character."""
        formulas, _values = _books(
            _content(ColumnSpec(header="Region", choices=['5" screen', '7" screen']))
        )
        validation = formulas["Sales"].data_validations.dataValidation[0]
        assert validation.formula1 == "Lists!$A$1:$A$2"
        assert [cell.value for cell in formulas["Lists"]["A"]] == ['5" screen', '7" screen']

    def test_a_measure_with_a_good_direction_gets_a_colour_scale(self) -> None:
        formulas, _values = _books(_content(ColumnSpec(header="Revenue", better="higher")))
        rules = [
            rule for ranges in formulas["Sales"].conditional_formatting for rule in ranges.rules
        ]
        assert [rule.type for rule in rules] == ["colorScale"]

    def test_a_wide_sheet_prints_in_landscape_one_page_wide(self) -> None:
        headers = [f"Column {index}" for index in range(8)]
        formulas, _values = _books(
            _content(headers=headers, rows=[[str(index) for index in range(8)]])
        )
        sheet = formulas["Sales"]
        assert sheet.page_setup.orientation == "landscape"
        # One page wide (the format's default width, so not written), any height.
        assert sheet.sheet_properties.pageSetUpPr.fitToPage
        assert sheet.page_setup.fitToWidth in (None, 1) and sheet.page_setup.fitToHeight == 0
        assert "&P" in sheet.oddFooter.center.text and "&N" in sheet.oddFooter.center.text


class TestDefinedNamesAreAlwaysLegal:
    """XlsxWriter only WARNS on an illegal name and defines nothing: every formula
    reading it would then show #NAME?. The name is made legal before it is asked for."""

    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("Tax rate", "Tax_rate"),
            ("TVA 2026", "TVA_2026"),
            ("Tax1", "Input_1"),
            ("R1C1", "Input_1"),
            ("C", "Input_1"),
            ("true", "Input_1"),
            ("2026 growth", "Input_1"),
            ("增长率", "增长率"),
            ("AB" + "1" * 58 + "x", "Input_1"),
            # A workbook's tables and defined names share one namespace.
            ("Table1", "Input_1"),
            ("TABLE12", "Input_1"),
            ("Tables", "Tables"),
            ("Table_1", "Table_1"),
            # Excel keeps its built-in names (print area, filter) for itself.
            ("_xlnm.Print_Area", "Input_1"),
            ("_XLNM._FilterDatabase", "Input_1"),
        ],
    )
    def test_a_label_becomes_a_legal_name(self, label: str, expected: str) -> None:
        from src.domains.document_generation.renderers.xlsx_parts import defined_name

        assert defined_name(label, set(), 1) == expected

    def test_two_labels_never_share_a_name(self) -> None:
        from src.domains.document_generation.renderers.xlsx_parts import defined_name

        taken: set[str] = set()
        assert [defined_name("Rate", taken, 1), defined_name("rate", taken, 2)] == [
            "Rate",
            "rate_2",
        ]


class TestConditionsAndRunningSumsLiveInTheWorkbook:
    def test_a_running_sum_anchors_its_first_row(self) -> None:
        formulas, values = _books(
            _content(ColumnSpec(header="Cumulative", formula="RUNNING_SUM({Revenue})"))
        )
        assert formulas["Sales"]["D2"].value == "=SUM(B$2:B2)"
        assert formulas["Sales"]["D5"].value == "=SUM(B$2:B5)"
        assert [values["Sales"].cell(row, 4).value for row in range(2, 6)] == [
            1000,
            1000 + 800,
            1000 + 800 + 500,
            1000 + 800 + 500 + 300,
        ]

    def test_a_condition_on_a_text_quotes_it(self) -> None:
        formulas, values = _books(
            _content(ColumnSpec(header="North", formula='IF({Region} = "north", {Revenue}, 0)'))
        )
        assert formulas["Sales"]["D2"].value == '=IF(A2="north",B2,0)'
        assert [values["Sales"].cell(row, 4).value for row in range(2, 6)] == [1000, 0, 500, 0]

    def test_a_column_reading_one_that_may_have_no_value_is_wrapped_too(self) -> None:
        """A cell with no value holds "" in the workbook, and "" * 2 is #VALUE!:
        the reader of a column that may have no value is wrapped as it is."""
        formulas, values = _books(
            _content(
                ColumnSpec(header="Ratio", formula="{Revenue} / {Cost}"),
                ColumnSpec(header="Twice", formula="{Ratio} * 2"),
            )
        )
        assert formulas["Sales"]["E3"].value == '=IFERROR(D3*2,"")'
        assert values["Sales"]["E3"].value in ("", None)
        assert values["Sales"]["E2"].value == pytest.approx(1000 / 400 * 2)


class TestAColumnNamedLikeItsInputReadsItInTheWorkbook:
    def test_the_formula_names_the_input_and_caches_its_value(self) -> None:
        formulas, values = _books(
            _content(
                ColumnSpec(header="Rent", formula="{Rent}"),
                ColumnSpec(header="Total", formula="{Rent} * 2"),
                headers=["Month", "Rent", "Total"],
                rows=[["2026-01", "", ""], ["2026-02", "", ""]],
                inputs=[SheetInput(name="Rent", value="1050", kind="amount")],
            )
        )
        assert "Rent" in formulas.defined_names
        assert formulas["Sales"]["B2"].value == "=Rent"
        assert formulas["Sales"]["C2"].value == "=B2*2"
        assert [values["Sales"].cell(row, 2).value for row in (2, 3)] == [1050, 1050]
        assert [values["Sales"].cell(row, 3).value for row in (2, 3)] == [2100, 2100]


def _budget(*figures: WorkbookFigure) -> TabularContent:
    return TabularContent(
        filename_stem="sales",
        title="Sales",
        sheets=[
            TableSheet(
                name="Sales",
                headers=["Region", "Revenue", "Cost"],
                rows=[list(row) for row in ROWS],
                columns=[ColumnSpec(header="Margin", formula="{Revenue} - {Cost}")],
            )
        ],
        inputs=[SheetInput(name="Bonus", value="1500", kind="amount")],
        figures=list(figures),
    )


REVENUE = 1000 + 800 + 500 + 300


class TestKeyFiguresLiveOnASheetOfTheirOwn:
    """After the assumptions, before the data: what was assumed, what it amounts to,
    then the detail — each figure a live formula, its value cached, a name of its own."""

    def test_the_sheet_follows_the_assumptions(self) -> None:
        formulas, _values = _books(
            _budget(WorkbookFigure(label="Annual revenue", formula="SUM({Sales/Revenue})"))
        )
        assert formulas.sheetnames == ["Assumptions", "Key figures", "Sales"]
        assert [cell.value for cell in formulas["Key figures"][1]] == ["Figure", "Value"]
        assert formulas["Key figures"].freeze_panes == "A2"

    def test_a_figure_reads_a_whole_column_and_an_input(self) -> None:
        formulas, values = _books(
            _budget(
                WorkbookFigure(
                    label="Annual revenue", formula="SUM({Sales/Revenue}) + {Bonus}", kind="amount"
                )
            )
        )
        sheet, cache = formulas["Key figures"], values["Key figures"]
        assert sheet["A2"].value == "Annual revenue"
        assert sheet["B2"].value == "=SUM(Sales!$B$2:$B$5)+Bonus"
        assert cache["B2"].value == REVENUE + 1500

    def test_a_figure_reading_a_figure_reads_its_name(self) -> None:
        formulas, values = _books(
            _budget(
                WorkbookFigure(label="Twice", formula="{Annual revenue} * 2"),
                WorkbookFigure(label="Annual revenue", formula="SUM({Sales/Revenue})"),
            )
        )
        sheet, cache = formulas["Key figures"], values["Key figures"]
        assert {"Twice", "Annual_revenue"} <= set(formulas.defined_names)
        assert sheet["B2"].value == "=Annual_revenue*2"
        assert cache["B2"].value == REVENUE * 2 and cache["B3"].value == REVENUE

    def test_a_computed_column_is_read_whole(self) -> None:
        formulas, values = _books(
            _budget(WorkbookFigure(label="Total margin", formula="SUM({Sales/Margin})"))
        )
        assert formulas["Key figures"]["B2"].value == "=SUM(Sales!$D$2:$D$5)"
        assert values["Key figures"]["B2"].value == (1000 - 400) + (800 - 0) + (500 - 450) + (
            300 - 100
        )

    def test_a_figure_that_may_have_no_value_is_wrapped(self) -> None:
        formulas, values = _books(
            _budget(WorkbookFigure(label="Average cost", formula="AVERAGE({Sales/Cost})"))
        )
        assert formulas["Key figures"]["B2"].value == '=IFERROR(AVERAGE(Sales!$C$2:$C$5),"")'
        assert values["Key figures"]["B2"].value == pytest.approx((400 + 0 + 450 + 100) / 4)

    def test_the_sheet_speaks_the_reader_s_language(self) -> None:
        formulas, _values = _books(
            _budget(WorkbookFigure(label="Total", formula="SUM({Sales/Revenue})")), language="fr"
        )
        assert formulas.sheetnames == ["Hypothèses", "Chiffres clés", "Sales"]

    def test_no_figure_no_sheet(self) -> None:
        formulas, _values = _books(_budget())
        assert formulas.sheetnames == ["Assumptions", "Sales"]

    def test_an_input_wins_over_a_figure_of_its_name(self) -> None:
        formulas, values = _books(
            _budget(
                WorkbookFigure(label="Bonus", formula="{Bonus} * 2"),
                WorkbookFigure(label="Half", formula="{Bonus} * 0.5"),
            )
        )
        sheet, cache = formulas["Key figures"], values["Key figures"]
        assert formulas.defined_names["Bonus"].attr_text == "Assumptions!$B$2"
        assert formulas.defined_names["Bonus_2"].attr_text == "'Key figures'!$B$2"
        assert [sheet["B2"].value, sheet["B3"].value] == ["=Bonus*2", "=Bonus*0.5"]
        assert [cache["B2"].value, cache["B3"].value] == [3000, 750]

    def test_a_figure_never_takes_a_table_s_name(self) -> None:
        formulas, values = _books(_budget(WorkbookFigure(label="Table1", formula="{Bonus} + 1")))
        tables = {name.casefold() for sheet in formulas.worksheets for name in sheet.tables.keys()}
        names = {name.casefold() for name in formulas.defined_names}
        assert "table1" in tables and not tables & names
        assert "figure_1" in names
        assert formulas["Key figures"]["A2"].value == "Table1"
        assert values["Key figures"]["B2"].value == 1501

    def test_a_figure_with_no_value_is_read_as_excel_reads_it(self) -> None:
        formulas, values = _books(
            _budget(
                WorkbookFigure(label="Zero", formula="{Bonus} - 1500"),
                WorkbookFigure(label="Ratio", formula="{Bonus} / {Zero}"),
                WorkbookFigure(label="Floor", formula="MIN({Ratio}, 5)"),
            )
        )
        sheet, cache = formulas["Key figures"], values["Key figures"]
        assert [sheet[f"B{row}"].value for row in (2, 3, 4)] == [
            "=Bonus-1500",
            '=IFERROR(Bonus/Zero,"")',
            "=MIN(Ratio,5)",
        ]
        assert (cache["B2"].value, cache["B4"].value) == (0, 5)
        assert cache["B3"].value in ("", None)

    def test_a_sheet_whose_title_has_a_space_is_quoted(self) -> None:
        content = _budget(WorkbookFigure(label="Total", formula="SUM({Monthly sales/Revenue})"))
        content.sheets[0].name = "Monthly sales"
        formulas, values = _books(content)
        assert formulas["Key figures"]["B2"].value == "=SUM('Monthly sales'!$B$2:$B$5)"
        assert values["Key figures"]["B2"].value == REVENUE

    def test_an_average_of_an_empty_column_has_no_value(self) -> None:
        content = _budget(WorkbookFigure(label="Mean", formula="AVERAGE({Sales/Spare})"))
        content.sheets[0].headers.append("Spare")
        for row in content.sheets[0].rows:
            row.append("")
        content.sheets[0].columns.append(ColumnSpec(header="Spare", kind="amount"))
        formulas, values = _books(content)
        # Written columns come first, computed ones after: « Spare » is D, « Margin » E.
        assert formulas["Key figures"]["B2"].value == '=IFERROR(AVERAGE(Sales!$D$2:$D$5),"")'
        assert values["Key figures"]["B2"].value in ("", None)

    def test_a_figure_the_sheets_cannot_compute_leaves_a_sheet_excel_opens(self) -> None:
        """The renderer trusts no caller: content that skipped normalization still
        gives a file whose figures sheet holds its header and no empty Table."""
        from src.domains.document_generation.context import RenderContext
        from src.domains.document_generation.renderers.xlsx import render_xlsx

        content = _budget(WorkbookFigure(label="Ghost", formula="SUM({Sales/Ghost})"))
        data = render_xlsx(content, RenderContext(language="en"))
        book = openpyxl.load_workbook(io.BytesIO(data))
        assert [cell.value for cell in book["Key figures"][1]] == ["Figure", "Value"]
        assert book["Key figures"].max_row == 1 and not book["Key figures"].tables

    def test_a_label_that_looks_like_a_formula_stays_text(self) -> None:
        """ADR-226: a label is written as text, neutralized, never as a formula."""
        formulas, _values = _books(_budget(WorkbookFigure(label="=1+1", formula="{Bonus}")))
        cell = formulas["Key figures"]["A2"]
        assert cell.value == "'=1+1" and cell.data_type != "f"
