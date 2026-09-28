"""A radio session's four doors: start, report, stop, and a segment's audio.

Stateless between requests (four workers, ADR-271): everything a session knows
lives in Redis (:mod:`~src.domains.radio.live_store`), and the loop producing it
runs on whichever worker holds its lease. A report that finds no loop starts one
where it landed — a worker restarted mid-session costs the listener a few
seconds of the station's music, never the session — and a stop that finds none
closes the books itself, since nobody else would read it. So does a start that
replaces a session no loop holds: a report on a replaced session never revives
its loop, so nobody else would end it either. Closing the books means the state
says it ended, its audio goes, and its end is filed in the transparency
register (``SessionBooks``, ADR-324 decision 31).

Order matters at the start: a listener whose radio spent its day's budget is
refused first (ADR-324 decision 37 — nothing taken, nothing read), then the
session takes its place under the instance's cap (a start past it is refused
before anything is read), then the state
is published BEFORE the record names the session, so a report never finds a
session without a state. A start that fails after taking its place gives it back.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from src.domains.radio.budget import BudgetReader
from src.domains.radio.constants import RADIO_RUN_ID_PREFIX
from src.domains.radio.live_store import RadioSessionRecord, RadioSessions, RadioSessionStore
from src.domains.radio.media import discard, segment_path
from src.domains.radio.pacing import Playhead
from src.domains.radio.runner import SessionBooks
from src.domains.radio.schemas import RadioPlayheadRequest, RadioSessionResponse, RadioStartRequest
from src.domains.radio.session import EndReason, SessionState, start, stopped
from src.domains.radio.setup import RadioSetup
from src.domains.radio.setup_builder import (
    REFUSED_BUDGET,
    REFUSED_INSTANCE_FULL,
    RadioStartRefused,
)
from src.domains.radio.view import cost_estimate, pending_seqs, session_response

logger = structlog.get_logger(__name__)


def radio_run_id(session_id: UUID) -> str:
    """What every euro of a session is filed under — one spelling, one place."""
    return f"{RADIO_RUN_ID_PREFIX}{session_id.hex}"


class SetupBuilder(Protocol):
    """Reads the listener's settings into a session's frozen setup."""

    async def build(
        self, user_id: UUID, request: RadioStartRequest, *, now: datetime, run_id: str
    ) -> tuple[RadioSetup, datetime | None]:
        """The setup, and the automatic stop (None for none).

        ``run_id`` is the session's: what the start reads of the listener is
        filed under it.
        """
        ...


class LoopLauncher(Protocol):
    """Runs a session's loop in this worker, unless a loop already holds its lease."""

    async def ensure(self, record: RadioSessionRecord) -> None:
        """Start the loop here if no loop holds the lease."""
        ...


class CostReader(Protocol):
    """What a session has cost so far, from the ledger its run fills."""

    async def cost_eur(self, run_id: str) -> float | None:
        """Every family, in euros; None when unknown."""
        ...


@dataclass(frozen=True, slots=True)
class RadioRuntime:
    """The session doors' settings.

    Attributes:
        media_root: Where the sessions' audio lies.
        record_ttl_s: How long a session's keys outlive their last write.
        max_active_sessions: The sessions the instance runs at once.
        live_horizon_s: How recently a live session has published, at the
            least (a session silent for longer holds no place).
        cost_estimate_min_audio_s: The radio produced before its cost is
            extrapolated to the planned listening.
        segment_gap_s: The station's music between two programmes, fixed in
            each session when it starts (ADR-324 decision 36).
    """

    media_root: Path
    record_ttl_s: int
    max_active_sessions: int
    live_horizon_s: float
    cost_estimate_min_audio_s: float
    segment_gap_s: float


class RadioSessionService:
    """The four doors, over Redis and the loop's ports."""

    def __init__(
        self,
        redis: Any,
        *,
        runtime: RadioRuntime,
        setups: SetupBuilder,
        loops: LoopLauncher,
        costs: CostReader,
        books: SessionBooks,
        budget: BudgetReader,
        clock: Callable[[], datetime],
    ) -> None:
        """Bind the doors.

        Args:
            redis: The cache client.
            runtime: Their settings.
            setups: Reads the listener's settings at a start.
            loops: Runs a session's loop.
            costs: Reads what a session has cost.
            books: Files a session's end in the transparency register.
            budget: Reads what the listener's radio spent over the rolling day.
            clock: The current instant (timezone-aware).
        """
        self._redis = redis
        self._runtime = runtime
        self._sessions = RadioSessions(redis, ttl_s=runtime.record_ttl_s)
        self._setups = setups
        self._loops = loops
        self._costs = costs
        self._books = books
        self._budget = budget
        self._clock = clock

    def _store(self, user_id: UUID, session_id: UUID) -> RadioSessionStore:
        return RadioSessionStore(
            self._redis,
            user_id=user_id,
            session_id=session_id,
            ttl_s=self._runtime.record_ttl_s,
            media_root=self._runtime.media_root,
            clock=self._clock,
        )

    async def start(self, user_id: UUID, request: RadioStartRequest) -> RadioSessionResponse:
        """Open a session — the account's previous one, if any, stops at its next tick.

        Args:
            user_id: The listener.
            request: What they chose for this session.

        Returns:
            The session, starting.

        Raises:
            RadioStartRefused: Past the listener's radio budget (with its bound
                and when it lifts), or past the instance's cap, or when the
                setup refuses.
        """
        now = self._clock()
        budget = await self._budget(user_id, now=now)
        if budget.reached:
            raise RadioStartRefused(
                REFUSED_BUDGET,
                detail={
                    "max_eur": budget.limit_eur,
                    "lifts_at": None if budget.lifts_at is None else budget.lifts_at.isoformat(),
                },
            )
        session_id = uuid4()
        previous = await self._sessions.current(user_id)
        admitted = await self._sessions.admit(
            session_id,
            replacing=None if previous is None else previous.session_id,
            now=now,
            horizon_s=self._runtime.live_horizon_s,
            cap=self._runtime.max_active_sessions,
        )
        if not admitted:
            raise RadioStartRefused(REFUSED_INSTANCE_FULL)
        try:
            setup, stop_at = await self._setups.build(
                user_id, request, now=now, run_id=radio_run_id(session_id)
            )
            record = RadioSessionRecord(
                session_id=session_id,
                user_id=user_id,
                run_id=radio_run_id(session_id),
                started_at=now,
                setup=setup.to_dict(),
            )
            state = start(now, stop_at, gap_s=self._runtime.segment_gap_s)
            await self._store(user_id, session_id).publish(state, {})
            await self._sessions.open(record)
        except BaseException:
            # Refused, failed or cancelled: the place taken is given back.
            await self._sessions.release(session_id)
            raise
        await self._loops.ensure(record)
        logger.info(
            "radio_session_started", radio_session_id=str(session_id), timer=stop_at is not None
        )
        if previous is not None:
            await self._close_replaced(previous)
        return session_response(
            session_id,
            state,
            {},
            cost_eur=None,
            startup_estimate_s=setup.startup_estimate_s,
            now=now,
            zone=_zone_of(record.setup),
            station_name=setup.station_name,
        )

    async def report(
        self, user_id: UUID, session_id: UUID, request: RadioPlayheadRequest
    ) -> RadioSessionResponse | None:
        """File the player's report and answer with the session.

        Args:
            user_id: The listener (a session of another account is unknown here).
            session_id: The session.
            request: Where the player is.

        Returns:
            The session; None when the account has no such session.
        """
        store = self._store(user_id, session_id)
        state = await store.read_state()
        if state is None:
            return None
        record = await self._sessions.current(user_id)
        current = record is not None and record.session_id == session_id
        if state.ended is None:
            if current and record is not None:
                await store.write_playhead(
                    Playhead(
                        seq=request.seq,
                        position_s=request.position_s,
                        reported_at=self._clock(),
                        playing=request.playing,
                        paused=request.paused,
                        flash_heard=request.flash_heard,
                    )
                )
                await self._loops.ensure(record)
            else:
                # Another start took the account's place: this session's loop stops
                # at its next tick, and the player is told so now.
                state = stopped(state)
        return await self._answer(store, session_id, state, record if current else None)

    async def stop(self, user_id: UUID, session_id: UUID) -> bool:
        """Stop a session — False when the account has no such session.

        The loop reads the stop at its next tick; with no loop holding the
        lease, nobody would, and the books are closed here.
        """
        store = self._store(user_id, session_id)
        state = await store.read_state()
        if state is None:
            return False
        await store.request_stop()
        if state.ended is None and not await store.loop_alive():
            await self._close_books(store, user_id, session_id, state)
            logger.info("radio_session_stopped_without_loop", radio_session_id=str(session_id))
        return True

    async def _close_replaced(self, previous: RadioSessionRecord) -> None:
        """End the session a start replaced, when no loop holds it — never failing the start.

        A loop that holds it reads the replacement at its next tick and closes
        the books itself; with none, a report on the old session never revives
        one, and nobody else would.
        """
        try:
            store = self._store(previous.user_id, previous.session_id)
            state = await store.read_state()
            if state is None or state.ended is not None or await store.loop_alive():
                return
            await self._close_books(store, previous.user_id, previous.session_id, state)
            logger.info(
                "radio_session_replaced_without_loop",
                radio_session_id=str(previous.session_id),
            )
        except Exception as exc:  # noqa: BLE001 — the new session is running
            logger.warning("radio_replaced_session_unclosed", error_type=type(exc).__name__)

    async def _close_books(
        self, store: RadioSessionStore, user_id: UUID, session_id: UUID, state: SessionState
    ) -> None:
        """Say the session ended at the listener's word, drop its audio, and file its end."""
        await store.publish(stopped(state), {})
        await discard(self._runtime.media_root, session_id)
        try:
            await self._books(
                user_id=user_id,
                run_id=radio_run_id(session_id),
                started_at=state.started_at,
                reason=EndReason.LISTENER,
            )
        except Exception as exc:  # noqa: BLE001 — observing never breaks the observed
            logger.warning("radio_books_unfiled", error_type=type(exc).__name__)

    async def audio_path(self, user_id: UUID, session_id: UUID, seq: int) -> Path | None:
        """A ready segment's — or news flash's — audio file; None when the account has no such."""
        state = await self._store(user_id, session_id).read_state()
        if state is None or not (seq in state.produced or _flash_ready(state, seq)):
            return None
        path = segment_path(self._runtime.media_root, session_id, seq)
        return path if await asyncio.to_thread(path.is_file) else None

    async def _answer(
        self,
        store: RadioSessionStore,
        session_id: UUID,
        state: SessionState,
        record: RadioSessionRecord | None,
    ) -> RadioSessionResponse:
        segments = await store.read_segments(pending_seqs(state))
        try:
            cost = await self._costs.cost_eur(radio_run_id(session_id))
        except Exception as exc:  # noqa: BLE001 — an unknown cost is shown as unknown
            logger.warning("radio_cost_unavailable", error_type=type(exc).__name__)
            cost = None
        startup = record.setup.get("startup_estimate_s") if record is not None else None
        return session_response(
            session_id,
            state,
            segments,
            cost_eur=cost,
            startup_estimate_s=float(startup) if isinstance(startup, int | float) else None,
            now=self._clock(),
            zone=_zone_of(record.setup) if record is not None else None,
            station_name=_station_of(record.setup) if record is not None else None,
            estimate=cost_estimate(
                state, cost, min_audio_s=self._runtime.cost_estimate_min_audio_s
            ),
        )


def _flash_ready(state: SessionState, seq: int) -> bool:
    """Whether ``seq`` is a news flash whose audio is ready (ADR-324 decision 32)."""
    return any(flash.seq == seq and flash.produced for flash in state.flashes)


def _station_of(setup: Mapping[str, object]) -> str | None:
    """The station's name in a session's frozen setup."""
    name = setup.get("station_name")
    return name if isinstance(name, str) and name else None


def _zone_of(setup: Mapping[str, object]) -> tzinfo | None:
    """The listener's timezone in a session's frozen setup; None when this host cannot read it."""
    try:
        return ZoneInfo(str(setup["timezone"]))
    except KeyError, ValueError, ZoneInfoNotFoundError:
        return None


__all__ = [
    "CostReader",
    "LoopLauncher",
    "RadioRuntime",
    "RadioSessionService",
    "SetupBuilder",
    "radio_run_id",
]
