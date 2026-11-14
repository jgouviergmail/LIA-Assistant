"""The public address of a routine another system starts (ADR-386).

``POST /api/v1/hooks/routines/{key}`` takes no session: the call is authenticated
by its signature alone, HMAC-SHA256 of the raw body under the routine's secret
(``webhooks.py``). Bounded before anything is read: the capability switch, a
per-client window, the body's size; then the service decides (``webhook_service``)
and the answer never waits for the run — the next pass of the scheduler serves
the call.

Answers: 202 (accepted, or a delivery already accepted), 403 (no valid
signature), 404 (no routine answers at this address), 413 (too large), 429 (the
address's window, or as many calls waiting as a routine may keep). A call is
counted here by what it became; the service logs it by its facts (a routine id,
a size, an outcome), never its body, its address or its sender's words.
"""

from __future__ import annotations

from typing import Annotated, Literal, NoReturn

import structlog
from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    RATE_LIMIT_ROUTINE_WEBHOOK_PER_IP_PER_MINUTE,
    ROUTINE_WEBHOOK_PATH,
    ROUTINE_WEBHOOK_RATE_LIMIT_KEY_PREFIX,
)
from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_invalid_webhook_signature,
    raise_not_found_or_unauthorized,
    raise_payload_too_large,
    raise_rate_limit_exceeded,
)
from src.core.time_utils import now_utc
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.parser import IngestionBodyError, read_bounded_body
from src.domains.scheduled_actions.webhook_service import (
    CALL_WINDOW_SECONDS,
    CallOutcome,
    RoutineWebhookService,
)
from src.infrastructure.observability.metrics_routine_webhooks import (
    routine_webhook_calls_total,
)
from src.infrastructure.rate_limiting.ip_limiter import create_ip_rate_limiter

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix=ROUTINE_WEBHOOK_PATH,
    tags=["Routine webhooks"],
    dependencies=capability_dependencies(PlatformCapability.ROUTINE_WEBHOOKS),
)

#: Every routine address shares one window per client: a stranger probing
#: addresses is slowed down before any read.
_rate_limit_client = create_ip_rate_limiter(
    namespace=ROUTINE_WEBHOOK_RATE_LIMIT_KEY_PREFIX,
    action="call",
    max_calls=RATE_LIMIT_ROUTINE_WEBHOOK_PER_IP_PER_MINUTE,
)

#: What an address key may look like: the url-safe alphabet it is drawn from.
AddressKey = Annotated[str, Path(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class RoutineWebhookCallResponse(BaseModel):
    """The answer to a call a routine accepted."""

    status: Literal["accepted", "duplicate"] = Field(
        ...,
        description=(
            "accepted = kept for the routine's next run; duplicate = this delivery "
            "was already accepted, and is not kept twice."
        ),
    )


async def _bounded_body(request: Request) -> bytes:
    """The raw body, refused before it is read past the routine's bound.

    Raises:
        PayloadTooLargeError: 413 when the declared or the streamed size is over.
    """
    limit = settings.routine_webhook_max_body_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        _refuse_too_large(limit)
    try:
        return await read_bounded_body(request.stream(), max_bytes=limit)
    except IngestionBodyError:
        _refuse_too_large(limit)


def _refuse_too_large(limit: int) -> NoReturn:
    """Count the refusal and answer 413."""
    routine_webhook_calls_total.labels(outcome=CallOutcome.TOO_LARGE.value).inc()
    raise_payload_too_large(f"Body over {limit} bytes")


@router.post(
    "/{key}",
    status_code=202,
    response_model=RoutineWebhookCallResponse,
    summary="Start a routine with a signed call",
)
async def receive_routine_call(
    key: AddressKey,
    request: Request,
    response: Response,
    _: None = Depends(_rate_limit_client),
    db: AsyncSession = Depends(get_db),
) -> RoutineWebhookCallResponse:
    """Keep a signed call for the routine at this address.

    The body is signed with HMAC-SHA256 under the routine's secret, sent as
    ``X-LIA-Signature-256: sha256=<hex>`` (``X-Hub-Signature-256`` is read
    alike). ``X-LIA-Delivery`` (or ``X-GitHub-Delivery``) names a delivery so a
    retry is kept once.
    """
    body = await _bounded_body(request)
    outcome = await RoutineWebhookService(db).receive(
        key, body=body, headers=request.headers, at=now_utc()
    )
    routine_webhook_calls_total.labels(outcome=outcome.value).inc()
    response.headers["Cache-Control"] = "no-store"
    if outcome is CallOutcome.UNKNOWN:
        logger.debug("routine_webhook_call_unknown")
        raise_not_found_or_unauthorized("routine_webhook")
    if outcome is CallOutcome.BAD_SIGNATURE:
        raise_invalid_webhook_signature("routine")
    if outcome in (CallOutcome.RATE_LIMITED, CallOutcome.FULL):
        limit = (
            settings.routine_webhook_rate_per_minute
            if outcome is CallOutcome.RATE_LIMITED
            else settings.routine_webhook_max_pending
        )
        raise_rate_limit_exceeded(
            limit=limit,
            window_seconds=CALL_WINDOW_SECONDS,
            retry_after=CALL_WINDOW_SECONDS,
            detail={
                "error": (
                    "rate_limit_exceeded"
                    if outcome is CallOutcome.RATE_LIMITED
                    else "routine_webhook_backlog_full"
                ),
                "retry_after_seconds": CALL_WINDOW_SECONDS,
            },
            headers={"Retry-After": str(CALL_WINDOW_SECONDS)},
        )
    return RoutineWebhookCallResponse(
        status="duplicate" if outcome is CallOutcome.DUPLICATE else "accepted"
    )


__all__ = ["RoutineWebhookCallResponse", "router"]
