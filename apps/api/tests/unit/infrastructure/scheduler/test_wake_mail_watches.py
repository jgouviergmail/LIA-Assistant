"""A watch is the person's own instruction, not a heartbeat decision.

Wired inside ``_gmail_signal`` at first, the arming sat BEHIND three gates that
belong to a different feature, and reviewing the module plus its call site was
not enough to see it — the gates are above the call site:

- the twenty-minute **wake cooldown**, which exists so the heartbeat is not
  woken too often. Mail arrives in bursts, so a watch would routinely be
  dropped because LIA had spoken a quarter of an hour earlier.
- **``heartbeat_enabled``**, which somebody may switch off while still wanting
  « tell me when Marie replies » to work.
- the refusal of the heartbeat's **``emails`` source**, which says « do not
  interrupt me ABOUT my mail » — not « stop watching for the reply I asked for ».

The precedent was five lines above, in the same function: the label-source
indexing runs « before any gate » because indexing is not a decision. An arming
is the same shape — it moves a trigger for a routine the person created, and
decides nothing.

What this file also pins is the COST, because the fix must not buy correctness
with somebody's Gmail quota: the delta is read only for an account that holds a
watch, and read ONCE when the wake proceeds too.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.push_channels.wake import WakePayload
from src.infrastructure.scheduler import heartbeat_wake_sweep as sweep

pytestmark = pytest.mark.unit

_MODULE = "src.infrastructure.scheduler.heartbeat_wake_sweep"
_WATCHES = "src.domains.scheduled_actions.mail_watches"


def _payload() -> WakePayload:
    return WakePayload(
        user_id=uuid.uuid4(),
        provider="google_gmail",
        enqueued_at=datetime.now(UTC) - timedelta(seconds=30),
    )


def _settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "push_channels_enabled": True,
        "push_wake_enabled": True,
        "heartbeat_enabled": True,
        "push_wake_payload_ttl_seconds": 3600,
        "push_wake_cooldown_minutes": 20,
        "push_wake_max_users_per_sweep": 10,
        "rag_spaces_mail_sync_enabled": False,
        # What the pre-filter reads once the wake proceeds past the gates.
        "push_wake_mail_require_labels": [],
        "push_wake_mail_exclude_labels": [],
        "push_wake_mail_exclude_list_mail": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _settings_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sweep, "settings", _settings())


MESSAGE = {"id": "m-1", "labelIds": ["INBOX"], "payload": {"headers": []}}


class _World:
    """Everything ``_serve_one`` reaches for on a Gmail wake."""

    def __init__(self, *, has_watch: bool, user: Any, cooldown_free: bool = True) -> None:
        self.arm = AsyncMock(return_value=1)
        self.has_watches = AsyncMock(return_value=has_watch)
        self.delta = AsyncMock(return_value=([MESSAGE], "999"))
        self.user = user
        self.cooldown_free = cooldown_free

    def patches(self) -> list[Any]:
        return [
            patch(f"{_WATCHES}.arm_mail_watches", self.arm),
            patch(f"{_WATCHES}.has_mail_watches", self.has_watches),
            patch.object(sweep, "_gmail_delta", self.delta),
            patch.object(sweep, "_load_user", AsyncMock(return_value=self.user)),
            patch.object(
                sweep,
                "try_acquire_wake_cooldown",
                AsyncMock(return_value=self.cooldown_free),
            ),
            patch.object(sweep, "record_surface_consultations", MagicMock()),
        ]


@asynccontextmanager
async def _world(world: _World) -> Any:
    """Enter every patch the world declares, and unwind them in order."""
    patches = world.patches()
    for item in patches:
        item.__enter__()
    try:
        yield world
    finally:
        for item in reversed(patches):
            item.__exit__(None, None, None)


def _user(*, heartbeat: bool = True, refused: list[str] | None = None) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="moi@example.com",
        heartbeat_enabled=heartbeat,
        heartbeat_disabled_sources=refused or [],
    )


class TestAWatchIgnoresTheHeartbeatsOwnGates:
    async def test_it_is_armed_even_when_the_wake_cooldown_refuses(self) -> None:
        """Mail arrives in bursts; this was the common case, not the edge."""
        world = _World(has_watch=True, user=_user(), cooldown_free=False)
        async with _world(world):
            outcome = await sweep._serve_one(MagicMock(), _payload())

        assert outcome == "cooldown"
        world.arm.assert_awaited_once()

    async def test_it_is_armed_even_when_the_heartbeat_is_switched_off(self) -> None:
        world = _World(has_watch=True, user=_user(heartbeat=False))
        async with _world(world):
            outcome = await sweep._serve_one(MagicMock(), _payload())

        assert outcome == "ineligible"
        world.arm.assert_awaited_once()

    async def test_it_is_armed_even_when_the_mail_source_is_refused(self) -> None:
        """« Do not interrupt me about my mail » is not « stop watching »."""
        world = _World(has_watch=True, user=_user(refused=["emails"]))
        async with _world(world):
            outcome = await sweep._serve_one(MagicMock(), _payload())

        assert outcome == "source_disabled"
        world.arm.assert_awaited_once()

    async def test_it_is_armed_with_the_messages_the_delta_returned(self) -> None:
        world = _World(has_watch=True, user=_user(), cooldown_free=False)
        async with _world(world):
            await sweep._serve_one(MagicMock(), _payload())

        assert world.arm.await_args.args[1] == [MESSAGE]


class TestThePreFilterHasNoSayEither:
    """The two questions are different, and now structurally separated.

    The wake pre-filter answers « is this worth waking the heartbeat »; a watch
    answers « is this the thing I am waiting for ». A mail the filter calls
    unimportant is exactly what somebody may be watching for.

    This used to be a matter of ORDER inside one function. Since the arming
    moved ahead of every gate, the filter cannot reach it at all — but the
    property is worth keeping pinned, because it is the reason the arming is
    where it is.
    """

    async def test_a_mail_the_filter_refuses_still_arms_the_watch(self) -> None:
        world = _World(has_watch=True, user=_user())
        refused = MagicMock(return_value=SimpleNamespace(passes=False, reason="list_mail"))
        async with _world(world):
            with patch("src.domains.heartbeat.wake_context.mail_verdict", refused):
                outcome = await sweep._serve_one(MagicMock(), _payload())

        assert outcome == "no_signal"
        world.arm.assert_awaited_once()


class TestItNeverCostsSomebodyElsesQuota:
    async def test_an_account_with_no_watch_reads_no_delta_early(self) -> None:
        """The pre-check is one indexed SELECT; a Gmail call is not."""
        world = _World(has_watch=False, user=_user(), cooldown_free=False)
        async with _world(world):
            await sweep._serve_one(MagicMock(), _payload())

        world.delta.assert_not_awaited()
        world.arm.assert_not_awaited()

    async def test_the_delta_is_read_once_when_the_wake_proceeds_too(self) -> None:
        """The early read is handed down; the wake must not read it again."""
        world = _World(has_watch=True, user=_user())
        served = AsyncMock(return_value="notified")
        async with _world(world):
            with patch.object(sweep, "_serve_heartbeat", served):
                await sweep._serve_one(MagicMock(), _payload())

        assert world.delta.await_count == 1


class TestTheWakeIsNeverTheVictim:
    async def test_a_failing_watch_lookup_does_not_stop_the_wake(self) -> None:
        world = _World(has_watch=True, user=_user())
        world.has_watches = AsyncMock(side_effect=RuntimeError("database gone"))
        served = AsyncMock(return_value="notified")
        async with _world(world):
            with patch.object(sweep, "_serve_heartbeat", served):
                assert await sweep._serve_one(MagicMock(), _payload()) == "notified"

    async def test_a_failing_arming_does_not_stop_the_wake(self) -> None:
        world = _World(has_watch=True, user=_user())
        world.arm = AsyncMock(side_effect=RuntimeError("boom"))
        served = AsyncMock(return_value="notified")
        async with _world(world):
            with patch.object(sweep, "_serve_heartbeat", served):
                assert await sweep._serve_one(MagicMock(), _payload()) == "notified"
