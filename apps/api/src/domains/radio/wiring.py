"""One radio per worker: the session doors, the loops they launch, the newsroom's reach (ADR-324).

The session doors and the loop launcher are built once per process, on the
cache client, the first time a route needs them; the shutdown cancels this
worker's loops (their leases lapse and the next report starts them elsewhere).
The robots.txt cache is shared by every discovery of the process, like the
collector's own. An HTTP client belongs to the request or the pass that opens
it (``newsroom_client``), never to the process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from src.domains.radio.adapters import AccountSetupBuilder, LedgerCostReader, session_parts
from src.domains.radio.budget import listener_budget
from src.domains.radio.constants import LOOP_STOP_TIMEOUT_S, NEWSROOM_REQUEST_TIMEOUT_S
from src.domains.radio.newsroom.robots import RobotsCache
from src.domains.radio.register import file_session
from src.domains.radio.runner import RadioLoopLauncher
from src.domains.radio.service import RadioSessionService
from src.domains.radio.settings_view import radio_runtime, runner_settings
from src.infrastructure.cache.redis import get_redis_cache


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _Radio:
    """This worker's radio, once built."""

    service: RadioSessionService
    launcher: RadioLoopLauncher
    robots: RobotsCache


_built: _Radio | None = None


async def _radio() -> _Radio:
    """This worker's radio, built on first use — once, whoever asks first.

    Built lazily inside the running loop (its locks bind to it). Two first
    requests may both build: the second test below has no ``await`` between it
    and the assignment, so exactly one build is kept, and the one set aside
    holds no loop yet.
    """
    global _built
    if _built is None:
        redis = await get_redis_cache()
        launcher = RadioLoopLauncher(
            redis,
            settings=runner_settings(),
            factory=session_parts,
            books=file_session,
            clock=_now,
        )
        candidate = _Radio(
            service=RadioSessionService(
                redis,
                runtime=radio_runtime(),
                setups=AccountSetupBuilder(),
                loops=launcher,
                costs=LedgerCostReader(),
                books=file_session,
                budget=listener_budget,
                clock=_now,
            ),
            launcher=launcher,
            robots=RobotsCache(),
        )
        if _built is None:
            _built = candidate
    return _built


async def radio_service() -> RadioSessionService:
    """This worker's session doors."""
    return (await _radio()).service


async def newsroom_robots() -> RobotsCache:
    """This worker's robots.txt cache (the discoveries' and the collector's)."""
    return (await _radio()).robots


async def stop_radio_loops() -> None:
    """Cancel this worker's loops and wait for them, within a bound (the shutdown step).

    A loop cancelled mid-segment drops the calls it was waiting on: the next
    report restarts it on a worker that stays, from the state it published.
    """
    if _built is not None:
        await _built.launcher.stop_all(timeout_s=LOOP_STOP_TIMEOUT_S)


@asynccontextmanager
async def newsroom_client() -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client for one discovery or one pass, closed when it ends.

    Redirections are followed by the newsroom's own fetch, hop by hop and
    checked at each one — never by the client.
    """
    async with httpx.AsyncClient(timeout=NEWSROOM_REQUEST_TIMEOUT_S) as client:
        yield client


__all__ = ["newsroom_client", "newsroom_robots", "radio_service", "stop_radio_loops"]
