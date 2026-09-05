"""Contract of the ledger repository, without a database (ADR-263).

The behaviour that needs PostgreSQL — who wins a contended claim, whether a
stale token can close a row — is proven in
``tests/integration/domains/agents/effects/``. What is checked here is the
shape a caller depends on, and the one rule that is pure logic: a claim request
cannot name a policy the catalogue does not define.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from src.domains.agents.effects.repository import ClaimOutcome, EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest

pytestmark = [pytest.mark.unit]


def _request(**overrides: object) -> ClaimRequest:
    base: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "thread_id": "thread-A",
        "run_id": "run-1",
        "source": "user",
        "execution_mode": "react",
        "tool_name": "send_email_tool",
        "mutation_policy": "draft",
        "idempotency_key": "call-1",
        "args_digest": "a" * 64,
    }
    base.update(overrides)
    return ClaimRequest(**base)  # type: ignore[arg-type]


class TestTheClaimRequest:
    def test_a_minimal_request_is_valid(self) -> None:
        request = _request()
        assert request.approval_kind is None
        assert request.label is None

    def test_an_unknown_policy_is_refused(self) -> None:
        """The ledger records the policy that applied; an invented one records nothing."""
        with pytest.raises(ValidationError, match="unknown mutation_policy"):
            _request(mutation_policy="maybe")

    def test_every_declared_policy_is_accepted(self) -> None:
        for policy in ("read", "draft", "confirm", "reversible", "artefact", "sandboxed"):
            assert _request(mutation_policy=policy).mutation_policy == policy

    def test_a_digest_must_be_a_digest(self) -> None:
        with pytest.raises(ValidationError):
            _request(args_digest="short")

    def test_an_unknown_source_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _request(source="heartbeat")

    def test_the_request_is_frozen(self) -> None:
        """A claim describes one moment; mutating it after the fact is a bug."""
        request = _request()
        with pytest.raises(ValidationError):
            request.tool_name = "other_tool"  # type: ignore[misc]


class TestTheOutcome:
    def test_a_lost_claim_carries_no_token(self) -> None:
        outcome = ClaimOutcome(effect=object(), claimed=False, claim_token=None)  # type: ignore[arg-type]
        assert outcome.claimed is False
        assert outcome.claim_token is None

    def test_the_outcome_is_frozen(self) -> None:
        outcome = ClaimOutcome(effect=object(), claimed=True, claim_token=uuid.uuid4())  # type: ignore[arg-type]
        with pytest.raises(Exception):
            outcome.claimed = False  # type: ignore[misc]


class TestTheRepositorySurface:
    @pytest.mark.parametrize(
        "method",
        [
            "claim",
            "close_success",
            "close_failure",
            "refuse",
            "abandon_stale",
            "count_claimed_orphans",
            "list_for_export",
            "list_for_run",
            "list_for_user",
            "decrypted_result",
            "decrypted_label",
        ],
    )
    def test_the_contract_is_exposed(self, method: str) -> None:
        assert callable(getattr(EffectLedgerRepository, method))
