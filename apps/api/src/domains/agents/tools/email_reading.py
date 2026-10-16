"""Detailed mailbox reads performed inside the email tool's consultation gate.

The public tool bounds the batch before calling this shared implementation.
Successes remain usable, a partial read is counted by its caller, and a total
failure never masquerades as a successfully read empty mailbox.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from src.core.constants import GMAIL_FORMAT_FULL
from src.domains.agents.emails.message_finishing import finish_messages
from src.domains.connectors.clients.protocols import EmailClientProtocol

logger = structlog.get_logger(__name__)


async def fetch_messages(
    client: EmailClientProtocol, message_ids: list[str], *, use_cache: bool
) -> list[dict[str, Any]]:
    """Preserve successes, propagate cancellation and raise on a fully failed batch."""
    results = await asyncio.gather(
        *(
            client.get_message(message_id=mid, format=GMAIL_FORMAT_FULL, use_cache=use_cache)
            for mid in message_ids
        ),
        return_exceptions=True,
    )
    fetched: list[dict[str, Any]] = []
    for message_id, result in zip(message_ids, results, strict=True):
        if isinstance(result, BaseException):
            if isinstance(result, asyncio.CancelledError):
                raise result
            logger.warning(
                "get_emails_fetch_error", message_id=message_id, error_type=type(result).__name__
            )
            continue
        fetched.append(result)
    if not fetched:
        failure = next((result for result in results if isinstance(result, BaseException)), None)
        if failure is not None:
            raise failure
    return await finish_messages(client, fetched)
