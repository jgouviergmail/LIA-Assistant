"""JEV's durable statistics: three doors, one sorted writer, a bounded loss (ADR-374)."""

import asyncio
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from prometheus_client import REGISTRY
from pydantic import SecretStr
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import current_tracker
from src.core.time_utils import now_utc
from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config import jev_statistics_sink as sink_module
from src.domains.llm_config.jev_gates import gate_defaults
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.domains.llm_config.jev_statistics_repository import (
    JevStatisticsBatch,
    JevStatisticsRepository,
)
from src.domains.llm_config.jev_statistics_sink import (
    JevStatisticsFlusher,
    JevStatisticsSink,
    count_jev_outcome,
    flush_jev_statistics,
    record_judgements,
    record_observer_agreement,
)
from src.infrastructure.llm import jev_runtime
from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    ChoiceBatchResult,
    DecisionUsage,
    TypeSafeError,
)

pytestmark = pytest.mark.unit

EMAIL = JevUsage.EMAIL_CLASSIFICATION
RADIO = JevUsage.RADIO_VERIFICATION
OBSERVER = JevUsage.OBSERVE_MEMORY


@pytest.fixture(autouse=True)
def sink() -> Iterator[JevStatisticsSink]:
    fresh = JevStatisticsSink()
    with patch.object(sink_module, "_SINK", fresh):
        yield fresh


def _today() -> date:
    return now_utc().date()


def _decisions(usage: JevUsage, outcome: str) -> float:
    labels = {"usage": usage.value, "outcome": outcome}
    return REGISTRY.get_sample_value("jev_decisions_total", labels) or 0.0


def _failures(stage: str) -> float:
    labels = {"stage": stage}
    return REGISTRY.get_sample_value("jev_statistics_flush_failures_total", labels) or 0.0


class TestDoors:
    def test_an_outcome_reaches_the_metric_and_the_daily_row(self, sink: JevStatisticsSink) -> None:
        before = _decisions(EMAIL, "classified")
        count_jev_outcome(EMAIL, "classified")
        count_jev_outcome(EMAIL, "classified")
        assert _decisions(EMAIL, "classified") - before == 2
        assert sink.take().outcomes == {(_today(), EMAIL.value, "classified"): 2}

    def test_disabled_writes_nothing(self, sink: JevStatisticsSink) -> None:
        before = _decisions(EMAIL, "disabled")
        count_jev_outcome(EMAIL, "disabled")
        assert _decisions(EMAIL, "disabled") == before + 1
        assert sink.pending_rows == 0

    def test_an_outcome_the_table_cannot_store_is_counted_not_queued(
        self, sink: JevStatisticsSink
    ) -> None:
        count_jev_outcome(EMAIL, "x" * 33)
        assert sink.pending_rows == 0

    def test_each_judged_answer_lands_in_its_exact_bucket(self, sink: JevStatisticsSink) -> None:
        record_judgements(EMAIL, [("priority", 0.29), ("priority", 1.0), ("category", 0.29)])
        # A margin's judgement lands at its distance to a certain answer: a Noul at 1.0
        # is certain (bucket 0), one at 0.155 is 0.155 away (rounded up to 16).
        record_judgements(RADIO, [("line_margin", 1.0), ("line_margin", 0.155)])
        assert sink.take().judgements == {
            (_today(), EMAIL.value, "priority", 29): 1,
            (_today(), EMAIL.value, "priority", 100): 1,
            (_today(), EMAIL.value, "category", 29): 1,
            (_today(), RADIO.value, "line_margin", 0): 1,
            (_today(), RADIO.value, "line_margin", 16): 1,
        }

    def test_a_score_that_is_no_number_is_no_judgement(self, sink: JevStatisticsSink) -> None:
        record_judgements(EMAIL, [("priority", float("nan"))])
        assert sink.pending_rows == 0

    def test_an_agreement_keeps_verdict_bucket_and_proposal(self, sink: JevStatisticsSink) -> None:
        record_observer_agreement(OBSERVER, "empty", 0.29, proposed=False)
        record_observer_agreement(OBSERVER, "x" * 17, 0.9, proposed=True)
        assert sink.take().agreement == {(_today(), OBSERVER.value, "empty", 29, False): 1}


def _recording_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session


def _statements(session: MagicMock) -> list[Insert]:
    return [call.args[0] for call in session.execute.await_args_list]


def _rows(statement: Insert) -> list[tuple[object, ...]]:
    params = statement.compile(dialect=postgresql.dialect()).params
    indexes = sorted({int(m.group(1)) for key in params if (m := re.search(r"_m(\d+)$", key))})
    return [
        (
            params[f"day_m{i}"],
            params[f"usage_m{i}"],
            params[f"gate_key_m{i}"],
            params[f"bucket_m{i}"],
        )
        for i in indexes
    ]


async def test_rows_are_sorted_and_deduplicated_before_upsert() -> None:
    day = date(2026, 11, 8)
    batch = JevStatisticsBatch()
    for key in [(day, "radio", "line_margin", 3), (day, "email", "priority", 80)] * 2:
        batch.judgements[key] += 1
    batch.judgements[(date(2026, 11, 7), "radio", "line_margin", 9)] += 1
    session = _recording_session()
    assert await JevStatisticsRepository(session).upsert(batch) == 3
    assert _rows(_statements(session)[0]) == [
        (date(2026, 11, 7), "radio", "line_margin", 9),
        (day, "email", "priority", 80),
        (day, "radio", "line_margin", 3),
    ]


async def test_a_large_batch_is_chunked_in_one_global_order() -> None:
    day = date(2026, 11, 8)
    batch = JevStatisticsBatch()
    for bucket in range(101):
        for gate_key in (f"g{i:02d}" for i in range(25)):
            batch.judgements[(day, "email", gate_key, bucket)] += 1
    session = _recording_session()
    assert await JevStatisticsRepository(session).upsert(batch) == 2525
    chunks = [_rows(statement) for statement in _statements(session)]
    assert [len(chunk) for chunk in chunks] == [1000, 1000, 525]
    flat = [row for chunk in chunks for row in chunk]
    assert flat == sorted(flat) and len(set(flat)) == len(flat)


@asynccontextmanager
async def _session(fail_on_exit: bool = False) -> AsyncIterator[AsyncSession]:
    session = MagicMock(spec=AsyncSession)
    yield session
    if fail_on_exit:
        raise ConnectionError("commit lost")


def _sink_with(rows: int) -> JevStatisticsSink:
    pending = JevStatisticsSink()
    for bucket in range(rows):
        pending.add_judgement(EMAIL, "priority", bucket, _today())
    return pending


class TestFlush:
    async def test_a_written_batch_leaves_nothing_pending(self) -> None:
        pending = _sink_with(3)
        with (
            patch("src.infrastructure.database.get_db_context", _session),
            patch.object(JevStatisticsRepository, "upsert", AsyncMock(return_value=3)),
        ):
            assert await flush_jev_statistics(pending) == 3
        assert pending.pending_rows == 0

    async def test_a_failed_statement_keeps_the_batch_for_the_next_flush(self) -> None:
        pending = _sink_with(3)
        before = _failures("statements")
        with (
            patch("src.infrastructure.database.get_db_context", _session),
            patch.object(
                JevStatisticsRepository, "upsert", AsyncMock(side_effect=ConnectionError("down"))
            ),
        ):
            assert await flush_jev_statistics(pending) == 0
        assert pending.pending_rows == 3
        assert _failures("statements") == before + 1

    async def test_an_unknown_commit_drops_the_batch_rather_than_count_it_twice(self) -> None:
        pending = _sink_with(3)
        before = _failures("commit")
        with (
            patch(
                "src.infrastructure.database.get_db_context",
                lambda: _session(fail_on_exit=True),
            ),
            patch.object(JevStatisticsRepository, "upsert", AsyncMock(return_value=3)),
        ):
            assert await flush_jev_statistics(pending) == 0
        assert pending.pending_rows == 0
        assert _failures("commit") == before + 1

    async def test_a_cancelled_flush_keeps_its_batch_and_propagates(self) -> None:
        pending = _sink_with(2)
        with (
            patch("src.infrastructure.database.get_db_context", _session),
            patch.object(
                JevStatisticsRepository, "upsert", AsyncMock(side_effect=asyncio.CancelledError)
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await flush_jev_statistics(pending)
        assert pending.pending_rows == 2

    async def test_nothing_pending_opens_no_session(self) -> None:
        opened = MagicMock()
        with patch("src.infrastructure.database.get_db_context", opened):
            assert await flush_jev_statistics(JevStatisticsSink()) == 0
        opened.assert_not_called()


class TestFlusher:
    async def test_it_flushes_every_period(self) -> None:
        pending = _sink_with(1)
        flusher = JevStatisticsFlusher(interval_seconds=0.01, final_timeout_seconds=1, sink=pending)
        upsert = AsyncMock(return_value=1)
        with (
            patch("src.infrastructure.database.get_db_context", _session),
            patch.object(JevStatisticsRepository, "upsert", upsert),
            patch.object(sink_module.random, "uniform", return_value=0.0),
        ):
            flusher.start()
            for _ in range(200):
                if upsert.await_count:
                    break
                await asyncio.sleep(0.01)
            await flusher.stop()
        assert upsert.await_count == 1

    async def test_the_flusher_is_awaited_at_shutdown_and_writes_what_is_left(self) -> None:
        pending = JevStatisticsSink()
        flusher = JevStatisticsFlusher(interval_seconds=3600, final_timeout_seconds=1, sink=pending)
        with (
            patch("src.infrastructure.database.get_db_context", _session),
            patch.object(JevStatisticsRepository, "upsert", AsyncMock(return_value=2)) as upsert,
        ):
            flusher.start()
            pending.add_outcome(EMAIL, "classified", _today())
            pending.add_outcome(EMAIL, "uncertain", _today())
            assert await flusher.stop() == 2
        assert not [t for t in asyncio.all_tasks() if t.get_name() == "jev-statistics-flusher"]
        upsert.assert_awaited_once()
        assert await flusher.stop() == 0

    async def test_a_flush_hanging_at_shutdown_cannot_hold_it_past_its_bound(self) -> None:
        pending = _sink_with(1)
        flusher = JevStatisticsFlusher(
            interval_seconds=0.01, final_timeout_seconds=0.05, sink=pending
        )
        started = asyncio.Event()

        async def hanging(_repository: object, _batch: object) -> int:
            started.set()
            await asyncio.sleep(10)
            return 1

        with (
            patch("src.infrastructure.database.get_db_context", _session),
            patch.object(JevStatisticsRepository, "upsert", hanging),
            patch.object(sink_module.random, "uniform", return_value=0.0),
        ):
            flusher.start()
            await asyncio.wait_for(started.wait(), timeout=5)
            assert await asyncio.wait_for(flusher.stop(), timeout=2) == 0
        # The cancelled flush gave its batch back: nothing was written, nothing lost.
        assert pending.pending_rows == 1

    async def test_the_last_flush_cannot_hold_shutdown_past_its_bound(self) -> None:
        pending = _sink_with(1)
        flusher = JevStatisticsFlusher(
            interval_seconds=3600, final_timeout_seconds=0.05, sink=pending
        )

        async def slow(_repository: object, _batch: object) -> int:
            await asyncio.sleep(10)
            return 1

        with (
            patch("src.infrastructure.database.get_db_context", _session),
            patch.object(JevStatisticsRepository, "upsert", slow),
        ):
            flusher.start()
            assert await asyncio.wait_for(flusher.stop(), timeout=2) == 0


PRICE = ModelPrice(
    "jev-1.14.0", Decimal(".042"), None, Decimal(0), "per_1m_tokens", datetime.now(UTC)
)
CONFIG = DecisionConfiguration("jev-1.14.0", 2, SecretStr("test-secret"), PRICE)


@pytest.mark.parametrize("fails", [False, True], ids=["paid", "failed"])
async def test_a_paid_attempt_files_its_judgements_and_a_failed_one_none(
    sink: JevStatisticsSink, fails: bool
) -> None:
    answer = ChoiceAnswer(
        type="choice", choice="normal", confidence=1, probabilities={"normal": 1, "urgent": 0}
    )
    batch = ChoiceBatchResult(
        CONFIG.model, {"i0_priority": answer}, DecisionUsage(input_tokens=10, output_tokens=1)
    )
    native = (
        AsyncMock(side_effect=TypeSafeError("timeout")) if fails else AsyncMock(return_value=batch)
    )
    owner = uuid4()
    token = current_tracker.set(TrackingContext("stats", owner, "chat", None, auto_commit=False))
    try:
        with (
            patch.object(jev_runtime, "enforce_usage_limit", AsyncMock()),
            patch.object(jev_runtime, "begin_trace", AsyncMock(return_value=None)),
            patch.object(jev_runtime, "get_cached_usd_eur_rate", return_value=0.9),
            patch("src.infrastructure.llm.typesafe_client.TypeSafeClient.choose_many", native),
        ):
            attempt = await jev_runtime.choose_many_with_jev(
                usage=EMAIL,
                user_id=owner,
                run_id="stats",
                state={},
                questions={"i0_priority": MagicMock()},
                snapshot=JevSnapshot(True, "ready", CONFIG, thresholds=gate_defaults(EMAIL)),
            )
    finally:
        current_tracker.reset(token)
    pending = sink.take().judgements
    if fails:
        assert attempt.outcome == "timeout" and pending == {}
    else:
        assert attempt.outcome == "success"
        assert pending == {(_today(), EMAIL.value, "priority", 100): 1}
