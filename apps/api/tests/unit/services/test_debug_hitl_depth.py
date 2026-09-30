"""What the panel says about a human-in-the-loop turn (B8, lot 7.3).

The section carried five booleans — interrupted, approved, cancelled — and
named the tool. It never said WHICH draft the person was shown, so two runs of
the same tool on different content were indistinguishable, and an « edit » loop
that went round three times looked exactly like one that went round once.

Three additions, and one deliberate refusal:

- **the draft's identity**: its type and its id, plus how many edit passes it
  took and the clarification LIA asked for;
- **the digest of what was shown**, which is the handle that says « the person
  approved THIS » — the same digest the pre-approval replay compares;
- **never the draft's CONTENT.** It holds recipients, subjects and message
  bodies, and the digest answers the correlation question without answering
  that one. The panel is not admin-only either — a superuser opens it directly,
  anyone else behind two switches — so the cheaper answer is the right one.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.streaming import debug_metrics_stages as stages

pytestmark = pytest.mark.unit


def _hitl(state: dict, interrupt: dict | None = None) -> dict | None:
    payload: dict = {}
    stages.build_hitl(payload, state, interrupt)
    return payload.get("hitl")


class TestTheDraftIsIdentified:
    def test_it_names_the_draft_type_and_id(self) -> None:
        hitl = _hitl(
            {
                "draft_action_result": {
                    "draft_id": "d-42",
                    "draft_type": "email_send",
                    "action": "confirm",
                }
            }
        )

        assert hitl is not None
        assert hitl["draft_type"] == "email_send"
        assert hitl["draft_id"] == "d-42"
        assert hitl["draft_action"] == "confirm"

    def test_it_digests_what_the_person_was_actually_shown(self) -> None:
        first = _hitl(
            {"draft_action_result": {"action": "confirm", "draft_content": {"to": "a@b.c"}}}
        )
        second = _hitl(
            {"draft_action_result": {"action": "confirm", "draft_content": {"to": "d@e.f"}}}
        )

        assert first is not None and second is not None
        # Two runs of the same tool on different content must not look alike.
        assert first["draft_digest"] != second["draft_digest"]

    def test_the_same_content_digests_the_same_way(self) -> None:
        content = {"to": "a@b.c", "subject": "Hello"}
        first = _hitl({"draft_action_result": {"action": "confirm", "draft_content": content}})
        second = _hitl(
            {"draft_action_result": {"action": "confirm", "draft_content": dict(content)}}
        )

        assert first is not None and second is not None
        assert first["draft_digest"] == second["draft_digest"]

    def test_it_counts_the_edit_passes(self) -> None:
        # An edit loop that went round three times looked exactly like one that
        # went round once.
        hitl = _hitl({"draft_action_result": {"action": "edit"}, "draft_edit_iteration": 3})

        assert hitl is not None
        assert hitl["draft_edit_iterations"] == 3

    def test_it_carries_the_question_lia_asked(self) -> None:
        hitl = _hitl(
            {
                "draft_action_result": {"action": "edit"},
                "draft_clarification_question": "Which address?",
            }
        )

        assert hitl is not None
        assert hitl["draft_clarification_question"] == "Which address?"


class TestTheContentNeverLeaves:
    def test_no_key_of_the_payload_holds_the_draft_itself(self) -> None:
        # A body printed here would be carried by the payload of every turn
        # that showed a draft, for no question the digest cannot answer.
        secret = "Dear Marie, about your salary review"
        hitl = _hitl(
            {
                "draft_action_result": {
                    "action": "confirm",
                    "draft_content": {"body": secret, "to": "marie@example.com"},
                }
            }
        )

        assert hitl is not None
        assert secret not in repr(hitl)
        assert "marie@example.com" not in repr(hitl)


class TestItStillSaysWhatItSaidBefore:
    def test_the_existing_flags_are_untouched(self) -> None:
        hitl = _hitl(
            {"plan_approved": True, "clarification_response": "yes", "clarification_field": "date"},
            {"action_type": "tool_confirmation", "tool_name": "send_email_tool"},
        )

        assert hitl is not None
        assert hitl["interrupted"] is True
        assert hitl["interrupt_action_type"] == "tool_confirmation"
        assert hitl["interrupt_tool_name"] == "send_email_tool"
        assert hitl["plan_approved"] is True
        assert hitl["clarification_response"] == "yes"
        assert hitl["clarification_field"] == "date"

    def test_a_turn_with_no_human_in_it_draws_no_section(self) -> None:
        assert _hitl({}) is None

    def test_the_gate_s_own_approval_is_no_human_decision(self) -> None:
        """The gate writes True on every plan it passes: that alone is no
        section — it used to draw « User decision: plan approved » on turns
        where nobody decided anything."""
        assert _hitl({"plan_approved": True}) is None

    def test_a_refusal_is_the_person_s_and_is_drawn(self) -> None:
        hitl = _hitl({"plan_approved": False})

        assert hitl is not None
        assert hitl["plan_approved"] is False

    def test_no_verdict_travels_as_none_never_as_a_refusal(self) -> None:
        hitl = _hitl({"plan_approved": None, "clarification_response": "yes"})

        assert hitl is not None
        assert hitl["plan_approved"] is None

    def test_the_decision_the_response_cleared_still_reaches_the_panel(self) -> None:
        """The final state never carries it — the response node clears it once
        executed — so the rows were null in production: the stream captures it."""
        from src.domains.agents.services.streaming.service import StreamingService

        service = StreamingService.__new__(StreamingService)
        service._debug_panel_enabled = True
        service._cached_draft_action_result = None
        service._cached_tool_scores = None
        service._cached_filtered_catalogue = None
        decision = {"action": "confirm", "draft_type": "email", "draft_id": "d-1"}
        # The method swallows its own errors: a crash inside it must fail HERE.
        with patch("src.domains.agents.services.streaming.service.logger") as log:
            service._cache_debug_data({"draft_action_result": decision})
            service._cache_debug_data({"draft_action_result": None})  # the response's
        failures = [c for c in log.method_calls if c[0] in {"warning", "error", "exception"}]
        assert failures == []

        assert service._cached_draft_action_result == decision
        service.tracker = None
        service.hitl_interrupt_info = None
        service.user_id = None
        builder = MagicMock()
        with patch(
            "src.domains.agents.services.streaming.debug_metrics_builder.DebugMetricsBuilder",
            builder,
        ):
            service._add_debug_metrics_sections({}, {"draft_action_result": None}, "r")
        hitl = _hitl(builder.return_value.build.call_args.args[1])
        assert hitl is not None and hitl["draft_type"] == "email"

    def test_a_draft_decision_alone_is_enough_to_draw_the_section(self) -> None:
        # Before this, a confirmed draft with no interrupt and no plan approval
        # produced NO section at all: the one turn where a person acted was the
        # one the panel said nothing about.
        assert _hitl({"draft_action_result": {"action": "confirm"}}) is not None
