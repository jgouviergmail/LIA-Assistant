"""A Gmail mailbox's cache identity and generation, kept at the request door (ADR-369).

Out of ``google_gmail_client.py`` (frozen at its audited size): every cached read
of a mailbox lives under the mailbox's GENERATION (``infrastructure.cache.mail_generation``),
and every write through the client's one request door moves it, whatever came
of the write. First in the client's MRO, so its ``_make_request`` wraps the base
door every mixin reaches.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

import httpx

from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.clients.retry_policy import CONNECTOR_REQUEST_ATTEMPTS
from src.infrastructure.cache.mail_generation import bump_mail_generation, mail_generation

#: The mailbox paths whose writes change what a cached read answers (ADR-369) —
#: a label's deletion or rename changes messages' labelIds and every ``label:`` search.
_MAILBOX_PATHS = (
    "/users/me/messages",
    "/users/me/drafts",
    "/users/me/threads",
    "/users/me/labels",
)


class GmailCacheGenerationMixin(BaseGoogleClient):
    """The mailbox's cache namespace, and the door that ages it on every write."""

    async def _mail_cache(self) -> Any:
        """The cache client the mailbox's own caches live in — the generation lives beside them.

        The client answers with its module's cache accessor, so whatever replaces
        its caches (a test double, a pool) carries the generation too.
        """
        raise NotImplementedError

    @property
    def _cache_account(self) -> str:
        """A verified grant or legacy connection generation identifies the mailbox."""
        binding = self.credentials.account_binding
        return f"{self.user_id}:grant:{binding}" if binding else str(self.user_id)

    async def _mail_cache_scope(self, use_cache: bool = True) -> str | None:
        """This mailbox's cache namespace at its generation; None bypasses the cache (ADR-369)."""
        if not use_cache:
            return None
        try:
            generation = await mail_generation(await self._mail_cache(), self._cache_account)
        except Exception:  # no cache client: read through the provider
            return None
        return None if generation is None else f"{self._cache_account}:g{generation}"

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = CONNECTOR_REQUEST_ATTEMPTS,
        extra_headers: dict[str, str] | None = None,
        *,
        content: bytes | None = None,
        base_url: str | None = None,
        idempotent: bool | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> dict[str, Any]:
        """Every write to the mailbox moves its cache generation, whatever came of it."""
        try:
            return await super()._make_request(
                method,
                endpoint,
                params=params,
                json_data=json_data,
                max_retries=max_retries,
                extra_headers=extra_headers,
                content=content,
                base_url=base_url,
                idempotent=idempotent,
                timeout=timeout,
            )
        finally:
            if method.upper() != "GET" and endpoint.startswith(_MAILBOX_PATHS):
                # No cache client means nothing cached to forget: the write stands.
                with suppress(Exception):
                    await bump_mail_generation(await self._mail_cache(), self._cache_account)


__all__ = ["GmailCacheGenerationMixin"]
