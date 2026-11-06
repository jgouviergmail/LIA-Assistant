"""OneDrive's changes and subscription, in the words of Drive's feed (ADR-369, lot 11).

The drain of a linked tree reads ``changes`` and a next token whichever drive it reads, so Graph's
delta answers in Drive's words. Three things differ, and stay here:

- A token lives inside a link Graph writes, in more than one form; only the value travels.
- Graph forgets a token with a 410: nothing can replay the feed, a full synchronisation catches up
  (``ChangesFeedLostError``).
- Graph holds one subscription per resource: a row purged while the connector was away leaves one
  behind, and creating a new one answers 409 until it is removed.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
from fastapi import status

from src.core.constants import (
    RAG_DRIVE_CHANGES_PAGE_SIZE_DEFAULT,
    RAG_DRIVE_CHANGES_PAGE_SIZE_MAX,
)
from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.google_drive_client import changes_feed_timeout
from src.domains.connectors.clients.normalizers.onedrive_normalizer import (
    DRIVE_ITEM_FIELDS,
    normalize_drive_item,
)
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

_DELTA: Final = "/me/drive/root/delta"
_SUBSCRIPTIONS: Final = "/subscriptions"
#: The whole drive: the one resource a work account may subscribe to.
_DRIVE_ROOT: Final = "me/drive/root"
_LATEST: Final = "latest"
_TOKEN_IN_PATH: Final = re.compile(r"token='([^']+)'")
#: What a feed entry reads, a deletion included.
_FEED_FIELDS: Final = f"{DRIVE_ITEM_FIELDS},deleted"


class ChangesFeedLostError(Exception):
    """The feed cannot be read from its token: only a full synchronisation catches up."""


def delta_token(link: str | None) -> str | None:
    """The token inside a link of Graph's delta.

    Args:
        link: ``@odata.nextLink`` or ``@odata.deltaLink``, if any.

    Returns:
        The token alone; None for no link, or a link that names none.
    """
    if not link:
        return None
    named = parse_qs(urlsplit(link).query).get("token")
    if named:
        return named[0]
    in_path = _TOKEN_IN_PATH.search(unquote(link))
    return in_path.group(1) if in_path else None


def _utc_instant(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _change_of(item: dict[str, Any]) -> dict[str, Any]:
    """A delta entry as an entry of Drive's feed."""
    file = normalize_drive_item(item)
    return {"fileId": file["id"], "removed": "deleted" in item, "file": file}


class OneDriveChangesMixin:
    """The feed and the subscription of ``MicrosoftOneDriveClient``."""

    if TYPE_CHECKING:

        async def _make_request(
            self,
            method: str,
            endpoint: str,
            params: dict[str, Any] | None = None,
            json_data: dict[str, Any] | None = None,
            max_retries: int = ...,
            extra_headers: dict[str, str] | None = None,
            *,
            content: bytes | None = None,
            base_url: str | None = None,
            idempotent: bool | None = None,
            timeout: httpx.Timeout | None = None,
            answer: Callable[[httpx.Response], dict[str, Any]] = ...,
        ) -> dict[str, Any]: ...

    async def get_changes_start_page_token(self) -> str:
        """Where the feed stands now, nothing enumerated.

        Returns:
            The token future changes are read from.

        Raises:
            ChangesFeedLostError: Graph named no token.
        """
        raw = await self._make_request("GET", _DELTA, {"token": _LATEST})
        token = delta_token(raw.get("@odata.deltaLink"))
        if token is None:
            raise ChangesFeedLostError
        return token

    async def list_changes(
        self, page_token: str, page_size: int = RAG_DRIVE_CHANGES_PAGE_SIZE_DEFAULT
    ) -> dict[str, Any]:
        """One page of the feed since ``page_token``.

        Args:
            page_token: The token kept with the channel, or the previous page's.
            page_size: Changes per page, within the feed's bound.

        Returns:
            ``changes``, then ``nextPageToken`` while more follows, else ``newStartPageToken``.

        Raises:
            ChangesFeedLostError: Graph no longer knows the token.
        """
        try:
            raw = await self._make_request(
                "GET",
                _DELTA,
                {
                    "token": page_token,
                    "$top": max(1, min(page_size, RAG_DRIVE_CHANGES_PAGE_SIZE_MAX)),
                    "$select": _FEED_FIELDS,
                },
                timeout=changes_feed_timeout(),
            )
        except ConnectorAPIError as error:
            if error.upstream_status_code == status.HTTP_410_GONE:
                raise ChangesFeedLostError from error
            raise
        page: dict[str, Any] = {"changes": [_change_of(item) for item in raw.get("value", [])]}
        following = delta_token(raw.get("@odata.nextLink"))
        if following is not None:
            page["nextPageToken"] = following
            return page
        baseline = delta_token(raw.get("@odata.deltaLink"))
        if baseline is not None:
            page["newStartPageToken"] = baseline
        return page

    async def create_subscription(
        self, address: str, client_state: str, expires_at: datetime
    ) -> dict[str, Any]:
        """Ask Graph to tell ``address`` when the drive changes.

        Args:
            address: The public endpoint; Graph calls it before it answers.
            client_state: The secret each notification carries back.
            expires_at: When it ends, within what Graph allows a drive.

        Returns:
            The subscription: its ``id`` and ``expirationDateTime``.
        """
        body = {
            "changeType": "updated",
            "notificationUrl": address,
            "resource": _DRIVE_ROOT,
            "expirationDateTime": _utc_instant(expires_at),
            "clientState": client_state,
            "latestSupportedTlsVersion": "v1_2",
        }
        try:
            return await self._make_request("POST", _SUBSCRIPTIONS, json_data=body, max_retries=1)
        except ConnectorAPIError as error:
            if error.upstream_status_code != status.HTTP_409_CONFLICT:
                raise
        await self._drop_drive_subscriptions()
        return await self._make_request("POST", _SUBSCRIPTIONS, json_data=body, max_retries=1)

    async def renew_subscription(
        self, subscription_id: str, expires_at: datetime
    ) -> dict[str, Any]:
        """Move a subscription's end.

        Args:
            subscription_id: The subscription.
            expires_at: Its new end.

        Returns:
            The subscription.
        """
        return await self._make_request(
            "PATCH",
            self._subscription_path(subscription_id),
            json_data={"expirationDateTime": _utc_instant(expires_at)},
        )

    async def delete_subscription(self, subscription_id: str) -> None:
        """End a subscription.

        Args:
            subscription_id: The subscription.
        """
        await self._make_request("DELETE", self._subscription_path(subscription_id))

    async def _drop_drive_subscriptions(self) -> None:
        """Remove what this application left on the drive; any other watch stays."""
        held = await self._make_request("GET", _SUBSCRIPTIONS)
        for subscription in held.get("value", []):
            if str(subscription.get("resource")).casefold() == _DRIVE_ROOT:
                await self.delete_subscription(str(subscription.get("id")))

    @staticmethod
    def _subscription_path(subscription_id: str) -> str:
        segment = path_segment(subscription_id, connector_type=ConnectorType.MICROSOFT_ONEDRIVE)
        return f"{_SUBSCRIPTIONS}/{segment}"


__all__ = ["ChangesFeedLostError", "OneDriveChangesMixin", "delta_token"]
