"""The shutdown stops the radio's loops where the deployment ships the radio (ADR-324)."""

from __future__ import annotations

import pytest

from src.domains.radio import wiring
from src.infrastructure.startup.shutdown import stop_radio_loops

pytestmark = pytest.mark.unit


@pytest.fixture
def stops(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    async def stop() -> None:
        calls.append(1)

    monkeypatch.setattr(wiring, "stop_radio_loops", stop)
    return calls


async def test_a_deployment_with_the_radio_stops_its_loops(stops: list[int]) -> None:
    await stop_radio_loops(enabled=True)

    assert stops == [1]


async def test_a_deployment_without_the_radio_has_nothing_to_stop(stops: list[int]) -> None:
    await stop_radio_loops(enabled=False)

    assert stops == []
