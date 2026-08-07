"""Every persisted run adds its cost to the instance ledger.

The ceiling is only as good as what feeds it: a run whose spend is never
recorded is a run the ceiling cannot see. ``TrackingContext.persist`` is the
one place where a run's cost becomes durable (LLM tokens, Google API calls,
image generation), so the ledger increment belongs right next to it — in the
SAME transaction, so the two either both land or both roll back.

Recording is UNCONDITIONAL, deliberately. Arming it only when a ceiling is
configured would leave a window where an administrator sets a ceiling and the
counter stays mute — the ceiling would then never trigger, which is exactly
the "setting defined but read nowhere" trap. One UPSERT on one indexed row,
once per run, next to the dozens of token-log inserts persist already does,
is not a measurable cost. As a bonus the ledger answers "what does this
instance spend per day" whether or not anyone bounds it.

What must hold:
- the recorded amount is the run's TOTAL cost, every family included;
- each persist records its own DELTA (records are cleared after each call and
  the summary UPSERT adds rather than replaces) — never a running total that
  would double-count an incremental voice run;
- a free run writes nothing;
- a failure never propagates: the answer is already served.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.usage_limits.instance_budget import InstanceBudgetService

pytestmark = pytest.mark.unit


def _summary(cost: float, google: float = 0.0, image: float = 0.0) -> dict[str, object]:
    return {
        "tokens_in": 100,
        "tokens_out": 50,
        "tokens_cache": 0,
        "cost_eur": cost,
        "google_api_cost_eur": google,
        "image_generation_cost_eur": image,
    }


async def test_the_run_cost_is_added_to_the_ledger_within_the_transaction() -> None:
    session = MagicMock()
    with patch(
        "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
        new_callable=AsyncMock,
    ) as record:
        await InstanceBudgetService.record_run_summary(
            session, _summary(0.01, google=0.002, image=0.5)
        )
    record.assert_awaited_once()
    # The caller's session: the increment and the token summary share one
    # transaction, so they either both land or both roll back.
    assert record.await_args.args[0] is session
    assert record.await_args.kwargs["cost_eur"] == Decimal("0.512")


async def test_a_free_run_writes_nothing() -> None:
    with patch(
        "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
        new_callable=AsyncMock,
    ) as record:
        await InstanceBudgetService.record_run_summary(MagicMock(), _summary(0.0))
    # A cached or local-model run costs nothing; a zero row is noise.
    record.assert_not_awaited()


async def test_a_summary_without_the_optional_cost_families_still_records() -> None:
    with patch(
        "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
        new_callable=AsyncMock,
    ) as record:
        await InstanceBudgetService.record_run_summary(
            MagicMock(), {"cost_eur": 0.02, "tokens_in": 1, "tokens_out": 1}
        )
    assert record.await_args.kwargs["cost_eur"] == Decimal("0.02")


async def test_recording_never_propagates_a_failure_to_the_run() -> None:
    with patch(
        "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
        AsyncMock(side_effect=RuntimeError("db down")),
    ):
        # The answer is already served; accounting is best effort.
        await InstanceBudgetService.record_run_summary(MagicMock(), _summary(0.01))


async def test_persist_records_the_spend_alongside_the_token_summary() -> None:
    """The wiring itself: the persist path calls the recorder before commit."""
    from src.domains.chat.service import TrackingContext

    order: list[str] = []
    db = MagicMock()
    db.commit = AsyncMock(side_effect=lambda: order.append("commit"))

    context = TrackingContext(
        run_id="run_1", user_id=MagicMock(), session_id="s", conversation_id=None
    )
    with (
        patch.object(TrackingContext, "get_summary", return_value=_summary(0.01)),
        patch.object(TrackingContext, "_update_user_statistics", new_callable=AsyncMock),
        patch(
            "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_run_summary",
            new_callable=AsyncMock,
            side_effect=lambda *a, **k: order.append("record"),
        ) as record,
        patch("src.domains.chat.repository.ChatRepository") as repo_class,
    ):
        repo = repo_class.return_value
        repo.bulk_create_token_logs = AsyncMock()
        repo.create_or_update_token_summary = AsyncMock(
            side_effect=lambda **k: order.append("summary")
        )
        await context._do_persist(db=db, commit=True)

    record.assert_awaited_once()
    # Same transaction, and the ledger lands before the commit that seals it.
    assert order == ["summary", "record", "commit"]
