"""The FOR_EACH HITL payload must claim the measured count, not the cap.

Prod 2026-08-17 (request d4d2c6ed): the interrupt payload said "Mutation
operation (send_peer_message_tool) will execute 10 times" while
``total_affected`` was 1 — the reason had been computed BEFORE pre-execution,
with ``iteration_count=step.for_each_max``, and never refreshed once the real
counts were known. The executor already recomputes the scope with the real
count at execution time (``for_each_scope_check_at_execution`` logged
"1 times"); the payload the user's confirmation is based on was the one place
still carrying the cap. ADR-185: a count shown is a claim — exact, or absent.

``refresh_for_each_scope_claims`` re-runs the scope detector with the
measured counts and stamps ``item_count`` on each step dict. It never touches
the approval DECISION (membership of the HITL list was settled before
pre-execution and stays settled) — only the claims.
"""

from __future__ import annotations

import pytest

from src.domains.agents.nodes.for_each_hitl_prep import (
    refresh_for_each_scope_claims,
)

pytestmark = pytest.mark.unit


def _mutation_step(**overrides: object) -> dict[str, object]:
    step = {
        "step_id": "step_2",
        "tool_name": "send_peer_message_tool",
        "for_each_max": 10,
        "for_each_source": "$steps.step_1.contacts",
        "is_mutation": True,
        "risk_level": "high",
        "reason": "Mutation operation (send_peer_message_tool) will execute 10 times",
    }
    step.update(overrides)
    return step


class TestRefreshForEachScopeClaims:
    def test_reason_claims_the_measured_count(self) -> None:
        """The prod payload itself: cap 10, measured 1."""
        steps = [_mutation_step()]

        refresh_for_each_scope_claims(steps, {"$steps.step_1.contacts": 1})

        assert "will execute 1 times" in steps[0]["reason"]
        assert "10 times" not in steps[0]["reason"]

    def test_item_count_is_stamped_for_the_message_builder(self) -> None:
        steps = [_mutation_step()]

        refresh_for_each_scope_claims(steps, {"$steps.step_1.contacts": 1})

        assert steps[0]["item_count"] == 1

    def test_unmeasured_source_is_left_untouched(self) -> None:
        """No measurement → no claim to correct, and no invented one."""
        steps = [_mutation_step()]

        refresh_for_each_scope_claims(steps, {"$steps.other.events": 4})

        assert steps[0]["reason"].endswith("10 times")
        assert "item_count" not in steps[0]

    def test_zero_count_is_left_untouched(self) -> None:
        """total_affected == 0 skips the HITL entirely — nothing to restate."""
        steps = [_mutation_step()]

        refresh_for_each_scope_claims(steps, {"$steps.step_1.contacts": 0})

        assert "item_count" not in steps[0]

    def test_membership_is_never_touched(self) -> None:
        """A read-only step whose measured count falls below every threshold
        keeps its place in the HITL list — the decision was made before
        pre-execution; only the claims are refreshed."""
        steps = [
            _mutation_step(
                tool_name="get_route_tool",
                is_mutation=False,
                risk_level="medium",
                reason="Large iteration count (10 items)",
            )
        ]

        refresh_for_each_scope_claims(steps, {"$steps.step_1.contacts": 2})

        assert len(steps) == 1
        assert steps[0]["item_count"] == 2
        assert "10 items" not in steps[0]["reason"]
