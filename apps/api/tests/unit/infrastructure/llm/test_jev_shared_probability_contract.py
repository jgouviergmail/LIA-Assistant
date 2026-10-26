"""Every registered usage inherits native rounding, atomicity and paid failures."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.infrastructure.llm import jev_http, jev_runtime
from src.infrastructure.llm.typesafe_client import (
    ChoiceQuestion,
    DecisionQuestion,
    NoulCriteria,
    NoulQuestion,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("usage", list(JevUsage))
@pytest.mark.parametrize("shape", ["single", "batch", "mixed"])
@pytest.mark.parametrize("malformed", [False, True])
async def test_each_usage_preserves_the_shared_native_contract_and_owns_one_bill(
    monkeypatch: pytest.MonkeyPatch, usage: JevUsage, shape: str, malformed: bool
) -> None:
    config = DecisionConfiguration(
        "jev-1.13.0",
        2,
        SecretStr("fictional-transport-key"),
        ModelPrice(
            "jev-1.13.0",
            Decimal(".042"),
            None,
            Decimal(0),
            "per_1m_tokens",
            datetime(2026, 10, 19, tzinfo=UTC),
        ),
    )
    tracker = TrackingContext(f"shared-native-{uuid4()}", uuid4(), "chat", None, auto_commit=False)
    key = "selection" if shape == "single" else "item"
    probabilities = {"winner": 0.93, "other": 0.05, "unknown": 0.01}
    if malformed:
        probabilities = {"winner": 0.96, "other": 0.02, "unknown": 0.0}
    questions: dict[str, DecisionQuestion] = {
        key: ChoiceQuestion(
            instructions="Classify the fictional observation.",
            criteria={option: option for option in probabilities},
        )
    }
    answers: dict[str, JsonValue] = {
        key: {
            "type": "choice",
            "choice": "winner",
            "confidence": 0.99,
            "probabilities": dict(probabilities),
        }
    }
    if shape == "mixed":
        # The public door carries both primitives in one atomic response.
        answers["condition"] = {"type": "noul", "noul": 0.97}
        questions["condition"] = NoulQuestion(
            instructions="Does the fictional condition hold?",
            criteria=NoulCriteria(true="Holds", false="Does not hold"),
        )
    sent: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "model": config.model,
                "answers": answers,
                "usage": {"input_tokens": 1000, "output_tokens": 40},
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        jev_http.httpx,
        "AsyncClient",
        lambda: original_client(transport=httpx.MockTransport(serve)),
    )
    monkeypatch.setattr(jev_runtime, "begin_trace", AsyncMock(return_value=None))
    monkeypatch.setattr(jev_runtime, "out_of_turn_spend", lambda *_: tracker)
    monkeypatch.setattr(jev_runtime, "get_cached_usd_eur_rate", lambda: 0.9)
    quota = AsyncMock()
    monkeypatch.setattr(jev_runtime, "enforce_usage_limit", quota)
    attempt = await jev_runtime.choose_many_with_jev(
        usage=usage,
        user_id=tracker.user_id,
        run_id=tracker.run_id,
        state="Fictional observation",
        questions=questions,
        snapshot=JevSnapshot(True, "ready", config),
    )
    assert len(sent) == 1
    assert set(json.loads(sent[0].content)["questions"]) == set(answers)
    quota.assert_awaited_once_with(tracker.user_id, layer="jev_decision")
    assert attempt.charge is not None and attempt.charge.input_tokens == 1000
    calls = tracker.get_llm_calls_breakdown()
    assert len(calls) == 1
    assert calls[0]["node_name"] == f"jev_{usage.value}"
    assert calls[0]["status"] == ("error" if malformed else "success")
    assert attempt.outcome == ("invalid_response" if malformed else "success")
    if malformed:
        assert not attempt.answers and not attempt.nouls and attempt.answer is None
    else:
        assert attempt.answers[key].probabilities == probabilities
        assert attempt.answers[key].confidence == pytest.approx(0.895)
        assert (attempt.answer is not None) == (shape == "single")
        if shape == "mixed":
            assert attempt.nouls["condition"].noul == 0.97
