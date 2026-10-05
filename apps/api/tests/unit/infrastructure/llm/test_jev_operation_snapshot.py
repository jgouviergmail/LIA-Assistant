"""One collection operation retains routing; every native batch still owns its bill."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from src.core.context import current_tracker
from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.infrastructure.llm import jev_runtime as module
from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    ChoiceBatchResult,
    ChoiceQuestion,
    DecisionUsage,
)

pytestmark = pytest.mark.unit
QUESTION = ChoiceQuestion(
    instructions="Judge items.q0.", criteria={"match": "Relevant", "unknown": "Unresolved"}
)
CONFIG = DecisionConfiguration(
    "jev-1.13.0",
    2,
    SecretStr("synthetic-test-secret"),
    ModelPrice(
        "jev-1.13.0",
        Decimal(".042"),
        None,
        Decimal(0),
        "per_1m_tokens",
        datetime(2026, 10, 4, tzinfo=UTC),
    ),
)


async def test_captured_on_snapshot_retains_routing_and_charges_each_batch() -> None:
    tracker = TrackingContext("collection-operation", uuid4(), "chat", None, auto_commit=False)
    snapshot = JevSnapshot(True, "ready", CONFIG)
    response = ChoiceBatchResult(
        CONFIG.model,
        {
            "q0": ChoiceAnswer(
                type="choice",
                choice="match",
                confidence=1,
                probabilities={"match": 1, "unknown": 0},
            )
        },
        DecisionUsage(input_tokens=1000, output_tokens=20),
    )
    token = current_tracker.set(tracker)
    try:
        with (
            patch.object(
                module, "load_jev_snapshot", AsyncMock(return_value=JevSnapshot(False, "ready"))
            ) as current,
            patch.object(module, "enforce_usage_limit", AsyncMock()) as quota,
            patch.object(module, "begin_trace", AsyncMock(return_value=None)),
            patch.object(module, "get_cached_usd_eur_rate", return_value=0.9),
            patch(
                "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose_many",
                AsyncMock(return_value=response),
            ) as provider,
        ):
            for _ in range(2):
                result = await module.choose_many_with_jev(
                    usage=JevUsage.FILTER_EVENT,
                    user_id=tracker.user_id,
                    run_id=tracker.run_id,
                    state={"items": {"q0": {"summary": "Synthetic event"}}},
                    questions={"q0": QUESTION},
                    snapshot=snapshot,
                )
                assert result.outcome == "success"
            current.assert_not_awaited()
            # The next operation observes the switched-off database value.
            result = await module.choose_many_with_jev(
                usage=JevUsage.FILTER_EVENT,
                user_id=tracker.user_id,
                run_id=tracker.run_id,
                state={},
                questions={"q0": QUESTION},
            )
        assert result.outcome == "disabled"
        current.assert_awaited_once_with(JevUsage.FILTER_EVENT)
        assert quota.await_count == provider.await_count == 2
        assert len(tracker._node_records) == 2
        assert sum(float(record.cost_usd) for record in tracker._node_records) == pytest.approx(
            0.000084
        )
        assert all(record.llm_type == "jev_filter_event" for record in tracker._node_records)
    finally:
        current_tracker.reset(token)


async def test_captured_off_snapshot_remains_off_without_quota_or_provider() -> None:
    with (
        patch.object(module, "load_jev_snapshot", AsyncMock()) as current,
        patch.object(module, "enforce_usage_limit", AsyncMock()) as quota,
        patch(
            "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose_many", AsyncMock()
        ) as provider,
    ):
        result = await module.choose_many_with_jev(
            usage=JevUsage.FILTER_EVENT,
            user_id=uuid4(),
            run_id="off-operation",
            state={},
            questions={"q0": QUESTION},
            snapshot=JevSnapshot(False, "ready"),
        )
    assert result.outcome == "disabled"
    current.assert_not_awaited()
    quota.assert_not_awaited()
    provider.assert_not_awaited()
