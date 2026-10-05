"""Settlement of one captured reminder generation before notification delivery."""

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.infrastructure.scheduler.reminder_notification import ReminderMessageResult

logger = structlog.get_logger(__name__)


async def account_reminder_spend(
    db: AsyncSession | None,
    *,
    reminder_id: str,
    user_id: UUID,
    run_id: str,
    conversation_id: UUID | None,
    result: ReminderMessageResult,
    cost_calculator: Callable[..., tuple[float, float]],
) -> float:
    """Use frozen costs and a one-time claim; legacy callers retain their price seam."""
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    records = getattr(result, "billing_records", ())
    if (
        result.tokens_in <= 0
        and result.tokens_out <= 0
        and result.tokens_cache <= 0
        and not records
    ):
        return 0.0
    cost_eur = 0.0
    try:
        if records:
            cost_eur = sum(record.cost_eur for record in records)
        else:
            _cost_usd, cost_eur = cost_calculator(
                model=result.model_name or "",
                prompt_tokens=result.tokens_in,
                completion_tokens=result.tokens_out,
                cached_tokens=result.tokens_cache,
                cache_write_tokens=result.tokens_cache_write,
            )
    except Exception as exc:
        logger.warning("reminder_cost_calculation_failed", reminder_id=reminder_id, error=str(exc))
    capture = getattr(result, "billing_capture", None)
    if capture is not None:
        records = capture.claim_billing_records(result.model_name or "unknown")
        if not records:
            return float(cost_eur)
    await track_proactive_tokens(
        user_id=user_id,
        task_type="reminder",
        target_id=reminder_id,
        conversation_id=conversation_id,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        tokens_cache=result.tokens_cache,
        tokens_cache_write=result.tokens_cache_write,
        model_name=result.model_name,
        billing_records=records,
        db=db,
        run_id=run_id,
        source="scheduled",
    )
    return float(cost_eur)
