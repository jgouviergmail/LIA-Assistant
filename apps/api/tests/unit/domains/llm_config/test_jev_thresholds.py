"""Thresholds are stored per usage, read with the switches and carried by the attempt (ADR-374)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import JEV_DEFAULT_TIMEOUT_SECONDS
from src.core.context import current_tracker
from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config import jev_settings
from src.domains.llm_config.jev_gates import gate_defaults
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import (
    DecisionConfiguration,
    JevRouting,
    JevSnapshot,
    load_jev_snapshot,
    resolve_thresholds,
)
from src.domains.system_settings.models import SystemSettingKey
from src.infrastructure.llm import jev_runtime
from src.infrastructure.llm.typesafe_client import ChoiceAnswer, ChoiceBatchResult, DecisionUsage

pytestmark = pytest.mark.unit

EMAIL = JevUsage.EMAIL_CLASSIFICATION
PRICE = ModelPrice(
    "jev-1.14.0", Decimal(".042"), None, Decimal(0), "per_1m_tokens", datetime.now(UTC)
)
CONFIG = DecisionConfiguration("jev-1.14.0", 2, SecretStr("test-secret"), PRICE)


class TestResolveThresholds:
    def test_nothing_stored_reads_the_defaults(self) -> None:
        assert resolve_thresholds(EMAIL, None) == gate_defaults(EMAIL)

    def test_a_stored_value_overrides_its_default_only(self) -> None:
        resolved = resolve_thresholds(EMAIL, '{"priority": "0.50"}')
        assert resolved == {**gate_defaults(EMAIL), "priority": Decimal("0.50")}

    def test_a_json_number_reads_exactly(self) -> None:
        assert resolve_thresholds(EMAIL, '{"category": 0.85}')["category"] == Decimal("0.85")

    @pytest.mark.parametrize(
        "stored",
        [
            "{not json",
            '["priority", 0.5]',
            '{"nope": "0.5"}',
            '{"category": "0.20"}',
            '{"category": "1.5"}',
            '{"category": "NaN"}',
            '{"category": true}',
            '{"category": "abc"}',
            '{"category": "0.805"}',
        ],
        ids=[
            "invalid",
            "not-an-object",
            "unknown-key",
            "below",
            "above",
            "nan",
            "bool",
            "text",
            "past-the-hundredth",
        ],
    )
    def test_an_unusable_value_falls_back_to_the_default(self, stored: str) -> None:
        with patch.object(jev_settings, "logger") as log:
            assert resolve_thresholds(EMAIL, stored) == gate_defaults(EMAIL)
        log.warning.assert_called()

    def test_a_usage_without_gate_resolves_nothing(self) -> None:
        assert resolve_thresholds(JevUsage.OBSERVE_MEMORY, '{"empty": "0.5"}') == {}


def test_every_deciding_usage_has_its_thresholds_key() -> None:
    for usage, spec in JEV_USAGES.items():
        has_gates = bool(gate_defaults(usage))
        assert (spec.thresholds_key is not None) is has_gates, usage
        if spec.thresholds_key is not None:
            assert spec.thresholds_key.name == f"JEV_{usage.value.upper()}_THRESHOLDS"
            assert len(spec.thresholds_key.name) <= 50


async def test_switches_and_thresholds_come_from_one_query() -> None:
    rows = [
        SimpleNamespace(key=SystemSettingKey.JEV_ENABLED, value="true"),
        SimpleNamespace(key=SystemSettingKey.JEV_EMAIL_CLASSIFICATION_ENABLED, value="true"),
        SimpleNamespace(
            key=SystemSettingKey.JEV_EMAIL_CLASSIFICATION_THRESHOLDS, value='{"priority": "0.5"}'
        ),
    ]
    result = MagicMock()
    result.all.return_value = rows
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = result
    routing = await jev_settings.read_routing(db)
    db.execute.assert_awaited_once()
    assert routing.flags["global"] and routing.flags[EMAIL.value]
    assert not routing.flags[JevUsage.MEETING_TEMPLATE.value]
    assert routing.thresholds == {EMAIL.value: '{"priority": "0.5"}'}


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    yield AsyncMock(spec=AsyncSession)


@pytest.mark.parametrize("enabled", [True, False])
async def test_the_snapshot_freezes_the_resolved_thresholds(enabled: bool) -> None:
    routing = JevRouting(
        flags={"global": True, EMAIL.value: enabled},
        thresholds={EMAIL.value: '{"priority": "0.55"}'},
    )
    with (
        patch.object(jev_settings, "read_routing", AsyncMock(return_value=routing)),
        patch.object(jev_settings, "read_configuration", AsyncMock(return_value=("ready", CONFIG))),
        patch("src.infrastructure.database.get_db_context", _session),
    ):
        snapshot = await load_jev_snapshot(EMAIL)
    assert snapshot.thresholds["priority"] == Decimal("0.55")
    assert snapshot.thresholds["category"] == Decimal("0.80")


async def test_every_attempt_carries_its_snapshot_thresholds() -> None:
    thresholds = {**gate_defaults(EMAIL), "priority": Decimal("0.55")}
    answer = ChoiceAnswer(
        type="choice", choice="normal", confidence=1, probabilities={"normal": 1, "urgent": 0}
    )
    batch = ChoiceBatchResult(
        CONFIG.model, {"i0_priority": answer}, DecisionUsage(input_tokens=10, output_tokens=1)
    )
    owner = uuid4()
    tracker = TrackingContext("thresholds", owner, "chat", None, auto_commit=False)
    token = current_tracker.set(tracker)
    with (
        patch.object(jev_runtime, "enforce_usage_limit", AsyncMock()),
        patch.object(jev_runtime, "begin_trace", AsyncMock(return_value=None)),
        patch.object(jev_runtime, "get_cached_usd_eur_rate", return_value=0.9),
        patch(
            "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose_many",
            AsyncMock(return_value=batch),
        ),
    ):
        paid = await jev_runtime.choose_many_with_jev(
            usage=EMAIL,
            user_id=owner,
            run_id="thresholds",
            state={},
            questions={"i0_priority": MagicMock()},
            snapshot=JevSnapshot(True, "ready", CONFIG, thresholds=thresholds),
        )
        off = await jev_runtime.choose_many_with_jev(
            usage=EMAIL,
            user_id=owner,
            run_id="thresholds",
            state={},
            questions={"i0_priority": MagicMock()},
            snapshot=JevSnapshot(False, "ready", thresholds=thresholds),
        )
    current_tracker.reset(token)
    assert paid.outcome == "success" and paid.thresholds == thresholds
    assert off.outcome == "disabled" and off.thresholds == thresholds


async def test_a_call_waits_as_long_as_its_slot_says() -> None:
    """The database first: no ceiling of the code's own over the slot's timeout."""
    for stored, expected in ((12.0, 12.0), (None, JEV_DEFAULT_TIMEOUT_SECONDS)):
        override = SimpleNamespace(**dict.fromkeys(jev_settings.OVERRIDE_FIELDS))
        override.provider, override.model, override.timeout_seconds = (
            "typesafe",
            "jev-1.14.0",
            stored,
        )
        key = SimpleNamespace(encrypted_key="ciphertext")
        model = SimpleNamespace()
        db = AsyncMock(spec=AsyncSession)
        db.scalar.side_effect = [override, key, model]
        with (
            patch.object(jev_settings, "decrypt_data", return_value="secret"),
            patch.object(
                jev_settings.AsyncPricingService,
                "get_active_model_price",
                AsyncMock(return_value=PRICE),
            ),
        ):
            readiness, config = await jev_settings.read_configuration(db, EMAIL)
        assert readiness == "ready" and config is not None
        assert config.timeout_seconds == expected
