"""Per-worker JEV statistics, aggregated in memory and flushed in sorted UPSERTs (ADR-374).

Three doors write here and nothing else does: ``count_jev_outcome`` (every consumer's
outcome: the Prometheus counter AND the durable row), ``record_judgements`` (every
answer a gate judged, by the runtime after a paid attempt) and
``record_observer_agreement`` (an observer's verdict beside what its extractor
proposed). A worker aggregates in memory under a lock; its own ``JevStatisticsFlusher``
writes the batch every ``jev_statistics_flush_interval`` seconds and once more at
shutdown, so a crash loses at most one period of counts.

A flush whose statements fail wrote nothing: its batch waits for the next flush. A flush
whose COMMIT fails has an unknown outcome: its batch is dropped rather than counted
twice. ``disabled`` reaches the metric only — a switched-off usage would otherwise write
a row per operation and per worker that says nothing. A key the tables cannot store is
refused at the door: one such row would fail every later flush of its worker.
"""

import asyncio
import random
import threading
from collections.abc import Sequence
from contextlib import suppress
from datetime import date

import structlog

from src.core.time_utils import now_utc
from src.domains.llm_config.jev_gates import confidence_bucket, gate, judgement_bucket
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_statistics_repository import (
    JevStatisticsBatch,
    JevStatisticsRepository,
)
from src.infrastructure.observability.metrics_jev import (
    jev_decisions_total,
    jev_statistics_flush_failures_total,
    jev_statistics_rows_total,
)
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for

logger = structlog.get_logger(__name__)

#: The outcome of an operation whose usage is switched off: counted, never stored.
DISABLED_OUTCOME = "disabled"
#: Column widths of the tables (jev_statistics_models.py).
_OUTCOME_MAX_LENGTH = 32
_VERDICT_MAX_LENGTH = 16


class JevStatisticsSink:
    """One worker's pending counts; every method may be called from any thread."""

    def __init__(self) -> None:
        """Start with nothing pending."""
        self._lock = threading.Lock()
        self._pending = JevStatisticsBatch()

    @property
    def pending_rows(self) -> int:
        """How many rows the next flush would write."""
        with self._lock:
            return self._pending.rows

    def add_outcome(self, usage: JevUsage, outcome: str, day: date) -> None:
        """Count one operation of ``usage`` that ended with ``outcome``."""
        with self._lock:
            self._pending.outcomes[(day, usage.value, outcome)] += 1

    def add_judgement(self, usage: JevUsage, gate_key: str, bucket: int, day: date) -> None:
        """Count one judgement of gate ``gate_key`` in ``bucket``."""
        with self._lock:
            self._pending.judgements[(day, usage.value, gate_key, bucket)] += 1

    def add_agreement(
        self, usage: JevUsage, verdict: str, bucket: int, proposed: bool, day: date
    ) -> None:
        """Count one observer verdict beside what the extractor proposed."""
        with self._lock:
            self._pending.agreement[(day, usage.value, verdict, bucket, proposed)] += 1

    def take(self) -> JevStatisticsBatch:
        """Hand over everything pending; what is counted from now on waits for later."""
        with self._lock:
            batch, self._pending = self._pending, JevStatisticsBatch()
        return batch

    def give_back(self, batch: JevStatisticsBatch) -> None:
        """Put a batch nothing wrote back in line, added to what came meanwhile."""
        with self._lock:
            self._pending.merge(batch)


_SINK = JevStatisticsSink()


def count_jev_outcome(usage: JevUsage, outcome: str) -> None:
    """The one door of a consumer's outcome: the metric, and the durable daily row.

    Args:
        usage: The usage whose operation ended.
        outcome: The bounded outcome code the consumer decided (never user content).
    """
    jev_decisions_total.labels(usage=usage, outcome=outcome).inc()
    if outcome == DISABLED_OUTCOME:
        return
    if not outcome or len(outcome) > _OUTCOME_MAX_LENGTH:
        logger.warning("jev_outcome_not_stored", usage=usage.value, length=len(outcome))
        return
    _SINK.add_outcome(usage, outcome, now_utc().date())


def record_judgements(usage: JevUsage, scores: Sequence[tuple[str, float]]) -> None:
    """Count each judged answer of one paid attempt in its gate's bucket.

    Args:
        usage: The usage whose gates judged.
        scores: ``(gate key, score)`` per judged answer (``jev_gates.judged_scores``); a
            gate judges several answers of one call when it reads several questions.
    """
    day = now_utc().date()
    for gate_key, score in scores:
        bucket = judgement_bucket(gate(usage, gate_key), score)
        if bucket is not None:
            _SINK.add_judgement(usage, gate_key, bucket, day)


def record_observer_agreement(usage: JevUsage, verdict: str, score: float, proposed: bool) -> None:
    """Count an observer's verdict beside what its extractor proposed.

    Args:
        usage: The observer usage.
        verdict: The observer's choice (``useful``, ``empty``, ``uncertain``).
        score: The verdict's confidence, bucketed like a confidence gate's.
        proposed: Whether the extractor itself proposed anything.
    """
    if not verdict or len(verdict) > _VERDICT_MAX_LENGTH:
        logger.warning("jev_agreement_not_stored", usage=usage.value, length=len(verdict))
        return
    bucket = confidence_bucket(score)
    if bucket is not None:
        _SINK.add_agreement(usage, verdict, bucket, proposed, now_utc().date())


async def flush_jev_statistics(sink: JevStatisticsSink | None = None) -> int:
    """Write the pending counts in one short transaction.

    Args:
        sink: The counts to write; this worker's own by default.

    Returns:
        How many rows were written; 0 when nothing was pending or the write failed.
    """
    from src.infrastructure.database import get_db_context

    pending = sink or _SINK
    batch = pending.take()
    if batch.rows == 0:
        return 0
    committing = False
    try:
        async with get_db_context() as db:
            written = await JevStatisticsRepository(db).upsert(batch)
            committing = True
    except BaseException as exc:
        if committing:
            # The commit itself failed: the rows may be there or not. Dropped, never
            # counted twice — a bounded loss of one flush.
            jev_statistics_flush_failures_total.labels(stage="commit").inc()
            logger.warning(
                "jev_statistics_flush_unknown", rows=batch.rows, error_type=type(exc).__name__
            )
        else:
            pending.give_back(batch)
            jev_statistics_flush_failures_total.labels(stage="statements").inc()
            logger.warning(
                "jev_statistics_flush_failed", rows=batch.rows, error_type=type(exc).__name__
            )
        if not isinstance(exc, Exception):
            raise
        return 0
    jev_statistics_rows_total.inc(written)
    return written


class JevStatisticsFlusher:
    """One worker's periodic writer: started by the lifespan, stopped and awaited by it."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        final_timeout_seconds: float,
        sink: JevStatisticsSink | None = None,
    ) -> None:
        """Prepare the writer; nothing runs before ``start``.

        Args:
            interval_seconds: The period between two flushes.
            final_timeout_seconds: The longest the last flush at shutdown may take.
            sink: The counts to write; this worker's own by default.
        """
        self._interval = interval_seconds
        self._final_timeout = final_timeout_seconds
        self._sink = sink or _SINK
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the periodic flush on the running loop (idempotent)."""
        if self._task is None:
            self._stopping = asyncio.Event()
            self._task = asyncio.create_task(self._run(), name="jev-statistics-flusher")

    async def _run(self) -> None:
        # Every worker starts at the same instant: a random share of the period keeps
        # their flushes apart (the scheduler's jitter rule, ADR-254's burst reasoning).
        spread = jitter_seconds_for(seconds=self._interval)
        while not self._stopping.is_set():
            delay = self._interval + random.uniform(0, spread)
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=delay)
            if self._stopping.is_set():
                return
            await flush_jev_statistics(self._sink)

    async def stop(self) -> int:
        """Let the current flush end, then write what is left — both within ONE bound.

        A flush hanging on the database when shutdown begins is cancelled at the bound
        (its batch given back, unwritten), so a stopping worker never waits past it.

        Returns:
            How many rows the last flush wrote.
        """
        task, self._task = self._task, None
        if task is None:
            return 0
        self._stopping.set()
        try:
            async with asyncio.timeout(self._final_timeout):
                await task
                return await flush_jev_statistics(self._sink)
        except TimeoutError:
            logger.warning("jev_statistics_final_flush_timeout", rows=self._sink.pending_rows)
            return 0
