"""Golden characterization of ``OrchestrationService._parse_approval_decision``
(audit F015, Target B).

This CC-59 dispatcher routes a user's HITL reply to a resume payload whose exact
shape depends on ``interrupt_type`` (draft_critique / for_each_confirmation /
tool_confirmation / generic). Each branch mixes a FR/EN fast-path, an LLM
classifier call, and a decision->payload mapping. These tests pin the exact
current payloads for every branch x decision (and every fallback) BEFORE the
logic is extracted into ``orchestration/approval_decision.py`` — so any behavior
drift during decomposition fails loudly here.

Redis (HITLStore) and the LLM classifier are mocked; no network is touched.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_DRAFT_ID,
    FIELD_INTERRUPT_DATA,
    FIELD_TYPE,
)
from src.domains.agents.constants import HITL_DECISION_NEW_REQUEST
from src.domains.agents.services.orchestration.service import OrchestrationService

CLASSIFIER_PATH = "src.domains.agents.services.hitl_classifier.HitlResponseClassifier"


def _pending(interrupt_type: str | None, *, draft_id: str | None = None) -> dict | None:
    """Build a pending-HITL payload with a single action request of a given type.

    ``interrupt_type=None`` yields an empty action-request list (stale HITL).
    """
    if interrupt_type is None:
        return {FIELD_INTERRUPT_DATA: {FIELD_ACTION_REQUESTS: []}}
    action: dict = {FIELD_TYPE: interrupt_type}
    if draft_id is not None:
        action[FIELD_DRAFT_ID] = draft_id
    return {FIELD_INTERRUPT_DATA: {FIELD_ACTION_REQUESTS: [action]}}


def _classification(
    decision: str,
    *,
    reasoning: str | None = None,
    edited_params: dict | None = None,
    clarification_question: str | None = None,
    confidence: float = 0.9,
) -> SimpleNamespace:
    """Mimic a HitlResponseClassifier result object."""
    return SimpleNamespace(
        decision=decision,
        reasoning=reasoning,
        edited_params=edited_params,
        clarification_question=clarification_question,
        confidence=confidence,
    )


async def _parse(
    message: str,
    pending: dict | None,
    *,
    classification: SimpleNamespace | None = None,
    classifier_error: Exception | None = None,
) -> dict:
    """Run _parse_approval_decision with mocked Redis + classifier."""
    svc = OrchestrationService()
    store = MagicMock()
    store.get_interrupt = AsyncMock(return_value=pending)

    classifier_instance = MagicMock()
    if classifier_error is not None:
        classifier_instance.classify = AsyncMock(side_effect=classifier_error)
    else:
        classifier_instance.classify = AsyncMock(return_value=classification)

    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.HITLStore", return_value=store),
        patch(CLASSIFIER_PATH, return_value=classifier_instance),
    ):
        return await svc._parse_approval_decision(
            user_message=message, conversation_id=uuid4(), run_id="test"
        )


# ============================================================================
# Context / stale HITL
# ============================================================================


class TestContext:
    async def test_empty_action_context_is_new_request(self):
        result = await _parse("ok", _pending(None))
        assert result["decision"] == HITL_DECISION_NEW_REQUEST
        assert result["user_message"] == "ok"

    async def test_none_pending_is_new_request(self):
        result = await _parse("whatever", None)
        assert result["decision"] == HITL_DECISION_NEW_REQUEST

    async def test_redis_failure_degrades_to_new_request(self):
        """A Redis failure during context fetch degrades to NEW_REQUEST, no crash.

        Regression: the pre-extraction code left ``pending_data`` unbound on the
        Redis-error path and raised ``UnboundLocalError`` in the stale-HITL log
        (``has_pending_data=pending_data is not None``). Fixed by initializing
        ``pending_data`` in ``_fetch_interrupt_context`` — the graceful-degradation
        path the ``except`` was written for now actually degrades gracefully.
        """
        svc = OrchestrationService()
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ):
            result = await svc._parse_approval_decision(
                user_message="ok", conversation_id=uuid4(), run_id="test"
            )
        assert result["decision"] == HITL_DECISION_NEW_REQUEST


# ============================================================================
# draft_critique branch -> {"action": ...}
# ============================================================================


class TestDraftCritique:
    async def test_confirm_word_fast_path(self):
        result = await _parse("envoie", _pending("draft_critique", draft_id="d1"))
        assert result == {"action": "confirm", "draft_id": "d1"}

    async def test_cancel_word_fast_path(self):
        result = await _parse("non", _pending("draft_critique", draft_id="d1"))
        assert result == {"action": "cancel", "draft_id": "d1"}

    async def test_classifier_approve(self):
        result = await _parse(
            "looks good to me",
            _pending("draft_critique", draft_id="d1"),
            classification=_classification("APPROVE"),
        )
        assert result == {"action": "confirm", "draft_id": "d1"}

    async def test_classifier_reject(self):
        result = await _parse(
            "no thanks, drop it",
            _pending("draft_critique", draft_id="d1"),
            classification=_classification("REJECT", reasoning="declined"),
        )
        assert result == {"action": "cancel", "draft_id": "d1", "reason": "declined"}

    async def test_classifier_edit_with_instructions(self):
        result = await _parse(
            "make it shorter",
            _pending("draft_critique", draft_id="d1"),
            classification=_classification(
                "EDIT", edited_params={"modification_instructions": "shorten it"}
            ),
        )
        assert result == {
            "action": "edit",
            "draft_id": "d1",
            "modification_instructions": "shorten it",
        }

    async def test_classifier_edit_without_params_falls_back_to_message(self):
        result = await _parse(
            "use their work email",
            _pending("draft_critique", draft_id="d1"),
            classification=_classification("EDIT", edited_params=None),
        )
        assert result == {
            "action": "edit",
            "draft_id": "d1",
            "modification_instructions": "use their work email",
        }

    async def test_classifier_ambiguous_maps_to_clarify(self):
        result = await _parse(
            "hmm",
            _pending("draft_critique", draft_id="d1"),
            classification=_classification(
                "AMBIGUOUS", clarification_question="What should change?"
            ),
        )
        assert result == {
            "action": "clarify",
            "draft_id": "d1",
            "clarification_question": "What should change?",
        }

    async def test_classifier_replan_converted_to_edit(self):
        result = await _parse(
            "rather call them",
            _pending("draft_critique", draft_id="d1"),
            classification=_classification(
                "REPLAN", edited_params={"reformulated_intent": "call instead"}
            ),
        )
        assert result == {
            "action": "edit",
            "draft_id": "d1",
            "modification_instructions": "call instead",
        }

    async def test_classifier_unknown_decision_maps_to_cancel(self):
        result = await _parse(
            "???",
            _pending("draft_critique", draft_id="d1"),
            classification=_classification("WEIRD"),
        )
        assert result["action"] == "cancel"
        assert result["draft_id"] == "d1"
        assert "WEIRD" in result["reason"]

    async def test_classifier_error_falls_back_to_edit(self):
        result = await _parse(
            "use their carven email",
            _pending("draft_critique", draft_id="d1"),
            classifier_error=RuntimeError("boom"),
        )
        assert result == {
            "action": "edit",
            "draft_id": "d1",
            "modification_instructions": "use their carven email",
        }


# ============================================================================
# for_each_confirmation branch -> {"decision": ...}
# ============================================================================


class TestForEachConfirmation:
    async def test_classifier_approve(self):
        result = await _parse(
            "yes all of them",
            _pending("for_each_confirmation"),
            classification=_classification("APPROVE"),
        )
        assert result == {"decision": "APPROVE"}

    async def test_classifier_reject(self):
        result = await _parse(
            "cancel it",
            _pending("for_each_confirmation"),
            classification=_classification("REJECT", reasoning="user cancelled"),
        )
        assert result == {"decision": "REJECT", "rejection_reason": "user cancelled"}

    async def test_classifier_edit_with_criteria(self):
        result = await _parse(
            "not the archived ones",
            _pending("for_each_confirmation"),
            classification=_classification("EDIT", edited_params={"exclude_criteria": "archived"}),
        )
        assert result == {"decision": "EDIT", "exclude_criteria": "archived"}

    async def test_classifier_edit_without_criteria_uses_message(self):
        result = await _parse(
            "skip the drafts",
            _pending("for_each_confirmation"),
            classification=_classification("EDIT", edited_params=None),
        )
        assert result == {"decision": "EDIT", "exclude_criteria": "skip the drafts"}

    async def test_classifier_replan_maps_to_edit_with_message(self):
        result = await _parse(
            "different set please",
            _pending("for_each_confirmation"),
            classification=_classification("REPLAN"),
        )
        assert result == {
            "decision": "EDIT",
            "exclude_criteria": "different set please",
        }

    async def test_classifier_ambiguous_maps_to_reject(self):
        result = await _parse(
            "maybe",
            _pending("for_each_confirmation"),
            classification=_classification("AMBIGUOUS", clarification_question="Which ones?"),
        )
        assert result == {"decision": "REJECT", "rejection_reason": "Which ones?"}

    async def test_classifier_unknown_maps_to_reject(self):
        result = await _parse(
            "???",
            _pending("for_each_confirmation"),
            classification=_classification("WAT"),
        )
        assert result["decision"] == "REJECT"
        assert "WAT" in result["rejection_reason"]

    async def test_classifier_error_falls_back_to_edit(self):
        result = await _parse(
            "only the recent ones",
            _pending("for_each_confirmation"),
            classifier_error=ValueError("nope"),
        )
        assert result == {
            "decision": "EDIT",
            "exclude_criteria": "only the recent ones",
        }


# ============================================================================
# tool_confirmation branch -> {"action": ...} (mutation gate, cancel default)
# ============================================================================


class TestToolConfirmation:
    async def test_confirm_word(self):
        result = await _parse("ok", _pending("tool_confirmation"))
        assert result == {"action": "confirm"}

    async def test_cancel_word(self):
        result = await _parse("annule", _pending("tool_confirmation"))
        assert result == {"action": "cancel"}

    async def test_classifier_approve_maps_to_confirm(self):
        result = await _parse(
            "go ahead and do it",
            _pending("tool_confirmation"),
            classification=_classification("APPROVE"),
        )
        assert result == {"action": "confirm"}

    async def test_classifier_non_approve_maps_to_cancel(self):
        result = await _parse(
            "not sure about that",
            _pending("tool_confirmation"),
            classification=_classification("AMBIGUOUS", reasoning="unclear"),
        )
        assert result == {"action": "cancel", "reason": "unclear"}

    async def test_classifier_error_maps_to_cancel(self):
        result = await _parse(
            "do the thing carefully",
            _pending("tool_confirmation"),
            classifier_error=RuntimeError("x"),
        )
        assert result == {"action": "cancel", "reason": "classification_failed"}


# ============================================================================
# generic branch (plan approval etc.) -> {"decision": ...}
# ============================================================================


class TestGeneric:
    async def test_confirm_word_fast_path(self):
        result = await _parse("oui", _pending("plan_approval"))
        assert result == {"decision": "APPROVE"}

    async def test_cancel_word_fast_path(self):
        result = await _parse("non", _pending("plan_approval"))
        assert result == {"decision": "REJECT", "rejection_reason": "User declined"}

    async def test_clarification_passthrough(self):
        result = await _parse("paris", _pending("clarification"))
        assert result == {"clarification": "paris"}


# ============================================================================
# clarification branch — cancel intent aborts, info passes through
# ============================================================================


class TestClarificationCancel:
    """Lot 1 Phase 0: a cancel intent on a clarification must ABORT the flow.

    Runtime-proven defect: without an abort path, "annule" either fast-paths to
    a plan-level ``{"decision": "REJECT"}`` the clarification_node ignores
    (bare word), or passes through as clarification text the planner dutifully
    replans with (full phrase) — both loop back into the same interrupt.
    """

    async def test_bare_cancel_word_aborts(self):
        result = await _parse("annule", _pending("clarification"))
        assert result == {"clarification": "annule", "cancelled": True}

    async def test_cancel_phrase_classified_reject_aborts(self):
        result = await _parse(
            "Non, annule cette action",
            _pending("clarification"),
            classification=_classification("REJECT", reasoning="user cancels"),
        )
        assert result == {"clarification": "Non, annule cette action", "cancelled": True}

    async def test_info_reply_passes_through_even_with_edit_classification(self):
        result = await _parse(
            "utilise jean.dupont@gmail.com",
            _pending("clarification"),
            classification=_classification("EDIT", edited_params={"to": "jean.dupont@gmail.com"}),
        )
        assert result == {"clarification": "utilise jean.dupont@gmail.com"}

    async def test_low_confidence_reject_passes_through(self):
        from src.core.config import settings

        below = settings.hitl_classifier_confidence_threshold - 0.2
        result = await _parse(
            "non pas celui-là, l'autre",
            _pending("clarification"),
            classification=_classification("REJECT", confidence=below),
        )
        assert result == {"clarification": "non pas celui-là, l'autre"}

    async def test_classifier_error_falls_back_to_passthrough(self):
        result = await _parse(
            "quelque chose de long et ambigu",
            _pending("clarification"),
            classifier_error=RuntimeError("llm down"),
        )
        assert result == {"clarification": "quelque chose de long et ambigu"}

    async def test_classifier_approve(self):
        result = await _parse(
            "sure go for it",
            _pending("plan_approval"),
            classification=_classification("APPROVE"),
        )
        assert result == {"decision": "APPROVE"}

    async def test_classifier_reject(self):
        result = await _parse(
            "no do not",
            _pending("plan_approval"),
            classification=_classification("REJECT", reasoning="user said no"),
        )
        assert result == {"decision": "REJECT", "rejection_reason": "user said no"}

    async def test_classifier_edit_builds_modifications(self):
        sentinel = [{"modification_type": "edit_params", "step_id": "step_1"}]
        with patch(
            "src.domains.agents.services.hitl.resumption_strategies."
            "_build_plan_modifications_from_classifier",
            return_value=sentinel,
        ):
            result = await _parse(
                "search for jean instead",
                _pending("plan_approval"),
                classification=_classification("EDIT", edited_params={"step_1": {"query": "jean"}}),
            )
        assert result["decision"] == "EDIT"
        assert result["modifications"] == sentinel
        assert result["edited_params"] == {"step_1": {"query": "jean"}}

    async def test_classifier_replan(self):
        result = await _parse(
            "get details of jean",
            _pending("plan_approval"),
            classification=_classification(
                "REPLAN", edited_params={"reformulated_intent": "detail jean"}
            ),
        )
        assert result["decision"] == "REPLAN"
        assert result["replan_instructions"] == "detail jean"
        assert result["edited_params"] == {"reformulated_intent": "detail jean"}

    async def test_classifier_ambiguous_maps_to_reject(self):
        result = await _parse(
            "well",
            _pending("plan_approval"),
            classification=_classification("AMBIGUOUS", clarification_question="Please clarify"),
        )
        assert result == {"decision": "REJECT", "rejection_reason": "Please clarify"}

    async def test_classifier_unknown_maps_to_reject(self):
        result = await _parse(
            "???",
            _pending("plan_approval"),
            classification=_classification("NOPE"),
        )
        assert result["decision"] == "REJECT"
        assert "NOPE" in result["rejection_reason"]

    async def test_classifier_error_maps_to_reject_without_leaking_the_message(self):
        """The reason names the failure TYPE, never the exception text.

        ``rejection_reason`` is summarized into the response node's prompt, so an
        arbitrary exception string would ship whatever it carries (a validation
        error echoing the user's payload, an HTTP error with its query string)
        straight into an LLM call. The full message stays in the structured log.
        """
        result = await _parse(
            "complex ambiguous message",
            _pending("plan_approval"),
            classifier_error=RuntimeError("kaboom user@example.com"),
        )
        assert result["decision"] == "REJECT"
        assert "RuntimeError" in result["rejection_reason"]
        assert "kaboom" not in result["rejection_reason"]
        assert "user@example.com" not in result["rejection_reason"]
