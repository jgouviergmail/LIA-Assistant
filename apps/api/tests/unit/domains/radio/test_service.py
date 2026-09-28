"""A session's doors: start, report, stop, audio — over Redis, with the loop's ports doubled."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from src.domains.radio.budget import BudgetStatus
from src.domains.radio.flash import Flash
from src.domains.radio.formats import MusicMood, RadioFormat, RadioRole
from src.domains.radio.live_store import ACTIVE_KEY, RadioSessionRecord, RadioSessionStore
from src.domains.radio.media import segment_path, session_dir
from src.domains.radio.pacing import Playhead
from src.domains.radio.programme import Slot
from src.domains.radio.schemas import RadioPlayheadRequest, RadioStartRequest
from src.domains.radio.service import RadioRuntime, RadioSessionService, radio_run_id
from src.domains.radio.session import EndReason
from src.domains.radio.setup import RadioSetup, VerificationMode
from src.domains.radio.setup_builder import RadioStartRefused
from tests.unit.domains.radio.fakes import Books, ClosedBooks, FakeRedis

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
ALICE = UUID("00000000-0000-4000-8000-0000000000a1")
BOB = UUID("00000000-0000-4000-8000-0000000000b0")
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


class Setups:
    def __init__(self, *, refuses: str | None = None, setup: RadioSetup = SETUP) -> None:
        self.refuses = refuses
        self.setup = setup

    async def build(
        self, user_id: UUID, request: RadioStartRequest, *, now: datetime, run_id: str
    ) -> tuple[RadioSetup, datetime | None]:
        assert run_id.startswith("radio_")  # what the start reads is filed under the session
        if self.refuses is not None:
            raise RadioStartRefused(self.refuses)
        return self.setup, now + timedelta(minutes=30)


class Loops:
    """Records every launch; with ``hold``, takes the lease like a real loop would."""

    def __init__(self, redis: FakeRedis, tmp_path: Path, *, hold: bool) -> None:
        self.redis = redis
        self.tmp_path = tmp_path
        self.hold = hold
        self.launched: list[UUID] = []

    async def ensure(self, record: RadioSessionRecord) -> None:
        self.launched.append(record.session_id)
        if self.hold:
            store = RadioSessionStore(
                self.redis,
                user_id=record.user_id,
                session_id=record.session_id,
                ttl_s=60,
                media_root=self.tmp_path,
            )
            await store.claim_loop("worker-a", lease_s=30)


class Costs:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.asked: list[str] = []

    async def cost_eur(self, run_id: str) -> float | None:
        self.asked.append(run_id)
        if self.fails:
            raise ConnectionError("database down")
        return 0.0042


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


#: A live session publishes at least this often (the idle timeout's order).
LIVE_HORIZON_S = 120.0


class Budget:
    """Stands for the listener's radio budget over the rolling day."""

    def __init__(self, status: BudgetStatus | None = None) -> None:
        self.status = status or BudgetStatus(limit_eur=2.0, spent_eur=0.0, lifts_at=None)

    async def __call__(self, user_id: UUID, *, now: datetime) -> BudgetStatus:
        return self.status


def service(
    redis: FakeRedis,
    tmp_path: Path,
    loops: Loops,
    *,
    costs: Costs | None = None,
    setups: Setups | None = None,
    cap: int = 20,
    clock: Clock | None = None,
    books: Books | None = None,
    budget: Budget | None = None,
) -> RadioSessionService:
    return RadioSessionService(
        redis,
        runtime=RadioRuntime(
            media_root=tmp_path,
            record_ttl_s=3600,
            max_active_sessions=cap,
            live_horizon_s=LIVE_HORIZON_S,
            cost_estimate_min_audio_s=120.0,
            segment_gap_s=5.0,
        ),
        setups=setups or Setups(),
        loops=loops,
        costs=costs or Costs(),
        books=books or Books(),
        budget=budget or Budget(),
        clock=clock or Clock(),
    )


def report(
    seq: int = 1, position_s: float = 0.0, playing: bool = True, paused: bool = False
) -> RadioPlayheadRequest:
    return RadioPlayheadRequest(seq=seq, position_s=position_s, playing=playing, paused=paused)


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


async def test_a_start_answers_at_once_and_launches_the_loop(
    redis: FakeRedis, tmp_path: Path
) -> None:
    loops = Loops(redis, tmp_path, hold=True)
    started = await service(redis, tmp_path, loops).start(ALICE, RadioStartRequest())
    assert (started.status, started.startup_estimate_s) == ("starting", 12.0)
    assert started.mood is MusicMood.MORNING  # 08:00 on the listener's clock, nothing planned
    assert started.stop_at == NOW + timedelta(minutes=30)
    assert loops.launched == [started.session_id]
    # A report arriving at once finds the state the start published.
    answer = await service(redis, tmp_path, loops).report(ALICE, started.session_id, report())
    assert answer is not None and answer.status == "starting"
    assert answer.mood is MusicMood.MORNING
    # The music between two programmes is the instance's at the start, told to the player.
    assert started.segment_gap_s == answer.segment_gap_s == 5.0


async def test_a_report_is_timed_by_the_server_and_revives_a_dead_loop(
    redis: FakeRedis, tmp_path: Path
) -> None:
    loops = Loops(redis, tmp_path, hold=False)  # the worker holding it restarted
    doors = service(redis, tmp_path, loops)
    session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
    answer = await doors.report(ALICE, session_id, report(seq=1, position_s=3.5, playing=False))
    assert answer is not None and answer.cost_eur == 0.0042
    store = RadioSessionStore(
        redis, user_id=ALICE, session_id=session_id, ttl_s=60, media_root=tmp_path
    )
    assert await store.playhead() == Playhead(seq=1, position_s=3.5, reported_at=NOW, playing=False)
    assert loops.launched == [session_id, session_id]


async def test_a_report_names_the_station_and_prices_the_planned_listening(
    redis: FakeRedis, tmp_path: Path
) -> None:
    loops = Loops(redis, tmp_path, hold=True)
    doors = service(redis, tmp_path, loops)
    started = await doors.start(ALICE, RadioStartRequest())
    assert (started.station_name, started.cost_estimate_eur) == ("LIA Radio", None)
    store = RadioSessionStore(
        redis, user_id=ALICE, session_id=started.session_id, ttl_s=60, media_root=tmp_path
    )
    state = await store.read_state()
    assert state is not None
    slot = Slot(seq=1, format=RadioFormat.OPENING, station_id=True, air_at=NOW, duration_s=210.0)
    await store.publish(replace(state, slots=(slot,), produced=frozenset({1})), {})
    answer = await doors.report(ALICE, started.session_id, report())
    assert answer is not None
    # 0.0042 € for 210 s of radio, over the 30 minutes planned.
    assert answer.station_name == "LIA Radio"
    assert answer.cost_estimate_eur == pytest.approx(0.0042 / 210 * 1800)
    assert answer.cost_estimate_s == 1800.0


async def test_a_report_prices_nothing_before_the_minimum_of_radio(
    redis: FakeRedis, tmp_path: Path
) -> None:
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True))
    started = await doors.start(ALICE, RadioStartRequest())
    store = RadioSessionStore(
        redis, user_id=ALICE, session_id=started.session_id, ttl_s=60, media_root=tmp_path
    )
    state = await store.read_state()
    assert state is not None
    # One short programme: under the runtime's minimum, a rate would be a guess.
    slot = Slot(seq=1, format=RadioFormat.OPENING, station_id=True, air_at=NOW, duration_s=60.0)
    await store.publish(replace(state, slots=(slot,), produced=frozenset({1})), {})
    answer = await doors.report(ALICE, started.session_id, report())
    assert answer is not None
    assert (answer.cost_estimate_eur, answer.cost_estimate_s) == (None, None)


async def test_the_listeners_pause_reaches_the_loop(redis: FakeRedis, tmp_path: Path) -> None:
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True))
    session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
    await doors.report(ALICE, session_id, report(seq=2, playing=False, paused=True))
    store = RadioSessionStore(
        redis, user_id=ALICE, session_id=session_id, ttl_s=60, media_root=tmp_path
    )
    assert await store.playhead() == Playhead(
        seq=2, position_s=0.0, reported_at=NOW, playing=False, paused=True
    )


async def test_another_account_s_session_is_unknown(redis: FakeRedis, tmp_path: Path) -> None:
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True))
    session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
    assert await doors.report(BOB, session_id, report()) is None
    assert not await doors.stop(BOB, session_id)
    assert await doors.audio_path(BOB, session_id, 1) is None


async def test_a_session_another_start_replaced_is_told_it_ended(
    redis: FakeRedis, tmp_path: Path
) -> None:
    loops = Loops(redis, tmp_path, hold=True)
    books = Books()
    doors = service(redis, tmp_path, loops, books=books)
    first = (await doors.start(ALICE, RadioStartRequest())).session_id
    second = (await doors.start(ALICE, RadioStartRequest())).session_id
    answer = await doors.report(ALICE, first, report())
    assert answer is not None
    assert (answer.status, answer.end_reason) == ("ended", EndReason.LISTENER.value)
    assert answer.mood is None  # no longer the account's: its clock is not read
    assert loops.launched == [first, second]  # the old one is never revived
    assert books.closed == []  # its loop ends it at its next tick, and closes its books


async def test_a_session_replaced_while_no_loop_holds_it_is_closed_by_the_start(
    redis: FakeRedis, tmp_path: Path
) -> None:
    """Nobody else would: its loop is gone and a report on it never revives one."""
    books = Books()
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=False), books=books)
    first = (await doors.start(ALICE, RadioStartRequest())).session_id
    session_dir(tmp_path, first).mkdir(parents=True)
    await doors.start(ALICE, RadioStartRequest())
    store = RadioSessionStore(redis, user_id=ALICE, session_id=first, ttl_s=60, media_root=tmp_path)
    state = await store.read_state()
    assert state is not None and state.ended is EndReason.LISTENER
    assert not session_dir(tmp_path, first).exists()
    assert books.closed == [ClosedBooks(ALICE, radio_run_id(first), NOW, EndReason.LISTENER)]


async def test_closing_a_replaced_session_never_fails_the_start(
    redis: FakeRedis, tmp_path: Path
) -> None:
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=False), books=Books(fails=True))
    await doors.start(ALICE, RadioStartRequest())
    second = await doors.start(ALICE, RadioStartRequest())
    assert second.status == "starting"


async def test_a_stop_is_left_to_the_loop_that_holds_the_lease(
    redis: FakeRedis, tmp_path: Path
) -> None:
    books = Books()
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True), books=books)
    session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
    session_dir(tmp_path, session_id).mkdir(parents=True)
    assert await doors.stop(ALICE, session_id)
    answer = await doors.report(ALICE, session_id, report())
    assert answer is not None and answer.status == "starting"  # the loop ends it at its tick
    assert session_dir(tmp_path, session_id).exists()
    assert books.closed == []  # and files its end


async def test_a_stop_with_no_loop_closes_the_books_itself(
    redis: FakeRedis, tmp_path: Path
) -> None:
    books = Books()
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=False), books=books)
    session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
    session_dir(tmp_path, session_id).mkdir(parents=True)
    assert await doors.stop(ALICE, session_id)
    store = RadioSessionStore(
        redis, user_id=ALICE, session_id=session_id, ttl_s=60, media_root=tmp_path
    )
    state = await store.read_state()
    assert state is not None and state.ended is EndReason.LISTENER
    assert not session_dir(tmp_path, session_id).exists()
    assert books.closed == [ClosedBooks(ALICE, radio_run_id(session_id), NOW, EndReason.LISTENER)]
    assert await doors.stop(ALICE, session_id)  # stopped twice: filed once
    assert len(books.closed) == 1


async def test_only_a_ready_segment_s_audio_is_served(redis: FakeRedis, tmp_path: Path) -> None:
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True))
    session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
    store = RadioSessionStore(
        redis, user_id=ALICE, session_id=session_id, ttl_s=60, media_root=tmp_path
    )
    state = await store.read_state()
    assert state is not None
    await store.publish(replace(state, produced=frozenset({1, 2})), {})
    path = segment_path(tmp_path, session_id, 1)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mp3")
    assert await doors.audio_path(ALICE, session_id, 1) == path
    assert await doors.audio_path(ALICE, session_id, 2) is None  # ready, but its file is gone
    assert await doors.audio_path(ALICE, session_id, 3) is None  # never produced


async def test_an_unknown_cost_is_shown_as_unknown(redis: FakeRedis, tmp_path: Path) -> None:
    costs = Costs(fails=True)
    doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True), costs=costs)
    session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
    answer = await doors.report(ALICE, session_id, report())
    assert answer is not None and answer.cost_eur is None
    assert costs.asked == [radio_run_id(session_id)]


class TestTheInstanceCap:
    """The instance runs at most ``max_active_sessions`` antennas at once."""

    async def test_a_start_past_the_cap_is_refused_and_takes_no_place(
        self, redis: FakeRedis, tmp_path: Path
    ) -> None:
        loops = Loops(redis, tmp_path, hold=True)
        alice = await service(redis, tmp_path, loops, cap=1).start(ALICE, RadioStartRequest())
        with pytest.raises(RadioStartRefused) as refused:
            await service(redis, tmp_path, loops, cap=1).start(BOB, RadioStartRequest())
        assert refused.value.reason == "instance_full"
        assert set(await redis.zrange(ACTIVE_KEY, 0, -1)) == {str(alice.session_id)}
        assert loops.launched == [alice.session_id]

    async def test_a_listener_past_the_radio_s_budget_is_refused_until_it_lifts(
        self, redis: FakeRedis, tmp_path: Path
    ) -> None:
        """ADR-324 decision 37: refused before any place is taken or anything is billed."""
        loops = Loops(redis, tmp_path, hold=True)
        lifts = NOW + timedelta(hours=3)
        spent = Budget(BudgetStatus(limit_eur=2.0, spent_eur=2.3, lifts_at=lifts))
        with pytest.raises(RadioStartRefused) as refused:
            await service(redis, tmp_path, loops, budget=spent).start(ALICE, RadioStartRequest())
        assert refused.value.reason == "budget_reached"
        assert refused.value.detail == {"max_eur": 2.0, "lifts_at": lifts.isoformat()}
        assert await redis.zrange(ACTIVE_KEY, 0, -1) == [] and loops.launched == []

    async def test_an_account_starting_again_at_the_cap_replaces_its_own(
        self, redis: FakeRedis, tmp_path: Path
    ) -> None:
        loops = Loops(redis, tmp_path, hold=True)
        await service(redis, tmp_path, loops, cap=1).start(ALICE, RadioStartRequest())
        again = await service(redis, tmp_path, loops, cap=1).start(ALICE, RadioStartRequest())
        assert again.status == "starting"  # its previous session stops at its next tick

    async def test_a_session_that_stopped_publishing_gives_its_place_back(
        self, redis: FakeRedis, tmp_path: Path
    ) -> None:
        clock = Clock()
        loops = Loops(redis, tmp_path, hold=True)
        await service(redis, tmp_path, loops, cap=1, clock=clock).start(ALICE, RadioStartRequest())
        clock.now = NOW + timedelta(seconds=LIVE_HORIZON_S + 1)  # its worker died
        bob = await service(redis, tmp_path, loops, cap=1, clock=clock).start(
            BOB, RadioStartRequest()
        )
        assert bob.status == "starting"

    async def test_a_start_whose_setup_is_refused_gives_its_place_back(
        self, redis: FakeRedis, tmp_path: Path
    ) -> None:
        loops = Loops(redis, tmp_path, hold=True)
        with pytest.raises(RadioStartRefused):
            await service(redis, tmp_path, loops, cap=1, setups=Setups(refuses="no_voice")).start(
                ALICE, RadioStartRequest()
            )
        assert await redis.zrange(ACTIVE_KEY, 0, -1) == []
        bob = await service(redis, tmp_path, loops, cap=1).start(BOB, RadioStartRequest())
        assert bob.status == "starting"


@pytest.mark.parametrize("zone", ["Nowhere/Unknown", "../etc/zone", ""])
async def test_a_timezone_this_host_cannot_read_plays_no_mood_and_breaks_nothing(
    redis: FakeRedis, tmp_path: Path, zone: str
) -> None:
    """Unknown here (a KeyError) or not a key at all (a ValueError): no mood, no crash."""
    lost = replace(SETUP, timezone=zone)
    loops = Loops(redis, tmp_path, hold=True)
    doors = service(redis, tmp_path, loops, setups=Setups(setup=lost))
    started = await doors.start(ALICE, RadioStartRequest())
    assert started.mood is None
    answer = await doors.report(ALICE, started.session_id, report())
    assert answer is not None and answer.mood is None


class TestTheFlash:
    """ADR-324 decision 32: the player says which flash it heard, and fetches its audio."""

    async def test_the_flash_the_player_heard_reaches_the_loop(
        self, redis: FakeRedis, tmp_path: Path
    ) -> None:
        doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True))
        session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
        await doors.report(
            ALICE,
            session_id,
            RadioPlayheadRequest(seq=2, position_s=7.5, playing=True, flash_heard=100_001),
        )
        store = RadioSessionStore(
            redis, user_id=ALICE, session_id=session_id, ttl_s=60, media_root=tmp_path
        )
        playhead = await store.playhead()
        assert playhead is not None and playhead.flash_heard == 100_001

    async def test_only_a_produced_flash_s_audio_is_served(
        self, redis: FakeRedis, tmp_path: Path
    ) -> None:
        doors = service(redis, tmp_path, Loops(redis, tmp_path, hold=True))
        session_id = (await doors.start(ALICE, RadioStartRequest())).session_id
        store = RadioSessionStore(
            redis, user_id=ALICE, session_id=session_id, ttl_s=60, media_root=tmp_path
        )
        state = await store.read_state()
        assert state is not None
        ready = Flash(seq=100_001, notes=("m1",), produced=True)
        making = Flash(seq=100_002, notes=("m2",))
        await store.publish(replace(state, flashes=(ready, making)), {})
        for seq in (100_001, 100_002):
            path = segment_path(tmp_path, session_id, seq)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"mp3")
        assert await doors.audio_path(ALICE, session_id, 100_001) == segment_path(
            tmp_path, session_id, 100_001
        )
        assert await doors.audio_path(ALICE, session_id, 100_002) is None
        assert await doors.audio_path(BOB, session_id, 100_001) is None
