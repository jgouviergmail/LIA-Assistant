"""One simulated uvicorn worker building the Today dashboard (driven by the shared-flight test).

The REAL ``BriefingService`` and ``run_shared_flight`` run against the real
Redis the test points every process at (base 15); only the sources are fakes,
timed like production's medians (scaled down). The child prints ``READY`` once
imported, waits for the start instant on stdin, then prints one JSON event per
line: requests and source reads, stamped against that instant.

Usage (by the test only): python briefing_flight_child.py <role> <delay> <scenario> <user_id>
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
import uuid
from types import SimpleNamespace
from typing import Any

#: Production medians (spec 2026-10-21 §0ter) divided by five: the order of
#: completion is what matters, not the absolute wait.
DURATIONS = {
    "weather": 0.99,
    "agenda": 0.35,
    "mails": 0.29,
    "documents": 0.27,
    "birthdays": 0.26,
    "tasks": 0.19,
    "health": 0.14,
    "for_you": 0.12,
    "workboard": 0.10,
    "reminders": 0.05,
    "sms": 0.02,
}


def main(role: str, delay: float, scenario: str, user_id: str) -> None:
    import src.domains.briefing.service as svc
    from src.domains.briefing.exceptions import ConnectorAccessError

    def emit(**event: Any) -> None:
        event.update(role=role, t=round(time.monotonic() - start, 3))
        print(json.dumps(event), flush=True)

    def fake(section: str) -> Any:
        async def fetch(*_args: object, **_kwargs: object) -> None:
            emit(ev="fetch_start", section=section)
            await asyncio.sleep(DURATIONS[section])
            if scenario == "push_mid_build" and section == "weather" and role == "cards_1":
                from src.domains.push_channels.cache_invalidation import invalidate_for_provider
                from src.domains.push_channels.models import PushChannelProvider

                await invalidate_for_provider(
                    PushChannelProvider.GOOGLE_GMAIL.value, uuid.UUID(user_id)
                )
                emit(ev="push", section="mails")
            if scenario == "weather_error" and section == "weather":
                raise ConnectorAccessError("google", "connector_network", "simulated failure")
            return None

        return fetch

    for section in DURATIONS:
        setattr(svc, f"fetch_{section}", fake(section))

    @contextlib.asynccontextmanager
    async def no_spend(*_args: object, **_kwargs: object) -> Any:
        yield None

    async def no_record(self: object, **_kwargs: object) -> None:
        return None

    svc.out_of_turn_spend = no_spend
    svc.record_surface_consultations = lambda **_kwargs: None
    svc.BriefingService._record_cards_turn = no_record  # type: ignore[method-assign]
    user = SimpleNamespace(
        id=uuid.UUID(user_id),
        language="fr",
        timezone="Europe/Paris",
        briefing_preferences=None,
        health_metrics_agents_enabled=True,
    )

    print("READY", flush=True)
    start_at = float(sys.stdin.readline())
    while time.time() < start_at:
        time.sleep(0.001)
    start = time.monotonic()

    async def run() -> None:
        await asyncio.sleep(delay)
        emit(ev="request_start")
        service = svc.BriefingService(user)  # type: ignore[arg-type]
        if role.startswith("synthesis"):
            cards, _missing = await service._read_cached_bundle()
            if _missing:
                await service.build_cards()
        else:
            await service.build_cards()
        emit(ev="request_end")

    asyncio.run(run())


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4])
