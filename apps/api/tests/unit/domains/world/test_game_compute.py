"""Computer work is bounded, external to CAS, and has a legal low-cost fallback."""

import asyncio

import pytest

from src.core.config import settings
from src.domains.world import game_compute
from tests.unit.domains.world.test_games import command, run, setup

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid", ["hidden", "away", "epoch", "sequence", "paused", "outsider", "old_match_controller"]
)
async def test_invalid_preparation_never_launches_computer_work(
    monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    state, (owner, outsider, _) = setup()
    run(state, owner, "start_computer")
    intent = command(state, "move", 2, move={"game": "tic_tac_toe", "cell": 0})
    actor = state.actors[owner.account]
    if invalid == "hidden":
        actor.visible = False
    elif invalid == "away":
        actor.position = {"x": 0.0, "y": 0.0}
    elif invalid == "epoch":
        intent = intent.model_copy(update={"epoch": "0" * 36})
    elif invalid == "sequence":
        actor.seq = intent.seq
    elif invalid == "paused":
        state.games[intent.cabinet].paused_at = 101
    elif invalid == "outsider":
        owner = outsider
    else:
        state.games[intent.cabinet].members[0].controller = "old-game-generation"

    async def forbidden(*args: object) -> None:
        pytest.fail("invalid intent must not acquire CPU admission")

    monkeypatch.setattr(game_compute, "_compute", forbidden)
    assert await game_compute.prepare_bounded(state, owner, intent) is None


async def test_busy_compute_does_not_queue_unbounded_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, (owner, _, _) = setup()
    run(state, owner, "start_computer")
    intent = command(state, "move", 2, move={"game": "tic_tac_toe", "cell": 0})
    gate = asyncio.Semaphore(0)
    monkeypatch.setattr(game_compute, "_slots", gate)
    prepared = await game_compute.prepare_bounded(state, owner, intent)
    assert prepared is not None and prepared.nodes == 0
    assert prepared.position.board.count(1) == prepared.position.board.count(2) == 1
    assert state.games[intent.cabinet].position.board == (0,) * 9


async def test_timeout_fallback_does_not_release_slot_until_worker_really_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, (owner, _, _) = setup()
    run(state, owner, "start_computer")
    intent = command(state, "move", 2, move={"game": "tic_tac_toe", "cell": 0})
    started, finish = asyncio.Event(), asyncio.Event()

    async def worker(*args: object) -> None:
        started.set()
        await finish.wait()
        return None

    monkeypatch.setattr(game_compute, "_slots", asyncio.Semaphore(1))
    monkeypatch.setattr(game_compute, "_compute", worker)
    monkeypatch.setattr(settings, "world_arcade_bot_seconds", 0.1)
    prepared = await game_compute.prepare_bounded(state, owner, intent)
    assert started.is_set() and prepared is not None and prepared.nodes == 0
    assert game_compute._slots.locked()
    finish.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not game_compute._slots.locked()


async def _outlived_search(
    monkeypatch: pytest.MonkeyPatch, finish: asyncio.Event
) -> set[asyncio.Task[object]]:
    """Leave one search running after its caller fell back at the deadline."""
    state, (owner, _, _) = setup()
    run(state, owner, "start_computer")
    intent = command(state, "move", 2, move={"game": "tic_tac_toe", "cell": 0})

    async def worker(*args: object) -> None:
        await finish.wait()

    running: set[asyncio.Task[object]] = set()
    monkeypatch.setattr(game_compute, "_running", running)
    monkeypatch.setattr(game_compute, "_slots", asyncio.Semaphore(1))
    monkeypatch.setattr(game_compute, "_compute", worker)
    monkeypatch.setattr(settings, "world_arcade_bot_seconds", 0.05)
    prepared = await game_compute.prepare_bounded(state, owner, intent)
    assert prepared is not None and prepared.nodes == 0
    assert len(running) == 1 and game_compute._slots.locked()
    return running


async def test_shutdown_drain_awaits_a_search_that_outlived_its_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finish = asyncio.Event()
    running = await _outlived_search(monkeypatch, finish)
    asyncio.get_running_loop().call_later(0.02, finish.set)
    assert await game_compute.drain_game_compute(timeout=2) == 0
    assert not running and not game_compute._slots.locked()


async def test_shutdown_drain_cancels_only_what_outlives_its_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running = await _outlived_search(monkeypatch, asyncio.Event())
    assert await game_compute.drain_game_compute(timeout=0.02) == 1
    assert not running and not game_compute._slots.locked()


async def test_shutdown_drain_with_nothing_running_returns_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(game_compute, "_running", set())
    assert await game_compute.drain_game_compute(timeout=0) == 0
