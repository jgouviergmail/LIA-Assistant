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
