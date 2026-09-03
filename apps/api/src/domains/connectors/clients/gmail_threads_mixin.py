"""Gmail thread listing and reading, mixed into ``GoogleGmailClient`` (ADR-262).

The Gmail client had no thread endpoint at all (measured 2026-09-03: no call
to ``/threads`` anywhere) and is frozen at its audited size, so the two calls
the mail RAG source needs live here. Nothing is cached: a thread read here
becomes a document on disk, never a prompt, and a cached copy would only
double the personal content.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.core.constants import GMAIL_FORMAT_FULL
from src.domains.connectors.clients.base_google_client import apply_max_items_limit


class _JsonRequester(Protocol):
    """What the mixin needs from its host: the OAuth client's request seam."""

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class GmailThreadsMixin:
    """``users.threads`` reads for a client exposing ``_make_request``."""

    async def get_thread(
        self: _JsonRequester, thread_id: str, *, format: str = GMAIL_FORMAT_FULL
    ) -> dict[str, Any]:
        """Read one thread with every message in the requested format.

        Args:
            thread_id: Gmail thread id.
            format: ``full`` (headers + bodies, the default the renderer needs),
                ``metadata`` or ``minimal``.

        Returns:
            The thread resource: ``id``, ``historyId``, ``messages`` (each a
            message resource with ``labelIds``, ``internalDate``, ``payload``).
        """
        return await self._make_request(
            "GET", f"/users/me/threads/{thread_id}", params={"format": format}
        )

    async def list_threads(
        self: _JsonRequester,
        *,
        label_ids: list[str],
        max_results: int,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List the threads carrying EVERY label in ``label_ids``.

        Args:
            label_ids: Labels a thread must carry (``labelIds`` is an AND).
            max_results: Page size, hard-capped by ``apply_max_items_limit``.
            page_token: Continuation token from a previous page.

        Returns:
            ``threads`` (``id``, ``historyId``, ``snippet``), ``nextPageToken``
            when there is more, ``resultSizeEstimate``.
        """
        params: dict[str, Any] = {
            "labelIds": list(label_ids),
            "maxResults": apply_max_items_limit(max_results),
        }
        if page_token:
            params["pageToken"] = page_token
        return await self._make_request("GET", "/users/me/threads", params=params)
