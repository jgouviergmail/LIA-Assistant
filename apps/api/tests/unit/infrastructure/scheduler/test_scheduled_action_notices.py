"""What a routine tells its owner when it did not run as planned.

Three notices, each paid for by a silence measured in the executor
(2026-11-12): a routine that failed told nobody, a routine paused after its
failures in a row told nobody, and a routine its account's usage ceiling stood
aside told nobody — it stayed « executing » until the stale recovery.

What must hold:

- a series of failures is announced ONCE, at its first failure, and once more
  when it pauses the routine; a run the person started themselves always says
  how it ended;
- the usage-ceiling notice is claimed atomically, once per ACCOUNT per window:
  the ceiling blocks every routine of the account at once, and one notice per
  routine would be a burst;
- a notice is a convenience: it never raises into the tick it reports on.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.constants import (
    SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
    SCHEDULED_ACTIONS_QUOTA_NOTIFIED_KEY_PREFIX,
)
from src.core.i18n_proactive import ProactiveMessages
from src.infrastructure.scheduler.scheduled_action_notices import (
    RoutineNotice,
    claim_quota_notice,
    failure_notice,
    send_routine_notice,
)

pytestmark = pytest.mark.unit

USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


class TestWhichFailureIsWorthANotice:
    @pytest.mark.parametrize(
        ("consecutive_failures", "disabled", "manual", "expected"),
        [
            # The first failure of a series is announced.
            (1, False, False, RoutineNotice.FAILED),
            # The following ones are not: the person already knows.
            (2, False, False, None),
            (4, False, False, None),
            # The failure that pauses the routine says so, whatever its rank.
            (5, True, False, RoutineNotice.DISABLED),
            (1, True, False, RoutineNotice.DISABLED),
            (5, True, True, RoutineNotice.DISABLED),
            # A run the person started is waited for: it always says it failed.
            (3, False, True, RoutineNotice.FAILED),
        ],
    )
    def test_the_decision(
        self,
        consecutive_failures: int,
        disabled: bool,
        manual: bool,
        expected: RoutineNotice | None,
    ) -> None:
        assert (
            failure_notice(
                consecutive_failures=consecutive_failures, disabled=disabled, manual=manual
            )
            is expected
        )


class TestTheVocabulary:
    def test_every_notice_has_its_sentence_and_no_sentence_is_orphaned(self) -> None:
        assert {notice.value for notice in RoutineNotice} == set(
            ProactiveMessages._ROUTINE_NOTICE_BODIES
        )


def _redis(set_result: Any = True) -> MagicMock:
    return MagicMock(set=AsyncMock(return_value=set_result))


class TestTheQuotaNoticeIsClaimedOncePerAccount:
    async def test_the_first_refusal_claims_it_for_the_configured_window(self) -> None:
        redis = _redis(True)
        with patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis)):
            claimed = await claim_quota_notice(USER_ID)

        assert claimed is True
        (key, _value), kwargs = redis.set.await_args
        assert key == f"{SCHEDULED_ACTIONS_QUOTA_NOTIFIED_KEY_PREFIX}:{USER_ID}"
        # Atomic: two routines due the same minute cannot both claim it.
        assert kwargs["nx"] is True
        assert kwargs["ex"] == settings.scheduled_actions_quota_notice_cooldown_hours * 3600

    async def test_a_refusal_inside_the_window_claims_nothing(self) -> None:
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(return_value=_redis(None)),
        ):
            assert await claim_quota_notice(USER_ID) is False

    async def test_without_a_cache_nobody_is_told_rather_than_at_every_tick(self) -> None:
        with patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=None)):
            assert await claim_quota_notice(USER_ID) is False

    async def test_a_cache_failure_claims_nothing_and_never_raises(self) -> None:
        redis = MagicMock(set=AsyncMock(side_effect=ConnectionError("down")))
        with patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis)):
            assert await claim_quota_notice(USER_ID) is False


def _routine() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), user_id=USER_ID, title="Morning briefing")


def _owner() -> SimpleNamespace:
    return SimpleNamespace(id=USER_ID, language="fr")


class TestARoutineNotice:
    async def test_it_leaves_through_the_dispatcher_naming_the_routine(self) -> None:
        action, db = _routine(), MagicMock()
        dispatcher = MagicMock(dispatch=AsyncMock(return_value=MagicMock(durably_delivered=True)))
        with patch(
            "src.infrastructure.proactive.notification.NotificationDispatcher",
            return_value=dispatcher,
        ):
            await send_routine_notice(
                db, user=_owner(), action=action, kind=RoutineNotice.FAILED, user_language="fr"
            )

        sent = dispatcher.dispatch.await_args.kwargs
        assert sent["task_type"] == "scheduled_action"
        assert sent["target_id"] == str(action.id)
        assert sent["metadata"] == {"routine_notice": "failed"}
        assert sent["title"] == ProactiveMessages.notification_title("scheduled_action", "fr")
        assert "Morning briefing" in sent["content"]
        assert (
            f"({settings.frontend_url}/dashboard/settings?section=scheduled-actions)"
            in sent["content"]
        )
        # The sentence states the threshold the executor enforces, not a copy of it.
        assert str(SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES) in sent["content"]

    async def test_a_dispatch_that_raises_never_reaches_the_tick(self) -> None:
        dispatcher = MagicMock(dispatch=AsyncMock(side_effect=RuntimeError("push down")))
        with patch(
            "src.infrastructure.proactive.notification.NotificationDispatcher",
            return_value=dispatcher,
        ):
            await send_routine_notice(
                MagicMock(),
                user=_owner(),
                action=_routine(),
                kind=RoutineNotice.QUOTA,
                user_language="en",
            )

        dispatcher.dispatch.assert_awaited_once()
