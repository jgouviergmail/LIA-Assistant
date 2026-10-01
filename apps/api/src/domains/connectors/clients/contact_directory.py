"""The address book read whole, for a surface that matches it itself.

Every contacts client answers ``search_contacts``, and the three answers are
three notions of « close »: Google matches prefixes, Apple filters locally with
a plain ``lower()``, Microsoft runs KQL. A surface that must match the SAME way
on every provider — a name without its accents, a number whatever its spacing
— cannot delegate the match; it reads the directory and matches it once
(``email_share/recipients.py``, ADR-321 amendment).

Three decisions, each measured or documented:

- **Pages of the provider's own size, not the global item ceiling.**
  ``API_MAX_ITEMS_PER_REQUEST`` bounds what an AGENT receives (25); applied to
  an internal read it would take forty requests for a thousand contacts — the
  ``RAG_DRIVE_CHANGES_PAGE_SIZE`` precedent. Google documents up to 1 000 per
  page and requires every other parameter to stay the same across pages, so
  the page size is fixed for the whole read; Microsoft documents no maximum for
  contacts, so a modest page follows ``@odata.nextLink``.
- **Bounded, and the bound is stated**: ``max_contacts`` is the caller's
  published cap and ``truncated`` says when the book was longer. Google is read
  most recently modified first, so a cut keeps the contacts in use.
- **Cached like the contact list** (same TTL, family ``contacts_directory``),
  keyed by provider and cap, and dropped by ``ContactsCache.invalidate_user``,
  which every contact write of the three clients calls. A cold read is done ONCE across workers
  (``run_shared_flight``): a person typing fast sends a request per pause, and
  two of them landing on two workers must not read the provider twice.
- **Compact, and stamped.** A People person carries metadata on every field:
  measured, 5 000 of them are 3.3 MB of JSON and 19 ms of ``json.loads`` on
  the event loop. Only names, addresses and numbers are kept, and a small
  stamp (version, cut) is written beside the book, so a reader that already
  derived what it needs from a version asks the stamp, never the book.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import structlog

from src.core.constants import CONTACTS_DIRECTORY_SHARED_WAIT_SECONDS
from src.infrastructure.cache import ContactsCache
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX, run_shared_flight

logger = structlog.get_logger(__name__)

#: What a directory entry needs: who, and how to reach them.
CONTACTS_DIRECTORY_FIELDS: tuple[str, ...] = ("names", "emailAddresses", "phoneNumbers")


@dataclass(frozen=True, slots=True)
class ContactDirectory:
    """The account's contacts, in the Google People shape every client produces.

    Attributes:
        persons: One ``person`` dict per contact (names, addresses, numbers).
        truncated: The book held more than the cap the caller asked for.
        from_cache: No provider was called for this read.
        version: Identifies this exact copy of the book — two reads with the
            same version hold the same persons, so a reader may keep what it
            derived from them. None when the copy was not cached.
    """

    persons: list[dict[str, Any]]
    truncated: bool
    from_cache: bool
    version: str | None = None


@dataclass(frozen=True, slots=True)
class DirectoryStamp:
    """What identifies a cached book without reading it.

    Attributes:
        version: The book's version (``ContactDirectory.version``).
        truncated: The book was cut at its cap.
    """

    version: str
    truncated: bool


#: Reads the provider: ``(max_contacts) -> (persons, truncated)``.
DirectoryReader = Callable[[int], Awaitable[tuple[list[dict[str, Any]], bool]]]

#: The name parts a directory keeps.
_NAME_KEYS: tuple[str, ...] = ("displayName", "givenName", "familyName")


def _kept(items: Any, keys: tuple[str, ...]) -> list[dict[str, str]]:
    """The ``keys`` of each item of a People list field, dropping the rest."""
    if not isinstance(items, list):
        return []
    kept = [
        {key: item[key] for key in keys if isinstance(item.get(key), str) and item[key]}
        for item in items
        if isinstance(item, dict)
    ]
    return [item for item in kept if item]


def compact_person(person: Any) -> dict[str, Any]:
    """A person reduced to what a directory entry reads: names, addresses, numbers.

    Args:
        person: A People-shape contact from any provider.

    Returns:
        The same person without metadata, sources, photos or etags.
    """
    if not isinstance(person, dict):
        return {}
    return {
        "names": _kept(person.get("names"), _NAME_KEYS),
        "emailAddresses": _kept(person.get("emailAddresses"), ("value",)),
        "phoneNumbers": _kept(person.get("phoneNumbers"), ("value",)),
    }


async def cached_directory(
    user_id: UUID, provider: str, max_contacts: int, read: DirectoryReader
) -> ContactDirectory:
    """The directory from the cache, or read from the provider and cached.

    A cache that cannot be reached is not a reason to answer nothing: the read
    happens uncached, exactly as it would on a miss.

    Args:
        user_id: Whose contacts.
        provider: The connector type's value — part of the key, so switching
            providers never serves the previous book.
        max_contacts: The caller's cap — part of the key too.
        read: The provider read.

    Returns:
        The directory, and whether it came from the cache.
    """
    cache: ContactsCache | None
    try:
        cache = ContactsCache(await get_redis_cache())
    except Exception as error:  # Redis down: read uncached rather than fail.
        logger.warning("contacts_directory_cache_unavailable", error_type=type(error).__name__)
        cache = None
    if cache is None:
        persons, truncated = await read(max_contacts)
        return ContactDirectory(persons=persons, truncated=truncated, from_cache=False)
    directory_cache = cache

    async def published() -> ContactDirectory | None:
        cached = await directory_cache.get_directory(user_id, provider, max_contacts)
        if cached is None:
            return None
        version = cached.get("version")
        return ContactDirectory(
            persons=list(cached.get("persons") or []),
            truncated=bool(cached.get("truncated")),
            from_cache=True,
            version=version if isinstance(version, str) else None,
        )

    async def build() -> ContactDirectory:
        raw, truncated = await read(max_contacts)
        persons = [compact_person(person) for person in raw]
        version = uuid4().hex
        await directory_cache.set_directory(
            user_id,
            provider,
            max_contacts,
            {"persons": persons, "truncated": truncated, "version": version},
        )
        return ContactDirectory(
            persons=persons, truncated=truncated, from_cache=False, version=version
        )

    # A hit takes no claim: most requests are one keystroke over a warm cache.
    hit = await published()
    if hit is not None:
        return hit
    flight = await run_shared_flight(
        f"{CLAIM_PREFIX}:contacts_directory:{user_id}:{provider}:{max_contacts}",
        build=build,
        read_shared=published,
        wait_budget_s=CONTACTS_DIRECTORY_SHARED_WAIT_SECONDS,
    )
    return flight.value


async def directory_stamp(user_id: UUID, provider: str, max_contacts: int) -> DirectoryStamp | None:
    """The stamp of the cached book, or None when there is none to trust.

    Args:
        user_id: Whose contacts.
        provider: The connector type's value.
        max_contacts: The cap the book was read under.

    Returns:
        The stamp, or None on a miss, an unreadable entry or an unreachable cache.
    """
    try:
        stamp = await ContactsCache(await get_redis_cache()).get_directory_stamp(
            user_id, provider, max_contacts
        )
    except Exception as error:
        logger.warning("contacts_directory_stamp_unavailable", error_type=type(error).__name__)
        return None
    if stamp is None or not isinstance(stamp.get("version"), str):
        return None
    return DirectoryStamp(version=stamp["version"], truncated=bool(stamp.get("truncated")))


async def invalidate_contacts_cache(user_id: UUID) -> None:
    """Drop every cached contacts read of the account after a write.

    Best-effort: a write that succeeded is not undone because the cache could
    not be reached; the TTL bounds what stays stale.

    Args:
        user_id: Whose contacts changed.
    """
    try:
        await ContactsCache(await get_redis_cache()).invalidate_user(user_id)
    except Exception as error:
        logger.warning("contacts_cache_invalidation_failed", error_type=type(error).__name__)


__all__ = [
    "CONTACTS_DIRECTORY_FIELDS",
    "ContactDirectory",
    "DirectoryReader",
    "DirectoryStamp",
    "cached_directory",
    "compact_person",
    "directory_stamp",
    "invalidate_contacts_cache",
]
