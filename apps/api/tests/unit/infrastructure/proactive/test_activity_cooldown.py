"""Activity-cooldown gate of the proactive EligibilityChecker (audit D-01, lot 1).

The historical gate read ``user.last_chat_activity_at`` — an attribute that
exists on NO model (its only occurrence in src/ was the read itself) — then
fell back to importing a ``Message`` class that does not exist, and swallowed
the ImportError into ``success()``. Executed proof on 2026-08-19: a user who
messaged ZERO seconds earlier was declared eligible without a single DB query.
The green unit test that hid this posed the attribute on an un-specced
MagicMock — these tests use the REAL ``User`` model so a phantom attribute can
never pass again.

New contract: the checker receives an ``activity_probe`` callable
``(user_id, db, since) -> datetime | None`` (wired by the schedulers to the
conversations repository). No probe → the gate is explicitly skipped; a probe
failure PROPAGATES (the runner's per-user try/except records it as a visible
failure — never a silent success).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.domains.users.models import User
from src.infrastructure.proactive.eligibility import (
    EligibilityChecker,
    EligibilityReason,
)


def _real_user() -> User:
    """A REAL User model instance — phantom attributes raise, as in prod."""
    user = User(email="activity-gate@test.local", hashed_password="x")
    user.id = uuid4()
    return user


def _checker(probe: Any = None, cooldown_minutes: int = 15) -> EligibilityChecker:
    return EligibilityChecker(
        task_type="heartbeat",
        enabled_field="heartbeat_enabled",
        start_hour_field="heartbeat_notify_start_hour",
        end_hour_field="heartbeat_notify_end_hour",
        min_per_day_field="heartbeat_min_per_day",
        max_per_day_field="heartbeat_max_per_day",
        activity_cooldown_minutes=cooldown_minutes,
        activity_probe=probe,
    )


class _ExplodingDB:
    """The gate must never query the session itself — the probe owns I/O."""

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the gate must not query the DB directly")


class TestActivityCooldownGate:
    async def test_user_active_now_is_blocked(self) -> None:
        """The S1 prod scenario, inverted: an active user must be blocked."""
        now = datetime.now(UTC)

        async def probe(user_id: UUID, db: Any, since: datetime) -> datetime | None:
            return now - timedelta(seconds=30)

        result = await _checker(probe)._check_activity_cooldown(_real_user(), _ExplodingDB(), now)
        assert result.eligible is False
        assert result.reason == EligibilityReason.ACTIVITY_COOLDOWN
        assert result.details is not None
        assert result.details["cooldown_minutes"] == 15

    async def test_probe_receives_the_cooldown_floor(self) -> None:
        """The probe is asked for activity SINCE the floor — a bounded scan."""
        now = datetime.now(UTC)
        seen: dict[str, Any] = {}

        async def probe(user_id: UUID, db: Any, since: datetime) -> datetime | None:
            seen["user_id"], seen["since"] = user_id, since
            return None

        user = _real_user()
        await _checker(probe, cooldown_minutes=7)._check_activity_cooldown(
            user, _ExplodingDB(), now
        )
        assert seen["user_id"] == user.id
        assert seen["since"] == now - timedelta(minutes=7)

    async def test_no_recent_activity_passes(self) -> None:
        async def probe(user_id: UUID, db: Any, since: datetime) -> datetime | None:
            return None  # nothing since the floor

        result = await _checker(probe)._check_activity_cooldown(
            _real_user(), _ExplodingDB(), datetime.now(UTC)
        )
        assert result.eligible is True

    async def test_no_probe_skips_the_gate_explicitly(self) -> None:
        """Unconfigured probe = gate off by explicit choice, not by accident."""
        result = await _checker(probe=None)._check_activity_cooldown(
            _real_user(), _ExplodingDB(), datetime.now(UTC)
        )
        assert result.eligible is True

    async def test_probe_failure_propagates(self) -> None:
        """No silent swallow: a probe error must surface to the runner's
        per-user failure accounting, never dissolve into success()."""

        async def probe(user_id: UUID, db: Any, since: datetime) -> datetime | None:
            raise RuntimeError("db unavailable")

        with pytest.raises(RuntimeError, match="db unavailable"):
            await _checker(probe)._check_activity_cooldown(
                _real_user(), _ExplodingDB(), datetime.now(UTC)
            )

    async def test_real_user_model_has_no_phantom_attribute(self) -> None:
        """Regression pin for the root cause: the attribute the old code read
        must not silently reappear half-wired — if someone adds it to the
        model, this test forces them to revisit the probe design."""
        assert not hasattr(User, "last_chat_activity_at")


class TestSchedulersWireTheProbe:
    """Both proactive schedulers must pass a real probe — an unconfigured
    checker in prod would be D-01 all over again."""

    def test_heartbeat_checker_has_probe(self) -> None:
        from src.infrastructure.scheduler.heartbeat_notification import (
            _create_heartbeat_eligibility_checker,
        )

        assert _create_heartbeat_eligibility_checker().activity_probe is not None

    def test_interest_checker_has_probe(self) -> None:
        from src.infrastructure.scheduler.interest_notification import (
            _create_interest_eligibility_checker,
        )

        assert _create_interest_eligibility_checker().activity_probe is not None
