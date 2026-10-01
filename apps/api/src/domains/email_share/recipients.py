"""Recipient suggestions for « Send by e-mail » (ADR-321 amendment).

While a person types in the recipient field of the dialog, the contacts of the
connector they activated are offered by name, first name or phone number, and
the one picked puts its ADDRESS in the field. Without a contacts connector,
nothing is offered — the field stays a plain address field.

What each piece is, and why it is here:

- **The directory** is the address book read whole and cached by the contacts
  client (``clients/contact_directory``) — the providers' own searches match
  three different ways, so the match is done once, in ``recipient_match``.
- **The projection is kept per worker, keyed by the directory's version.** The
  measured cost of projecting 5 000 contacts is ~140 ms of CPU, far too much
  per keystroke; the match itself is ~12 ms. A keystroke asks the book's small
  STAMP first: when this worker already projected that version, neither the
  book nor the connector is opened. A contact written drops the cache, the
  next read is a new version, and the stale projection is replaced. Both
  computations run in a thread: CPU work never holds the event loop.
- **A read of the book is a CONSULTATION** of the person's contacts (ADR-263),
  recorded on the ``email_share`` surface when a provider was actually opened —
  a cache hit opened nothing and records nothing; a read that failed records
  ``failed``, never a silent success.
- **No model, no spend**: matching is deterministic, and the People, CardDAV
  and Graph contact reads are not billed calls.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID, uuid4

import structlog

from src.core.config import settings
from src.core.constants import (
    EMAIL_SHARE_DIRECTORY_READ_TIMEOUT_SECONDS,
    EMAIL_SHARE_RECIPIENT_PROJECTION_MEMO_MAX_ENTRIES,
    EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
    EMAIL_SHARE_RECIPIENT_SUGGESTIONS_MAX,
)
from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.clients.contact_directory import (
    ContactDirectory,
    directory_stamp,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.provider_resolver import resolve_active_connector
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.email_share.recipient_match import (
    RecipientEntry,
    RecipientSuggestion,
    is_searchable,
    match_recipients,
    project_directory,
)
from src.domains.shared.consultation_sink import collector_is_active, consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.infrastructure.observability.metrics_email_share import (
    email_share_recipient_directory_reads_total,
)

logger = structlog.get_logger(__name__)

_CONTACTS_CATEGORY = "contacts"
#: The surface and section this module files its reads under (ADR-263).
_SURFACE = "email_share"
_SECTION = "contacts"


@dataclass(frozen=True, slots=True)
class RecipientSuggestions:
    """What the recipient field is offered for one query.

    Attributes:
        query: The query as received, so the field can tell a late answer from
            the one to what is typed now.
        suggestions: At most the published number, names first.
        truncated: The book was longer than the directory cap: some contacts
            are never suggested, and the list can say so.
    """

    query: str
    suggestions: list[RecipientSuggestion]
    truncated: bool


async def suggestions_available(user_id: UUID) -> bool:
    """Whether the account has a contacts connector to suggest from.

    Args:
        user_id: The account.

    Returns:
        True when a contacts connector is active.
    """
    return await _active_contacts_provider(user_id) is not None


async def _active_contacts_provider(user_id: UUID) -> ConnectorType | None:
    """The account's active contacts connector (the connector list is Redis-cached)."""
    async with DetachedConnectorService().unit_of_work() as connectors:
        return await resolve_active_connector(user_id, _CONTACTS_CATEGORY, connectors)


async def suggest_recipients(user_id: UUID, query: str) -> RecipientSuggestions:
    """The contacts to offer for what is being typed.

    Never raises: a book that cannot be read offers nothing, and the field
    remains a plain address field.

    Args:
        user_id: The account.
        query: One recipient being typed (a name, a first name, a number, the
            start of an address).

    Returns:
        The suggestions, possibly empty.
    """
    if not is_searchable(query, EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS):
        return RecipientSuggestions(query=query, suggestions=[], truncated=False)
    book = await _entries(user_id)
    if book is None:
        return RecipientSuggestions(query=query, suggestions=[], truncated=False)
    entries, truncated = book
    found = await asyncio.to_thread(
        match_recipients,
        entries,
        query,
        limit=EMAIL_SHARE_RECIPIENT_SUGGESTIONS_MAX,
        min_chars=EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
    )
    return RecipientSuggestions(query=query, suggestions=found, truncated=truncated)


async def _entries(user_id: UUID) -> tuple[list[RecipientEntry], bool] | None:
    """The projected book and its cut — from this worker's memo when it holds its version."""
    try:
        provider = await _active_contacts_provider(user_id)
    except Exception as error:  # The connectors could not be read: offer nothing.
        email_share_recipient_directory_reads_total.labels(outcome="failed").inc()
        logger.warning(
            "email_share_contacts_provider_unreadable",
            user_id=str(user_id),
            error_type=type(error).__name__,
        )
        return None
    if provider is None:
        email_share_recipient_directory_reads_total.labels(outcome="no_connector").inc()
        return None
    stamp = await directory_stamp(
        user_id, provider.value, settings.email_share_directory_max_contacts
    )
    if stamp is not None:
        kept = _PROJECTIONS.get((str(user_id), stamp.version))
        if kept is not None:
            _PROJECTIONS.move_to_end((str(user_id), stamp.version))
            email_share_recipient_directory_reads_total.labels(outcome="cached").inc()
            return kept, stamp.truncated
    directory = await _read_directory(user_id)
    if directory is None:
        return None
    return await _projection(user_id, directory), directory.truncated


async def _read_directory(user_id: UUID) -> ContactDirectory | None:
    """The account's directory, recording the read when a provider was opened."""
    started = perf_counter()
    try:
        async with asyncio.timeout(EMAIL_SHARE_DIRECTORY_READ_TIMEOUT_SECONDS):
            async with open_active_client(_CONTACTS_CATEGORY, user_id) as opened:
                if not isinstance(opened, ActiveClient):
                    email_share_recipient_directory_reads_total.labels(outcome="no_connector").inc()
                    return None
                directory: ContactDirectory = await opened.client.list_email_directory(
                    settings.email_share_directory_max_contacts
                )
    except Exception as error:
        outcome = "timeout" if isinstance(error, TimeoutError) else "failed"
        email_share_recipient_directory_reads_total.labels(outcome=outcome).inc()
        logger.warning(
            "email_share_directory_read_failed",
            user_id=str(user_id),
            outcome=outcome,
            error_type=type(error).__name__,
        )
        await _record(user_id, started, failed=True)
        return None
    if directory.from_cache:
        email_share_recipient_directory_reads_total.labels(outcome="cached").inc()
    else:
        email_share_recipient_directory_reads_total.labels(outcome="live").inc()
        await _record(user_id, started, failed=False)
    return directory


async def _record(user_id: UUID, started: float, *, failed: bool) -> None:
    """File one consultation of the account's contacts (ADR-263)."""
    async with _consultation_run():
        record_surface_consultations(
            surface=_SURFACE,
            user_id=user_id,
            opened=[_SECTION],
            failed=[_SECTION] if failed else (),
            duration_ms=int((perf_counter() - started) * 1000),
        )


@asynccontextmanager
async def _consultation_run() -> AsyncIterator[None]:
    """Publish a collector unless a run already collects.

    The register keeps only what a published collector gathers: a row recorded
    without one is dropped in silence (ADR-263) — and this route is a request
    of its own, never inside a turn.
    """
    if collector_is_active():
        yield
        return
    async with consultation_collector(f"email_share_contacts_{uuid4().hex[:12]}"):
        yield


#: Projections kept by this worker, most recently used last, keyed by
#: ``(account, directory version)``. A module-level CACHE of a pure function of
#: the directory — never per-request state: the same key always maps to the
#: same entries. Bounded by the number of entries it holds, not of books.
_PROJECTIONS: OrderedDict[tuple[str, str], list[RecipientEntry]] = OrderedDict()


async def _projection(user_id: UUID, directory: ContactDirectory) -> list[RecipientEntry]:
    """The projected directory, projected once per version on this worker.

    Only the event loop reads and writes the memo; the projection itself runs
    in a thread.
    """
    if directory.version is None:
        return await asyncio.to_thread(project_directory, directory.persons)
    key = (str(user_id), directory.version)
    kept = _PROJECTIONS.get(key)
    if kept is not None:
        _PROJECTIONS.move_to_end(key)
        return kept
    entries = await asyncio.to_thread(project_directory, directory.persons)
    _remember(key, entries)
    return entries


def _remember(key: tuple[str, str], entries: list[RecipientEntry]) -> None:
    """Keep a projection: one version per account, within the entry budget."""
    for stale in [k for k in _PROJECTIONS if k[0] == key[0] and k != key]:
        del _PROJECTIONS[stale]
    _PROJECTIONS[key] = entries
    held = sum(len(kept) for kept in _PROJECTIONS.values())
    while held > EMAIL_SHARE_RECIPIENT_PROJECTION_MEMO_MAX_ENTRIES and len(_PROJECTIONS) > 1:
        _oldest, dropped = _PROJECTIONS.popitem(last=False)
        held -= len(dropped)


__all__ = ["RecipientSuggestions", "suggest_recipients", "suggestions_available"]
