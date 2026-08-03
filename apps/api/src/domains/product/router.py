"""Product telemetry ingestion endpoint (ADR-178 Phase 4).

One public, IP-rate-limited endpoint with OPTIONAL session auth:
authenticated callers may send every client event; anonymous callers are
restricted to the pre-signup funnel subset (arbitration a) and their rows
store counts only (``user_id NULL``, no IP, no fingerprint). Search and Web
Vitals items feed bounded Prometheus families and never touch the database.
Invalid-for-context items are dropped silently — telemetry must never
degrade the UX.
"""

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.client_metadata import parse_user_agent
from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session, get_optional_session
from src.domains.product.constants import (
    ANONYMOUS_EVENT_TYPES,
    WEB_VITAL_SECONDS_METRICS,
    ProductEventType,
    derive_device_class,
)
from src.domains.product.schemas import ClientEventAck, ClientEventBatch, ClientEventItem
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/product", tags=["product"])

RATE_LIMIT_PRODUCT_EVENTS_PER_MINUTE = 60


async def _rate_limit_product_events(request: Request) -> None:
    """IP-keyed Redis rate limit (fail-open, pattern of auth dependencies).

    Args:
        request: Incoming request (client IP extraction).
    """
    from src.core.exceptions import raise_rate_limit_exceeded
    from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

    try:
        limiter = await get_rate_limiter()
        # Proxy-aware: behind cloudflared/nginx request.client is the proxy —
        # keying on it would throttle every visitor in one shared bucket.
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )
        allowed = await limiter.acquire(
            key=f"product:events:{client_ip}",
            max_calls=RATE_LIMIT_PRODUCT_EVENTS_PER_MINUTE,
            window_seconds=60,
        )
        if not allowed:
            raise_rate_limit_exceeded(
                limit=RATE_LIMIT_PRODUCT_EVENTS_PER_MINUTE,
                window_seconds=60,
                retry_after=60,
                detail={"error": "rate_limit_exceeded"},
                headers={"Retry-After": "60"},
            )
    except Exception as exc:
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            raise
        # Fail-open: a Redis hiccup must not break telemetry ingestion.
        logger.debug("product_events_rate_limit_check_failed", error=str(exc))


def _observe_prometheus_item(item: ClientEventItem, device_class: str) -> bool:
    """Route a search/vital item to its bounded Prometheus family.

    Args:
        item: Validated telemetry item.
        device_class: Bounded device class derived from the User-Agent.

    Returns:
        True when the item was complete and observed.
    """
    from src.infrastructure.observability.metrics_product import (
        product_search_total,
        product_web_vital_ratio,
        product_web_vital_seconds,
    )

    if item.kind == "search":
        if item.surface is None or item.outcome is None:
            return False
        product_search_total.labels(
            surface=item.surface, outcome=item.outcome, device_class=device_class
        ).inc()
        return True
    if item.metric is None or item.value is None:
        return False
    family = (
        product_web_vital_seconds
        if item.metric in WEB_VITAL_SECONDS_METRICS
        else product_web_vital_ratio
    )
    family.labels(metric=item.metric, device_class=device_class).observe(item.value)
    return True


@router.post(
    "/events",
    response_model=ClientEventAck,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest bounded client telemetry (funnel, search, Web Vitals)",
)
async def ingest_client_events(
    request: Request,
    batch: ClientEventBatch,
    current_user: User | None = Depends(get_optional_session),
    _rate_limit: None = Depends(_rate_limit_product_events),
) -> ClientEventAck:
    """Accept a telemetry batch; drop unauthorized items silently.

    Anonymous callers may only send the pre-signup funnel subset
    (``ANONYMOUS_EVENT_TYPES``) plus search/vitals; everything else needs a
    session. Never raises for content reasons (schema validation aside).

    Args:
        request: Incoming request (bounded UA reduction, ADR-144).
        batch: Enum-bounded telemetry items.
        current_user: Session user, when authenticated.
        _rate_limit: IP rate-limit guard (fail-open).

    Returns:
        Accepted/dropped counts.
    """
    from src.domains.product.repository import ProductRepository
    from src.infrastructure.database import get_db_context
    from src.infrastructure.observability.metrics_product import (
        product_client_events_total,
    )

    _, os_family = parse_user_agent(request.headers.get("user-agent"))
    device_class = derive_device_class(os_family)
    user_id = current_user.id if current_user is not None else None

    accepted = 0
    dropped = 0
    db_events: list[ProductEventType] = []
    for item in batch.events:
        if item.kind in ("search", "vital"):
            if _observe_prometheus_item(item, device_class):
                accepted += 1
            else:
                dropped += 1
            continue
        if item.event_type is None:
            dropped += 1
            continue
        event_type = ProductEventType(item.event_type)
        if user_id is None and event_type not in ANONYMOUS_EVENT_TYPES:
            dropped += 1
            continue
        db_events.append(event_type)

    if db_events:
        async with get_db_context() as db:
            repo = ProductRepository(db)
            for event_type in db_events:
                await repo.record_event(
                    user_id=user_id,
                    event_type=event_type,
                    run_id=None,
                    channel="web",
                )
            await db.commit()
        # Counter increments AFTER the commit (rollup rule): an aborted
        # transaction must not leave phantom event increments in Prometheus.
        for event_type in db_events:
            product_client_events_total.labels(event_type=event_type.value, channel="web").inc()
            accepted += 1

    # Counts only at INFO (PII rule) — item contents never logged.
    logger.debug(
        "product_client_events_ingested",
        accepted=accepted,
        dropped=dropped,
        authenticated=user_id is not None,
    )
    return ClientEventAck(accepted=accepted, dropped=dropped)


class PersonalResultsResponse(BaseModel):
    """What the assistant achieved for this account, over its billing cycle.

    Four figures, each an EXACT aggregate over its own set (ADR-185). Two
    candidates were deliberately left out rather than estimated: "time saved",
    which no source in this system measures, and "documents actually used",
    which no table records durably — an injected chunk is not a used one.
    """

    model_config = ConfigDict(frozen=True)

    cycle_start: datetime = Field(description="Start of the billing cycle these cover.")
    useful_results: int = Field(ge=0, description="Results confirmed useful (E1 or E2).")
    actions: int = Field(ge=0, description="Successful actions among them.")
    automations: int = Field(ge=0, description="Successful routine runs among them.")
    commitments_closed: int = Field(ge=0, description="Commitments closed in the window.")
    #: False when product analytics is off on this instance: the client then
    #: says so instead of showing four zeros, which would read as "you achieved
    #: nothing" rather than "nothing is being measured".
    measured: bool = Field(description="Whether outcome recording is enabled here.")


@router.get(
    "/me/results",
    response_model=PersonalResultsResponse,
    summary="Results achieved for the current user this cycle",
)
async def get_personal_results(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PersonalResultsResponse:
    """Outcomes and closed commitments over the current billing cycle.

    The dashboard led with messages, tokens, Google requests and cost — useful
    for administration, not as the story of what the assistant is for.
    """
    from src.domains.chat.service import StatisticsService
    from src.domains.open_loops.repository import OpenLoopRepository
    from src.domains.product.repository import ProductRepository

    # The same window the consumption tiles use — the two blocks must never
    # describe different periods on one screen.
    since = StatisticsService.calculate_cycle_start(current_user.created_at)

    measured = bool(getattr(settings, "product_analytics_enabled", False))
    outcomes = (
        await ProductRepository(db).personal_results(user_id=current_user.id, since=since)
        if measured
        else {"useful_results": 0, "actions": 0, "automations": 0}
    )
    closed = await OpenLoopRepository(db).count_closed_since(current_user.id, since)

    return PersonalResultsResponse(
        cycle_start=since,
        useful_results=outcomes["useful_results"],
        actions=outcomes["actions"],
        automations=outcomes["automations"],
        commitments_closed=closed,
        measured=measured,
    )
