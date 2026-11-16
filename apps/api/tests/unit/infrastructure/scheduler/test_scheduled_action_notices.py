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

import json
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
from src.core.conversation_target import ConversationOrigin
from src.core.field_names import FIELD_CONVERSATION_ID
from src.core.i18n_proactive import ProactiveMessages
from src.infrastructure.scheduler.scheduled_action_notices import (
    RoutineNotice,
    claim_quota_notice,
    failure_notice,
    notify_result,
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

    async def test_a_run_asked_in_an_annex_is_told_there(self) -> None:
        """ADR-378 amendment 2026-11-14: the notice follows the run's origin."""
        origin = ConversationOrigin(uuid.uuid4(), 3)
        dispatcher = MagicMock(dispatch=AsyncMock(return_value=MagicMock(durably_delivered=True)))
        with patch(
            "src.infrastructure.proactive.notification.NotificationDispatcher",
            return_value=dispatcher,
        ):
            await send_routine_notice(
                MagicMock(),
                user=_owner(),
                action=_routine(),
                kind=RoutineNotice.FAILED,
                user_language="fr",
                origin=origin,
            )

        assert dispatcher.dispatch.await_args.kwargs["origin"] == origin


_CHANNELS = "src.infrastructure.scheduler.scheduled_action_notices.send_notification_to_channels"


class _Pushes:
    """The two halves of a routine's result, captured where they leave."""

    def __init__(self) -> None:
        self.fcm = MagicMock(send_to_user=AsyncMock())
        self.redis = MagicMock(publish=AsyncMock())

    def patches(self) -> tuple[Any, Any]:
        return (
            patch(
                "src.domains.notifications.service.FCMNotificationService",
                return_value=self.fcm,
            ),
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                AsyncMock(return_value=self.redis),
            ),
        )

    @property
    def push_data(self) -> dict[str, str]:
        data: dict[str, str] = self.fcm.send_to_user.await_args.kwargs["data"]
        return data

    @property
    def live_event(self) -> dict[str, Any]:
        _channel, payload = self.redis.publish.await_args.args
        event: dict[str, Any] = json.loads(payload)
        return event


class TestARoutineResultNamesItsAnnex:
    """Both halves describe ONE notification: the toast reads its place from either."""

    async def _notify(self, discussion: uuid.UUID | None) -> _Pushes:
        pushes = _Pushes()
        fcm_patch, redis_patch = pushes.patches()
        with fcm_patch, redis_patch, patch(_CHANNELS, AsyncMock(return_value=0)):
            await notify_result(
                MagicMock(),
                user_id=USER_ID,
                action=_routine(),
                content="Résultat",
                user_language="fr",
                discussion=discussion,
            )
        return pushes

    async def test_a_result_in_an_annex_names_it_on_both_halves(self) -> None:
        annex = uuid.uuid4()
        pushes = await self._notify(annex)

        assert pushes.push_data[FIELD_CONVERSATION_ID] == str(annex)
        assert pushes.push_data["url"] == f"/dashboard/chat?conversation={annex}"
        assert pushes.live_event["metadata"] == {FIELD_CONVERSATION_ID: str(annex)}

    async def test_a_result_in_main_names_none(self) -> None:
        pushes = await self._notify(None)

        assert FIELD_CONVERSATION_ID not in pushes.push_data
        assert "url" not in pushes.push_data
        assert pushes.live_event["metadata"] == {}


class TestARoutineResultReachesTheChannels:
    """The Telegram FAQ promised the results of the routines; the executor only
    pushed and toasted them (``SCHEDULED_ACTIONS.md``: « jamais poussé vers
    Telegram »). The result now reaches every active channel, whole, as the
    chat shows it — each channel draws it (Telegram lot 1)."""

    async def _notify(
        self, channels: AsyncMock, *, enabled: bool = True, routine: SimpleNamespace | None = None
    ) -> _Pushes:
        pushes = _Pushes()
        fcm_patch, redis_patch = pushes.patches()
        with (
            fcm_patch,
            redis_patch,
            patch(_CHANNELS, channels),
            patch.object(settings, "channels_enabled", enabled),
        ):
            await notify_result(
                MagicMock(),
                user_id=USER_ID,
                action=routine or _routine(),
                content='**3** mails\n\n<div class="card">x</div>',
                user_language="en",
            )
        return pushes

    async def test_the_whole_result_is_sent_to_the_channels(self) -> None:
        channels = AsyncMock(return_value=1)
        routine = _routine()

        pushes = await self._notify(channels, routine=routine)

        channels.assert_awaited_once()
        sent = channels.await_args.kwargs
        assert sent["user_id"] == USER_ID
        assert sent["body"] == '**3** mails\n\n<div class="card">x</div>'
        assert sent["task_type"] == "scheduled_action"
        assert sent["target_id"] == str(routine.id)
        assert sent["language"] == "en"
        # One notification, two surfaces: the channel's title is the push's.
        assert sent["title"] == pushes.fcm.send_to_user.await_args.kwargs["title"]

    async def test_the_channels_are_reached_before_the_push_opens_its_transaction(self) -> None:
        """The push reads and writes its device rows on the tick's session and
        leaves them uncommitted: a channel reached after it would hold those
        row locks across Telegram (ADR-304)."""
        order: list[str] = []
        channels = AsyncMock(side_effect=lambda **_kw: order.append("channels") or 1)
        pushes = _Pushes()
        pushes.fcm.send_to_user = AsyncMock(side_effect=lambda **_kw: order.append("push"))
        fcm_patch, redis_patch = pushes.patches()
        with fcm_patch, redis_patch, patch(_CHANNELS, channels):
            with patch.object(settings, "channels_enabled", True):
                await notify_result(
                    MagicMock(),
                    user_id=USER_ID,
                    action=_routine(),
                    content="Résultat",
                    user_language="fr",
                )

        assert order == ["channels", "push"]

    async def test_an_instance_without_channels_asks_none(self) -> None:
        channels = AsyncMock(return_value=1)

        await self._notify(channels, enabled=False)

        channels.assert_not_awaited()

    async def test_a_channel_that_fails_never_reaches_the_tick_or_the_push(self) -> None:
        channels = AsyncMock(side_effect=ConnectionError("database away"))

        pushes = await self._notify(channels)

        pushes.fcm.send_to_user.assert_awaited_once()
        pushes.redis.publish.assert_awaited_once()
