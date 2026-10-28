"""The shutdown awaits the World arcade's computer searches, through their one owner."""

from __future__ import annotations

import ast
import inspect

import pytest

from src.core.config import settings
from src.domains.world import game_compute
from src.infrastructure.startup import shutdown
from src.infrastructure.startup.shutdown import stop_world_game_compute

pytestmark = pytest.mark.unit


@pytest.fixture
def drains(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    calls: list[float] = []

    async def drain(timeout: float) -> int:
        calls.append(timeout)
        return 0

    monkeypatch.setattr(game_compute, "drain_game_compute", drain)
    return calls


async def test_a_deployment_with_world_drains_its_searches_within_one_deadline(
    drains: list[float],
) -> None:
    await stop_world_game_compute(enabled=True)

    assert drains == [settings.world_arcade_bot_seconds]


async def test_a_deployment_without_world_has_nothing_to_drain(drains: list[float]) -> None:
    await stop_world_game_compute(enabled=False)

    assert drains == []


def test_the_searches_are_awaited_before_the_loop_s_dependencies_close() -> None:
    tree = ast.parse(inspect.getsource(shutdown.shutdown_application))
    lines: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            lines[node.func.id] = min(lines.get(node.func.id, node.lineno), node.lineno)
    stop = lines["stop_world_game_compute"]
    assert lines["wait_all_background_tasks"] < stop
    assert stop < lines["close_db"] and stop < lines["close_redis"]
