"""Rejection observability of the initiative read-only validation (lot 0).

Prod showed 2 `decision=act` evaluations for 0 executed actions with no
counter explaining the gap — the only trace was a logger.warning. These tests
pin the `initiative_actions_rejected_total{reason}` counter emitted by
``_validate_read_only`` (reasons: non_readonly | duplicate).
"""

from __future__ import annotations

from types import SimpleNamespace

from src.domains.agents.nodes.initiative_node import InitiativeAction
from src.domains.agents.nodes.initiative_plan import _validate_read_only
from src.domains.agents.orchestration.plan_schemas import ParameterItem, ParameterValue
from src.infrastructure.observability.metrics_agents import (
    initiative_actions_rejected_total,
)


def _reason_value(reason: str) -> float:
    return initiative_actions_rejected_total.labels(reason=reason)._value.get()


def _manifest(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _action(tool_name: str, **params: str) -> InitiativeAction:
    return InitiativeAction(
        tool_name=tool_name,
        parameters=[
            ParameterItem(name=k, value=ParameterValue(string_value=v)) for k, v in params.items()
        ],
        rationale="test",
    )


class TestRejectionCounter:
    def test_non_readonly_rejection_is_counted(self) -> None:
        before = _reason_value("non_readonly")
        validated = _validate_read_only(
            [_action("send_email_tool", to="x@y.z")],
            [_manifest("get_events_tool")],
        )
        assert validated == []
        assert _reason_value("non_readonly") == before + 1

    def test_duplicate_rejection_is_counted(self) -> None:
        before = _reason_value("duplicate")
        validated = _validate_read_only(
            [_action("get_events_tool", day="today"), _action("get_events_tool", day="today")],
            [_manifest("get_events_tool")],
        )
        assert len(validated) == 1
        assert _reason_value("duplicate") == before + 1

    def test_valid_actions_touch_no_counter(self) -> None:
        before_nr = _reason_value("non_readonly")
        before_dup = _reason_value("duplicate")
        validated = _validate_read_only(
            [_action("get_events_tool", day="today")],
            [_manifest("get_events_tool")],
        )
        assert len(validated) == 1
        assert _reason_value("non_readonly") == before_nr
        assert _reason_value("duplicate") == before_dup
