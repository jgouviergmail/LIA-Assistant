"""``ScheduledActionService`` against a repository double.

The first unit suite of the service: until ADR-265 its behaviour was only
exercised through the router and the users service. What it pins is the
timezone move — a paused routine must follow the user's zone like an active
one, because re-enabling and editing both re-derive the trigger from the
stored ``user_timezone``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.scheduled_actions.service import ScheduledActionService

pytestmark = pytest.mark.unit

PARIS_MORNING = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)  # 08:00 Paris


def _action(**over: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "days_of_week": [1, 2, 3, 4, 5, 6, 7],
        "trigger_hour": 8,
        "trigger_minute": 0,
        "user_timezone": "Europe/Paris",
        "is_enabled": True,
        "next_trigger_at": PARIS_MORNING,
        "status": "active",
        "consecutive_failures": 0,
        "last_error": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _service(actions: list[SimpleNamespace]) -> tuple[ScheduledActionService, MagicMock]:
    service = ScheduledActionService(MagicMock())
    repo = MagicMock()
    repo.get_all_for_user = AsyncMock(return_value=actions)
    repo.update_timezone_for_user = AsyncMock(
        side_effect=lambda **kw: len(kw["recalculated_triggers"])
    )
    service.repository = repo
    return service, repo


class TestTimezoneMove:
    async def test_a_paused_routine_follows_the_move_like_an_active_one(self) -> None:
        active, paused = _action(), _action(is_enabled=False)
        service, repo = _service([active, paused])

        count = await service.recalculate_all_for_user(uuid.uuid4(), "America/New_York")

        assert count == 2
        recalculated = repo.update_timezone_for_user.await_args.kwargs["recalculated_triggers"]
        assert set(recalculated) == {active.id, paused.id}
        # The same wall clock, 08:00, read on the NEW zone for both.
        for instant in recalculated.values():
            assert instant.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).hour == 8

    async def test_nothing_to_move_writes_nothing(self) -> None:
        service, repo = _service([])
        assert await service.recalculate_all_for_user(uuid.uuid4(), "Asia/Tokyo") == 0
        repo.update_timezone_for_user.assert_not_awaited()

    async def test_re_enabling_after_a_move_wakes_up_on_the_new_zone(self) -> None:
        """The defect the move fix closes, end to end at the service level.

        Before: the paused routine kept ``Europe/Paris`` through the move, and
        ``toggle`` re-armed it from that stored zone — 08:00 Paris, i.e. 02:00
        in New York. After: the move rewrites the zone on the paused row too,
        so the re-arm reads 08:00 New York.
        """
        paused = _action(is_enabled=False)
        service, repo = _service([paused])

        async def _apply_move(**kw: Any) -> int:
            paused.user_timezone = kw["new_timezone"]
            return len(kw["recalculated_triggers"])

        repo.update_timezone_for_user = AsyncMock(side_effect=_apply_move)
        await service.recalculate_all_for_user(uuid.uuid4(), "America/New_York")

        async def _update(action: Any, data: dict[str, Any]) -> Any:
            for key, value in data.items():
                setattr(action, key, value)
            return action

        service.get_with_ownership_check = AsyncMock(return_value=paused)  # type: ignore[method-assign]
        repo.update = AsyncMock(side_effect=_update)
        toggled = await service.toggle(paused.id, uuid.uuid4())

        assert toggled.is_enabled is True
        local = toggled.next_trigger_at.astimezone(
            __import__("zoneinfo").ZoneInfo("America/New_York")
        )
        assert (local.hour, local.minute) == (8, 0)
