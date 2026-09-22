"""Recovering a tool call the schema rejected for its ``null`` values (2026-09-05).

A model that fills every property of the tool schema writes ``null`` where it
has nothing to say. When the field has a default and does not admit ``None``,
that ``null`` is the model's spelling of « absent »: the key is dropped so the
default applies. A ``null`` on an Optional field is a value and stays; a
``null`` on a required field is an error and stays.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field, ValidationError

from src.infrastructure.llm.tool_call_rescue import (
    drop_nulls_with_defaults,
    invalid_call_arguments,
    quote_bare_values,
    rejection_reason,
    rescue_invalid_tool_call,
    rescue_tool_call,
    validate_with_defaulted_nulls,
)

pytestmark = pytest.mark.unit


class _Topic(BaseModel):
    title: str
    notes: list[str] = Field(default_factory=list)


class _Section(BaseModel):
    key: str
    paragraph: str | None = None
    bullets: list[str] = Field(default_factory=list)
    topics: list[_Topic] = Field(default_factory=list)
    lead: _Topic | None = None
    summary: _Topic = Field(default_factory=lambda: _Topic(title="none"))


class _Minutes(BaseModel):
    title: str
    sections: list[_Section] = Field(default_factory=list)
    tags: list[str] = []


def test_a_null_on_a_defaulted_list_is_dropped_so_the_default_applies() -> None:
    payload, dropped = drop_nulls_with_defaults(_Minutes, {"title": "t", "tags": None})
    assert payload == {"title": "t"} and dropped == 1
    assert _Minutes.model_validate(payload).tags == []


def test_a_null_on_an_optional_field_is_a_value_and_stays() -> None:
    payload = {"title": "t", "sections": [{"key": "k", "paragraph": None, "lead": None}]}
    kept, dropped = drop_nulls_with_defaults(_Minutes, payload)
    assert kept == payload and dropped == 0


def test_a_null_on_a_required_field_stays_and_still_fails() -> None:
    payload, dropped = drop_nulls_with_defaults(_Minutes, {"title": None, "tags": None})
    assert payload == {"title": None} and dropped == 1
    with pytest.raises(ValidationError):
        validate_with_defaulted_nulls(_Minutes, {"title": None})


def test_nulls_are_defaulted_recursively_through_lists_and_nested_models() -> None:
    payload = {
        "title": "t",
        "sections": [
            {
                "key": "k",
                "bullets": None,
                "topics": [{"title": "a", "notes": None}],
                "summary": {"title": "s", "notes": None},
            }
        ],
    }
    instance, dropped = validate_with_defaulted_nulls(_Minutes, payload)
    assert dropped == 3
    section = instance.sections[0]
    assert section.bullets == [] and section.topics[0].notes == [] and section.summary.notes == []


def test_a_non_dict_payload_is_returned_untouched() -> None:
    assert drop_nulls_with_defaults(_Minutes, "text") == ("text", 0)
    assert drop_nulls_with_defaults(_Minutes, None) == (None, 0)


def test_unknown_keys_are_left_alone() -> None:
    payload, dropped = drop_nulls_with_defaults(_Minutes, {"title": "t", "extra": None})
    assert payload == {"title": "t", "extra": None} and dropped == 0


# ------------------------------------------------------------- rescue_tool_call


def _message(args: dict[str, Any] | None, content: str = "") -> AIMessage:
    calls = (
        [{"name": "_Minutes", "args": args, "id": "call_1", "type": "tool_call"}] if args else []
    )
    return AIMessage(content=content, tool_calls=calls)


def test_rescue_tool_call_returns_the_instance_and_the_count() -> None:
    instance, dropped = rescue_tool_call(_message({"title": "t", "tags": None}), _Minutes)
    assert instance is not None and instance.title == "t" and dropped == 1


def test_rescue_tool_call_gives_up_on_a_still_invalid_call_or_no_call() -> None:
    assert rescue_tool_call(_message({"title": None}), _Minutes) == (None, 0)
    assert rescue_tool_call(_message(None), _Minutes) == (None, 0)
    assert rescue_tool_call(None, _Minutes) == (None, 0)


def test_rescue_tool_call_does_not_claim_a_payload_that_needed_no_help() -> None:
    """A valid call is the parser's job; the rescue only answers for what it changed."""
    assert rescue_tool_call(_message({"title": "t"}), _Minutes) == (None, 0)


# ------------------------------------------------------------ rejection_reason


def test_rejection_reason_names_the_schema_paths_of_a_rejected_call() -> None:
    try:
        _Minutes.model_validate({"title": None, "sections": [{"key": "k", "bullets": "x"}]})
    except ValidationError as exc:
        reason = rejection_reason(_message({"title": None}), exc)
    assert reason.startswith("tool call rejected by schema (2 errors: ")
    assert "title" in reason and "sections.0.bullets" in reason


def test_rejection_reason_distinguishes_no_call_from_an_empty_answer() -> None:
    assert rejection_reason(_message(None, content="some prose"), None) == (
        "no tool call, text rescue failed"
    )
    assert rejection_reason(_message(None), None) == "no tool call, empty answer"
    assert rejection_reason(None, None) == "no tool call, empty answer"


# ------------------------------------------------- invalid tool calls (2026-09-20)
#
# DeepSeek V4.1-Flash writes a bare word where a JSON string belongs — measured on
# dev: 11 of 24 query-analyzer calls, the same field each time. LangChain then
# files the call under ``invalid_tool_calls`` with ``tool_calls`` empty, and the
# door used to read « no tool call, empty answer » and drop the whole turn.

_MEASURED_ARGS = (
    '{"intent": "action", "english_query": "I want to play tic-tac-toe", '
    '"reasoning": "User wants to play tic-tac-toe game, matching skill.", '
    '"skill_name": "tic-tac-toe", "primary_domain": mcp, "confidence": 0.85, '
    '"is_mutation_intent": false, "has_cardinality_risk": false, '
    '"encyclopedia_keywords": [], "semantic_filter_terms": []}'
)


class _Analysis(BaseModel):
    intent: str
    english_query: str
    reasoning: str
    skill_name: str | None = None
    primary_domain: str | None = None
    confidence: float = 0.8
    is_mutation_intent: bool = False
    has_cardinality_risk: bool = False
    encyclopedia_keywords: list[str] = Field(default_factory=list)
    semantic_filter_terms: list[str] = Field(default_factory=list)


def _invalid(args: str | None, content: str = "") -> AIMessage:
    return AIMessage(
        content=content,
        invalid_tool_calls=[
            {
                "name": "_Analysis",
                "args": args,
                "id": "call_1",
                "error": (
                    f"Function _Analysis arguments:\n\n{args}\n\nare not valid JSON. "
                    "Received JSONDecodeError Expecting value: line 1 column 1 (char 0)"
                ),
                "type": "invalid_tool_call",
            }
        ],
    )


def test_a_bare_word_in_value_position_is_quoted_and_nothing_else_moves() -> None:
    repaired, count = quote_bare_values(_MEASURED_ARGS)
    assert count == 1
    payload = json.loads(repaired)
    assert payload["primary_domain"] == "mcp"
    assert payload["confidence"] == 0.85 and payload["is_mutation_intent"] is False
    assert payload["encyclopedia_keywords"] == []


def test_a_bare_word_inside_a_string_is_left_alone() -> None:
    repaired, count = quote_bare_values('{"note": "domain: mcp, then", "k": v}')
    assert count == 1
    assert json.loads(repaired) == {"note": "domain: mcp, then", "k": "v"}


def test_literals_and_numbers_are_not_quoted_and_array_items_are() -> None:
    text = '{"a": true, "b": null, "c": -1.5e3, "d": [x, "y", z], "e": {"f": false}}'
    repaired, count = quote_bare_values(text)
    assert count == 2
    assert json.loads(repaired) == {
        "a": True,
        "b": None,
        "c": -1500.0,
        "d": ["x", "y", "z"],
        "e": {"f": False},
    }


def test_valid_json_comes_back_untouched() -> None:
    assert quote_bare_values(_MEASURED_ARGS.replace(": mcp,", ': "mcp",')) == (
        _MEASURED_ARGS.replace(": mcp,", ': "mcp",'),
        0,
    )


def test_rescue_invalid_tool_call_repairs_the_measured_payload() -> None:
    instance, repairs = rescue_invalid_tool_call(_invalid(_MEASURED_ARGS), _Analysis)
    assert instance is not None and repairs == 1
    assert instance.primary_domain == "mcp" and instance.skill_name == "tic-tac-toe"


def test_rescue_invalid_tool_call_gives_up_when_the_repair_makes_no_json() -> None:
    assert rescue_invalid_tool_call(_invalid('{"intent": "action", "x": }'), _Analysis) == (
        None,
        0,
    )
    assert rescue_invalid_tool_call(_invalid(None), _Analysis) == (None, 0)
    assert rescue_invalid_tool_call(_message(None), _Analysis) == (None, 0)
    assert rescue_invalid_tool_call(None, _Analysis) == (None, 0)


def test_rescue_invalid_tool_call_gives_up_when_the_schema_still_refuses() -> None:
    # The word is quoted, the JSON parses, but the required field is missing.
    assert rescue_invalid_tool_call(_invalid('{"intent": action}'), _Analysis) == (None, 0)


def test_rejection_reason_names_a_call_whose_arguments_were_not_json() -> None:
    reason = rejection_reason(_invalid('{"intent": "action", "x": }'), None)
    assert reason == (
        "tool call arguments not valid JSON "
        "(JSONDecodeError Expecting value: line 1 column 1 (char 0))"
    )


def test_invalid_call_arguments_are_what_the_error_carries_for_diagnosis() -> None:
    assert invalid_call_arguments(_invalid(_MEASURED_ARGS)) == _MEASURED_ARGS
    assert invalid_call_arguments(_message(None)) == ""
    assert invalid_call_arguments(None) == ""
