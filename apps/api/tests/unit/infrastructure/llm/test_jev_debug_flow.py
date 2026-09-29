"""Observe the real runtime and selector without a paid provider or a live database."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from src.domains.chat.service import TrackingContext
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.domains.meetings import jev_selection as selector
from src.infrastructure.llm import jev_debug_store as store
from src.infrastructure.llm import jev_runtime as runtime
from src.infrastructure.llm.jev_debug_models import JevCallTrace, context_preview
from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    ChoiceResult,
    DecisionUsage,
    TypeSafeError,
)
from tests.unit.domains.meetings.test_template_resolution import DEFAULT, MEDICAL
from tests.unit.infrastructure.llm.test_jev_runtime import PRICE

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "scenario,action,outcome",
    [
        ("success", "selected", "success"),
        ("uncertain", "fallback", "low_confidence"),
        ("abstain", "fallback", "no_match"),
        ("http_error", "fallback", "provider_error"),
        ("invalid", "fallback", "invalid_response"),
        ("wrong_model", "fallback", "unexpected_model"),
        ("accounting_error", "aborted", "selection_error"),
        ("tracker_error", "aborted", "processing_error"),
        ("cancel_call", "cancelled", "cancelled"),
        ("cancel_selection", "cancelled", "cancelled"),
    ],
)
async def test_one_native_call_exposes_its_actual_branch(
    scenario: str, action: str, outcome: str
) -> None:
    owner = uuid4()
    trace = JevCallTrace(
        id=uuid4(),
        run_id="meeting-run",
        caller="meeting_template_selection",
        usage="meeting_template",
        started_at=datetime.now(UTC),
        requested_model="jev-1.13.0",
        context=context_preview("synthetic transcript"),
    )
    tracker = TrackingContext("meeting-run", owner, "meeting", None, auto_commit=False)
    if scenario == "tracker_error":
        tracker.record_node_tokens = AsyncMock(side_effect=RuntimeError("ledger failed"))
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("never-in-debug"), PRICE)
    answer = ChoiceAnswer(
        type="choice",
        choice="none" if scenario == "abstain" else "c1",
        confidence=0.7 if scenario == "uncertain" else 0.99,
        probabilities={"c1": 0.999, "none": 0.001},
    )
    provider = AsyncMock(
        return_value=ChoiceResult(
            "unexpected" if scenario == "wrong_model" else config.model,
            answer,
            DecisionUsage(input_tokens=100, output_tokens=2),
        )
    )
    if scenario == "http_error":
        provider.side_effect = TypeSafeError("provider_error", status_code=503)
    elif scenario == "invalid":
        provider.side_effect = TypeSafeError("invalid_response")
    elif scenario == "cancel_call":
        provider.side_effect = asyncio.CancelledError()
    ledger = AsyncMock()
    if scenario == "accounting_error":
        ledger.side_effect = RuntimeError("ledger failed")
    elif scenario == "cancel_selection":
        ledger.side_effect = asyncio.CancelledError()
    saved: list[JevCallTrace] = []

    async def capture(user_id: object, entry: JevCallTrace) -> None:
        assert user_id == owner
        saved.append(entry)

    with (
        patch.object(
            runtime, "load_jev_snapshot", AsyncMock(return_value=JevSnapshot(True, "ready", config))
        ),
        patch.object(runtime, "enforce_usage_limit", AsyncMock()),
        patch.object(runtime, "begin_trace", AsyncMock(return_value=trace), create=True),
        patch.object(runtime, "out_of_turn_spend", return_value=tracker),
        patch.object(runtime, "get_cached_usd_eur_rate", return_value=0.9),
        patch.object(store, "write_trace", side_effect=capture),
        patch.object(selector, "record_selection_charge", ledger),
        patch("src.infrastructure.llm.typesafe_client.TypeSafeClient.choose", provider),
    ):
        kwargs = {
            "meeting_id": uuid4(),
            "user_id": owner,
            "run_id": "meeting-run",
            "candidates": [DEFAULT, MEDICAL],
            "excerpt": "synthetic",
            "calendar_title": None,
        }
        if scenario.startswith("cancel"):
            with pytest.raises(asyncio.CancelledError):
                await selector.select_template_with_jev(**kwargs)
        elif scenario in {"accounting_error", "tracker_error"}:
            with pytest.raises(RuntimeError, match="ledger"):
                await selector.select_template_with_jev(**kwargs)
        else:
            result = await selector.select_template_with_jev(**kwargs)
            assert (result.template is MEDICAL) == (scenario == "success")
    provider.assert_awaited_once()
    assert saved, "Every actual call must leave a diagnostic when capture is enabled"
    assert all(entry.id == trace.id for entry in saved)
    last = saved[-1]
    assert (last.action, last.outcome) == (action, outcome)
    assert "never-in-debug" not in last.model_dump_json()
    assert (last.response is None) == (scenario in {"http_error", "invalid", "cancel_call"})
    assert (last.reported_model is None) == (scenario in {"http_error", "invalid", "cancel_call"})
    if action == "selected":
        assert last.action_target == f"{MEDICAL.ref}: {MEDICAL.name}"
    elif action == "fallback":
        assert last.action_target == "meeting_synthesis"
    if scenario == "http_error":
        assert last.status_code == 503


async def test_debug_outage_and_timeout_do_not_escape() -> None:
    trace = JevCallTrace(
        id=uuid4(),
        run_id="run",
        caller="caller",
        usage="meeting_template",
        started_at=datetime.now(UTC),
        requested_model="jev",
        context=context_preview("x"),
    )
    with patch.object(store, "write_trace", AsyncMock(side_effect=ConnectionError("secret body"))):
        await store.save_trace(uuid4(), trace)

    async def stalled(*args: object) -> None:
        await asyncio.Event().wait()

    with (
        patch.object(store, "write_trace", side_effect=stalled),
        patch.object(store, "DEBUG_IO_SECONDS", 0.01),
    ):
        async with asyncio.timeout(0.5):
            await store.save_trace(uuid4(), trace)


async def test_debug_never_swallows_cancellation() -> None:
    trace = JevCallTrace(
        id=uuid4(),
        run_id="run",
        caller="caller",
        usage="meeting_template",
        started_at=datetime.now(UTC),
        requested_model="jev",
        context=context_preview("x"),
    )
    with (
        patch.object(store, "write_trace", AsyncMock(side_effect=asyncio.CancelledError())),
        pytest.raises(asyncio.CancelledError),
    ):
        await store.save_trace(uuid4(), trace)
