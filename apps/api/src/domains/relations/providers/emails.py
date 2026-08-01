"""Mail exchanged with one person (Bloc C, B2).

Queried by ADDRESS, never by display name: the mail search matches a name
against MIME headers, which produces both misses and strangers. The addresses
come from the contact card, so the CRM's notion of identity stays the one
``fold_name`` defines.

**Three searches per address, and that is not an optimization oversight.** A
single "from OR to OR cc" query cannot survive the three providers:

- Apple — ``convert_imap_query`` builds an **AND** of criteria, so
  ``from:x to:x`` matches nothing at all;
- Microsoft — ``build_search_filter`` routes to the **inbox** folder unless
  ``in:`` says otherwise, so sent mail is simply invisible;
- Gmail — space-separated operators are ANDed too.

So each direction is asked for on its own terms, and each answer carries the
direction that produced it. Being in COPY is being written to — dropping ``cc``
would hide every thread where the person was not the first recipient — which is
why ``cc:`` was taught to both converters rather than smuggled in as free text.
One failing search never blanks the others: part of an exchange is a lens with
a hole, an empty section is a false negative.

The window bounds RELEVANCE and what the provider scans, never quota: a search
costs one call whatever it spans. It rides ``after:``, one of the few operators
all three converters understand (Apple maps it to ``date_gte``, Microsoft to a
``receivedDateTime`` filter).

No count is reported: a provider page cannot prove how many messages exist
behind it, and ADR-185 forbids a count that is not exact.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from src.core.exceptions import MaxRetriesExceededError
from src.domains.relations.providers.client import open_category_client
from src.domains.relations.providers.schemas import ExchangedEmail

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)

#: Direction → the query that finds it. `in:sent` is load-bearing for Microsoft
#: (inbox-by-default) and Apple (one IMAP folder at a time); the `to`/`cc` pair
#: is load-bearing everywhere, since none of the three can express an OR.
_DIRECTION_QUERIES: tuple[tuple[str, str], ...] = (
    ("received", "from:{address}"),
    ("sent", "in:sent to:{address}"),
    ("sent", "in:sent cc:{address}"),
)

#: Gmail's date format, understood by all three converters.
_AFTER_FORMAT = "%Y/%m/%d"

#: Shown when the provider gave no subject — never an empty line.
_NO_SUBJECT = "(no subject)"

#: Sorting key for a message the provider dated unusably: it goes last, but it
#: is never dropped — that would hide real correspondence over a header quirk.
_UNDATED_SORT_KEY = datetime.min.replace(tzinfo=UTC)


def _occurred_at(message: dict[str, Any]) -> datetime | None:
    """Parse ``internalDate`` (epoch ms) — the shape all three providers emit."""
    raw = message.get("internalDate")
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _to_email(message: dict[str, Any], direction: str) -> ExchangedEmail | None:
    """Map one normalized message onto the contract (None when unusable)."""
    message_id = str(message.get("id") or "").strip()
    if not message_id:
        return None  # nothing stable to key a row on
    subject = str(message.get("subject") or "").strip() or _NO_SUBJECT
    return ExchangedEmail(
        id=message_id,
        direction=direction,
        subject=subject,
        occurred_at=_occurred_at(message),
    )


async def _search_one(
    client: Any, query: str, direction: str, limit: int, user_id: UUID
) -> list[ExchangedEmail]:
    """Run ONE directional search; a failure yields nothing, never raises.

    Degrading per query is deliberate: a provider that refuses ``in:sent``
    would otherwise blank an exchange whose received half is perfectly
    readable. The caught set mirrors the briefing fetchers, including
    ``MaxRetriesExceededError`` — THE shape a tired provider takes in this
    codebase, and the one most likely to hit a third search.
    """
    try:
        response = await client.search_emails(query, max_results=limit, use_cache=True)
    except (TimeoutError, httpx.HTTPError, MaxRetriesExceededError, ValueError, KeyError) as exc:
        logger.info(
            "relations_email_search_degraded",
            user_id=str(user_id),
            direction=direction,
            error_type=type(exc).__name__,
        )
        return []
    found = []
    for message in response.get("messages") or []:
        if isinstance(message, dict) and (email := _to_email(message, direction)) is not None:
            found.append(email)
    return found


async def fetch_exchanged_emails(
    user_id: UUID, *, addresses: list[str], limit: int, window_days: int, now: datetime
) -> list[ExchangedEmail]:
    """Mail exchanged with one person, newest first, both directions.

    Args:
        user_id: Owner of the mailbox.
        addresses: The person's addresses, already capped by the caller.
        limit: Cap on returned items (also the per-search page size).
        window_days: How far back to search. Bounds relevance and the
            provider's scan — not quota, which counts CALLS.
        now: Timezone-aware UTC reference instant.

    Returns:
        Deduplicated messages, newest first; empty when no address was given.

    Raises:
        ProviderNotConfigured: When no mail connector is usable — an unasked
            question, which the caller renders differently from an empty one.
    """
    if not addresses:
        return []
    since = (now - timedelta(days=window_days)).strftime(_AFTER_FORMAT)
    seen: dict[str, ExchangedEmail] = {}
    async with open_category_client("email", user_id) as opened:
        client = opened.client
        for address in addresses:
            for direction, template in _DIRECTION_QUERIES:
                query = f"{template.format(address=address)} after:{since}"
                for email in await _search_one(client, query, direction, limit, user_id):
                    # Two addresses of one person can surface the same thread;
                    # the first sighting wins, so a message is listed once.
                    seen.setdefault(email.id, email)
    ordered = sorted(
        seen.values(), key=lambda email: email.occurred_at or _UNDATED_SORT_KEY, reverse=True
    )
    return ordered[:limit]
