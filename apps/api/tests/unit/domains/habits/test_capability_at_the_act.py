"""The operator's HABITS switch stops the ACTS, and leaves the record open.

ADR-280 filed ``habits`` under « the route is the capability »; measured
2026-09-11 with the switch OFF: the nightly job recomputed, the heartbeat
was served the rhythm, the tick was deferred toward the learned window — only
the panel (the record the person reads and corrects) had closed. That is the
inverse of ADR-280's own rule. ``habits`` is now ``service_enforced``: one
async predicate (``habits_capability_enabled``) at every act — the nightly
job, the ledger write, the chat-side promotion, the three consumers and the
presence banking — and route guards on the two act endpoints only
(``/recompute``, ``/presence``); GET / PATCH / DELETE stay open.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability

pytestmark = pytest.mark.unit

_CAP = "src.domains.habits.capability.is_capability_enabled"


class TestTheDeclaration:
    def test_habits_and_heartbeat_are_service_enforced(self) -> None:
        for capability in (PlatformCapability.HABITS, PlatformCapability.HEARTBEAT):
            spec = CAPABILITY_SPECS[capability]
            assert spec.service_enforced is True
            assert spec.route_enforced is False


class TestTheNightlyJob:
    async def test_the_switch_off_stops_the_recompute_before_any_read(self) -> None:
        from src.infrastructure.scheduler import habit_profile_job

        with (
            patch.object(habit_profile_job.settings, "habits_enabled", True),
            patch(f"{_CAP}", AsyncMock(return_value=False)),
            patch("src.infrastructure.scheduler.habit_profile_job.get_db_context") as ctx,
        ):
            await habit_profile_job.run_habit_profile_job()
        ctx.assert_not_called()


class TestTheLedgerWrite:
    async def test_the_switch_off_counts_feature_disabled(self) -> None:
        from src.domains.agents.services.recurrence_ledger import (
            record_occurrence_if_allowed,
        )
        from src.infrastructure.observability.metrics_agents import (
            recurrence_ledger_writes_total,
        )

        before = recurrence_ledger_writes_total.labels(outcome="feature_disabled")._value.get()
        with (
            patch(f"{_CAP}", AsyncMock(return_value=False)),
            patch("src.domains.habits.learning_gate.read_learning_gate") as gate,
            patch("src.infrastructure.cache.redis.get_redis_cache") as redis,
        ):
            from datetime import date

            await record_occurrence_if_allowed(
                str(uuid.uuid4()),
                "email",
                local_date=date(2026, 9, 11),
                local_hour=9.0,
                settings=SimpleNamespace(),
            )
        gate.assert_not_called()
        redis.assert_not_called()
        after = recurrence_ledger_writes_total.labels(outcome="feature_disabled")._value.get()
        assert after == before + 1


class TestTheConsumers:
    async def test_the_heartbeat_block_is_empty_when_the_switch_is_off(self) -> None:
        from src.domains.heartbeat.habit_context import fetch_habits_context

        user = SimpleNamespace(habits_enabled=True, timezone="Europe/Paris")
        with patch(f"{_CAP}", AsyncMock(return_value=False)):
            assert (
                await fetch_habits_context(
                    MagicMock(), uuid.uuid4(), user, SimpleNamespace(habits_enabled=True)
                )
                is None
            )

    async def test_the_tick_is_never_deferred_when_the_switch_is_off(self) -> None:
        from src.domains.habits.tick_scoring import should_defer_tick_for_rhythm
        from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask

        with patch(f"{_CAP}", AsyncMock(return_value=False)):
            assert (
                await should_defer_tick_for_rhythm(
                    uuid.uuid4(),
                    {"habits_enabled": True},
                    SimpleNamespace(habits_tick_scoring_enabled=True, habits_enabled=True),
                    surface=HeartbeatProactiveTask.tick_surface,
                )
                is False
            )

    async def test_the_ambient_block_is_empty_when_the_switch_is_off(self) -> None:
        from src.domains.habits.ambient import build_habits_rhythm_block

        with patch(f"{_CAP}", AsyncMock(return_value=False)):
            assert await build_habits_rhythm_block(uuid.uuid4()) == ""


class TestPresence:
    async def test_no_hour_is_banked_when_the_switch_is_off(self) -> None:
        from src.domains.habits.presence import record_presence

        user = SimpleNamespace(id=uuid.uuid4(), habits_enabled=True, timezone="Europe/Paris")
        with (
            patch(f"{_CAP}", AsyncMock(return_value=False)),
            patch("src.domains.habits.presence.settings") as stg,
        ):
            stg.habits_enabled = True
            stg.habits_presence_enabled = True
            outcome = await record_presence(MagicMock(), user, kind="visibility")
        assert outcome == "disabled"


class TestTheRouter:
    def test_only_the_two_act_routes_carry_the_guard(self) -> None:
        from src.domains.habits.router import router

        def _names(dependencies: Any) -> set[str]:
            names = set()
            for dependency in dependencies or []:
                fn = getattr(getattr(dependency, "dependency", None), "__name__", "")
                if fn.startswith("require_capability_"):
                    names.add(fn.removeprefix("require_capability_"))
            return names

        assert _names(router.dependencies) == set()
        guarded = {
            route.path
            for route in router.routes
            if "habits" in _names(getattr(route, "dependencies", []))
        }
        assert guarded == {"/habits/recompute", "/habits/presence"}, guarded
