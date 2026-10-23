"""Recovering a tool call the schema rejected for values that only spell « absent ».

A model that fills every property of the tool schema writes ``null`` where it
has nothing to say (2026-09-05). When the field has a default and does not admit
``None``, that ``null`` is the model's spelling of « absent »: the key is dropped
so the default applies. A ``null`` on an Optional field is a value and stays; a
``null`` on a required field is an error and stays.

A model may also add a key the schema never declared and leave it empty
(2026-10-22, ``"source_quote_note": ""`` inside a requested outcome): on a model
that forbids extras the empty key is dropped, since nothing could read it; a key
that says something stays, because it may be a declared field misspelled.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.infrastructure.llm.tool_call_rescue import (
    AbsentValues,
    drop_absent_values,
    invalid_call_arguments,
    quote_bare_values,
    refusal_verdict,
    repair_refused_answer,
    rescue_invalid_tool_call,
    rescue_payload,
    rescue_tool_call,
    validate_without_absent_values,
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
    payload, absent = drop_absent_values(_Minutes, {"title": "t", "tags": None})
    assert payload == {"title": "t"} and absent == AbsentValues(nulls=1)
    assert _Minutes.model_validate(payload).tags == []


def test_a_null_on_an_optional_field_is_a_value_and_stays() -> None:
    payload = {"title": "t", "sections": [{"key": "k", "paragraph": None, "lead": None}]}
    kept, absent = drop_absent_values(_Minutes, payload)
    assert kept == payload and absent == AbsentValues()


def test_a_null_on_a_required_field_stays_and_still_fails() -> None:
    payload, absent = drop_absent_values(_Minutes, {"title": None, "tags": None})
    assert payload == {"title": None} and absent == AbsentValues(nulls=1)
    with pytest.raises(ValidationError):
        validate_without_absent_values(_Minutes, {"title": None})


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
    instance, absent = validate_without_absent_values(_Minutes, payload)
    assert absent == AbsentValues(nulls=3)
    section = instance.sections[0]
    assert section.bullets == [] and section.topics[0].notes == [] and section.summary.notes == []


def test_a_non_dict_payload_is_returned_untouched() -> None:
    assert drop_absent_values(_Minutes, "text") == ("text", AbsentValues())
    assert drop_absent_values(_Minutes, None) == (None, AbsentValues())


def test_unknown_keys_are_left_alone_where_the_model_ignores_them() -> None:
    """Pydantic drops them itself: there is nothing to repair."""
    payload, absent = drop_absent_values(_Minutes, {"title": "t", "extra": None})
    assert payload == {"title": "t", "extra": None} and absent == AbsentValues()


# ------------------------------------------------ undeclared keys (2026-10-22)
#
# Haiku 5.5 with thinking, on the auto-tool door (a forced tool is refused
# there), added ``"source_quote_note": ""`` to a requested outcome whose model
# forbids extras: the whole query analysis was refused and the turn fell back
# to a bare conversation, its tools gone.


class _Goal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    min_count: int | None = None


class _Request(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: str
    goals: list[_Goal] = Field(default_factory=list)
    lead: _Goal | None = None


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str


@pytest.mark.parametrize("empty", ["", "   ", None, [], {}])
def test_an_undeclared_key_that_says_nothing_is_dropped_where_extras_are_forbidden(
    empty: object,
) -> None:
    payload = {"label": "l", "source_quote": "q", "source_quote_note": empty}
    cleaned, absent = drop_absent_values(_Goal, payload)
    assert cleaned == {"label": "l", "source_quote": "q"}
    assert absent == AbsentValues(extras=1)


def test_the_measured_shape_validates_once_its_empty_key_is_dropped() -> None:
    payload = {
        "intent": "action",
        "goals": [{"label": "l", "source_quote": "q", "source_quote_note": ""}],
        "lead": {"label": "m", "source_quote": "r", "note": None},
    }
    with pytest.raises(ValidationError):
        _Request.model_validate(payload)
    instance, absent = validate_without_absent_values(_Request, payload)
    assert instance.goals[0].source_quote == "q" and instance.lead is not None
    assert absent == AbsentValues(extras=2)


def test_an_undeclared_key_that_says_something_stays_and_still_fails() -> None:
    """``minimum_count: 3`` may be ``min_count`` misspelled: dropping it would
    let the default replace what the model meant."""
    payload = {"label": "l", "source_quote": "q", "minimum_count": 3}
    cleaned, absent = drop_absent_values(_Goal, payload)
    assert cleaned == payload and absent == AbsentValues()
    with pytest.raises(ValidationError):
        validate_without_absent_values(_Goal, payload)


def test_an_undeclared_key_is_data_where_the_model_allows_extras() -> None:
    payload = {"title": "t", "note": ""}
    cleaned, absent = drop_absent_values(_Open, payload)
    assert cleaned == payload and absent == AbsentValues()
    assert _Open.model_validate(cleaned).model_extra == {"note": ""}


class _Aliased(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: str = Field(default="", alias="from")
    tags: list[str] = Field(default_factory=list)


def test_a_key_spelled_by_its_alias_is_a_declared_field() -> None:
    """An empty value under an alias is a value, never an undeclared key to drop."""
    instance, absent = validate_without_absent_values(_Aliased, {"from": "", "tags": None})
    assert instance.sender == "" and absent == AbsentValues(nulls=1)
    defaulted, absent = validate_without_absent_values(_Aliased, {"from": None})
    assert defaulted.sender == "" and absent == AbsentValues(nulls=1)


def test_nulls_and_empty_undeclared_keys_are_counted_apart() -> None:
    payload = {"title": "t", "tags": None, "sections": [{"key": "k", "bullets": None}]}
    _, nulls = drop_absent_values(_Minutes, payload)
    _, both = drop_absent_values(
        _Request,
        {"intent": "a", "goals": None, "lead": {"label": "l", "source_quote": "q", "x": ""}},
    )
    assert nulls == AbsentValues(nulls=2)
    assert both == AbsentValues(nulls=1, extras=1) and both.total == 2


def test_rescue_payload_answers_only_for_what_it_changed() -> None:
    assert rescue_payload(_Goal, {"label": "l", "source_quote": "q"}) == (None, AbsentValues())
    assert rescue_payload(_Goal, {"label": "l", "source_quote": "", "x": ""}) == (
        None,
        AbsentValues(),
    )
    instance, absent = rescue_payload(_Goal, {"label": "l", "source_quote": "q", "x": ""})
    assert instance == _Goal(label="l", source_quote="q") and absent == AbsentValues(extras=1)


# ------------------------------------------------------------- rescue_tool_call


def _message(args: dict[str, Any] | None, content: str = "") -> AIMessage:
    calls = (
        [{"name": "_Minutes", "args": args, "id": "call_1", "type": "tool_call"}] if args else []
    )
    return AIMessage(content=content, tool_calls=calls)


def test_rescue_tool_call_returns_the_instance_and_the_count() -> None:
    instance, absent = rescue_tool_call(_message({"title": "t", "tags": None}), _Minutes)
    assert instance is not None and instance.title == "t" and absent == AbsentValues(nulls=1)


def test_rescue_tool_call_gives_up_on_a_still_invalid_call_or_no_call() -> None:
    assert rescue_tool_call(_message({"title": None}), _Minutes) == (None, AbsentValues())
    assert rescue_tool_call(_message(None), _Minutes) == (None, AbsentValues())
    assert rescue_tool_call(None, _Minutes) == (None, AbsentValues())


def test_rescue_tool_call_does_not_claim_a_payload_that_needed_no_help() -> None:
    """A valid call is the parser's job; the rescue only answers for what it changed."""
    assert rescue_tool_call(_message({"title": "t"}), _Minutes) == (None, AbsentValues())


# ------------------------------------------------------- repair_refused_answer


def test_the_repairs_are_tried_in_order_and_each_names_its_outcome() -> None:
    absent, outcome = repair_refused_answer(
        _message({"title": "t", "tags": None}), _Minutes, "p", "_Minutes"
    )
    assert absent is not None and outcome == "absent_values_dropped"
    quoted, outcome = repair_refused_answer(_invalid(_MEASURED_ARGS), _Analysis, "p", "_Analysis")
    assert quoted is not None and outcome == "invalid_call_repaired"
    text, outcome = repair_refused_answer(
        _message(None, content='Here: {"title": "t"}'), _Minutes, "p", "_Minutes"
    )
    assert text is not None and outcome == "text_rescued"


def test_nothing_repairable_is_a_rejection() -> None:
    assert repair_refused_answer(_message({"title": None}), _Minutes, "p", "_Minutes") == (
        None,
        "rejected",
    )
    assert repair_refused_answer(None, _Minutes, "p", "_Minutes") == (None, "rejected")


# ------------------------------------------------------------ refusal_verdict


def test_refusal_verdict_names_the_schema_paths_of_a_rejected_call() -> None:
    try:
        _Minutes.model_validate({"title": None, "sections": [{"key": "k", "bullets": "x"}]})
    except ValidationError as exc:
        reason = refusal_verdict(_message({"title": None}), exc)
    assert reason.startswith("tool call rejected by schema (2 errors: ")
    assert "title" in reason and "sections.0.bullets" in reason


def test_refusal_verdict_distinguishes_no_call_from_an_empty_answer() -> None:
    assert refusal_verdict(_message(None, content="some prose"), None) == (
        "no tool call, text rescue failed"
    )
    assert refusal_verdict(_message(None), None) == "no tool call, empty answer"
    assert refusal_verdict(None, None) == "no tool call, empty answer"


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


def test_refusal_verdict_names_a_call_whose_arguments_were_not_json() -> None:
    reason = refusal_verdict(_invalid('{"intent": "action", "x": }'), None)
    assert reason == (
        "tool call arguments not valid JSON "
        "(JSONDecodeError Expecting value: line 1 column 1 (char 0))"
    )


def test_refusal_verdict_never_quotes_an_error_that_carries_no_parser_verdict() -> None:
    """The verdict is logged above DEBUG: an error with no « Received » part is
    the payload itself, and the payload is the person's words (ADR-317)."""
    arguments = '{"english_query": "Write to Jeanne about her test results"'
    refused = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "_Analysis",
                "args": arguments,
                "id": "call_1",
                "error": f"Function _Analysis arguments:\n\n{arguments}\n\nare not valid JSON.",
                "type": "invalid_tool_call",
            }
        ],
    )
    assert refusal_verdict(refused, None) == "tool call arguments not valid JSON"


def test_invalid_call_arguments_are_what_the_error_carries_for_diagnosis() -> None:
    assert invalid_call_arguments(_invalid(_MEASURED_ARGS)) == _MEASURED_ARGS
    assert invalid_call_arguments(_message(None)) == ""
    assert invalid_call_arguments(None) == ""
