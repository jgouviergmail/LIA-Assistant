"""
Microsoft Outlook (Graph API) client for email operations.

Provides email search, read, send, reply, forward, and trash operations
via Microsoft Graph API v1.0. Implements the same interface as GoogleGmailClient
for transparent provider switching.

API Reference:
- https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview

Scopes required:
- Mail.Read, Mail.ReadWrite, Mail.Send
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    build_search_filter,
    normalize_graph_folder,
    normalize_graph_message,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)

# Default fields to request from Microsoft Graph (performance optimization)
_MESSAGE_SELECT_FIELDS = (
    "id,conversationId,subject,from,toRecipients,ccRecipients,bccRecipients,"
    "body,bodyPreview,receivedDateTime,isRead,isDraft,hasAttachments,"
    "flag,importance,webLink,parentFolderId,attachments"
)

_MESSAGE_LIST_SELECT_FIELDS = (
    "id,conversationId,subject,from,toRecipients,bodyPreview,"
    "receivedDateTime,isRead,hasAttachments,flag,importance"
)


class MicrosoftOutlookClient(BaseMicrosoftClient):
    """
    Microsoft Outlook email client via Graph API.

    Implements EmailClientProtocol (structural typing) for transparent
    provider switching with GoogleGmailClient and AppleEmailClient.

    Example:
        >>> client = MicrosoftOutlookClient(user_id, credentials, connector_service)
        >>> results = await client.search_emails("from:john subject:meeting")
        >>> for msg in results["messages"]:
        ...     print(msg["subject"])
    """

    connector_type = ConnectorType.MICROSOFT_OUTLOOK

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
    ) -> None:
        """Initialize Microsoft Outlook client."""
        super().__init__(user_id, credentials, connector_service)

    # =========================================================================
    # SEARCH & RETRIEVAL
    # =========================================================================

    async def search_emails(
        self,
        query: str,
        max_results: int = settings.emails_tool_default_max_results,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Search emails using Microsoft Graph.

        Translates Gmail-style queries to Microsoft Graph API parameters.
        Uses endpoint-based folder routing for ``label:`` / ``in:`` operators
        and KQL ``$search`` for keyword queries.

        Microsoft Graph constraints handled:
        - ``$search`` and ``$orderby`` are mutually exclusive.
        - ``$search`` and ``$filter`` cannot be combined.
        - Folder filtering uses ``/me/mailFolders/{id}/messages`` endpoint.

        Args:
            query: Gmail-style query string (translated to KQL/OData).
            max_results: Maximum results to return.
            fields: Field projection (unused, kept for interface compatibility).
            use_cache: Whether to use cache (unused, kept for interface compatibility).

        Returns:
            Dict with 'messages' list in Gmail API format.
        """
        max_results = apply_max_items_limit(max_results)

        # Translate Gmail-style query to Microsoft Graph parameters
        search_params = build_search_filter(query)

        params: dict[str, Any] = {
            "$top": max_results,
            "$select": _MESSAGE_LIST_SELECT_FIELDS,
        }

        has_search = bool(search_params.get("search"))

        if has_search:
            # $search and $orderby are mutually exclusive in Microsoft Graph
            params["$search"] = search_params["search"]
        else:
            # Only add $orderby when not using $search
            params["$orderby"] = "receivedDateTime desc"

        if search_params.get("filter"):
            # $filter and $search cannot be combined — prefer $filter for date/boolean filters
            if has_search:
                logger.warning(
                    "outlook_search_filter_conflict",
                    user_id=str(self.user_id),
                    query=query,
                    detail="$search and $filter cannot be combined; dropping $search",
                )
                del params["$search"]
                params["$orderby"] = "receivedDateTime desc"
            params["$filter"] = search_params["filter"]

        # Folder-based filtering via endpoint routing
        folder = search_params.get("folder")
        if folder:
            endpoint = f"/me/mailFolders/{folder}/messages"
        else:
            endpoint = "/me/messages"

        logger.debug(
            "outlook_search_request",
            endpoint=endpoint,
            params=dict(params),
            search_params=search_params,
            query=query,
        )

        response = await self._make_request("GET", endpoint, params)

        # Normalize to Gmail API format
        messages = [normalize_graph_message(msg) for msg in response.get("value", [])]

        logger.info(
            "outlook_search_emails",
            user_id=str(self.user_id),
            query=query,
            results_count=len(messages),
        )

        return {
            "messages": messages,
            "resultSizeEstimate": len(messages),
        }

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get a specific email message by ID.

        Args:
            message_id: Microsoft Graph message ID.
            format: Message format (unused, kept for interface compatibility).
            fields: Field projection (unused, kept for interface compatibility).
            use_cache: Whether to use cache (unused, kept for interface compatibility).

        Returns:
            Dict in Gmail API message format.
        """
        params: dict[str, Any] = {
            "$select": _MESSAGE_SELECT_FIELDS,
            "$expand": "attachments($select=id,name,contentType,size)",
        }

        response = await self._make_request("GET", f"/me/messages/{message_id}", params)

        logger.info(
            "outlook_get_message",
            user_id=str(self.user_id),
            message_id=message_id,
        )

        return normalize_graph_message(response)

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """
        Send a new email via Microsoft Graph.

        Args:
            to: Comma-separated recipient email addresses.
            subject: Email subject.
            body: Email body content.
            cc: Comma-separated CC addresses (optional).
            bcc: Comma-separated BCC addresses (optional).
            is_html: Whether body is HTML (default: False).

        Returns:
            Dict with send confirmation.
        """
        message_body: dict[str, Any] = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "html" if is_html else "text",
                    "content": body,
                },
                "toRecipients": _build_recipients(to),
            }
        }

        if cc:
            message_body["message"]["ccRecipients"] = _build_recipients(cc)
        if bcc:
            message_body["message"]["bccRecipients"] = _build_recipients(bcc)

        await self._make_request("POST", "/me/sendMail", json_data=message_body)

        logger.info(
            "outlook_email_sent",
            user_id=str(self.user_id),
            to=to,
            subject=subject,
        )

        return {"id": "", "labelIds": ["SENT"], "threadId": ""}

    async def reply_email(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """
        Reply to an email.

        Args:
            message_id: Message ID to reply to.
            body: Reply body content.
            reply_all: Whether to reply to all recipients.
            is_html: Whether body is HTML.

        Returns:
            Dict with reply confirmation.
        """
        action = "replyAll" if reply_all else "reply"
        reply_body: dict[str, Any] = {
            "comment": body,
        }

        await self._make_request(
            "POST", f"/me/messages/{message_id}/{action}", json_data=reply_body
        )

        logger.info(
            "outlook_email_replied",
            user_id=str(self.user_id),
            message_id=message_id,
            reply_all=reply_all,
        )

        return {"id": message_id, "threadId": ""}

    async def forward_email(
        self,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
        include_attachments: bool = True,
    ) -> dict[str, Any]:
        """
        Forward an email.

        Args:
            message_id: Message ID to forward.
            to: Recipient email addresses.
            body: Optional body text to prepend.
            cc: Optional CC addresses.
            is_html: Whether body is HTML.
            include_attachments: Attachments are included automatically by Graph API.

        Returns:
            Dict with forward confirmation.
        """
        forward_body: dict[str, Any] = {
            "toRecipients": _build_recipients(to),
        }

        if body:
            forward_body["comment"] = body

        await self._make_request(
            "POST", f"/me/messages/{message_id}/forward", json_data=forward_body
        )

        logger.info(
            "outlook_email_forwarded",
            user_id=str(self.user_id),
            message_id=message_id,
            to=to,
        )

        return {"id": message_id, "threadId": ""}

    async def trash_email(self, message_id: str) -> dict[str, Any]:
        """
        Move an email to the Deleted Items folder.

        Args:
            message_id: Message ID to trash.

        Returns:
            Dict with trash confirmation.
        """
        move_body: dict[str, Any] = {"destinationId": "deleteditems"}

        await self._make_request("POST", f"/me/messages/{message_id}/move", json_data=move_body)

        logger.info(
            "outlook_email_trashed",
            user_id=str(self.user_id),
            message_id=message_id,
        )

        return {"id": message_id, "labelIds": ["TRASH"], "threadId": ""}

    # =========================================================================
    # LABELS (FOLDERS)
    # =========================================================================

    async def list_labels(self, use_cache: bool = True) -> dict[str, str]:
        """
        List all mail folders (equivalent to Gmail labels).

        Args:
            use_cache: Whether to use cache (unused, kept for interface compatibility).

        Returns:
            Dict mapping folder ID to display name.
        """
        response = await self._make_request("GET", "/me/mailFolders", {"$top": 100})

        labels: dict[str, str] = {}
        for folder in response.get("value", []):
            normalized = normalize_graph_folder(folder)
            labels[normalized["id"]] = normalized["name"]

        logger.info(
            "outlook_labels_listed",
            user_id=str(self.user_id),
            count=len(labels),
        )

        return labels

    async def resolve_label_names_in_query(self, query: str, use_cache: bool = True) -> str:
        """
        Resolve label/folder names in query string.

        Microsoft Graph handles folder resolution differently from Gmail.
        This method is kept for interface compatibility but performs
        minimal transformation.

        Args:
            query: Query string potentially containing label: operators.
            use_cache: Whether to use cache.

        Returns:
            Query string with resolved label references.
        """
        # Microsoft Graph uses $filter on parentFolderId,
        # which is handled in build_search_filter()
        return query


def _build_recipients(addresses_str: str) -> list[dict[str, Any]]:
    """
    Build Microsoft Graph recipients list from comma-separated addresses.

    Args:
        addresses_str: Comma-separated email addresses.

    Returns:
        List of recipient dicts for Graph API.
    """
    recipients: list[dict[str, Any]] = []
    for addr in addresses_str.split(","):
        addr = addr.strip()
        if not addr:
            continue
        # Handle "Name <email>" format
        if "<" in addr and ">" in addr:
            name = addr[: addr.index("<")].strip().strip('"')
            email = addr[addr.index("<") + 1 : addr.index(">")].strip()
        else:
            name = ""
            email = addr
        recipients.append({"emailAddress": {"address": email, "name": name}})
    return recipients
