"""A native total refusal never gains approval, edits, or an unrelated account."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr

from src.core.context import current_tracker
from src.domains.agents.services.hitl import jev_rejection
from src.domains.agents.services.hitl_classifier import ClassificationResult, HitlResponseClassifier
from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.infrastructure.llm import jev_runtime
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    DecisionUsage,
    TypeSafeClient,
    TypeSafeError,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
USER = UUID("00000000-0000-0000-0000-000000000029")
ACTIONS = [{"name": "send_email_tool", "args": {"to": "synthetic@example.test"}}]


def _answer(choice="reject_all", confidence=1.0):
    return ChoiceAnswer(
        type="choice", choice=choice, confidence=confidence, probabilities={choice: 1.0}
    )


@pytest.fixture
def native_context(monkeypatch):
    tracker = SimpleNamespace(user_id=USER, run_id="synthetic-rejection-run")
    token = current_tracker.set(tracker)
    native = AsyncMock(return_value=DecisionAttempt(answer=_answer(), outcome="success"))
    action = AsyncMock()
    monkeypatch.setattr(jev_rejection, "choose_with_jev", native)
    monkeypatch.setattr(jev_rejection, "record_action", action)
    monkeypatch.setattr(jev_rejection, "runtime_context_if_running", lambda: None)
    try:
        yield tracker, native, action
    finally:
        current_tracker.reset(token)


def _classifier(monkeypatch, decision="APPROVE"):
    classifier = HitlResponseClassifier.__new__(HitlResponseClassifier)
    classifier.llm = MagicMock()
    classifier._provider = "openai"
    classifier._build_prompt = MagicMock(return_value=[])
    baseline = AsyncMock(
        return_value=ClassificationResult(
            decision=decision,
            confidence=1.0,
            reasoning="baseline",
            edited_params=(
                {"query": "synthetic replacement"} if decision in {"EDIT", "REPLAN"} else None
            ),
        )
    )
    monkeypatch.setattr(
        "src.domains.agents.services.hitl_classifier.get_structured_output", baseline
    )
    return classifier, baseline


async def test_current_tracker_has_authority_before_graph_runtime(native_context):
    tracker, native, action = native_context
    result = await jev_rejection.try_reject_all("Stop all proposed work.", ACTIONS)
    assert result.choice == "reject_all"
    request = native.await_args.kwargs
    assert request["usage"] is JevUsage.HITL_REJECTION
    assert request["user_id"] == tracker.user_id
    assert request["run_id"] == tracker.run_id
    assert request["state"] == {"user_reply": "Stop all proposed work.", "pending_actions": ACTIONS}
    assert action.await_args.kwargs["target"] == "hitl_rejected"


async def test_refusal_skips_generative_and_returns_no_parameters(native_context, monkeypatch):
    classifier, baseline = _classifier(monkeypatch)
    # The old argument can be a TokenTrackingCallback; it is never the owner.
    result = await classifier.classify("Stop all proposed work.", ACTIONS, tracker=object())
    assert result.decision == "REJECT"
    assert result.reasoning == ""
    assert result.edited_params is result.clarification_question is None
    baseline.assert_not_awaited()
    classifier._build_prompt.assert_not_called()


@pytest.mark.parametrize("decision", ["APPROVE", "EDIT", "REPLAN", "AMBIGUOUS"])
async def test_other_replies_keep_original_classifier(native_context, monkeypatch, decision):
    _, native, action = native_context
    native.return_value = DecisionAttempt(answer=_answer("other"), outcome="success")
    classifier, baseline = _classifier(monkeypatch, decision)
    result = await classifier.classify("No, use the other recipient instead.", ACTIONS)
    assert result.decision == decision
    baseline.assert_awaited_once()
    assert action.await_args.kwargs["target"] == "hitl_classifier"


@pytest.mark.parametrize(
    ("outcome", "answer"),
    [
        ("success", _answer(confidence=0.98)),
        ("success", _answer("uncertain")),
        ("success", _answer("other")),
        ("disabled", None),
        ("timeout", None),
        ("invalid_response", None),
        ("too_large", _answer()),
    ],
)
async def test_only_successful_certain_total_refusal_is_admitted(native_context, outcome, answer):
    _, native, action = native_context
    native.return_value = DecisionAttempt(answer=answer, outcome=outcome)
    assert await jev_rejection.try_reject_all("Stop.", ACTIONS) is None
    assert action.await_args.kwargs["action"] == "fallback"


@pytest.mark.parametrize("enabled", [False, True])
async def test_runtime_off_or_paid_failure_keeps_baseline_and_accounting(
    native_context, monkeypatch, enabled
):
    _, _, action = native_context
    tracker = TrackingContext(str(uuid4()), USER, "chat", None, auto_commit=False)
    price = ModelPrice(
        "jev-1.13.0",
        Decimal(".042"),
        None,
        Decimal(0),
        "per_1m_tokens",
        datetime(2026, 9, 28, tzinfo=UTC),
    )
    config = DecisionConfiguration(price.model_name, 2, SecretStr("synthetic-secret"), price)
    monkeypatch.setattr(jev_rejection, "choose_with_jev", jev_runtime.choose_with_jev)
    monkeypatch.setattr(
        jev_runtime,
        "load_jev_snapshot",
        AsyncMock(return_value=JevSnapshot(enabled, "ready", config if enabled else None)),
    )
    guard = AsyncMock()
    monkeypatch.setattr(jev_runtime, "enforce_usage_limit", guard)
    monkeypatch.setattr(jev_runtime, "begin_trace", AsyncMock(return_value=None))
    monkeypatch.setattr(jev_runtime, "get_cached_usd_eur_rate", lambda: 0.9)
    provider = AsyncMock(
        side_effect=TypeSafeError(
            "invalid_response",
            model=config.model,
            usage=DecisionUsage(input_tokens=1000, output_tokens=20),
            reason="probability_sum",
        )
    )
    monkeypatch.setattr(TypeSafeClient, "choose", provider)
    classifier, baseline = _classifier(monkeypatch, "REJECT")
    token = current_tracker.set(tracker)
    try:
        result = await classifier.classify("No thanks.", ACTIONS)
        calls = tracker.get_llm_calls_breakdown()
    finally:
        current_tracker.reset(token)
    assert result.reasoning == "baseline"
    baseline.assert_awaited_once()
    if enabled:
        provider.assert_awaited_once()
        guard.assert_awaited_once_with(USER, layer="jev_decision")
        assert len(calls) == 1
        assert calls[0]["call_type"] == "decision"
        assert calls[0]["status"] == "error"
        assert calls[0]["model_name"] == "jev-1.13.0"
        assert calls[0]["cost_eur"] == pytest.approx(0.0000378)
        assert action.await_args.kwargs["outcome"] == "invalid_response"
    else:
        provider.assert_not_awaited()
        guard.assert_not_awaited()
        assert calls == []
        assert action.await_args.kwargs["outcome"] == "disabled"


async def test_pending_action_mutation_abstains(native_context):
    _, native, action = native_context
    pending = [{"name": "send_email_tool", "args": {"body": "完整正文 " * 500}}]

    async def change(**kwargs):
        assert kwargs["state"]["pending_actions"][0]["args"]["body"] == "完整正文 " * 500
        pending[0]["args"]["body"] = "changed during inference"
        return DecisionAttempt(answer=_answer(), outcome="success")

    native.side_effect = change
    assert await jev_rejection.try_reject_all("Stop everything.", pending) is None
    assert action.await_args.kwargs["action"] == "fallback"


@pytest.mark.parametrize("pending", [[], [{"name": "invalid", "args": {"value": float("nan")}}]])
async def test_unsupported_or_empty_actions_do_not_call_native(native_context, pending):
    _, native, _ = native_context
    assert await jev_rejection.try_reject_all("No.", pending) is None
    native.assert_not_awaited()


async def test_no_current_owner_preserves_baseline(native_context):
    _, native, _ = native_context
    token = current_tracker.set(None)
    try:
        assert await jev_rejection.try_reject_all("No.", ACTIONS) is None
    finally:
        current_tracker.reset(token)
    native.assert_not_awaited()


async def test_runtime_account_mismatch_never_spends(native_context, monkeypatch):
    _, native, _ = native_context
    monkeypatch.setattr(
        jev_rejection, "runtime_context_if_running", lambda: SimpleNamespace(user_id=UUID(int=30))
    )
    assert await jev_rejection.try_reject_all("No.", ACTIONS) is None
    native.assert_not_awaited()


async def test_optional_native_exception_does_not_replace_classifier(native_context):
    _, native, _ = native_context
    native.side_effect = RuntimeError("synthetic native failure")
    assert await jev_rejection.try_reject_all("No.", ACTIONS) is None
