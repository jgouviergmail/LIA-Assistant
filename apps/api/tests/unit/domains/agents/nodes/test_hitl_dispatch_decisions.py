"""HITL dispatch — what the user is shown, and what their answer authorises.

These four pure functions sit on either side of the interrupt that guards every
side effect: two build the payload the confirmation card renders, two read the
answer back and decide whether the action happens.

Their failure mode is not an exception. A payload that loses a field shows a
card confirming nothing identifiable; a decision reader that misreads an answer
either performs an action the user refused, or refuses one they approved. Both
are silent.

Two properties are asserted throughout, because they are what makes this layer
safe rather than merely functional:

* **Fail-closed.** Anything the reader does not understand — a missing action,
  an unknown verb, a mismatched draft id — resolves to ``cancel``. Nothing is
  ever performed by default.
* **Identity.** A decision only authorises the draft it names. Confirming
  draft A must never execute draft B.

The entity-disambiguation branch of this module is deliberately NOT covered: its
only producer is ``agents/tools/entity_resolution_tool.py``, which no module in
`src/` or `tests/` imports (0 of the 96 registered tools). Testing it would
manufacture coverage on a path no user can reach.
"""

from typing import Any

import pytest

from src.domains.agents.nodes.hitl_dispatch_node import (
    _build_draft_critique_payload,
    _build_tool_confirmation_payload,
    _process_draft_action,
    _process_tool_confirmation_decision,
)
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo
from src.domains.agents.services.hitl.protocols import HitlInteractionType

pytestmark = pytest.mark.unit


def make_draft(**overrides: Any) -> PendingDraftInfo:
    """A draft as `parallel_executor` hands it over."""
    defaults: dict[str, Any] = {
        "draft_id": "draft_abc123",
        "draft_type": "email",
        "draft_content": {"to": "jean@example.com", "subject": "RDV", "body": "Bonjour"},
        "draft_summary": "Email pour jean@example.com",
        "registry_ids": ["email_7f8a9b"],
        "tool_name": "send_email_tool",
        "step_id": "step_1",
    }
    defaults.update(overrides)
    return PendingDraftInfo(**defaults)


def only_request(payload: dict[str, Any]) -> dict[str, Any]:
    """The single action request a payload carries."""
    requests = payload["action_requests"]
    assert len(requests) == 1
    return requests[0]


# =============================================================================
# Draft critique — the payload
# =============================================================================


class TestBuildDraftCritiquePayload:
    def test_carries_everything_the_card_needs_to_identify_the_draft(self) -> None:
        draft = make_draft()

        request = only_request(_build_draft_critique_payload(draft))

        assert request["type"] == "draft_critique"
        assert request["draft_id"] == "draft_abc123"
        assert request["draft_type"] == "email"
        assert request["draft_content"] == draft.draft_content
        assert request["registry_ids"] == ["email_7f8a9b"]
        assert request["tool_name"] == "send_email_tool"
        assert request["step_id"] == "step_1"

    def test_declares_the_interaction_type_the_registry_dispatches_on(self) -> None:
        payload = _build_draft_critique_payload(make_draft())

        assert payload["hitl_type"] == HitlInteractionType.DRAFT_CRITIQUE.value
        assert payload["generate_question_streaming"] is True

    def test_carries_the_language_the_question_is_generated_in(self) -> None:
        payload = _build_draft_critique_payload(make_draft(), user_language="de")

        assert payload["user_language"] == "de"

    def test_a_single_draft_carries_no_batch_context(self) -> None:
        # `batch_total` present would switch the card to the static batch
        # rendering and drop the per-draft LLM critique.
        request = only_request(_build_draft_critique_payload(make_draft()))

        assert "batch_total" not in request
        assert "batch_drafts" not in request

    def test_a_batch_announces_its_size_and_carries_every_item(self) -> None:
        # The count is what the user reads before approving a bulk action — a
        # wrong one authorises more than they think.
        drafts = [{"to": "a@b.c"}, {"to": "d@e.f"}, {"to": "g@h.i"}]

        request = only_request(
            _build_draft_critique_payload(make_draft(), batch_total=3, batch_drafts=drafts)
        )

        assert request["batch_total"] == 3
        assert request["batch_drafts"] == drafts

    def test_a_batch_without_its_items_degrades_to_an_empty_list(self) -> None:
        request = only_request(_build_draft_critique_payload(make_draft(), batch_total=2))

        assert request["batch_drafts"] == []

    def test_a_clarification_question_is_surfaced_with_the_redisplayed_draft(self) -> None:
        # After a "clarify" decision the question used to be logged and never
        # shown, leaving the user staring at the same draft with no hint.
        request = only_request(
            _build_draft_critique_payload(make_draft(), clarification_question="Quel jour ?")
        )

        assert request["clarification_question"] == "Quel jour ?"

    @pytest.mark.parametrize("empty", [None, ""])
    def test_no_clarification_means_no_key_at_all(self, empty: str | None) -> None:
        request = only_request(
            _build_draft_critique_payload(make_draft(), clarification_question=empty)
        )

        assert "clarification_question" not in request


# =============================================================================
# Draft critique — the decision
# =============================================================================


class TestProcessDraftAction:
    def test_a_confirmation_authorises_the_action(self) -> None:
        action, content, error = _process_draft_action(
            {"action": "confirm", "draft_id": "draft_abc123"}, make_draft()
        )

        assert (action, content, error) == ("confirm", None, None)

    def test_a_cancellation_is_reported_without_an_error(self) -> None:
        action, content, error = _process_draft_action(
            {"action": "cancel", "draft_id": "draft_abc123"}, make_draft()
        )

        assert (action, content, error) == ("cancel", None, None)

    def test_an_edit_carries_the_new_content(self) -> None:
        updated = {"subject": "RDV décalé"}

        action, content, error = _process_draft_action(
            {"action": "edit", "draft_id": "draft_abc123", "updated_content": updated},
            make_draft(),
        )

        assert action == "edit"
        assert content == updated
        assert error is None

    @pytest.mark.parametrize("empty", [{}, None])
    def test_an_edit_with_nothing_changed_re_presents_the_original(self, empty: Any) -> None:
        draft = make_draft()

        action, content, _ = _process_draft_action(
            {"action": "edit", "draft_id": draft.draft_id, "updated_content": empty}, draft
        )

        assert action == "edit"
        assert content == draft.draft_content

    def test_a_decision_naming_another_draft_cancels_instead_of_acting(self) -> None:
        # The identity guard: confirming draft A must never execute draft B.
        action, content, error = _process_draft_action(
            {"action": "confirm", "draft_id": "draft_SOMETHING_ELSE"}, make_draft()
        )

        assert action == "cancel"
        assert content is None
        assert error is not None
        assert "draft_abc123" in error

    def test_a_null_draft_id_is_a_mismatch_not_a_pass(self) -> None:
        # `.get(key, default)` returns None for an EXPLICIT null — the default
        # only covers an absent key. Fail-closed either way.
        action, _, error = _process_draft_action(
            {"action": "confirm", "draft_id": None}, make_draft()
        )

        assert action == "cancel"
        assert error is not None

    def test_a_decision_without_a_draft_id_is_applied_to_the_pending_one(self) -> None:
        # CHARACTERIZED: an absent id defaults to the pending draft, so the
        # identity guard only bites when an id is explicitly wrong. The frontend
        # always sends one (ADR-132 `build_structured_decision`).
        action, _, error = _process_draft_action({"action": "confirm"}, make_draft())

        assert action == "confirm"
        assert error is None

    @pytest.mark.parametrize(
        "decision",
        [
            {},
            {"draft_id": "draft_abc123"},
            {"action": None, "draft_id": "draft_abc123"},
            {"action": "", "draft_id": "draft_abc123"},
            {"action": "approve", "draft_id": "draft_abc123"},
            {"action": "CONFIRM", "draft_id": "draft_abc123"},
            {"action": "delete_everything", "draft_id": "draft_abc123"},
        ],
    )
    def test_anything_not_understood_cancels(self, decision: dict[str, Any]) -> None:
        # Fail-closed: no verb this reader does not know may perform an action.
        # Note the casing — "CONFIRM" is NOT accepted, the contract is exact.
        action, content, _ = _process_draft_action(decision, make_draft())

        assert action == "cancel"
        assert content is None

    def test_an_unknown_verb_says_which_one_it_refused(self) -> None:
        _, _, error = _process_draft_action(
            {"action": "yolo", "draft_id": "draft_abc123"}, make_draft()
        )

        assert error is not None
        assert "yolo" in error


# =============================================================================
# Tool confirmation — the payload
# =============================================================================


class TestBuildToolConfirmationPayload:
    def test_names_the_tool_and_its_arguments(self) -> None:
        # The arguments ARE the confirmation: "delete the label" means nothing
        # without knowing which label.
        context = {
            "tool_name": "delete_label_tool",
            "tool_args": {"label_id": "Label_9", "label_name": "pro/capge"},
            "confirmation_message": "Supprimer le label pro/capge ?",
            "step_id": "step_2",
        }

        request = only_request(_build_tool_confirmation_payload(context))

        assert request["type"] == "tool_confirmation"
        assert request["tool_name"] == "delete_label_tool"
        assert request["tool_args"] == context["tool_args"]
        assert request["confirmation_message"] == context["confirmation_message"]
        assert request["step_id"] == "step_2"

    def test_declares_its_interaction_type(self) -> None:
        payload = _build_tool_confirmation_payload({"tool_name": "t"})

        assert payload["hitl_type"] == HitlInteractionType.TOOL_CONFIRMATION.value
        assert payload["generate_question_streaming"] is True

    def test_an_empty_context_still_produces_a_well_formed_payload(self) -> None:
        # A malformed context must not crash the node before the interrupt: the
        # user would get no card at all rather than a degraded one.
        request = only_request(_build_tool_confirmation_payload({}))

        assert request["tool_name"] == ""
        assert request["tool_args"] == {}
        assert request["confirmation_message"] == ""
        assert request["step_id"] is None

    def test_carries_the_user_language(self) -> None:
        payload = _build_tool_confirmation_payload({"tool_name": "t"}, user_language="zh-CN")

        assert payload["user_language"] == "zh-CN"


# =============================================================================
# Tool confirmation — the decision
# =============================================================================


class TestProcessToolConfirmationDecision:
    def test_a_confirmation_authorises_the_tool(self) -> None:
        action, error = _process_tool_confirmation_decision(
            {"action": "confirm"}, {"tool_name": "delete_label_tool"}
        )

        assert (action, error) == ("confirm", None)

    def test_a_cancellation_is_reported_without_an_error(self) -> None:
        action, error = _process_tool_confirmation_decision(
            {"action": "cancel"}, {"tool_name": "delete_label_tool"}
        )

        assert (action, error) == ("cancel", None)

    @pytest.mark.parametrize(
        "decision",
        [
            {},
            {"action": None},
            {"action": ""},
            {"action": "yes"},
            {"action": "CONFIRM"},
            {"action": "ok"},
        ],
    )
    def test_anything_not_understood_cancels(self, decision: dict[str, Any]) -> None:
        action, _ = _process_tool_confirmation_decision(decision, {"tool_name": "t"})

        assert action == "cancel"

    def test_an_unknown_verb_says_which_one_it_refused(self) -> None:
        _, error = _process_tool_confirmation_decision({"action": "maybe"}, {"tool_name": "t"})

        assert error is not None
        assert "maybe" in error

    def test_a_missing_action_cancels_quietly(self) -> None:
        # An absent key is the default path, not an anomaly: no error text.
        action, error = _process_tool_confirmation_decision({}, {"tool_name": "t"})

        assert (action, error) == ("cancel", None)


# =============================================================================
# The property that matters across both readers
# =============================================================================


class TestFailClosedInvariant:
    """No decision reader may perform an action it did not understand."""

    UNKNOWN_DECISIONS: list[dict[str, Any]] = [
        {},
        {"action": None},
        {"action": ""},
        {"action": "confirmed"},
        {"action": "Confirm"},
        {"action": 1},
        {"action": ["confirm"]},
    ]

    @pytest.mark.parametrize("decision", UNKNOWN_DECISIONS)
    def test_the_draft_reader_never_confirms_what_it_cannot_read(
        self, decision: dict[str, Any]
    ) -> None:
        decision = {**decision, "draft_id": "draft_abc123"}

        assert _process_draft_action(decision, make_draft())[0] != "confirm"

    @pytest.mark.parametrize("decision", UNKNOWN_DECISIONS)
    def test_the_tool_reader_never_confirms_what_it_cannot_read(
        self, decision: dict[str, Any]
    ) -> None:
        assert _process_tool_confirmation_decision(decision, {"tool_name": "t"})[0] != "confirm"
