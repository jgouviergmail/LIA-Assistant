"""Unit tests for the "is the content actually there?" helpers.

These two gate whether LIA stops and ASKS the user for missing content before
acting. Both failure directions are user-visible and silent:

- too strict → LIA re-asks for a body the user already dictated;
- too lax    → LIA sends an email / creates an event with an empty body.

``_check_field_has_value`` inspects the planned step parameters;
``_check_request_has_inline_content`` looks at the raw user request, stripping
the known trigger phrases ("send an email to X") to see whether anything
substantial remains. Neither had a test.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.semantic_validator import (
    _check_field_has_value,
    _check_request_has_inline_content,
)

pytestmark = pytest.mark.unit


# ============================================================================
# _check_field_has_value — is the field populated in the step parameters?
# ============================================================================


class TestCheckFieldHasValue:
    def test_non_empty_string_counts(self) -> None:
        assert _check_field_has_value({"body": "Happy birthday!"}, ["body"]) is True

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_blank_string_does_not_count(self, blank: str) -> None:
        """A whitespace-only body is exactly the case the clarification exists
        for — it must not be mistaken for provided content."""
        assert _check_field_has_value({"body": blank}, ["body"]) is False

    def test_missing_key_does_not_count(self) -> None:
        assert _check_field_has_value({"subject": "hi"}, ["body"]) is False

    def test_none_value_does_not_count(self) -> None:
        assert _check_field_has_value({"body": None}, ["body"]) is False

    def test_any_of_the_aliases_satisfies_the_field(self) -> None:
        """A field is satisfiable by several parameter names (body /
        content_instruction / message …) — one populated alias is enough."""
        params = {"body": None, "content_instruction": "wish her a happy birthday"}
        assert _check_field_has_value(params, ["body", "content_instruction"]) is True

    def test_no_alias_populated(self) -> None:
        params: dict[str, Any] = {"body": "", "content_instruction": None}
        assert _check_field_has_value(params, ["body", "content_instruction"]) is False

    @pytest.mark.parametrize("value", [["a"], {"k": "v"}])
    def test_non_empty_collections_count(self, value: Any) -> None:
        assert _check_field_has_value({"attendees": value}, ["attendees"]) is True

    @pytest.mark.parametrize("value", [[], {}])
    def test_empty_collections_do_not_count(self, value: Any) -> None:
        assert _check_field_has_value({"attendees": value}, ["attendees"]) is False

    @pytest.mark.parametrize("value", [0, 0.0, False, 42, True])
    def test_numeric_and_boolean_values_always_count(self, value: Any) -> None:
        """Documented choice: 0 / False are legitimate values for a numeric or
        boolean field, not emptiness — pinned so a future "falsy means missing"
        refactor cannot silently start re-asking for them."""
        assert _check_field_has_value({"priority": value}, ["priority"]) is True

    def test_empty_param_name_list(self) -> None:
        assert _check_field_has_value({"body": "text"}, []) is False

    def test_empty_params_dict(self) -> None:
        assert _check_field_has_value({}, ["body"]) is False


# ============================================================================
# _check_request_has_inline_content — did the user dictate the content inline?
# ============================================================================


class TestCheckRequestHasInlineContent:
    def test_unknown_domain_has_no_patterns_and_returns_false(self) -> None:
        """Without trigger patterns nothing can be stripped, so no inline
        content can be established — fail-closed, i.e. LIA will ask."""
        assert (
            _check_request_has_inline_content(
                "some very long request with plenty of words in it", "not_a_domain", 10
            )
            is False
        )

    def test_trigger_phrase_alone_is_not_content(self) -> None:
        """The bare instruction carries no body: after stripping the trigger
        almost nothing remains."""
        assert _check_request_has_inline_content("envoie un email à marie", "email", 30) is False

    def test_dictated_body_after_the_trigger_is_content(self) -> None:
        request = "envoie un email à marie pour lui souhaiter un très joyeux anniversaire"
        assert _check_request_has_inline_content(request, "email", 30) is True

    def test_threshold_is_honoured(self) -> None:
        """Same request, two thresholds: the caller's threshold decides."""
        request = "envoie un email à marie pour lui souhaiter un très joyeux anniversaire"
        assert _check_request_has_inline_content(request, "email", 1000) is False
        assert _check_request_has_inline_content(request, "email", 5) is True

    def test_empty_request_is_not_content(self) -> None:
        assert _check_request_has_inline_content("", "email", 10) is False

    def test_detection_is_case_insensitive(self) -> None:
        """Patterns are matched lower-cased, so shouting must behave the same."""
        lower = "envoie un email à marie pour lui souhaiter un très joyeux anniversaire"
        assert _check_request_has_inline_content(lower.upper(), "email", 30) is (
            _check_request_has_inline_content(lower, "email", 30)
        )

    def test_recipient_counts_towards_the_remaining_length(self) -> None:
        """CHARACTERIZATION, not endorsement.

        Stripping only removes the trigger phrase, so whatever follows — the
        RECIPIENT included — counts as "content". A long recipient name can
        therefore clear the threshold on its own and suppress the clarification,
        even though no body was dictated.

        Pinned rather than changed: the boundary between recipient and body is
        not recoverable from a plain string strip, and tightening the rule would
        start re-asking on genuinely complete requests. Any future change (NER,
        recipient-aware stripping) must be measured against this pin.
        """
        assert (
            _check_request_has_inline_content(
                "envoie un email à jean-baptiste de la tour du pin", "email", 30
            )
            is True
        )
