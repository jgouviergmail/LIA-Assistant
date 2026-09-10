"""What the gate decides, before it touches a database (ADR-263).

The decision is a pure function of three things — the tool's declared policy,
the scope the executor published, and whether a human is there at all — so it
can be enumerated exhaustively. Every branch below is one sentence of the
owner's rule:

    a confirmation is owed by a mutation that modifies, deletes or communicates
    to a third party; never by a read; and no paranoia.
"""

from __future__ import annotations

import pytest

from src.domains.agents.effects.gate import (
    ERROR_CONFIRMATION_IMPOSSIBLE,
    ERROR_CONFIRMATION_MISSING,
    GateAction,
    decide_effect,
)
from src.domains.agents.effects.scope import EffectScope

pytestmark = [pytest.mark.unit]


def _scope(**overrides: object) -> EffectScope:
    base: dict[str, object] = {
        "run_id": "run-1",
        "idempotency_key": "call-1",
        "source": "user",
        "approved": False,
    }
    base.update(overrides)
    return EffectScope(**base)  # type: ignore[arg-type]


class TestWhatNeverTouchesTheLedger:
    """A ledger of "external effects" must not fill up with non-effects."""

    @pytest.mark.parametrize("policy", ["read", "sandboxed"])
    def test_reads_and_sandboxed_runs_pass_through(self, policy: str) -> None:
        decision = decide_effect(policy, _scope())
        assert decision.action is GateAction.PASS_THROUGH

    def test_a_draft_producing_call_passes_through(self) -> None:
        """The tool only BUILDS the draft; the executor is what acts."""
        assert decide_effect("draft", _scope()).action is GateAction.PASS_THROUGH

    def test_a_draft_passes_through_with_no_scope_at_all(self) -> None:
        """No scope is not an unattended scope: a caller that published none is
        unknown, and refusing on ignorance would break the 25 draft-producing
        tools wherever a scope has not reached them yet."""
        assert decide_effect("draft", None).action is GateAction.PASS_THROUGH

    def test_a_tool_without_a_manifest_passes_through(self) -> None:
        """22 registered instances have none (browser sub-tools, legacy readers)."""
        assert decide_effect(None, _scope()).action is GateAction.PASS_THROUGH


class TestAnUnattendedRunCannotDraft:
    """ADR-276 amends ADR-263: a draft owes the same answer as a confirmation.

    A ``draft`` tool asks a human by RAISING a HITL interrupt. In an unattended
    run there is nobody to answer it: measured on the routine path, the
    interrupt becomes a non-retryable ``RuntimeError`` and STAYS on the thread,
    so the next chat turn is answered as a decision nobody made. The gate
    already refuses ``confirm`` for exactly this reason.
    """

    def test_a_draft_is_refused_when_nobody_can_answer_it(self) -> None:
        decision = decide_effect("draft", _scope(source="scheduled"))
        assert decision.action is GateAction.REFUSE
        assert decision.error_code == ERROR_CONFIRMATION_IMPOSSIBLE

    def test_the_refusal_tells_the_model_not_to_announce_it_as_done(self) -> None:
        """ADR-182: never report as performed what was not performed."""
        message = decide_effect("draft", _scope(source="scheduled")).llm_message or ""
        assert "never announce it as done" in message

    def test_an_attended_turn_still_drafts(self) -> None:
        """The 25 draft-producing tools must keep working in the chat."""
        for source in ("user", "proactive"):
            assert (
                decide_effect("draft", _scope(source=source)).action is GateAction.PASS_THROUGH
            ), source

    def test_a_confirm_is_refused_the_same_way_it_always_was(self) -> None:
        """The amendment must not disturb the rule it extends."""
        decision = decide_effect("confirm", _scope(source="scheduled"))
        assert decision.action is GateAction.REFUSE
        assert decision.error_code == ERROR_CONFIRMATION_IMPOSSIBLE


class TestWhatIsRecorded:
    @pytest.mark.parametrize("policy", ["reversible", "artefact"])
    def test_an_exempt_mutation_is_recorded_without_asking(self, policy: str) -> None:
        decision = decide_effect(policy, _scope())
        assert decision.action is GateAction.LEDGER

    def test_a_confirmed_effect_is_recorded(self) -> None:
        decision = decide_effect(
            "confirm", _scope(approved=True, approval_kind="tool_confirmation")
        )
        assert decision.action is GateAction.LEDGER


class TestWhatIsRefused:
    def test_confirm_without_an_approval_is_refused(self) -> None:
        decision = decide_effect("confirm", _scope(approved=False))
        assert decision.action is GateAction.REFUSE
        assert decision.error_code == "confirmation_missing"

    def test_confirm_without_any_scope_is_refused(self) -> None:
        """No scope means no executor published one: nobody can have confirmed."""
        decision = decide_effect("confirm", None)
        assert decision.action is GateAction.REFUSE

    def test_an_automated_source_is_refused_with_its_own_reason(self) -> None:
        """A scheduled action has nobody to ask — say THAT, not 'not confirmed'."""
        decision = decide_effect("confirm", _scope(source="scheduled"))
        assert decision.action is GateAction.REFUSE
        assert decision.error_code == "confirmation_impossible_unattended"

    def test_an_automated_source_may_still_perform_an_exempt_mutation(self) -> None:
        """The owner refused paranoia: a scheduled light still switches off."""
        assert decide_effect("reversible", _scope(source="scheduled")).action is GateAction.LEDGER

    def test_a_refusal_message_is_technical_english_for_the_model(self) -> None:
        """Doctrine: the model reformulates in the user's language (ADR-256)."""
        message = decide_effect("confirm", _scope(source="scheduled")).llm_message
        assert message and message[0].isupper() and message.endswith(".")


class TestTheUnscopedCase:
    """A ledgered effect with no scope still runs — and is counted, never silent."""

    def test_an_exempt_mutation_without_a_scope_still_runs(self) -> None:
        decision = decide_effect("reversible", None)
        assert decision.action is GateAction.LEDGER
        assert decision.unscoped is True

    def test_a_scoped_effect_is_not_flagged_unscoped(self) -> None:
        assert decide_effect("reversible", _scope()).unscoped is False


class TestTheVocabularyIsExhaustive:
    def test_every_declared_policy_has_a_decision(self) -> None:
        """A policy nobody decided on must not silently pass through."""
        from src.domains.agents.registry.catalogue import MUTATION_POLICIES

        for policy in MUTATION_POLICIES:
            decision = decide_effect(policy, _scope(approved=True))
            assert decision.action in set(GateAction), policy


class TestASurfaceThatCanCarryTheQuestion:
    """ADR-276 lot 7: a workboard ticket can put a draft in front of the person.

    Nobody is there NOW, but the question has somewhere to go — so for such a
    run the two policies that need somebody ask exactly as they do in the chat,
    and the run captures the interrupt instead of leaving it on the thread.
    """

    def test_a_confirm_becomes_the_draft_the_chat_would_show(self) -> None:
        decision = decide_effect("confirm", _scope(source="scheduled"), carrier=True)
        assert decision.action is GateAction.REFUSE
        assert decision.error_code == ERROR_CONFIRMATION_MISSING  # the ASK path

    def test_a_draft_builds_its_own(self) -> None:
        decision = decide_effect("draft", _scope(source="scheduled"), carrier=True)
        assert decision.action is GateAction.PASS_THROUGH

    def test_a_routine_is_still_refused(self) -> None:
        """The flag is the surface's, never the source's: a routine cannot carry
        a draft anywhere, and keeps the refusal ADR-276 gave it."""
        for policy in ("confirm", "draft"):
            decision = decide_effect(policy, _scope(source="scheduled"))
            assert decision.action is GateAction.REFUSE, policy
            assert decision.error_code == ERROR_CONFIRMATION_IMPOSSIBLE, policy

    def test_an_attended_turn_is_unchanged_by_the_flag(self) -> None:
        assert decide_effect("draft", _scope(), carrier=True).action is GateAction.PASS_THROUGH
        assert decide_effect("confirm", _scope(), carrier=True).error_code == (
            ERROR_CONFIRMATION_MISSING
        )

    def test_a_carrier_never_turns_a_refusal_into_an_execution(self) -> None:
        """Carrying the question is not answering it."""
        decision = decide_effect("confirm", _scope(source="scheduled"), carrier=True)
        assert decision.action is not GateAction.LEDGER

    def test_an_approved_replay_on_a_carrier_is_recorded_and_performed(self) -> None:
        decision = decide_effect("confirm", _scope(source="scheduled", approved=True), carrier=True)
        assert decision.action is GateAction.LEDGER
