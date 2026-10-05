"""A call retains its tariff and UTC ledger date across delayed callbacks."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.domains.chat.repository import ChatRepository
from src.domains.chat.service import TrackingContext
from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.observability.callbacks import MetricsCallbackHandler, TokenTrackingCallback

pytestmark = pytest.mark.unit


@pytest.fixture
def windowed_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pricing_cache,
        "_local_cache",
        PricingCacheData(
            models={
                "windowed": CachedModelPrice(
                    input_unit_price=1,
                    output_unit_price=3,
                    cached_input_unit_price=0.25,
                    pricing_unit="per_1m_tokens",
                    cache_write_multiplier=1.25,
                    time_slots=[
                        {
                            "start_utc": "01:00",
                            "end_utc": "04:00",
                            "weekdays": [1, 2, 3, 4, 5],
                            "input_unit_price": 2,
                            "output_unit_price": 6,
                            "cached_input_unit_price": 0.5,
                        }
                    ],
                )
            },
            usd_eur_rate=0.9,
            last_refresh_ts=0,
        ),
    )


def _result() -> LLMResult:
    message = AIMessage(
        content="done",
        response_metadata={"model_name": "windowed"},
        usage_metadata={
            "input_tokens": 2_000_000,
            "output_tokens": 1_000_000,
            "total_tokens": 3_000_000,
            "input_token_details": {"cache_read": 1_000_000, "cache_creation": 250_000},
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


@pytest.mark.parametrize(
    ("started", "finished", "expected"),
    [
        (
            datetime(2026, 8, 17, 0, 59, 59, tzinfo=UTC),
            datetime(2026, 8, 17, 1, 0, 1, tzinfo=UTC),
            4.3125,
        ),
        (
            datetime(2026, 8, 17, 3, 59, 59, tzinfo=UTC),
            datetime(2026, 8, 17, 4, 0, 1, tzinfo=UTC),
            8.625,
        ),
        (datetime(2026, 8, 21, 3, 59, 59, tzinfo=UTC), datetime(2026, 8, 22, 2, tzinfo=UTC), 8.625),
        (datetime(2026, 8, 23, 2, tzinfo=UTC), datetime(2026, 8, 24, 2, tzinfo=UTC), 4.3125),
    ],
)
async def test_metrics_and_ledger_charge_start_tariff_once(
    windowed_cache: None,
    monkeypatch: pytest.MonkeyPatch,
    started: datetime,
    finished: datetime,
    expected: float,
) -> None:
    """Read/write cache, input and output remain priced on the same start day."""
    from src.core.config import settings

    monkeypatch.setattr(settings, "default_currency", "EUR")
    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", uuid4(), auto_commit=False)
    callback = TokenTrackingCallback(tracker, run_id=run_id)
    metrics = MetricsCallbackHandler(node_name="response")
    llm_run = uuid4()
    clock = {"at": started.timestamp()}

    class ClockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(clock["at"], tz)

    monkeypatch.setattr(pricing_cache, "datetime", ClockDateTime)
    with (
        patch(
            "src.infrastructure.observability.callbacks.time.time", side_effect=lambda: clock["at"]
        ),
        patch("src.infrastructure.observability.callbacks.llm_cost_total") as cost_metric,
    ):
        await callback.on_chat_model_start(
            {}, [[]], run_id=llm_run, metadata={"langgraph_node": "response"}
        )
        await metrics.on_chat_model_start({}, [[]], run_id=llm_run)
        clock["at"] = finished.timestamp()
        await callback.on_llm_end(_result(), run_id=llm_run)
        await metrics.on_llm_end(_result(), run_id=llm_run)
        await callback.on_llm_end(_result(), run_id=llm_run)
        await metrics.on_llm_end(_result(), run_id=llm_run)

    try:
        assert len(tracker._node_records) == 1
        record = tracker._node_records[0]
        assert record.cost_usd == pytest.approx(expected)
        assert record.cost_eur == pytest.approx(expected * 0.9)
        assert record.created_at == started
        cost_metric.labels.return_value.inc.assert_called_once_with(pytest.approx(expected * 0.9))
    finally:
        tracker.cleanup_run_records(run_id)


async def test_derived_start_prices_before_boundary(windowed_cache: None) -> None:
    finished = datetime(2026, 8, 17, 4, 0, 1, tzinfo=UTC)
    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", uuid4(), auto_commit=False)
    with patch("src.domains.chat.service.datetime") as clock:
        clock.now.return_value = finished
        clock.fromtimestamp.side_effect = datetime.fromtimestamp
        await tracker.record_node_tokens("response", "windowed", 1_000_000, 0, 0, duration_ms=2000)
    try:
        record = tracker._node_records[0]
        assert record.cost_usd == 2
        assert record.created_at == finished - timedelta(seconds=2)
    finally:
        tracker.cleanup_run_records(run_id)


@pytest.mark.parametrize(
    "started,finished,expected",
    [
        (
            datetime(2026, 8, 21, 21, 59, 59, tzinfo=UTC),
            datetime(2026, 8, 21, 22, 0, 1, tzinfo=UTC),
            4.3125,
        ),
        (
            datetime(2026, 8, 21, 23, 59, 59, tzinfo=UTC),
            datetime(2026, 8, 22, 0, 0, 1, tzinfo=UTC),
            8.625,
        ),
        # The reader's local Saturday clock maps to Friday's UTC overnight slot.
        (
            datetime(2026, 8, 22, 3, 59, 59, tzinfo=ZoneInfo("Europe/Paris")),
            datetime(2026, 8, 22, 2, 0, 1, tzinfo=UTC),
            8.625,
        ),
        (
            datetime(2026, 8, 23, 23, 59, 59, tzinfo=UTC),
            datetime(2026, 8, 24, 0, 0, 1, tzinfo=UTC),
            8.625,
        ),
    ],
)
async def test_overnight_ledger_uses_the_utc_day_that_opened_the_window(
    windowed_cache: None,
    monkeypatch: pytest.MonkeyPatch,
    started: datetime,
    finished: datetime,
    expected: float,
) -> None:
    cache = pricing_cache._local_cache
    assert cache is not None
    cache.models["windowed"].time_slots = [
        {
            "start_utc": "22:00",
            "end_utc": "02:00",
            "weekdays": [5, 7],
            "input_unit_price": 2,
            "output_unit_price": 6,
            "cached_input_unit_price": 0.5,
        }
    ]
    await test_metrics_and_ledger_charge_start_tariff_once(
        windowed_cache, monkeypatch, started, finished, expected
    )


async def test_bulk_ledger_preserves_call_date() -> None:
    """A later flush uses the charged instant in the existing ledger column."""
    db = MagicMock()
    db.flush = AsyncMock()
    started = datetime(2026, 8, 21, 23, 59, 59, tzinfo=UTC)
    rows = await ChatRepository(db).bulk_create_token_logs(
        "run",
        uuid4(),
        [
            {
                "node_name": "response",
                "model_name": "windowed",
                "prompt_tokens": 1,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "cost_usd": Decimal("0.000002"),
                "cost_eur": Decimal("0.0000018"),
                "created_at": started,
            }
        ],
    )
    assert rows[0].created_at == started


async def test_capture_and_funnel_keep_each_retry_price_after_cache_change(
    windowed_cache: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two paid attempts straddle a window; later tracking never recomputes."""
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    capture = TokenCaptureHandler("requested-model")
    early = datetime(2026, 8, 17, 3, 59, 59, tzinfo=UTC).timestamp()
    late = datetime(2026, 8, 17, 4, 0, 1, tzinfo=UTC).timestamp()
    first, retry = uuid4(), uuid4()
    with patch("src.infrastructure.llm.token_capture.time", return_value=early):
        capture.on_chat_model_start({}, [[]], run_id=first)
    with patch("src.infrastructure.llm.token_capture.time", return_value=late):
        capture.on_llm_end(_result(), run_id=first)
        capture.on_chat_model_start({}, [[]], run_id=retry)
        capture.on_llm_end(_result(), run_id=retry)
        capture.on_llm_end(_result(), run_id=retry)  # duplicate delivery
    records = capture.get_billing_records("changed-config")
    assert [record.model_name for record in records] == ["windowed", "windowed"]
    assert [record.cost_usd for record in records] == [8.625, 4.3125]
    assert [record.started_at for record in records] == [early, late]
    assert capture.tokens_in == 2_000_000
    assert capture.tokens_cache == 2_000_000

    # Simulate a later tariff publication: no display or persistence may
    # re-price these paid attempts using the new cache/configuration.
    monkeypatch.setattr(pricing_cache, "_local_cache", None)
    assert capture.get_billing_records("other") == records
    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", None, auto_commit=False)
    tracker.commit = AsyncMock()
    with (
        patch("src.domains.chat.service.TrackingContext", return_value=tracker),
        patch("src.infrastructure.proactive.tracking._record_out_of_turn", new=AsyncMock()),
        patch(
            "src.infrastructure.proactive.tracking.get_cached_cost_usd_eur",
            side_effect=AssertionError("must not re-price"),
        ),
    ):
        result = await track_proactive_tokens(
            tracker.user_id,
            "meeting",
            "target",
            None,
            capture.tokens_in,
            capture.tokens_out,
            capture.tokens_cache,
            model_name="changed-config",
            source="user",
            run_id=run_id,
            billing_records=records,
        )
    try:
        assert result == run_id
        assert [row.model_name for row in tracker._node_records] == ["windowed", "windowed"]
        assert [row.cost_usd for row in tracker._node_records] == [8.625, 4.3125]
        assert [row.created_at.timestamp() for row in tracker._node_records] == [early, late]
        assert sum(row.cost_eur for row in tracker._node_records) == pytest.approx(12.9375 * 0.9)
    finally:
        tracker.cleanup_run_records(run_id)


async def test_fully_cached_empty_response_is_still_accounted(windowed_cache: None) -> None:
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", None, auto_commit=False)
    tracker.commit = AsyncMock()
    started = datetime(2026, 8, 17, 2, tzinfo=UTC).timestamp()
    with (
        patch("src.domains.chat.service.TrackingContext", return_value=tracker),
        patch("src.infrastructure.proactive.tracking._record_out_of_turn", new=AsyncMock()),
    ):
        result = await track_proactive_tokens(
            tracker.user_id,
            "meeting",
            "target",
            None,
            0,
            0,
            1_000_000,
            model_name="windowed",
            source="user",
            run_id=run_id,
            started_at=started,
        )
    try:
        assert result == run_id
        assert len(tracker._node_records) == 1
        assert tracker._node_records[0].cost_usd == 0.5
        assert tracker._node_records[0].created_at.timestamp() == started
    finally:
        tracker.cleanup_run_records(run_id)


def test_paid_capture_survives_cancellation_and_records_stay_internal(windowed_cache: None) -> None:
    from src.core.llm_usage import LLMUsage

    capture = TokenCaptureHandler("windowed")
    run_id = uuid4()
    instant = datetime(2026, 8, 17, 2, tzinfo=UTC).timestamp()
    with patch("src.infrastructure.llm.token_capture.time", return_value=instant):
        capture.on_chat_model_start({}, [[]], run_id=run_id)
        capture.on_llm_end(_result(), run_id=run_id)
        capture.on_llm_error(BaseException("cancelled after paid result"), run_id=run_id)
    records = capture.get_billing_records("other")
    assert len(records) == 1 and records[0].cost_usd == 8.625
    assert "billing_records" not in LLMUsage(billing_records=records).model_dump(mode="json")


async def test_price_and_fx_refresh_during_call_preserves_start_generation(
    windowed_cache: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The returned alias is resolved against the tariffs known before spending."""
    capture = TokenCaptureHandler("requested-model")
    run_id = str(uuid4())
    llm_run = uuid4()
    tracker = TrackingContext(run_id, uuid4(), "session", None, auto_commit=False)
    callback = TokenTrackingCallback(tracker, run_id)
    metrics = MetricsCallbackHandler("response")
    started = datetime(2026, 8, 17, 2, tzinfo=UTC).timestamp()
    with (
        patch("src.infrastructure.llm.token_capture.time", return_value=started),
        patch("src.infrastructure.observability.callbacks.time.time", return_value=started),
        patch("src.infrastructure.observability.callbacks.llm_cost_total") as metric,
    ):
        capture.on_chat_model_start({}, [[]], run_id=llm_run)
        await callback.on_chat_model_start({}, [[]], run_id=llm_run)
        await metrics.on_chat_model_start({}, [[]], run_id=llm_run)
        monkeypatch.setattr(
            pricing_cache,
            "_local_cache",
            PricingCacheData({"windowed": CachedModelPrice(100, 100, 100)}, 0.1, started + 1),
        )
        capture.on_llm_end(_result(), run_id=llm_run)
        await callback.on_llm_end(_result(), run_id=llm_run)
        await metrics.on_llm_end(_result(), run_id=llm_run)
    try:
        priced = capture.get_billing_records("changed-model")[0]
        assert priced.cost_usd == 8.625
        assert priced.cost_eur == pytest.approx(8.625 * 0.9)
        assert priced.usd_to_eur_rate == 0.9
        assert tracker._node_records[0].cost_usd == priced.cost_usd
        assert tracker._node_records[0].cost_eur == priced.cost_eur
        from src.core.config import settings

        expected = (
            priced.cost_eur if settings.default_currency.upper() == "EUR" else priced.cost_usd
        )
        metric.labels.return_value.inc.assert_called_once_with(pytest.approx(expected))
    finally:
        tracker.cleanup_run_records(run_id)


@pytest.mark.parametrize("slot", [False, True])
@pytest.mark.parametrize("cached_price,expected", [(None, 2), (0, 0), (0.25, 0.25)])
def test_optional_cache_price_differs_from_explicit_free(
    windowed_cache: None, slot: bool, cached_price: float | None, expected: float
) -> None:
    """No cached rate uses the current slot's input; zero is explicitly free."""
    from src.domains.llm.pricing_service import ModelPrice, token_cost_usd

    at = datetime(2026, 8, 17, 2, tzinfo=UTC)
    slots = (
        [
            {
                "start_utc": "01:00",
                "end_utc": "04:00",
                "weekdays": [1],
                "input_unit_price": 2,
                "output_unit_price": 6,
                "cached_input_unit_price": cached_price,
            }
        ]
        if slot
        else None
    )
    # The Redis index resolves an absent base rate before publishing its
    # historical numeric shape; the slot override remains context-dependent.
    cached = CachedModelPrice(
        2 if not slot else 99, 6, 2 if cached_price is None else cached_price, time_slots=slots
    )
    async_price = ModelPrice(
        "model",
        Decimal(str(cached.input_unit_price)),
        Decimal(str(cached_price)) if cached_price is not None else None,
        Decimal("6"),
        "per_1m_tokens",
        at,
        slots,
    )
    assert token_cost_usd(async_price, 0, 0, 1_000_000, at) == expected
    assert (
        pricing_cache._tariff_cost_usd(cached, 0, 0, 1_000_000, at, cache_write_tokens=0)
        == expected
    )


@pytest.mark.parametrize("error", [RuntimeError("stream failed"), asyncio.CancelledError()])
async def test_paid_partial_error_keeps_start_price_and_is_recorded_once(
    windowed_cache: None, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    """Provider-reported partial usage remains paid when a stream aborts."""
    from src.core.config import settings

    monkeypatch.setattr(settings, "default_currency", "EUR")
    capture = TokenCaptureHandler("requested-model")
    run_id = str(uuid4())
    llm_run = uuid4()
    tracker = TrackingContext(run_id, uuid4(), "session", None, auto_commit=False)
    callback = TokenTrackingCallback(tracker, run_id)
    metrics = MetricsCallbackHandler("response")
    started = datetime(2026, 8, 21, 3, 59, 59, tzinfo=UTC).timestamp()
    finished = datetime(2026, 8, 22, 2, tzinfo=UTC).timestamp()
    try:
        with (
            patch("src.infrastructure.llm.token_capture.time", return_value=started),
            patch("src.infrastructure.observability.callbacks.time.time", return_value=started),
        ):
            capture.on_chat_model_start({}, [[]], run_id=llm_run)
            await callback.on_chat_model_start(
                {}, [[]], run_id=llm_run, invocation_params={"model": "requested-model"}
            )
            await metrics.on_chat_model_start({}, [[]], run_id=llm_run)
        monkeypatch.setattr(pricing_cache, "_local_cache", None)
        with (
            patch("src.infrastructure.observability.callbacks.time.time", return_value=finished),
            patch("src.infrastructure.observability.callbacks.llm_cost_total") as cost_metric,
            patch("src.infrastructure.observability.callbacks.llm_api_calls_total") as calls,
        ):
            for _ in range(2):
                capture.on_llm_error(error, run_id=llm_run, response=_result())
                await callback.on_llm_error(error, run_id=llm_run, response=_result())
                await metrics.on_llm_error(error, run_id=llm_run, response=_result())
            # An SDK's late end callback cannot charge the same partial attempt again.
            capture.on_llm_end(_result(), run_id=llm_run)
            await callback.on_llm_end(_result(), run_id=llm_run)
            await metrics.on_llm_end(_result(), run_id=llm_run)
        records = capture.claim_billing_records("requested-model")
        assert len(records) == 1
        record = records[0]
        assert record.model_name == "windowed"
        assert record.started_at == started
        assert record.cost_usd == 8.625
        assert record.cost_eur == pytest.approx(8.625 * 0.9)
        assert record.status == "error"
        assert record.failure_kind is not None
        assert (
            record.tokens_in,
            record.tokens_out,
            record.tokens_cache,
            record.tokens_cache_write,
        ) == (
            1_000_000,
            1_000_000,
            1_000_000,
            250_000,
        )
        assert capture.claim_billing_records("requested-model") == ()
        assert len(tracker._node_records) == 1
        row = tracker._node_records[0]
        assert row.status == "error"
        assert row.failure_kind == record.failure_kind
        assert row.model_name == "windowed"
        assert row.created_at == datetime.fromtimestamp(started, UTC)
        assert row.cost_usd == record.cost_usd
        assert row.cost_eur == record.cost_eur
        cost_metric.labels.return_value.inc.assert_called_once_with(record.cost_eur)
        calls.labels.assert_called_once_with(model="windowed", node_name="response", status="error")
        calls.labels.return_value.inc.assert_called_once_with()
    finally:
        tracker.cleanup_run_records(run_id)


async def test_partial_error_without_provider_usage_preserves_zero_error_trace(
    windowed_cache: None,
) -> None:
    capture = TokenCaptureHandler("requested-model")
    run_id = str(uuid4())
    llm_run = uuid4()
    tracker = TrackingContext(run_id, uuid4(), "session", None, auto_commit=False)
    callback = TokenTrackingCallback(tracker, run_id)
    partial = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="partial"))]])
    try:
        capture.on_chat_model_start({}, [[]], run_id=llm_run)
        await callback.on_chat_model_start(
            {}, [[]], run_id=llm_run, invocation_params={"model": "requested-model"}
        )
        for _ in range(2):
            capture.on_llm_error(RuntimeError("failed"), run_id=llm_run, response=partial)
            await callback.on_llm_error(RuntimeError("failed"), run_id=llm_run, response=partial)
        assert capture.claim_billing_records("requested-model") == ()
        assert len(tracker._node_records) == 1
        row = tracker._node_records[0]
        assert row.status == "error"
        assert row.model_name == "requested-model"
        assert (row.prompt_tokens, row.completion_tokens, row.cached_tokens) == (0, 0, 0)
        assert row.cost_usd == 0
    finally:
        tracker.cleanup_run_records(run_id)
