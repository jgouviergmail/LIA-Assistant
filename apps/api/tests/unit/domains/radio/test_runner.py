"""Where a loop runs: one per session, its parts closed, its end deciding the audio's fate
and closing the session's books in the transparency register."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from prometheus_client import REGISTRY

from src.domains.radio import runner as runner_module
from src.domains.radio.aired import HeardLine
from src.domains.radio.flash import FlashNote
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.live_store import RadioSessionRecord, RadioSessionStore
from src.domains.radio.media import session_dir
from src.domains.radio.orchestrator import HeardLedger, Listening, LoopPorts, LoopTuning
from src.domains.radio.pacing import StageTimings
from src.domains.radio.production import ProducedSegment
from src.domains.radio.programme import Slot
from src.domains.radio.runner import LoopParts, RadioLoopLauncher, RunnerSettings
from src.domains.radio.session import EndReason, SessionRules, SessionState, start
from src.domains.radio.setup import RadioSetup, VerificationMode
from tests.unit.domains.radio.fakes import Books, ClosedBooks, FakeRedis

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
USER = UUID("00000000-0000-4000-8000-0000000000c1")
TUNING = LoopTuning(
    tick_s=1.0,
    first_delay_s=15.0,
    timings=StageTimings(
        writer_s=6.0, analysis_s=15.0, tts_realtime_factor=0.4, tts_concurrency=3, mix_s=0.5
    ),
    rules=SessionRules(
        idle_timeout_s=60,
        pause_timeout_s=900,
        failures_max=3,
        lookahead_safety=1.5,
        lookahead_margin_s=15,
    ),
)
SETUP = RadioSetup(
    language="en",
    language_name="English",
    timezone="UTC",
    station_name="LIA Radio",
    personality="Calm.",
    listener_name=None,
    interests=(),
    stated_tastes=(),
    frequencies={},
    public_mode=False,
    voices={RadioRole.HOST: "voice-a"},
    verification=VerificationMode.OFF,
    disabled_sources=frozenset(),
    disabled_feeds=frozenset(),
    seed=7,
    startup_estimate_s=12.0,
)


class Producer:
    async def produce(
        self, slot: Slot, *, previous: RadioFormat | None, following: RadioFormat | None
    ) -> ProducedSegment | None:
        raise AssertionError("run_session is stood in for")

    async def produce_flash(
        self,
        notes: Sequence[FlashNote],
        *,
        seq: int,
        cuts: RadioFormat | None,
        resumes: RadioFormat | None,
    ) -> ProducedSegment | None:
        raise AssertionError("run_session is stood in for")


class Ledger:
    async def remember(self, lines: Sequence[HeardLine]) -> None:
        raise AssertionError("run_session is stood in for")


async def nothing_available() -> frozenset[RadioFormat]:
    return frozenset()


async def not_blocked() -> bool:
    return False


class Factory:
    """Opens the loop's parts and records that they were closed."""

    def __init__(self, *, broken: bool = False, broken_on_exit: bool = False) -> None:
        self.broken = broken
        self.broken_on_exit = broken_on_exit
        self.opened = 0
        self.closed = 0
        self.ledger = Ledger()

    @contextlib.asynccontextmanager
    async def _parts(self) -> AsyncIterator[LoopParts]:
        if self.broken:
            raise RuntimeError("TTS client misconfigured")
        self.opened += 1
        try:
            yield LoopParts(
                producer=Producer(),
                available=nothing_available,
                spend_blocked=not_blocked,
                aired=self.ledger,
            )
        finally:
            self.closed += 1
        if self.broken_on_exit:
            raise RuntimeError("the TTS client failed to close")

    def __call__(
        self, record: RadioSessionRecord, setup: RadioSetup
    ) -> contextlib.AbstractAsyncContextManager[LoopParts]:
        assert setup == SETUP
        return self._parts()


class Session:
    """Stands for ``run_session``: ends as told, or waits until released."""

    def __init__(self, reason: EndReason, *, hold: bool = False) -> None:
        self.reason = reason
        self.released = asyncio.Event()
        if not hold:
            self.released.set()
        self.runs = 0
        self.ready: Mapping[int, ProducedSegment] | None = None
        self.aired: HeardLedger | None = None

    async def __call__(
        self,
        state: SessionState,
        *,
        listening: Listening,
        ports: LoopPorts,
        tuning: LoopTuning,
        ready: Mapping[int, ProducedSegment] | None = None,
    ) -> EndReason:
        self.runs += 1
        self.ready, self.aired = ready, ports.aired
        await self.released.wait()
        await ports.board.publish(
            SessionState(started_at=state.started_at, stop_at=state.stop_at, ended=self.reason),
            {},
        )
        return self.reason


def record(setup: dict[str, object] | None = None) -> RadioSessionRecord:
    session_id = uuid4()
    return RadioSessionRecord(
        session_id=session_id,
        user_id=USER,
        run_id=f"radio_{session_id.hex}",
        started_at=NOW,
        setup=SETUP.to_dict() if setup is None else setup,
    )


def store(redis: FakeRedis, rec: RadioSessionRecord, root: Path) -> RadioSessionStore:
    return RadioSessionStore(
        redis, user_id=USER, session_id=rec.session_id, ttl_s=60, media_root=root
    )


async def begun(
    redis: FakeRedis, root: Path, setup: dict[str, object] | None = None
) -> RadioSessionRecord:
    rec = record(setup)
    await store(redis, rec, root).publish(start(NOW, NOW + timedelta(minutes=30)), {})
    session_dir(root, rec.session_id).mkdir(parents=True)
    return rec


def launcher(
    redis: FakeRedis, root: Path, factory: Factory, *, books: Books | None = None
) -> RadioLoopLauncher:
    return RadioLoopLauncher(
        redis,
        settings=RunnerSettings(media_root=root, record_ttl_s=60, lease_s=30, tuning=TUNING),
        factory=factory,
        books=books or Books(),
        clock=lambda: NOW,
    )


async def settle(radio: RadioLoopLauncher) -> None:
    """Let every loop of the launcher run to its end."""
    for _ in range(50):
        await asyncio.sleep(0)
    await radio.stop_all()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


async def test_one_loop_per_session_and_its_parts_are_closed(
    redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = Session(EndReason.TIMER, hold=True)
    monkeypatch.setattr(runner_module, "run_session", session)
    factory = Factory()
    rec = await begun(redis, tmp_path)
    radio = launcher(redis, tmp_path, factory)
    await radio.ensure(rec)
    await asyncio.sleep(0)
    await radio.ensure(rec)  # this worker already runs it
    await launcher(redis, tmp_path, factory).ensure(rec)  # another worker: the lease is held
    for _ in range(5):
        await asyncio.sleep(0)
    assert await store(redis, rec, tmp_path).loop_alive()
    session.released.set()
    await settle(radio)
    assert session.runs == 1
    assert (factory.opened, factory.closed) == (1, 1)
    assert not await store(redis, rec, tmp_path).loop_alive()


async def test_a_loop_starts_from_the_published_segments_and_files_in_its_parts_ledger(
    redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restarted loop (a deploy, a reload) finds what was produced before it: heard
    after the restart, it is filed all the same (ADR-324 decision 35)."""
    session = Session(EndReason.TIMER)
    monkeypatch.setattr(runner_module, "run_session", session)
    factory = Factory()
    rec = await begun(redis, tmp_path)
    produced = ProducedSegment(
        title="Opening",
        audio_path=tmp_path / "0001.mp3",
        duration_s=20.0,
        transcript=(),
        dropped_lines=0,
        unrendered=(),
        memory=(HeardLine(offset_s=0.5, personal=frozenset({"event:dentist"})),),
    )
    await store(redis, rec, tmp_path).publish(
        start(NOW, NOW + timedelta(minutes=30)), {1: produced}
    )
    radio = launcher(redis, tmp_path, factory)
    await radio.ensure(rec)
    await settle(radio)
    assert session.ready is not None and session.ready[1].memory == produced.memory
    assert session.aired is factory.ledger


@pytest.mark.parametrize(
    ("reason", "kept"),
    [
        (EndReason.LISTENER, False),
        (EndReason.IDLE, False),
        (EndReason.TIMER, True),  # the player still has the farewell to play
        (EndReason.BUDGET, True),
        (EndReason.FAILURES, True),
    ],
)
async def test_the_audio_follows_the_reason_the_session_ended(
    redis: FakeRedis,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: EndReason,
    kept: bool,
) -> None:
    discarded: list[UUID] = []

    async def discard(root: Path, session_id: UUID) -> None:
        discarded.append(session_id)

    monkeypatch.setattr(runner_module, "run_session", Session(reason))
    monkeypatch.setattr(runner_module, "discard", discard)
    rec = await begun(redis, tmp_path)
    radio = launcher(redis, tmp_path, Factory())
    await radio.ensure(rec)
    await settle(radio)
    assert discarded == ([] if kept else [rec.session_id])


async def test_an_unreadable_setup_ends_the_session_as_failed(
    redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = Session(EndReason.TIMER)
    monkeypatch.setattr(runner_module, "run_session", session)
    rec = await begun(redis, tmp_path, setup={"language": "en"})
    radio = launcher(redis, tmp_path, Factory())
    await radio.ensure(rec)
    await settle(radio)
    state = await store(redis, rec, tmp_path).read_state()
    assert state is not None and state.ended is EndReason.FAILURES
    assert session.runs == 0


async def test_a_loop_that_breaks_ends_the_session_and_frees_the_lease(
    redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER))
    rec = await begun(redis, tmp_path)
    radio = launcher(redis, tmp_path, Factory(broken=True))
    await radio.ensure(rec)
    await settle(radio)
    state = await store(redis, rec, tmp_path).read_state()
    assert state is not None and state.ended is EndReason.FAILURES
    assert not await store(redis, rec, tmp_path).loop_alive()


async def test_a_shutdown_ends_nothing_another_worker_takes_it_up(
    redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER, hold=True))
    factory = Factory()
    rec = await begun(redis, tmp_path)
    radio = launcher(redis, tmp_path, factory)
    await radio.ensure(rec)
    for _ in range(5):
        await asyncio.sleep(0)
    await radio.stop_all()
    state = await store(redis, rec, tmp_path).read_state()
    assert state is not None and state.ended is None
    assert not await store(redis, rec, tmp_path).loop_alive()
    assert factory.closed == 1
    assert session_dir(tmp_path, rec.session_id).exists()


class Stubborn:
    """Stands for a ``run_session`` whose unwinding outlasts a shutdown's patience."""

    def __init__(self) -> None:
        self.unwinding = asyncio.Event()
        self.may_leave = asyncio.Event()

    async def __call__(
        self,
        state: SessionState,
        *,
        listening: Listening,
        ports: LoopPorts,
        tuning: LoopTuning,
        ready: Mapping[int, ProducedSegment] | None = None,
    ) -> EndReason:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.unwinding.set()
            await self.may_leave.wait()
            raise
        raise AssertionError("a loop that is never released never returns")


async def test_a_shutdown_waits_for_its_loops_within_a_bound(
    redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loop still unwinding never holds the teardown: the wait is bounded."""
    stubborn = Stubborn()
    monkeypatch.setattr(runner_module, "run_session", stubborn)
    rec = await begun(redis, tmp_path)
    radio = launcher(redis, tmp_path, Factory())
    await radio.ensure(rec)
    for _ in range(5):
        await asyncio.sleep(0)
    await asyncio.wait_for(radio.stop_all(timeout_s=0.05), timeout=2)
    assert stubborn.unwinding.is_set()
    # The loop is still this launcher's: once it may leave, a stop waits for it.
    stubborn.may_leave.set()
    await asyncio.wait_for(radio.stop_all(), timeout=2)
    assert not await store(redis, rec, tmp_path).loop_alive()


async def test_an_ended_session_is_never_run_again(
    redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = Session(EndReason.TIMER)
    monkeypatch.setattr(runner_module, "run_session", session)
    rec = record()
    ended = SessionState(started_at=NOW, stop_at=None, ended=EndReason.LISTENER)
    await store(redis, rec, tmp_path).publish(ended, {})
    radio = launcher(redis, tmp_path, Factory())
    await radio.ensure(rec)
    await settle(radio)
    assert session.runs == 0


def ended(reason: EndReason) -> float:
    labels = {"reason": reason.value}
    return REGISTRY.get_sample_value("radio_sessions_ended_total", labels) or 0.0


def loop_failures() -> float:
    return REGISTRY.get_sample_value("radio_loop_failures_total") or 0.0


class TestEveryEndIsCounted:
    async def test_a_session_that_ends_is_counted_by_its_reason(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER))
        before = ended(EndReason.TIMER)
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory())

        await radio.ensure(rec)
        await settle(radio)

        assert ended(EndReason.TIMER) == before + 1

    async def test_a_loop_that_breaks_is_a_failure_and_an_end(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER))
        failures, ends = loop_failures(), ended(EndReason.FAILURES)
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory(broken=True))

        await radio.ensure(rec)
        await settle(radio)

        assert (loop_failures(), ended(EndReason.FAILURES)) == (failures + 1, ends + 1)

    async def test_a_worker_stopping_ends_nothing(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER, hold=True))
        before = {reason: ended(reason) for reason in EndReason}
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory())

        await radio.ensure(rec)
        for _ in range(5):
            await asyncio.sleep(0)
        await radio.stop_all()

        assert {reason: ended(reason) for reason in EndReason} == before


class TestTheBooksAreClosedWhenTheSessionEnds:
    """One row in the decision register per session, under its run (ADR-324 decision 31)."""

    async def test_a_session_that_ends_files_its_end_under_its_run(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER))
        books = Books()
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory(), books=books)

        await radio.ensure(rec)
        await settle(radio)

        assert books.closed == [ClosedBooks(USER, rec.run_id, NOW, EndReason.TIMER)]

    @pytest.mark.parametrize("unreadable_setup", [False, True])
    async def test_a_loop_that_breaks_files_a_failed_session(
        self,
        redis: FakeRedis,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        unreadable_setup: bool,
    ) -> None:
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER))
        books = Books()
        rec = await begun(redis, tmp_path, setup={"language": "en"} if unreadable_setup else None)
        radio = launcher(redis, tmp_path, Factory(broken=not unreadable_setup), books=books)

        await radio.ensure(rec)
        await settle(radio)

        assert [closed.reason for closed in books.closed] == [EndReason.FAILURES]

    async def test_a_defect_after_the_end_files_the_end_that_stands(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The programme ran to its timer and only closing its parts failed: the
        session ended on its timer, and saying ``failures`` would be the register
        — and the counter — lying about how it ended."""
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER))
        books = Books()
        failures, timers, broken = (
            loop_failures(),
            ended(EndReason.TIMER),
            ended(EndReason.FAILURES),
        )
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory(broken_on_exit=True), books=books)

        await radio.ensure(rec)
        await settle(radio)

        assert [closed.reason for closed in books.closed] == [EndReason.TIMER]
        assert loop_failures() == failures + 1
        assert (ended(EndReason.TIMER), ended(EndReason.FAILURES)) == (timers + 1, broken)

    async def test_a_listener_s_end_followed_by_a_defect_still_discards_the_audio(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        discarded = discards(monkeypatch)
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.LISTENER))
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory(broken_on_exit=True))

        await radio.ensure(rec)
        await settle(radio)

        assert discarded == [rec.session_id]

    async def test_a_shutdown_or_an_ended_session_files_nothing(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.TIMER, hold=True))
        books = Books()
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory(), books=books)
        await radio.ensure(rec)
        for _ in range(5):
            await asyncio.sleep(0)
        await radio.stop_all()  # another worker takes it up: the session has not ended

        done = record()
        ended_state = SessionState(started_at=NOW, stop_at=None, ended=EndReason.LISTENER)
        await store(redis, done, tmp_path).publish(ended_state, {})
        await radio.ensure(done)  # already closed by whoever ended it
        await settle(radio)

        assert books.closed == []

    async def test_a_register_that_fails_never_keeps_the_audio(
        self, redis: FakeRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        discarded = discards(monkeypatch)
        monkeypatch.setattr(runner_module, "run_session", Session(EndReason.IDLE))
        books = Books(fails=True)
        rec = await begun(redis, tmp_path)
        radio = launcher(redis, tmp_path, Factory(), books=books)

        await radio.ensure(rec)
        await settle(radio)

        assert len(books.closed) == 1
        assert discarded == [rec.session_id]


def discards(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    """Record the audio the runner throws away — the real removal runs in a thread,
    which ``settle`` may cancel mid-flight under a loaded run."""
    discarded: list[UUID] = []

    async def discard(root: Path, session_id: UUID) -> None:
        discarded.append(session_id)

    monkeypatch.setattr(runner_module, "discard", discard)
    return discarded
