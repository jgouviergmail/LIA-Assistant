"""Shared JSON extraction from model text (ADR-220, ex-F5).

``_rescue_structured_from_text`` delimited the payload with ``find("{")`` /
``rfind("}")`` — the audit's ten-form corpus (real shapes produced by models,
deepseek-v4-flash first) failed on three everyday forms: prose AFTER the JSON
containing a closing brace, a JSON example at the end of the message, and a
trailing comma. The JSON-mode fallback had its own, even stricter variant
(bare ``json.loads``). Both now consume ONE implementation; this corpus is its
contract, the three historical misses pinned as regression cases.
"""

from __future__ import annotations

import json

import pytest

from src.infrastructure.llm.json_recovery import extract_json_payload


def _loads(text: str) -> object:
    payload = extract_json_payload(text)
    assert payload is not None, f"no payload extracted from: {text!r}"
    return json.loads(payload)


class TestHistoricalPasses:
    """The seven forms the old delimiter already handled — must keep passing."""

    def test_bare_json(self) -> None:
        assert _loads('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}

    def test_fenced_json_block(self) -> None:
        assert _loads('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fence_without_language(self) -> None:
        assert _loads('```\n{"a": 1}\n```') == {"a": 1}

    def test_prose_before_json(self) -> None:
        text = 'Here is the plan you asked for:\n{"steps": ["one", "two"]}'
        assert _loads(text) == {"steps": ["one", "two"]}

    def test_missing_closing_brace(self) -> None:
        """A truncated completion (output budget) is repaired, not dropped."""
        assert _loads('{"a": {"b": 1}') == {"a": {"b": 1}}

    def test_brace_inside_string_value(self) -> None:
        assert _loads('{"code": "if (x) { return; }"}') == {"code": "if (x) { return; }"}

    def test_escaped_quote_inside_string(self) -> None:
        assert _loads('{"quote": "she said \\"hi\\" {ok}"}') == {"quote": 'she said "hi" {ok}'}


class TestHistoricalMisses:
    """The three audit MISS forms — the reason this module exists."""

    def test_prose_after_json_containing_a_closing_brace(self) -> None:
        text = (
            '{"intent": "search"}\n\n'
            "Note: I used the schema you provided (the one ending with `}`)."
        )
        assert _loads(text) == {"intent": "search"}

    def test_json_example_at_end_of_message(self) -> None:
        text = (
            "I could not fill every field. A minimal valid answer looks like this:\n"
            '{"result": [], "confidence": 0.0}'
        )
        assert _loads(text) == {"result": [], "confidence": 0.0}

    def test_trailing_comma(self) -> None:
        assert _loads('{"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}


class TestBeyondTheCorpus:
    """Shapes the shared implementation must also hold."""

    def test_root_array(self) -> None:
        assert _loads('The items are:\n[{"id": 1}, {"id": 2}]') == [{"id": 1}, {"id": 2}]

    def test_first_brace_is_prose_second_is_payload(self) -> None:
        """A '{' in prose must not poison the scan — later candidates are tried."""
        text = 'Use { as the opening token. Final answer: {"ok": true}'
        assert _loads(text) == {"ok": True}

    def test_truncated_inside_a_string(self) -> None:
        """Truncation mid-string closes the string, then the structure."""
        assert _loads('{"a": "hell') == {"a": "hell"}

    def test_unicode_survives(self) -> None:
        assert _loads('{"ville": "Besançon", "emoji": "📞"}') == {
            "ville": "Besançon",
            "emoji": "📞",
        }

    def test_nested_fences_prefer_the_json_block(self) -> None:
        text = 'Explanation first.\n```json\n{"a": 1}\n```\nMore prose after.'
        assert _loads(text) == {"a": 1}

    @pytest.mark.parametrize("text", ["", "   ", "no json here", "{{{", "]["])
    def test_no_payload_returns_none(self, text: str) -> None:
        assert extract_json_payload(text) is None

    def test_returned_payload_is_directly_loadable(self) -> None:
        """The contract: the return value feeds json.loads verbatim."""
        payload = extract_json_payload('x {"a": [1, 2,], } y')
        assert payload is not None
        assert json.loads(payload) == {"a": [1, 2]}
