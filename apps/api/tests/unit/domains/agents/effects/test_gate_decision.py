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

    def test_a_tool_without_a_manifest_passes_through(self) -> None:
        """22 registered instances have none (browser sub-tools, legacy readers)."""
        assert decide_effect(None, _scope()).action is GateAction.PASS_THROUGH


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
