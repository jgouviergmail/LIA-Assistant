"""Where a session's loop runs: one task per session, in the worker holding its lease.

:meth:`RadioLoopLauncher.ensure` takes the session's lease with a fresh owner
token; the worker that gets it runs the loop as a task of its own, kept in a
registry the shutdown cancels — so a deploy never leaves a loop producing on a
worker that is going away: the lease lapses, and the next report, on whichever
worker it lands, starts the loop again where the state says it stood
(:func:`~src.domains.radio.orchestrator.reloaded`).

What the loop is made of — the antenna, its sources, its voices, the ledger its
run fills, the spending ceilings it asks — is built by a factory the caller
hands in, as an async context manager: whatever it opens (a tracker, a TTS
client) it closes when the loop ends, on every path.

When the loop ends, the audio follows the reason: the listener stopped, or
nobody was listening — it is removed at once; the timer's farewell, a ceiling,
failures — it stays for the player to finish, and the orphan sweep takes it
later. A session whose frozen setup cannot be read, or whose loop breaks on a
defect, is ended as failed rather than left to hang until its keys expire —
unless it had already ended, in which case the end that stands is the one
counted and filed; a loop cancelled by its worker's shutdown ends nothing —
another worker takes it up.

Every end closes the session's books: one row in the transparency register's
decision record, under the session's run (``SessionBooks``, ADR-324 decision
31). The service closes them itself for a session no loop holds.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

import structlog

from src.domains.radio.formats import RadioFormat
from src.domains.radio.live_store import RadioSessionRecord, RadioSessionStore
from src.domains.radio.media import discard
from src.domains.radio.orchestrator import (
    FlashSource,
    HeardLedger,
    LoopPorts,
    LoopTuning,
    Producer,
    reloaded,
    run_session,
)
from src.domains.radio.session import DISCARD_AT_END, EndReason, SessionState, ended_for
from src.domains.radio.setup import RadioSetup, listening_of
from src.infrastructure.locks.redis_claim import ClaimLost, held_claim
from src.infrastructure.observability.metrics_radio import (
    radio_loop_failures_total,
    radio_sessions_ended_total,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LoopParts:
    """What one loop is made of.

    Attributes:
        producer: Produces the segments (the antenna).
        available: The formats that have something to say.
        spend_blocked: Whether a spending ceiling refuses the next production.
        aired: Where what the listener heard is filed (the aired ledger).
        flashes: What LIA wrote to the listener, for a news flash; None when
            nothing personal may air or the notifications are silenced.
    """

    producer: Producer
    available: Callable[[], Awaitable[frozenset[RadioFormat]]]
    spend_blocked: Callable[[], Awaitable[bool]]
    aired: HeardLedger
    flashes: FlashSource | None = None


class LoopFactory(Protocol):
    """Builds a loop's parts for a session, and closes what it opened."""

    def __call__(
        self, record: RadioSessionRecord, setup: RadioSetup
    ) -> contextlib.AbstractAsyncContextManager[LoopParts]:
        """The parts, for the life of the loop."""
        ...


class SessionBooks(Protocol):
    """Files a session's end in the transparency register, once — never raises."""

    async def __call__(
        self, *, user_id: UUID, run_id: str, started_at: datetime, reason: EndReason
    ) -> None:
        """File the end of the session ``run_id`` for ``reason``."""
        ...


@dataclass(frozen=True, slots=True)
class RunnerSettings:
    """The loops' settings.

    Attributes:
        media_root: Where the sessions' audio lies.
        record_ttl_s: How long a session's keys outlive their last write.
        lease_s: The loop lease's life (renewed while the loop runs).
        tuning: The loop's timings.
    """

    media_root: Path
    record_ttl_s: int
    lease_s: int
    tuning: LoopTuning


class RadioLoopLauncher:
    """Runs sessions' loops in this worker, and stops them all at shutdown."""

    def __init__(
        self,
        redis: Any,
        *,
        settings: RunnerSettings,
        factory: LoopFactory,
        books: SessionBooks,
        clock: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Bind the launcher.

        Args:
            redis: The cache client.
            settings: The loops' settings.
            factory: Builds a loop's parts.
            books: Files a session's end in the transparency register.
            clock: The current instant (timezone-aware).
            sleep: How a loop waits between two ticks.
        """
        self._redis = redis
        self._settings = settings
        self._factory = factory
        self._books = books
        self._clock = clock
        self._sleep = sleep
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def _store(self, record: RadioSessionRecord) -> RadioSessionStore:
        return RadioSessionStore(
            self._redis,
            user_id=record.user_id,
            session_id=record.session_id,
            ttl_s=self._settings.record_ttl_s,
            media_root=self._settings.media_root,
            clock=self._clock,
        )

    async def ensure(self, record: RadioSessionRecord) -> None:
        """Run the session's loop here, unless a loop already holds its lease."""
        running = self._tasks.get(record.session_id)
        if running is not None and not running.done():
            return
        token = uuid4().hex
        if not await self._store(record).claim_loop(token, lease_s=self._settings.lease_s):
            return
        task = asyncio.create_task(self._run(record, token), name=f"radio-loop-{record.session_id}")
        self._tasks[record.session_id] = task
        task.add_done_callback(lambda done: self._forget(record.session_id, done))

    def _forget(self, session_id: UUID, task: asyncio.Task[None]) -> None:
        if self._tasks.get(session_id) is task:
            del self._tasks[session_id]

    async def stop_all(self, *, timeout_s: float | None = None) -> None:
        """Cancel every loop of this worker and wait for them (the leases are released).

        Args:
            timeout_s: The longest wait (None: until every loop stopped). A loop
                still unwinding past it is left to the process's end, and its
                lease lapses on its own.
        """
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout_s)

    async def _run(self, record: RadioSessionRecord, token: str) -> None:
        store = self._store(record)
        try:
            async with held_claim(
                self._redis, store.loop_key, token, ttl_seconds=self._settings.lease_s
            ):
                state = await store.read_state()
                if state is None or state.ended is not None:
                    return
                reason = await self._drive(record, store, state)
        except ClaimLost as lost:
            logger.info("radio_loop_taken_over", reason=lost.reason)
            return
        except Exception:
            logger.exception("radio_loop_failed", radio_session_id=str(record.session_id))
            radio_loop_failures_total.inc()
            reason = await self._end_after_defect(store)
        await self._ended(record, reason)

    async def _ended(self, record: RadioSessionRecord, reason: EndReason) -> None:
        """Count the end, close the session's books, and let its audio follow the reason."""
        radio_sessions_ended_total.labels(reason=reason.value).inc()
        try:
            await self._books(
                user_id=record.user_id,
                run_id=record.run_id,
                started_at=record.started_at,
                reason=reason,
            )
        except Exception as exc:  # noqa: BLE001 — observing never breaks the observed
            logger.warning("radio_books_unfiled", error_type=type(exc).__name__)
        if reason in DISCARD_AT_END:
            await discard(self._settings.media_root, record.session_id)

    async def _end_after_defect(self, store: RadioSessionStore) -> EndReason:
        """Tell the player the session is over, as far as the store can still be reached.

        Returns:
            The end that stands: the one already published when the defect came
            after it, else ``failures``.
        """
        try:
            state = await store.read_state()
            if state is not None:
                closed = ended_for(state, EndReason.FAILURES)
                await store.publish(closed, {})
                return closed.ended or EndReason.FAILURES
        except Exception as exc:  # noqa: BLE001 — the keys expire on their own
            logger.warning("radio_loop_end_unpublished", error_type=type(exc).__name__)
        return EndReason.FAILURES

    async def _drive(
        self, record: RadioSessionRecord, store: RadioSessionStore, state: SessionState
    ) -> EndReason:
        try:
            setup = RadioSetup.from_dict(record.setup)
            listening = listening_of(setup)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("radio_setup_unreadable", error_type=type(exc).__name__)
            await store.publish(ended_for(state, EndReason.FAILURES), {})
            return EndReason.FAILURES
        async with self._factory(record, setup) as parts:
            return await run_session(
                reloaded(state),
                listening=listening,
                ports=LoopPorts(
                    inbox=store,
                    board=store,
                    producer=parts.producer,
                    available=parts.available,
                    spend_blocked=parts.spend_blocked,
                    aired=parts.aired,
                    now=self._clock,
                    sleep=self._sleep,
                    flashes=parts.flashes,
                ),
                tuning=self._settings.tuning,
                # What a previous loop produced: heard after the restart, still filed.
                ready=await store.read_ready(),
            )


__all__ = [
    "LoopFactory",
    "LoopParts",
    "RadioLoopLauncher",
    "RunnerSettings",
    "SessionBooks",
]
