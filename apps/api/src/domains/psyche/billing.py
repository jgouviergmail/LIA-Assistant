"""Known paid summary attempts share the caller's settlement transaction."""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.llm.token_capture import TokenCaptureHandler

logger = structlog.get_logger(__name__)


async def settle_summary_capture(
    capture: TokenCaptureHandler, user_id: UUID, model_name: str, db: AsyncSession
) -> None:
    """Claim each captured attempt once without making accounting a UI failure."""
    try:
        if capture.has_usage:
            from src.infrastructure.proactive.tracking import track_proactive_tokens

            records = capture.claim_billing_records(model_name)
            await track_proactive_tokens(
                user_id=user_id,
                task_type="psyche_summary",
                target_id=str(user_id),
                conversation_id=None,
                tokens_in=capture.tokens_in,
                tokens_out=capture.tokens_out,
                tokens_cache=capture.tokens_cache,
                tokens_cache_write=capture.tokens_cache_write,
                model_name=records[-1].model_name,
                billing_records=records,
                db=db,
                source="proactive",
            )
    except Exception as exc:
        logger.debug("psyche_summary_token_tracking_failed", error=str(exc))
