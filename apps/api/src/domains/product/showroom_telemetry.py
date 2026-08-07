"""Credential-less showroom funnel collector (P0 — public-web-showroom program).

One ``202`` endpoint deliberately unlike the ordinary telemetry route:

- NO session dependency and NO ``Request`` parameter — the handler cannot
  read cookies, ``Request.client``, forwarding headers, or the User-Agent,
  so rows are non-attributed by construction (``user_id=NULL``,
  ``run_id=NULL``, ``channel="web_showroom"``);
- abuse control uses fixed GLOBAL Redis quota keys (never an IP-, cookie-,
  or visitor-derived bucket); quota exhaustion or Redis failure drops the
  batch with ``202`` — fail-closed measurement loss, never a fail-open
  identifiable write and never a UX-visible error;
- the vocabulary is the exclusive ``SHOWROOM_EVENT_TYPES`` subset; anything
  else is schema-rejected (422). Mission behavior never depends on this
  route: the browser emitter is fire-and-forget with ``credentials: "omit"``.
"""

from typing import Any

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel, Field, field_validator

from src.core.config import settings
from src.domains.product.constants import SHOWROOM_EVENT_TYPES, ProductEventType
from src.domains.product.schemas import MAX_EVENTS_PER_BATCH, ClientEventAck

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/product", tags=["product"])

#: Fixed global quota keys — shared by every caller on purpose (non-attribution).
SHOWROOM_MINUTE_QUOTA_KEY = "product:showroom:minute"
SHOWROOM_DAY_QUOTA_KEY = "product:showroom:day"

_SHOWROOM_EVENT_VALUES = frozenset(e.value for e in SHOWROOM_EVENT_TYPES)


async def _get_rate_limiter() -> Any:
    """Indirection point for the Redis limiter (monkeypatched in tests)."""
    from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

    return await get_rate_limiter()


class ShowroomEventBatch(BaseModel):
    """Enum-only showroom batch — plain event names, no item envelope.

    Attributes:
        events: Bounded ``SHOWROOM_EVENT_TYPES`` values (1..batch cap).
    """

    events: list[str] = Field(
        min_length=1,
        max_length=MAX_EVENTS_PER_BATCH,
        description="Bounded showroom event names — never free text.",
    )

    @field_validator("events")
    @classmethod
    def _bounded_events(cls, values: list[str]) -> list[str]:
        for value in values:
            if value not in _SHOWROOM_EVENT_VALUES:
                raise ValueError(f"unknown showroom event '{value}'")
        return values


async def _acquire_global_quota() -> bool:
    """Consume one request slot from both fixed global windows.

    Returns:
        True when both the minute and day windows admit this request.
    """
    limiter = await _get_rate_limiter()
    minute_ok = await limiter.acquire(
        key=SHOWROOM_MINUTE_QUOTA_KEY,
        max_calls=settings.product_showroom_minute_cap,
        window_seconds=60,
    )
    if not minute_ok:
        return False
    return bool(
        await limiter.acquire(
            key=SHOWROOM_DAY_QUOTA_KEY,
            max_calls=settings.product_showroom_day_cap,
            window_seconds=86_400,
        )
    )


@router.post(
    "/showroom-events",
    response_model=ClientEventAck,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest non-attributed showroom funnel attempts (P0 program)",
)
async def ingest_showroom_events(batch: ShowroomEventBatch) -> ClientEventAck:
    """Record bounded showroom attempts with no identity or network metadata.

    Args:
        batch: Enum-only showroom event names.

    Returns:
        Accepted/dropped counts — dropping is silent by design.
    """
    from src.domains.product.repository import ProductRepository
    from src.infrastructure.database import get_db_context
    from src.infrastructure.observability.metrics_product import (
        product_client_events_total,
    )

    try:
        allowed = await _acquire_global_quota()
    except Exception as exc:
        # Fail-closed: a Redis outage loses measurement, never identifies the
        # caller through a fallback path and never surfaces an error.
        logger.debug("showroom_events_quota_check_failed", error=str(exc))
        allowed = False
    if not allowed:
        logger.debug("showroom_events_dropped", count=len(batch.events))
        return ClientEventAck(accepted=0, dropped=len(batch.events))

    async with get_db_context() as db:
        repo = ProductRepository(db)
        for name in batch.events:
            await repo.record_event(
                user_id=None,
                event_type=ProductEventType(name),
                run_id=None,
                channel="web_showroom",
            )
        await db.commit()
    # Counter increments AFTER the commit (rollup rule, mirrors the ordinary
    # route): an aborted transaction must not leave phantom increments.
    for name in batch.events:
        product_client_events_total.labels(event_type=name, channel="web_showroom").inc()
    logger.debug("showroom_events_ingested", accepted=len(batch.events))
    return ClientEventAck(accepted=len(batch.events), dropped=0)
