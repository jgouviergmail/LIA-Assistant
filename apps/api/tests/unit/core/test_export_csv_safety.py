"""Spreadsheet exports preserve data without executing user controlled formulas."""

import csv
import io

import pytest

from src.core.export_utils import create_csv_response

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value",
    [
        '=HYPERLINK("https://example.test")',
        "+SUM(1,2)",
        "-1+2",
        "@SUM(1,2)",
        "\t=1+1",
        "\r=1+1",
        " =1+1",
    ],
)
async def test_csv_user_text_never_starts_a_spreadsheet_formula(value: str) -> None:
    response = create_csv_response([{"topic": value, "number": -3}], "interests")
    chunks = [chunk async for chunk in response.body_iterator]
    content = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)
    item = next(csv.DictReader(io.StringIO(content.lstrip("\ufeff"))))
    assert item["topic"] == "'" + value
    assert item["number"] == "-3"


@pytest.mark.parametrize(
    "value",
    [
        '=HYPERLINK("https://example.test")',
        "+SUM(1,2)",
        "-1+2",
        "@SUM(1,2)",
        "\t=1+1",
        " =1+1",
        "plain text",
        "it's quoted inside",
        "'a text that opens on a quote",
        "",
    ],
)
def test_a_protected_cell_reads_back_as_the_text_it_was(value: str) -> None:
    """What an export protects, an import of that export restores: one rule, read both ways."""
    from src.core.export_utils import spreadsheet_cell_text, spreadsheet_safe_cell

    assert spreadsheet_cell_text(spreadsheet_safe_cell(value)) == value


def test_the_one_text_the_protection_cannot_tell_from_its_own_mark() -> None:
    """A text that already opened on a quote AND a formula sign is exported as it is, so
    it reads back without its quote: the CSV is lossy there, the JSON export is not."""
    from src.core.export_utils import spreadsheet_cell_text, spreadsheet_safe_cell

    assert spreadsheet_safe_cell("'=1+1") == "'=1+1"
    assert spreadsheet_cell_text("'=1+1") == "=1+1"
