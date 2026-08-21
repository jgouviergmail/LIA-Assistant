"""Gmail Settings client (lot I, 2026-08).

Dedicated client for the ``gmail.settings.basic`` surface (vacation
responder, filters, sendAs). Lives apart from GoogleGmailClient because that
file is size-frozen; both ride the same GOOGLE_GMAIL connector token.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class GoogleGmailSettingsClient(BaseGoogleClient):
    """Vacation responder, filters and sendAs settings of the user's mailbox."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    api_base_url = "https://gmail.googleapis.com/gmail/v1"

    async def get_vacation(self) -> dict[str, Any]:
        """Current vacation responder settings."""
        return await self._make_request("GET", "/users/me/settings/vacation")

    async def update_vacation(
        self,
        enable: bool,
        subject: str | None = None,
        body: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> dict[str, Any]:
        """Update the vacation responder (write — always behind HITL).

        Args:
            enable: Turn the auto-reply on or off.
            subject: Auto-reply subject (when enabling).
            body: Auto-reply plain-text body (when enabling).
            start_time_ms: Optional activation start (epoch milliseconds).
            end_time_ms: Optional activation end (epoch milliseconds, exclusive).

        Returns:
            The updated vacation settings as returned by Gmail.
        """
        payload: dict[str, Any] = {"enableAutoReply": enable}
        if enable:
            if subject is not None:
                payload["responseSubject"] = subject
            if body is not None:
                payload["responseBodyPlainText"] = body
            if start_time_ms is not None:
                payload["startTime"] = start_time_ms
            if end_time_ms is not None:
                payload["endTime"] = end_time_ms
        response = await self._make_request("PUT", "/users/me/settings/vacation", json_data=payload)
        logger.info(
            "gmail_vacation_updated",
            user_id=str(self.user_id),
            enabled=enable,
        )
        return response

    async def list_filters(self) -> dict[str, Any]:
        """The user's Gmail filters ({"filter": [...]})."""
        return await self._make_request("GET", "/users/me/settings/filters")

    async def create_filter(
        self, criteria: dict[str, Any], action: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a Gmail filter (write — always behind HITL).

        Args:
            criteria: Gmail filter criteria (from, to, subject, query, ...).
            action: Gmail filter action (addLabelIds, removeLabelIds, ...).

        Returns:
            The created filter resource (with its id).
        """
        response = await self._make_request(
            "POST",
            "/users/me/settings/filters",
            json_data={"criteria": criteria, "action": action},
        )
        logger.info("gmail_filter_created", user_id=str(self.user_id))
        return response

    async def list_send_as(self) -> dict[str, Any]:
        """The user's sendAs aliases ({"sendAs": [...]})."""
        return await self._make_request("GET", "/users/me/settings/sendAs")

    async def watch_mailbox(self, topic_name: str) -> dict[str, Any]:
        """Subscribe the mailbox to Pub/Sub push (lot H phase 2).

        Lives here (not in the size-frozen GoogleGmailClient) with the other
        mailbox-configuration calls. INBOX only — the delta consumer
        (heartbeat gmail_delta) reads INBOX message adds.

        Args:
            topic_name: Full Pub/Sub topic (projects/{project}/topics/{topic}).

        Returns:
            {"historyId": str, "expiration": str} — the watch baseline.
        """
        return await self._make_request(
            "POST",
            "/users/me/watch",
            json_data={"topicName": topic_name, "labelIds": ["INBOX"]},
        )

    async def stop_mailbox_watch(self) -> dict[str, Any]:
        """Stop the mailbox Pub/Sub subscription."""
        return await self._make_request("POST", "/users/me/stop")
