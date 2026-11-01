"""What a tool's own choice changes in the synthesis, and what the page is told (spec D5, D6).

Each tool says the choice that applies, whether a « never » is suspended, and what
« by default » gives — so the page can offer the three choices stating the third. A
candidate choice is previewed like any other change: what LIA would stop asking about
is the same oracle the alert and the assistant read, at every level including the tool.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.core.config import settings
from src.domains.user_mcp.behavior import (
    BehaviorInputs,
    describe_server_behavior,
    questions_lost,
    with_candidates,
)
from src.domains.user_mcp.behavior_schemas import BehaviorNote, BehaviorPreviewRequest
from src.infrastructure.mcp.confirmation import (
    ConfirmationReason,
    StoredToolChoice,
    ToolChoice,
    declaration_fingerprint,
)

pytestmark = pytest.mark.unit

_DELETE: dict[str, Any] = {
    "name": "delete_note",
    "input_schema": {"type": "object"},
    "annotations": {"destructive_hint": True},
}
_READ: dict[str, Any] = {
    "name": "read_note",
    "input_schema": {"type": "object"},
    "annotations": {"read_only_hint": True},
}


@pytest.fixture(autouse=True)
def _instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mcp_hitl_required", False)
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", True)


def _inputs(
    *, hitl: bool | None = None, choices: dict[str, StoredToolChoice] | None = None
) -> BehaviorInputs:
    return BehaviorInputs(
        server_id=UUID(int=1),
        server_name="Notes",
        hitl_required=hitl,
        iterative_mode=False,
        react_expand_iterative=None,
        tools=(_DELETE, _READ),
        tool_choices=choices or {},
    )


def _never(tool: dict[str, Any]) -> StoredToolChoice:
    return StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(tool))


def _tool(behavior: Any, name: str) -> Any:
    return next(tool for tool in behavior.tools if tool.tool_name == name)


class TestEachToolSaysItsChoice:
    def test_never_stops_the_question_and_says_why(self) -> None:
        behavior = describe_server_behavior(
            _inputs(hitl=True, choices={"delete_note": _never(_DELETE)}), None
        )

        tool = _tool(behavior, "delete_note")
        assert tool.asks is False
        assert tool.reason is ConfirmationReason.TOOL_NEVER
        assert tool.choice is ToolChoice.NEVER
        assert tool.default_asks is True, "« by default » would ask: the server says always"
        assert "delete_note" not in behavior.unattended_refused, "it runs when nobody is there"

    def test_always_asks_a_read_and_says_why(self) -> None:
        always = StoredToolChoice(ToolChoice.ALWAYS, declaration_fingerprint(_READ))
        behavior = describe_server_behavior(_inputs(choices={"read_note": always}), None)

        tool = _tool(behavior, "read_note")
        assert tool.asks is True
        assert tool.reason is ConfirmationReason.TOOL_ALWAYS
        assert tool.default_asks is False

    def test_a_suspended_never_is_said_on_the_tool_and_on_the_server(self) -> None:
        stale = StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(_READ))
        behavior = describe_server_behavior(
            _inputs(hitl=True, choices={"delete_note": stale}), None
        )

        tool = _tool(behavior, "delete_note")
        assert tool.choice is None and tool.suspended is True
        assert tool.asks is True
        assert tool.reason is ConfirmationReason.SERVER_ALWAYS
        assert BehaviorNote.CHOICE_SUSPENDED in behavior.notes

    def test_without_a_choice_nothing_is_said_about_one(self) -> None:
        behavior = describe_server_behavior(_inputs(), None)

        assert all(t.choice is None and not t.suspended for t in behavior.tools)
        assert BehaviorNote.CHOICE_SUSPENDED not in behavior.notes


class TestACandidateChoiceIsPreviewed:
    def test_never_on_an_asked_tool_loses_its_questions(self) -> None:
        stored = _inputs(hitl=True)
        candidate = with_candidates(
            stored, BehaviorPreviewRequest(tool_choices={"delete_note": ToolChoice.NEVER})
        )

        lost = questions_lost(
            stored,
            describe_server_behavior(stored, None),
            describe_server_behavior(candidate, None),
        )

        assert [loss.tool_name for loss in lost] == ["delete_note"]
        assert candidate.tool_choices["delete_note"] == _never(
            _DELETE
        ), "a candidate binds to the declaration the catalogue lists now"

    def test_back_to_default_from_always_loses_what_the_default_does_not_ask(self) -> None:
        always = StoredToolChoice(ToolChoice.ALWAYS, declaration_fingerprint(_READ))
        stored = _inputs(choices={"read_note": always})
        candidate = with_candidates(
            stored, BehaviorPreviewRequest(tool_choices={"read_note": None})
        )

        lost = questions_lost(
            stored,
            describe_server_behavior(stored, None),
            describe_server_behavior(candidate, None),
        )

        assert {loss.tool_name for loss in lost} == {"read_note"}

    def test_always_loses_nothing_and_an_unknown_tool_changes_nothing(self) -> None:
        stored = _inputs()
        candidate = with_candidates(
            stored,
            BehaviorPreviewRequest(
                tool_choices={"read_note": ToolChoice.ALWAYS, "absent": ToolChoice.NEVER}
            ),
        )

        assert "absent" not in candidate.tool_choices
        assert (
            questions_lost(
                stored,
                describe_server_behavior(stored, None),
                describe_server_behavior(candidate, None),
            )
            == []
        )

    def test_a_tool_choice_survives_a_strategy_change(self) -> None:
        """Strategy previews read the tools' choices: a never'd tool loses nothing more."""
        stored = _inputs(choices={"delete_note": _never(_DELETE)})

        lost = questions_lost(
            stored,
            describe_server_behavior(stored, True),
            describe_server_behavior(stored, False),
        )

        assert {loss.tool_name for loss in lost} == {"read_note"}


class TestTheRequestIsStrict:
    def test_a_choice_outside_the_vocabulary_is_refused(self) -> None:
        with pytest.raises(ValueError):
            BehaviorPreviewRequest(tool_choices={"read_note": "sometimes"})  # type: ignore[dict-item]
