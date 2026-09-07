"""A reminder notification is billed to the person it was written for.

Until 2026-09-07 this path wrote one row — the per-run aggregate in
``message_token_summary`` — and nothing else. Measured consequences, all three
verified against production: no ``token_usage_logs`` row under any reminder
name, so no Article-12 trace; no ``user_statistics`` increment, so the
account's own quota never moved; no ``instance_daily_budget`` entry, so the
deployment ceiling could not see it.

The detail that makes it a defect rather than an omission: this path DOES call
``is_user_blocked_for_llm`` before generating. It read a counter it never fed.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


class _Result:
    """The generated message and its usage, as the notifier builds it."""

    def __init__(self, tokens_in: int = 800, tokens_out: int = 60) -> None:
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.tokens_cache = 0
        self.model_name = "gpt-5.6-luna"


class TestReminderSpendReachesTheAccount:
    """The funnel every other out-of-turn surface uses, finally used here too."""

    async def test_the_spend_is_sent_through_the_shared_funnel(self) -> None:
        from src.infrastructure.scheduler.reminder_notification import _account_reminder_spend

        seen: list[dict] = []
        with (
            patch(
                "src.infrastructure.proactive.tracking.track_proactive_tokens",
                AsyncMock(side_effect=lambda **kw: seen.append(kw)),
            ),
            patch(
                "src.infrastructure.scheduler.reminder_notification.get_cached_cost_usd_eur",
                return_value=(0.004, 0.0037),
            ),
        ):
            cost = await _account_reminder_spend(
                AsyncMock(),
                reminder_id="rem-1",
                user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                run_id="run-abc",
                conversation_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                result=_Result(),
            )

        assert cost == pytest.approx(0.0037)
        assert len(seen) == 1
        assert seen[0]["tokens_in"] == 800
        assert seen[0]["tokens_out"] == 60

    async def test_the_archived_run_id_is_reused_not_regenerated(self) -> None:
        """The message's metadata already carries this run id.

        Generating a fresh one here would leave the archived notification and
        its cost pointing at different runs — the message unexplained, the cost
        unattributed.
        """
        from src.infrastructure.scheduler.reminder_notification import _account_reminder_spend

        seen: list[dict] = []
        with (
            patch(
                "src.infrastructure.proactive.tracking.track_proactive_tokens",
                AsyncMock(side_effect=lambda **kw: seen.append(kw)),
            ),
            patch(
                "src.infrastructure.scheduler.reminder_notification.get_cached_cost_usd_eur",
                return_value=(0.004, 0.0037),
            ),
        ):
            await _account_reminder_spend(
                AsyncMock(),
                reminder_id="rem-2",
                user_id=uuid.uuid4(),
                run_id="run-preassigned",
                conversation_id=uuid.uuid4(),
                result=_Result(),
            )

        assert seen[0]["run_id"] == "run-preassigned"

    async def test_the_callers_session_is_reused(self) -> None:
        """One transaction, so the cost and the notification commit together."""
        from src.infrastructure.scheduler.reminder_notification import _account_reminder_spend

        session = AsyncMock()
        seen: list[dict] = []
        with (
            patch(
                "src.infrastructure.proactive.tracking.track_proactive_tokens",
                AsyncMock(side_effect=lambda **kw: seen.append(kw)),
            ),
            patch(
                "src.infrastructure.scheduler.reminder_notification.get_cached_cost_usd_eur",
                return_value=(0.0, 0.0),
            ),
        ):
            await _account_reminder_spend(
                session,
                reminder_id="rem-3",
                user_id=uuid.uuid4(),
                run_id="run-3",
                conversation_id=uuid.uuid4(),
                result=_Result(),
            )

        assert seen[0]["db"] is session

    async def test_a_notification_that_used_no_model_accounts_nothing(self) -> None:
        """A templated fallback message costs nothing and must bill nothing."""
        from src.infrastructure.scheduler.reminder_notification import _account_reminder_spend

        seen: list[dict] = []
        with patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens",
            AsyncMock(side_effect=lambda **kw: seen.append(kw)),
        ):
            cost = await _account_reminder_spend(
                AsyncMock(),
                reminder_id="rem-4",
                user_id=uuid.uuid4(),
                run_id="run-4",
                conversation_id=uuid.uuid4(),
                result=_Result(tokens_in=0, tokens_out=0),
            )

        assert cost == 0.0
        assert seen == []

    async def test_an_unpriced_model_still_reports_its_tokens(self) -> None:
        """A price we cannot look up must not silence the token accounting."""
        from src.infrastructure.scheduler.reminder_notification import _account_reminder_spend

        seen: list[dict] = []
        with (
            patch(
                "src.infrastructure.proactive.tracking.track_proactive_tokens",
                AsyncMock(side_effect=lambda **kw: seen.append(kw)),
            ),
            patch(
                "src.infrastructure.scheduler.reminder_notification.get_cached_cost_usd_eur",
                side_effect=KeyError("unpriced"),
            ),
        ):
            cost = await _account_reminder_spend(
                AsyncMock(),
                reminder_id="rem-5",
                user_id=uuid.uuid4(),
                run_id="run-5",
                conversation_id=uuid.uuid4(),
                result=_Result(),
            )

        assert cost == 0.0
        assert len(seen) == 1, "the tokens were dropped because the price was missing"
