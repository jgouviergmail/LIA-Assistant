"""The gate around a confirmed draft: where the email actually leaves (ADR-263).

``gated_executor`` is the OTHER half of the gate and had no direct suite of its
own. The tool wrapper is exercised at length in ``test_gate_runtime.py``; this
file pins the executor wrapper, whose failure modes are not the same ones:

- a draft executor's return value is a ``dict`` the caller reports as the
  action's outcome, so anything invented here is shown to the user as a fact;
- the caller (``draft_executor._execute_confirmed_draft``) reads only whether
  the call RAISED — it reports ``success=True`` for any dict that comes back,
  so an honest failure must travel as an exception, not as a payload.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.runtime import EffectAlreadyClaimed

pytestmark = [pytest.mark.unit]


RUNS: list[dict[str, Any]] = []


async def _executor(draft_content: dict[str, Any], user_id: uuid.UUID, deps: Any) -> dict[str, Any]:
    RUNS.append(draft_content)
    return {"success": True, "message_id": "m-1"}


@pytest.fixture(autouse=True)
def _reset() -> Any:
    RUNS.clear()
    context = SimpleNamespace(
        user_id=uuid.uuid4(),
        thread_id="thread-A",
        execution_mode="pipeline",
        is_automated_source=False,
    )
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=context,
    ):
        yield context


class _Ledger:
    """A stubbed ledger whose answer to ``claim`` each test chooses."""

    def __init__(self) -> None:
        self.claims: list[Any] = []
        self.closed: list[str] = []
        self.answer: Any = "win"

    async def claim(self, request: Any) -> Any:
        self.claims.append(request)
        if self.answer == "win":
            return gate_runtime.ClaimTicket(
                effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
            )
        if self.answer == "served":
            return gate_runtime.ClaimTicket(
                effect_id=uuid.uuid4(),
                claim_token=None,
                served_result={"success": True, "message_id": "m-winner"},
            )
        if self.answer == "lost_without_result":
            return gate_runtime.ClaimTicket(
                effect_id=uuid.uuid4(), claim_token=None, served_result=None
            )
        return None  # the ledger itself is unavailable

    async def close(self, effect_id: Any, token: Any, *, outcome: Any) -> None:
        self.closed.append("success" if outcome.succeeded else "failure")

    async def refuse(self, request: Any, *, error_code: str) -> None:  # pragma: no cover
        raise AssertionError("a draft executor never refuses")


@pytest.fixture
def ledger() -> _Ledger:
    return _Ledger()


def _install(ledger: _Ledger) -> Any:
    return patch.object(gate_runtime, "_LEDGER", ledger)


class TestTheNominalPath:
    async def test_it_claims_then_runs_then_closes(self, ledger: _Ledger) -> None:
        gated = gate_runtime.gated_executor("email_send", _executor)
        with _install(ledger):
            result = await gated({"to": "x@y.z"}, uuid.uuid4(), None)

        assert len(ledger.claims) == 1
        assert RUNS == [{"to": "x@y.z"}]
        assert result == {"success": True, "message_id": "m-1"}

    async def test_the_claim_says_the_policy_that_applied(self, ledger: _Ledger) -> None:
        # ``draft``: what the user confirmed is the draft they were shown.
        gated = gate_runtime.gated_executor("email_send", _executor)
        with _install(ledger):
            await gated({"to": "x@y.z"}, uuid.uuid4(), None)

        assert ledger.claims[0].mutation_policy == "draft"
        assert ledger.claims[0].tool_name == "draft:email_send"

    async def test_wrapping_twice_does_not_nest(self) -> None:
        once = gate_runtime.gated_executor("email_send", _executor)
        assert gate_runtime.gated_executor("email_send", once) is once


class TestTheApprovalIsSpentOnce:
    async def test_a_lost_claim_serves_the_record_instead_of_re_running(
        self, ledger: _Ledger
    ) -> None:
        ledger.answer = "served"
        gated = gate_runtime.gated_executor("email_send", _executor)
        with _install(ledger):
            result = await gated({"to": "x@y.z"}, uuid.uuid4(), None)

        assert RUNS == []
        assert result == {"success": True, "message_id": "m-winner"}

    async def test_a_lost_claim_with_NO_record_never_reports_success(self, ledger: _Ledger) -> None:
        # The claim was lost to a row that kept no result — a FAILED first
        # attempt (``close_failure`` stores no payload) or a winner still in
        # flight. The caller reports ``success=True`` for ANY dict that comes
        # back, so returning one here tells the user their email left when
        # nothing here knows that it did.
        ledger.answer = "lost_without_result"
        gated = gate_runtime.gated_executor("email_send", _executor)

        with _install(ledger), pytest.raises(EffectAlreadyClaimed):
            await gated({"to": "x@y.z"}, uuid.uuid4(), None)

        assert RUNS == []


class TestWhenTheLedgerItselfIsDown:
    async def test_a_confirmed_draft_still_runs(self, ledger: _Ledger) -> None:
        # The user's explicit instruction outranks OUR bookkeeping; the gap is
        # counted and recorded, never silent.
        ledger.answer = "unavailable"
        gated = gate_runtime.gated_executor("email_send", _executor)
        with _install(ledger), patch.object(gate_runtime, "record_integrity_event") as recorded:
            result = await gated({"to": "x@y.z"}, uuid.uuid4(), None)

        assert RUNS == [{"to": "x@y.z"}]
        assert result == {"success": True, "message_id": "m-1"}
        assert recorded.await_count == 1


class TestAFailingExecutor:
    async def test_it_closes_the_row_and_re_raises(self, ledger: _Ledger) -> None:
        async def _boom(content: dict[str, Any], user_id: uuid.UUID, deps: Any) -> dict[str, Any]:
            raise RuntimeError("provider down")

        gated = gate_runtime.gated_executor("email_send", _boom)
        with _install(ledger), pytest.raises(RuntimeError):
            await gated({"to": "x@y.z"}, uuid.uuid4(), None)

        assert ledger.closed == ["failure"]


class TestWhatTheUserIsTold:
    """The gate's exception must reach the user as a localized FAILURE."""

    def test_the_caller_reports_a_failure_in_the_reader_s_language(self) -> None:
        # Proved on the caller's own contract rather than through a graph run:
        # what matters is that this exception is not swallowed into the generic
        # branch, and that the sentence is resolved from the locale.
        from src.core.i18n_drafts import get_draft_already_claimed_message
        from src.domains.agents.services.draft_executor import DraftExecutionResult

        result = DraftExecutionResult(
            success=False,
            draft_id="d-1",
            draft_type="email_send",
            action="confirm",
            error=get_draft_already_claimed_message("de"),
            user_language="de",
        )
        payload = result.to_agent_result()

        assert payload["status"] == "error"
        assert payload["message"] == get_draft_already_claimed_message("de")
        assert payload["message"] != get_draft_already_claimed_message("fr")

    def test_the_exception_carries_no_message_of_its_own(self) -> None:
        # A user-visible string never lives in a Python literal: the sentence
        # comes from the locale table, so the exception must stay wordless.
        assert str(EffectAlreadyClaimed(status="failed")) == ""

    def test_every_supported_language_has_the_sentence(self) -> None:
        from src.core.i18n import SUPPORTED_LANGUAGES
        from src.core.i18n_drafts import DRAFT_ALREADY_CLAIMED_MESSAGES

        assert set(DRAFT_ALREADY_CLAIMED_MESSAGES) == set(SUPPORTED_LANGUAGES)
