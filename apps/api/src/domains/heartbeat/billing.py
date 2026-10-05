"""Settlement for a heartbeat decision that produces no notification."""

from collections.abc import Callable
from uuid import UUID, uuid4

import structlog

from src.core.config import Settings
from src.core.llm_usage import LLMBillingRecord

logger = structlog.get_logger(__name__)


async def track_skipped_decision(
    user_id: UUID,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int,
    tokens_cache_write: int,
    billing_records: tuple[LLMBillingRecord, ...],
    *,
    settings_reader: Callable[[], Settings],
) -> None:
    """Preserve the decision's known spend under its enclosing sweep run."""
    if tokens_in == 0 and tokens_out == 0 and tokens_cache == 0 and not billing_records:
        return
    try:
        from src.core.llm_config_helper import get_llm_config_for_agent
        from src.infrastructure.proactive.tracking import ambient_run_id, track_proactive_tokens

        model_name = (
            billing_records[-1].model_name
            if billing_records
            else get_llm_config_for_agent(settings_reader(), "heartbeat_decision").model
        )
        await track_proactive_tokens(
            user_id=user_id,
            task_type="heartbeat",
            target_id=f"heartbeat_skip_{uuid4().hex[:8]}",
            conversation_id=None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            tokens_cache_write=tokens_cache_write,
            model_name=model_name,
            billing_records=billing_records,
            source="proactive",
            run_id=ambient_run_id(),
        )
    except Exception as exc:
        logger.warning("heartbeat_skip_token_tracking_failed", user_id=str(user_id), error=str(exc))
