"""Recovering a tool call the schema rejected for its ``null`` values (2026-09-05).

A model that fills every property of the tool schema writes ``null`` where it
has nothing to say. When the field has a default and does not admit ``None``,
that ``null`` is the model's spelling of « absent »: the key is dropped so the
default applies. A ``null`` on an Optional field is a value and stays; a
``null`` on a required field is an error and stays.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field, ValidationError

from src.infrastructure.llm.tool_call_rescue import (
    drop_nulls_with_defaults,
    rejection_reason,
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
