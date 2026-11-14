"""Recovering a call whose structures were written as text, or closed once too often.

Two shapes measured on real models (bench 2026-11-13, ADR-388), each a complete
answer the door threw away and paid again:

- a workbook's ``sheets`` written as JSON TEXT, the text stopped between two
  values and the rest of the open sheet (``columns``, ``chart``) written as keys
  of the call itself — 4 workbooks lost in 9;
- a long report's arguments, whole and valid, followed by one ``}`` (« Extra
  data ») — three calls refused in ten.

The repairs add only the brackets a text owes, move a key only into an object
whose schema declares it, and never read as JSON a value a text may be.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from src.infrastructure.llm.json_recovery import close_cut_structure, drop_trailing_closers
from src.infrastructure.llm.tool_call_rescue import (
    CallRepair,
    TextStructures,
    decode_text_structures,
    repair_refused_answer,
    rescue_invalid_tool_call,
    rescue_text_structures,
)

pytestmark = pytest.mark.unit


class _Column(BaseModel):
    header: str
    formula: str = ""
    remark: str = ""


class _Chart(BaseModel):
    intent: str = ""


class _Sheet(BaseModel):
    name: str
    headers: list[str]
    rows: list[list[str]] = Field(default_factory=list)
    columns: list[_Column] = Field(default_factory=list)
    chart: _Chart | None = None
    remark: str = ""


class _Input(BaseModel):
    name: str
    value: str


class _Book(BaseModel):
    title: str
    sheets: list[_Sheet] = Field(min_length=1)
    inputs: list[_Input] = Field(default_factory=list)
    note: str | list[str] = ""


#: The measured shape, synthetic values: the sheet stops after ``rows``.
_CUT_SHEETS = '[{"name": "Budget", "headers": ["Month", "Income"], "rows": [["2026-01", "3200"]]'
_COLUMNS = [{"header": "Balance", "formula": "{Income} - 100"}]


def _call(args: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "_Book", "args": args, "id": "call_1", "type": "tool_call"}],
    )


def _refused(args: str) -> AIMessage:
    return AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "_Book",
                "args": args,
                "id": "call_1",
                "error": "Received JSONDecodeError Extra data",
                "type": "invalid_tool_call",
            }
        ],
    )


# ------------------------------------------------------------- the text readings


class TestACutStructureIsClosedOnlyWhereItStoppedCleanly:
    @pytest.mark.parametrize(
        ("text", "depth"),
        [
            ('[{"a": [1, 2]', 2),
            ('{"a": {"b": "x"}', 1),
            ("[1, 2", 1),
            ('  [{"a": 1}]  ', 0),
            ('{"text": "a } inside, [ too"', 1),
        ],
    )
    def test_the_owed_brackets_are_added(self, text: str, depth: int) -> None:
        cut = close_cut_structure(text)
        assert cut is not None and cut[1] == depth
        json.loads(cut[0])

    @pytest.mark.parametrize(
        "text",
        [
            '[{"a": "cut inside a te',
            '[{"a": 1,',
            '{"a":',
            '{"a"',
            '[{"a": 1}] trailing',
            '[{"a": 1]',
            "plain words",
            "",
            "3",
        ],
    )
    def test_anything_else_is_no_cut(self, text: str) -> None:
        assert close_cut_structure(text) is None


class TestABracketThatClosesNothingIsDropped:
    def test_only_brackets_after_a_whole_value_go(self) -> None:
        assert drop_trailing_closers('{"title": "t"}}') == ('{"title": "t"}', 1)
        assert drop_trailing_closers('  {"title": "t"} } ]\n') == ('  {"title": "t"}', 2)

    @pytest.mark.parametrize(
        "text",
        [
            '{"title": "t"}',
            '{"title": "t"}, "sheets": []}',
            '{"title": "t"}{"title": "u"}',
            '{"title": "t"',
            "not json",
        ],
    )
    def test_what_may_be_content_stays(self, text: str) -> None:
        assert drop_trailing_closers(text) == (text, 0)


# ------------------------------------------------------------- the call repairs


class TestAStructureWrittenAsTextIsReadBack:
    def test_the_measured_shape_is_put_back_together(self) -> None:
        args = {"title": "Budget", "sheets": _CUT_SHEETS, "columns": _COLUMNS, "chart": {}}
        instance, found = rescue_text_structures(_call(args), _Book)
        assert instance is not None
        sheet = instance.sheets[0]
        assert sheet.rows == [["2026-01", "3200"]]
        assert [column.header for column in sheet.columns] == ["Balance"]
        assert sheet.chart == _Chart()
        assert found == TextStructures(decoded=1, closed=1, rehomed=2)

    def test_each_key_goes_back_into_the_innermost_open_object_that_declares_it(self) -> None:
        """The text stopped inside a column of the sheet: a column's key goes back to
        the column, a sheet's key to the sheet — the innermost object first."""
        sheets = '[{"name": "S", "headers": ["A"], "columns": [{"header": "B"'
        payload, found = decode_text_structures(
            _Book, {"title": "t", "sheets": sheets, "formula": "{A} * 2", "chart": {}}
        )
        sheet = payload["sheets"][0]
        assert sheet["columns"] == [{"header": "B", "formula": "{A} * 2"}]
        assert sheet["chart"] == {}
        assert "formula" not in payload and "chart" not in payload
        assert found == TextStructures(decoded=1, closed=1, rehomed=2)

    def test_a_key_both_open_objects_declare_goes_to_the_innermost(self) -> None:
        """The model was writing the column when it stopped: what follows is the column's."""
        sheets = '[{"name": "S", "headers": ["A"], "columns": [{"header": "B"'
        payload, _found = decode_text_structures(
            _Book, {"title": "t", "sheets": sheets, "remark": "r"}
        )
        sheet = payload["sheets"][0]
        assert sheet["columns"] == [{"header": "B", "remark": "r"}]
        assert "remark" not in sheet

    def test_a_key_never_goes_into_an_object_the_text_closed(self) -> None:
        """The column was closed before the text stopped: only the sheet is open."""
        sheets = '[{"name": "S", "headers": ["A"], "columns": [{"header": "B"}'
        payload, found = decode_text_structures(
            _Book, {"title": "t", "sheets": sheets, "formula": "{A} * 2"}
        )
        assert payload["sheets"][0]["columns"] == [{"header": "B"}]
        assert payload["formula"] == "{A} * 2"
        assert found == TextStructures(decoded=1, closed=1)

    def test_a_whole_text_closed_once_too_often_keeps_its_value(self) -> None:
        """Measured on a third model: the whole array, then the call's own ``}``."""
        sheets = json.dumps([{"name": "S", "headers": ["A"], "rows": [["1"]]}]) + "}"
        payload, found = decode_text_structures(_Book, {"title": "t", "sheets": sheets})
        assert payload["sheets"] == [{"name": "S", "headers": ["A"], "rows": [["1"]]}]
        assert found == TextStructures(decoded=1, closers=1)

    def test_a_stray_character_inside_the_text_is_no_repair(self) -> None:
        """Measured too: a ``)`` inside a row — where it belongs would be a guess."""
        sheets = '[{"name": "S", "headers": ["A", "B"], "rows": [["1", "") ]]}]'
        payload, found = decode_text_structures(_Book, {"title": "t", "sheets": sheets})
        assert payload["sheets"] == sheets and found == TextStructures()

    def test_a_whole_text_is_decoded_and_its_neighbours_stay(self) -> None:
        sheets = json.dumps([{"name": "S", "headers": ["A"], "rows": [["1"]]}])
        payload, found = decode_text_structures(
            _Book, {"title": "t", "sheets": sheets, "columns": _COLUMNS}
        )
        assert payload["sheets"] == [{"name": "S", "headers": ["A"], "rows": [["1"]]}]
        assert payload["columns"] == _COLUMNS  # nothing was cut: nothing to put back
        assert found == TextStructures(decoded=1)

    def test_a_key_already_present_or_declared_nowhere_stays_where_it_was(self) -> None:
        sheets = '[{"name": "S", "headers": ["A"], "columns": []'
        payload, found = decode_text_structures(
            _Book, {"title": "t", "sheets": sheets, "columns": _COLUMNS, "mood": "x"}
        )
        assert payload["sheets"][0]["columns"] == []
        assert payload["columns"] == _COLUMNS and payload["mood"] == "x"
        assert found == TextStructures(decoded=1, closed=1)

    def test_nested_texts_and_list_items_are_read_too(self) -> None:
        sheet = {"name": "S", "headers": ["A"], "columns": json.dumps(_COLUMNS)}
        payload, found = decode_text_structures(
            _Book, {"title": "t", "sheets": [json.dumps(sheet)], "inputs": "[]"}
        )
        assert payload["sheets"][0]["columns"] == _COLUMNS
        assert payload["inputs"] == []
        assert found.decoded == 3

    def test_a_field_a_text_may_fill_is_never_read_as_json(self) -> None:
        payload, found = decode_text_structures(
            _Book, {"title": "[1]", "sheets": [], "note": '["a"]'}
        )
        assert payload["title"] == "[1]" and payload["note"] == '["a"]'
        assert found == TextStructures()

    @pytest.mark.parametrize(
        "sheets",
        [
            '[{"name": "S", "headers": ["A"], "rows": [["cut insi',
            "a sentence, not a structure",
            '{"name": "S", "headers": ["A"]}',
        ],
    )
    def test_a_text_that_is_no_clean_structure_of_the_right_kind_stays(self, sheets: str) -> None:
        payload, found = decode_text_structures(_Book, {"title": "t", "sheets": sheets})
        assert payload["sheets"] == sheets and found == TextStructures()

    def test_a_call_that_needed_no_reading_is_left_to_the_parser(self) -> None:
        call = _call({"title": "t", "sheets": [{"name": "S", "headers": ["A"]}]})
        assert rescue_text_structures(call, _Book) == (None, TextStructures())

    def test_a_reading_the_schema_still_refuses_rescues_nothing(self) -> None:
        call = _call({"title": "t", "sheets": "[]"})
        assert rescue_text_structures(call, _Book) == (None, TextStructures())
        assert rescue_text_structures(None, _Book) == (None, TextStructures())


class TestTheExtraBracketOfAWholeCallIsDropped:
    def test_the_measured_shape_is_rescued(self) -> None:
        whole = json.dumps({"title": "t", "sheets": [{"name": "S", "headers": ["A"]}]})
        instance, repair = rescue_invalid_tool_call(_refused(whole + "}"), _Book)
        assert instance is not None and instance.title == "t"
        assert repair == CallRepair(closers=1)

    def test_content_after_the_value_is_never_dropped(self) -> None:
        whole = json.dumps({"title": "t", "sheets": [{"name": "S", "headers": ["A"]}]})
        refused = _refused(whole[:-1] + '}, "inputs": []}')
        assert rescue_invalid_tool_call(refused, _Book) == (None, CallRepair())


class TestTheChainNamesEachRepair:
    def test_a_structure_read_back_is_its_own_outcome(self) -> None:
        args = {"title": "Budget", "sheets": _CUT_SHEETS, "columns": _COLUMNS}
        instance, outcome = repair_refused_answer(_call(args), _Book, "p", "_Book")
        assert instance is not None and outcome == "structures_decoded"

    def test_a_dropped_bracket_is_a_repaired_call(self) -> None:
        whole = json.dumps({"title": "t", "sheets": [{"name": "S", "headers": ["A"]}]})
        instance, outcome = repair_refused_answer(_refused(whole + "}"), _Book, "p", "_Book")
        assert instance is not None and outcome == "invalid_call_repaired"
