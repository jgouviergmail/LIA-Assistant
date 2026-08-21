"""Google push webhook endpoints (lot H, 2026-08).

Both endpoints are unauthenticated by nature (Google is the caller) and
ALWAYS answer 200: a non-2xx would trigger Google/Pub/Sub retries, and a
differentiated status would reveal what the channel registry knows to anyone
who found the public URL. Authentication happens inside the service (channel
token / platform push token, constant-time).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.domains.push_channels.notifications import (
    parse_channel_headers,
    parse_pubsub_body,
)
from src.domains.push_channels.service import PushChannelService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Push"])


@router.post("/google", summary="Google channel notifications (Calendar/Drive)")
async def google_channel_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Receive an X-Goog-* channel notification (lot H phase 1).

    Returns:
        {"status": "ok"} — always, whatever the processing outcome.
    """
    notif = parse_channel_headers(dict(request.headers))
    if notif is not None:
        outcome = await PushChannelService(db).handle_channel_notification(notif)
        logger.debug("google_channel_webhook", outcome=outcome.value)
    return {"status": "ok"}


@router.post("/google/pubsub", summary="Gmail Pub/Sub push notifications")
async def google_pubsub_webhook(
    request: Request,
    token: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Receive a Gmail Pub/Sub push delivery (lot H phase 2).

    The push subscription appends ?token=<secret> to the endpoint URL; the
    service validates it in constant time.

    Returns:
        {"status": "ok"} — always (a non-2xx would make Pub/Sub redeliver
        forever for payloads we will never accept).
    """
    body: Any = None
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — malformed body ⇒ ignored, still 200
        logger.debug("google_pubsub_webhook_unparseable_body")
    if isinstance(body, dict):
        event = parse_pubsub_body(body)
        if event is not None:
            outcome = await PushChannelService(db).handle_gmail_push(event, provided_token=token)
            logger.debug("google_pubsub_webhook", outcome=outcome.value)
    return {"status": "ok"}
