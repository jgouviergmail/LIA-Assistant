"""A ReAct tool failure is DECLARED, never guessed (ADR-303).

Two halves of the same rule, both measured on production before being written:

* The loop tells the honesty channel that a call failed — structurally, on
  ``ToolMessage.status``, because ``compose_tool_message`` emits the tool's
  PROSE and no JSON any reader could parse. Without it, a scheduled ReAct
  briefing whose calendar, tasks and mail tools all failed announced that
  those three ACTIVE connectors were « not configured », every other morning
  from 2026-09-10 to 2026-09-21.

* A declared failure buys NO iteration. ``_is_productive_result`` read
  ``success`` on a dict only, and ``UnifiedToolOutput.failure(...)`` is a
  Pydantic model — so it fell through to ``bool(raw_result)``, always True,
  and a loop failing every call bought itself iterations up to the ceiling.
  Its own docstring forbids exactly that.
"""

from __future__ import annotations

import pytest

from src.domains.agents.nodes.react_nodes import _is_productive_result
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = [pytest.mark.unit]


class TestDeclaredFailureIsNotProductive:
    """Productivity buys iterations, so it must mean « the context learned »."""

    def test_a_failed_unified_output_is_not_productive(self) -> None:
        failure = UnifiedToolOutput.failure(
            message="Calendar unavailable: token expired.", error_code="AUTHENTICATION_ERROR"
        )
        assert _is_productive_result(failure) is False

    def test_a_successful_unified_output_is_productive(self) -> None:
        success = UnifiedToolOutput.data_success(
            message="3 events today", structured_data={"events": [1, 2, 3]}
        )
        assert _is_productive_result(success) is True

    def test_a_failed_dict_is_not_productive(self) -> None:
        assert _is_productive_result({"success": False, "error": "boom"}) is False

    def test_a_plain_string_is_still_productive(self) -> None:
        """A tool that answers prose said something — unchanged behaviour."""
        assert _is_productive_result("Paris: 10-22 °C") is True

    def test_none_and_empty_are_not_productive(self) -> None:
        assert _is_productive_result(None) is False
        assert _is_productive_result("") is False

    def test_an_empty_container_is_not_productive(self) -> None:
        """The docstring's own contract: an empty result teaches nothing.

        ``{}`` used to buy an iteration — the dict branch answered « no
        declared failure, therefore production » about a payload carrying
        nothing at all (ADR-303 review).
        """
        assert _is_productive_result({}) is False
        assert _is_productive_result([]) is False

    def test_a_dict_that_carries_something_is_productive(self) -> None:
        assert _is_productive_result({"events": [1, 2]}) is True
        assert _is_productive_result({"success": True, "data": {}}) is True


class TestFailureIsMarkedOnTheToolMessage:
    """The verdict travels with the message, never inferred from its words."""

    @staticmethod
    def _status_of(result: object) -> str:
        from src.domains.agents.nodes.react_nodes import _tool_message_status

        return _tool_message_status(result)

    def test_a_declared_failure_is_marked_error(self) -> None:
        failure = UnifiedToolOutput.failure(message="Token expired.", error_code="AUTH")
        assert self._status_of(failure) == "error"

    def test_a_failed_dict_is_marked_error(self) -> None:
        assert self._status_of({"success": False, "error": "boom"}) == "error"

    def test_a_success_is_marked_success(self) -> None:
        assert self._status_of(UnifiedToolOutput.data_success(message="ok")) == "success"

    def test_prose_is_marked_success(self) -> None:
        """A tool that answers a plain string did not fail."""
        assert self._status_of("Paris: 10-22 °C") == "success"
