"""Gmail search, mixed into ``GoogleGmailClient`` (ADR-287, ADR-369).

A search lists ids, then reads each hit — one request per hit, at bounded
concurrency. The page carries Gmail's estimate, the next page's token and how
many hits it listed but could not read (F11): counted, never dropped in
silence, and a page missing hits is not cached, so the next read retries them.
``search_in_labels`` is Gmail's own: a label of the person's is read by its id
(``labelIds``, documented), never through a ``label:`` term Gmail is not known
to read ids in. Out of ``google_gmail_client.py``, frozen at its audited size.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    GMAIL_FORMAT_FULL,
    GMAIL_FORMAT_METADATA,
    REDIS_KEY_GMAIL_SEARCH_PREFIX,
)
from src.core.field_names import FIELD_CACHED_AT, FIELD_SKIPPED_HITS
from src.domains.connectors.clients.base_google_client import apply_max_items_limit

logger = structlog.get_logger(__name__)


class _GmailSearchHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID

    async def _mail_cache(self) -> Any: ...

    async def _mail_cache_scope(self, use_cache: bool = True) -> str | None: ...

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def get_message(
        self,
        message_id: str,
        format: str = GMAIL_FORMAT_FULL,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]: ...

    async def _search_messages(
        self,
        query: str,
        max_results: int,
        use_cache: bool,
        page_token: str | None,
        headers_only: bool,
        label_ids: Sequence[str],
    ) -> dict[str, Any]: ...


class GmailSearchMixin:
    """``users.messages.list`` searches, each hit read."""

    async def search_emails(
        self: _GmailSearchHost,
        query: str,
        max_results: int = settings.emails_tool_default_max_results,
        fields: list[str] | None = None,
        use_cache: bool = True,
        page_token: str | None = None,
        headers_only: bool = False,
    ) -> dict[str, Any]:
        """
        Search emails using Gmail search query syntax.

        Gmail query syntax: https://support.google.com/mail/answer/7190
        Examples:
        - "from:john@example.com" - Emails from John
        - "subject:meeting" - Emails with "meeting" in subject
        - "is:unread" - Unread emails
        - "has:attachment" - Emails with attachments
        - "after:2025/01/01" - Emails after Jan 1, 2025

        Args:
            query: Gmail search query (supports all Gmail search operators).
            max_results: Maximum number of results (default 10, max 500).
            fields: Field projection (default: GOOGLE_GMAIL_SEARCH_FIELDS).
            use_cache: Use Redis cache (default True).
            page_token: The ``next_page_token`` of a previous page, to continue
                the same search (ADR-287).
            headers_only: Read each hit at ``format=metadata`` (headers, no
                body, no MIME parts) instead of ``format=full``. Either way one
                request per hit: the list endpoint returns ids only.

        Returns:
            Dict with:
            - messages: List of message objects
            - resultSizeEstimate: Approximate total matches (an ESTIMATE:
              Gmail never counts exactly)
            - next_page_token: Token of the next page, or None
            - skipped_hits: Hits listed but not read (the page is partial)
            - from_cache: Boolean (True if served from cache)
            - cached_at: Cache timestamp (if from cache)

        Example:
            >>> results = await client.search_emails(
            ...     query="from:john@example.com subject:invoice",
            ...     max_results=20
            ... )
        """
        return await self._search_messages(
            query, max_results, use_cache, page_token, headers_only, label_ids=()
        )

    async def search_in_labels(
        self: _GmailSearchHost,
        label_ids: Sequence[str],
        query: str = "",
        *,
        max_results: int = settings.emails_tool_default_max_results,
        use_cache: bool = True,
        page_token: str | None = None,
        headers_only: bool = False,
    ) -> dict[str, Any]:
        """The messages carrying every label of ``label_ids``, matching ``query``.

        Args:
            label_ids: Gmail label ids, each one a hit carries.
            query: Gmail search query narrowing them further (none by default).
            max_results: Maximum number of results.
            use_cache: Use Redis cache.
            page_token: The ``next_page_token`` of a previous page.
            headers_only: Read each hit at ``format=metadata``.

        Returns:
            The page, shaped as ``search_emails`` shapes it.
        """
        return await self._search_messages(
            query, max_results, use_cache, page_token, headers_only, label_ids=label_ids
        )

    async def _search_messages(
        self: _GmailSearchHost,
        query: str,
        max_results: int,
        use_cache: bool,
        page_token: str | None,
        headers_only: bool,
        label_ids: Sequence[str],
    ) -> dict[str, Any]:
        """One page of a search, every hit read (see the module)."""
        hit_format = GMAIL_FORMAT_METADATA if headers_only else GMAIL_FORMAT_FULL
        scope = await self._mail_cache_scope(use_cache)
        cache_key = _search_cache_key(scope, query, label_ids, max_results, hit_format, page_token)
        if scope is not None:
            cached = await _cached_page(self, cache_key, query)
            if cached is not None:
                return cached

        effective_max_results = apply_max_items_limit(max_results)
        response = await self._make_request(
            "GET",
            "/users/me/messages",
            params=_list_params(query, label_ids, page_token, max_results),
        )
        message_ids = [msg["id"] for msg in response.get("messages", [])]
        fetched = await _read_hits(self, message_ids[:effective_max_results], hit_format, use_cache)
        messages = [msg for msg in fetched if msg is not None]
        result = {
            "messages": messages,
            # Gmail always states its estimate; absent, nothing is stated (ADR-185).
            "resultSizeEstimate": response.get("resultSizeEstimate"),
            "next_page_token": response.get("nextPageToken"),
            # F11: a hit listed but not read is counted, never dropped in silence.
            FIELD_SKIPPED_HITS: len(fetched) - len(messages),
        }
        # Cache a WHOLE page only: one missing hits is read again next time.
        if scope is not None and not result[FIELD_SKIPPED_HITS]:
            await _cache_page(self, cache_key, result)
        return {**result, "from_cache": False}


def _search_cache_key(
    scope: str | None,
    query: str,
    label_ids: Sequence[str],
    max_results: int,
    hit_format: str,
    page_token: str | None,
) -> str:
    """The page's identity: the words, the labels, the page and the hit format —
    page 2 is never served from page 1's entry, nor a headers-only page to a caller
    expecting bodies."""
    page_part = f":{page_token}" if page_token else ""
    asked = json.dumps([query, list(label_ids)]) if label_ids else query
    return (
        f"{REDIS_KEY_GMAIL_SEARCH_PREFIX}{scope}:"
        f"{hashlib.md5(asked.encode()).hexdigest()}:{max_results}:{hit_format}{page_part}"
    )


def _list_params(
    query: str, label_ids: Sequence[str], page_token: str | None, max_results: int
) -> dict[str, Any]:
    """``users.messages.list``'s params: only what was asked, the size under the global cap."""
    params: dict[str, Any] = {"maxResults": apply_max_items_limit(max_results)}
    if query:
        params["q"] = query
    if label_ids:
        params["labelIds"] = list(label_ids)
    if page_token:
        params["pageToken"] = page_token
    return params


async def _cached_page(host: _GmailSearchHost, cache_key: str, query: str) -> dict[str, Any] | None:
    """A page kept by an earlier search, or None."""
    redis_client = await host._mail_cache()
    cached_data_raw = await redis_client.get(cache_key)
    if not cached_data_raw:
        return None
    cached_data = json.loads(cached_data_raw)
    logger.debug("gmail_search_cache_hit", user_id=str(host.user_id), query_preview=query[:50])
    return {**cached_data, "from_cache": True, FIELD_CACHED_AT: cached_data.get(FIELD_CACHED_AT)}


async def _read_hits(
    host: _GmailSearchHost, message_ids: Sequence[str], hit_format: str, use_cache: bool
) -> list[dict[str, Any] | None]:
    """Each hit read, in the list's order; one that could not be read is None.

    The list endpoint returns ids only, so each hit costs one more round-trip
    (audit wave 3, N-194.8): fetched concurrently under a semaphore, every fetch
    still through the Redis rate limiter of ``_make_request``.
    """
    semaphore = asyncio.Semaphore(settings.emails_search_fetch_concurrency)

    async def _fetch_hit(msg_id: str) -> dict[str, Any] | None:
        async with semaphore:
            try:
                return await host.get_message(msg_id, format=hit_format, use_cache=use_cache)
            except Exception as e:
                logger.warning(
                    "gmail_search_message_fetch_failed",
                    message_id=msg_id,
                    error_type=type(e).__name__,
                )
                return None

    return list(await asyncio.gather(*(_fetch_hit(msg_id) for msg_id in message_ids)))


async def _cache_page(host: _GmailSearchHost, cache_key: str, result: dict[str, Any]) -> None:
    """Keeps a whole page for the search cache's lifetime."""
    redis_client = await host._mail_cache()
    await redis_client.set(
        cache_key,
        json.dumps({**result, FIELD_CACHED_AT: datetime.now(UTC).isoformat()}),
        ex=settings.emails_cache_search_ttl_seconds,
    )
