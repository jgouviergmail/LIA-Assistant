"""The vendor's own bill of a live session, read on the person's key and shown — never recorded.

A live session runs on the PERSON's key: the platform re-bills nothing of it,
so nothing of the vendor's charge reaches a ledger, a card or a statistic
(``cost_bearers``, owner directive 2026-09-16, amended 2026-09-19: a live,
indicative display is allowed). On a vendor-billed provider the platform
prices nothing during the session (the meter shows the clock alone); at the
end, a provider that can state its bill (``VendorBilling``) is asked on the
key, under the probe's own timeout, and the answer travels in the end
response alone. **A vendor settles its books after the socket closes**
(measured 2026-09-20: ``in-progress`` and no cost while the browser's close
frame lands, the bill stated 0.3 s after the close handshake), so a read
that finds no bill asks again — ``LIVE_VENDOR_BILL_SETTLE_ATTEMPTS`` times,
``LIVE_VENDOR_BILL_SETTLE_INTERVAL_SECONDS`` apart — and never longer.
Extracted from ``service.py``, which is size-capped.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import (
    LIVE_VENDOR_BILL_SETTLE_ATTEMPTS,
    LIVE_VENDOR_BILL_SETTLE_INTERVAL_SECONDS,
)
from src.core.i18n import resolve_language
from src.domains.connectors.models import ConnectorType
from src.domains.live.providers import PROVIDERS, VendorBilling
from src.domains.live.schemas import LiveVendorBill

if TYPE_CHECKING:
    from src.domains.live.connector_service import LiveConnectorService
    from src.domains.live.session_store import LiveSessionRecord
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)


async def fetch_vendor_bill(
    connectors: LiveConnectorService,
    user: User,
    record: LiveSessionRecord,
    conversation_ids: list[str],
) -> LiveVendorBill | None:
    """What the session's provider billed the person, or None — never raising.

    A session that slept opened one provider conversation per connection
    (ADR-329): every one is read, in parallel, and the bills are summed. A
    figure shown is exact or absent — one conversation whose bill cannot be
    read hides the total rather than understate it.

    Args:
        connectors: The account's live connectors (the key is read through it).
        user: The person.
        record: The session's record (its provider).
        conversation_ids: The provider's own ids of the session's
            conversations, in order (a repeated id is read once); empty when
            the wire names none.

    Returns:
        The bill, or None when the wire named no conversation, the provider
        states no bill, the connector is gone, or a conversation could not be
        read.
    """
    distinct = [cid for cid in dict.fromkeys(conversation_ids) if cid]
    if not distinct:
        return None
    provider = next(
        (candidate for candidate in PROVIDERS.values() if candidate.provider_id == record.provider),
        None,
    )
    if provider is None or not isinstance(provider, VendorBilling):
        return None
    try:
        connector = await connectors.connector_of(
            user, record.provider, language=resolve_language()
        )
        api_key = await connectors.api_key_of(user.id, ConnectorType(connector.connector_type))
        bills = await asyncio.gather(*(_settled_bill(provider, api_key, cid) for cid in distinct))
    except Exception as exc:  # noqa: BLE001 - a bill that cannot be read costs the person nothing
        logger.info(
            "live_vendor_bill_unavailable",
            provider=record.provider,
            error_type=type(exc).__name__,
        )
        return None
    read = [bill for bill in bills if bill is not None]
    logger.debug(
        "live_vendor_bill_read",
        provider=record.provider,
        conversations=len(distinct),
        available=len(read),
    )
    if len(read) != len(distinct):
        return None
    return read[0] if len(read) == 1 else merge_bills(read)


async def _settled_bill(
    provider: VendorBilling, api_key: str, conversation_id: str
) -> LiveVendorBill | None:
    """One conversation's bill, asked again while the vendor is still settling it."""
    bill: LiveVendorBill | None = None
    for attempt in range(1, LIVE_VENDOR_BILL_SETTLE_ATTEMPTS + 1):
        bill = await provider.conversation_bill(
            api_key, conversation_id, timeout=settings.live_probe_timeout_seconds
        )
        if bill is not None or attempt == LIVE_VENDOR_BILL_SETTLE_ATTEMPTS:
            break
        # The vendor is still settling the conversation: ask again shortly.
        await asyncio.sleep(LIVE_VENDOR_BILL_SETTLE_INTERVAL_SECONDS)
    return bill


def merge_bills(bills: list[LiveVendorBill]) -> LiveVendorBill:
    """One bill for several conversations: amounts summed, names stated once each.

    Driven by the schema's own fields, so a field the vendor bill gains is
    merged too, never dropped. An amount no bill states stays absent — never
    an invented zero.
    """
    merged: dict[str, Any] = {}
    for name in LiveVendorBill.model_fields:
        if name == "provider":
            continue
        stated = [getattr(bill, name) for bill in bills if getattr(bill, name) is not None]
        if not stated:
            merged[name] = None
        elif isinstance(stated[0], str):
            merged[name] = ", ".join(dict.fromkeys(str(value) for value in stated))
        else:
            merged[name] = sum(stated)
    return LiveVendorBill(provider=bills[0].provider, **merged)


__all__ = ["fetch_vendor_bill", "merge_bills"]
