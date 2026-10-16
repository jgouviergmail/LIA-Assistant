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

import base64
from collections import deque
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    MICROSOFT_MAIL_FOLDERS_PAGE_SIZE,
    OUTLOOK_INLINE_ATTACHMENT_MAX_BYTES,
)
from src.core.field_names import FIELD_CACHED_AT, FIELD_SET_ASIDE_ON_PAGE
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentContent,
    EmailAttachmentNotFoundError,
    attachment_mime,
    ensure_within_bound,
    select_attachment,
)
from src.domains.connectors.clients.mail_folders import (
    EXCLUDES_ITS_FOLDER,
    MailFolder,
    find_mail_folder,
)
from src.domains.connectors.clients.normalizers.graph_mail_query import (
    GraphMailQuery,
    graph_mail_query,
)
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    build_graph_recipients,
    normalize_graph_folder,
    normalize_graph_message,
)
from src.domains.connectors.clients.outlook_drafts_mixin import OutlookDraftsMixin
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.email.outgoing import OutgoingAttachment

logger = structlog.get_logger(__name__)

# Default fields to request from Microsoft Graph (performance optimization)
_MESSAGE_SELECT_FIELDS = (
    "id,conversationId,subject,from,toRecipients,ccRecipients,bccRecipients,replyTo,"
    "body,bodyPreview,receivedDateTime,isRead,isDraft,hasAttachments,"
    "flag,importance,webLink,parentFolderId,attachments"
)

_MESSAGE_LIST_SELECT_FIELDS = (
    "id,conversationId,subject,from,toRecipients,ccRecipients,bodyPreview,"
    "receivedDateTime,isRead,hasAttachments,flag,importance"
)

# What a folder walk reads of each folder: its id, its name, whether it has children.
_FOLDER_WALK_FIELDS = "id,displayName,childFolderCount"


class MicrosoftOutlookClient(OutlookDraftsMixin, BaseMicrosoftClient):
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
    # A file rides INSIDE the send request (an upload session is not built).
    OUTGOING_FILE_MAX_BYTES = OUTLOOK_INLINE_ATTACHMENT_MAX_BYTES
    # The Graph listing selects bodyPreview, never body nor attachments.
    SEARCH_HITS_ARE_WHOLE = False

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

    def _is_graph_continuation(self, url: str) -> bool:
        """Whether ``url`` is a continuation of THIS API: same scheme, same host,
        under the API's own path — decided on the parsed url, never on a string
        prefix (a prefix check is only as safe as the path the base happens to
        carry). The request that follows carries the person's bearer token.
        """
        base = urlsplit(self.api_base_url)
        try:
            candidate = urlsplit(url)
        except ValueError:
            return False
        return (
            candidate.scheme == base.scheme
            and candidate.netloc == base.netloc
            and candidate.path.startswith(base.path.rstrip("/") + "/")
        )

    async def search_emails(
        self,
        query: str,
        max_results: int = settings.emails_tool_default_max_results,
        fields: list[str] | None = None,
        use_cache: bool = True,
        page_token: str | None = None,
        headers_only: bool = False,
    ) -> dict[str, Any]:
        """
        Search emails using Microsoft Graph.

        Translates the Gmail-style query into ONE request Graph accepts
        (``graph_mail_query``, RC3.1): a ``$search`` when words or people name
        the mail — the dates and the read state KQL cannot carry are then
        checked on the page —, otherwise a ``$filter`` led by the reception
        date. Folders are routed by endpoint (``/me/mailFolders/{id}/messages``):
        a well-known one by its Graph id, a folder of the person's own found
        among the mailbox's folders (``mail_folders``), never the inbox in its
        place.

        Args:
            query: Gmail-style query string (translated to KQL/OData). A
                continuation re-reads its conditions from it, as Gmail re-reads
                its ``q``.
            max_results: Maximum results to return.
            fields: Field projection (unused, kept for interface compatibility).
            use_cache: Whether to use cache (unused, kept for interface compatibility).
            page_token: The ``next_page_token`` of a previous page — Graph's
                ``@odata.nextLink`` url, followed as is (ADR-287). It is
                accepted ONLY on the Graph host: the request carries the
                person's bearer token, and a model can hand back any string.
            headers_only: Accepted for provider parity; the Graph listing already
                selects ``bodyPreview`` and never ``body``.

        Returns:
            Dict with the normalised ``messages`` list, ``resultSizeEstimate``
            (Graph's ``@odata.count`` when the response carries one, else
            ``None`` — never the page size, ADR-185), ``next_page_token``, and
            ``set_aside_on_page`` when a page check set messages aside.

        Raises:
            ValueError: A ``page_token`` that does not point at the Graph host,
                a date operator whose value is not a date, or a query that
                excludes the folder it reads.
            MailFolderLookupError: A folder the query names that no folder, or
                several, of the mailbox answer to.
        """
        translated = graph_mail_query(query)
        if translated.excludes_its_folder:
            raise ValueError(EXCLUDES_ITS_FOLDER)
        if page_token:
            if not self._is_graph_continuation(page_token):
                raise ValueError("page_token must be a Graph continuation url")
            response = await self._make_request_full_url("GET", page_token)
            return self._search_page(response, query, translated)

        params: dict[str, Any] = {
            "$top": apply_max_items_limit(max_results),
            "$select": _MESSAGE_LIST_SELECT_FIELDS,
            **translated.params,
        }
        folder = (
            translated.folder
            if translated.folder_name is None
            else await self._folder_id(translated.folder_name)
        )
        endpoint = f"/me/mailFolders/{folder}/messages"
        logger.debug("outlook_search_request", endpoint=endpoint, params=params)

        response = await self._make_request("GET", endpoint, params)
        return self._search_page(response, query, translated)

    async def _folder_id(self, name: str) -> str:
        """The Graph id of the folder of the person's own a query names.

        Raises:
            MailFolderLookupError: No folder, or several, answer to ``name``.
        """
        folders, complete = await self._mail_folders()
        return find_mail_folder(folders, name, complete=complete).folder_id

    async def _mail_folders(self) -> tuple[list[MailFolder], bool]:
        """The mailbox's folders, their paths built level by level, and whether all were read.

        Graph lists one level at a time (``childFolders``) in pages of its own
        size; the walk stops at ``outlook_mail_folders_walk_max`` folders — an
        internal read, never the agent-facing item ceiling.
        """
        budget = settings.outlook_mail_folders_walk_max
        folders: list[MailFolder] = []
        pending: deque[tuple[str, str]] = deque([("/me/mailFolders", "")])
        next_link: str | None = None
        while pending and len(folders) < budget:
            endpoint, parent = pending.popleft()
            response = await self._make_request(
                "GET",
                endpoint,
                {"$top": MICROSOFT_MAIL_FOLDERS_PAGE_SIZE, "$select": _FOLDER_WALK_FIELDS},
            )
            while True:
                for raw in response.get("value", []):
                    name = str(raw.get("displayName") or "")
                    path = f"{parent}/{name}" if parent else name
                    folders.append(MailFolder(str(raw.get("id") or ""), path, name))
                    if raw.get("childFolderCount"):
                        pending.append((f"/me/mailFolders/{raw.get('id')}/childFolders", path))
                next_link = response.get("@odata.nextLink")
                if not next_link or len(folders) >= budget:
                    break
                response = await self._make_request_full_url("GET", next_link)
        complete = not pending and not next_link and len(folders) <= budget
        return folders[:budget], complete

    def _search_page(
        self, response: dict[str, Any], query: str, translated: GraphMailQuery
    ) -> dict[str, Any]:
        """Shape one page of a Graph listing — first page and continuations alike."""
        kept, set_aside = translated.screen(response.get("value", []))
        messages = [normalize_graph_message(msg) for msg in kept]

        logger.info(
            "outlook_search_emails",
            user_id=str(self.user_id),
            query_length=len(query) if query else 0,
            results_count=len(messages),
            set_aside_on_page=set_aside,
        )

        # Graph reads are always live: the freshness metadata is stated
        # explicitly so every email provider answers the same contract
        # (see GoogleGmailClient / AppleEmailClient).
        # ADR-185: a count is exact or does not exist. Graph states a total only
        # when asked (``@odata.count``); the page size is neither an estimate nor
        # a total, so it is never published as one.
        page: dict[str, Any] = {
            "messages": messages,
            "resultSizeEstimate": response.get("@odata.count"),
            "next_page_token": response.get("@odata.nextLink"),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }
        if set_aside:
            # A thin page is not the whole answer: say so (RC3.1).
            page[FIELD_SET_ASIDE_ON_PAGE] = set_aside
        return page

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

        return {
            **normalize_graph_message(response),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }

    async def download_attachment(
        self,
        message_id: str,
        *,
        attachment_id: str | None = None,
        filename: str | None = None,
        max_bytes: int | None = None,
    ) -> EmailAttachmentContent:
        """Download ONE attachment of a message, by handle or by name.

        Graph lists the attachments of a message (id, name, type, size) and
        serves one ``fileAttachment`` with its ``contentBytes`` (base64) — never
        one the listing already says exceeds ``max_bytes``.

        Args:
            message_id: Graph message id.
            attachment_id: Graph attachment id; wins when given.
            filename: The name as sent, when the id is unknown.
            max_bytes: Refuse, before downloading, a part listed larger.

        Returns:
            The file name, the MIME type as sent and the bytes.

        Raises:
            EmailAttachmentNotFoundError: No attachment matches, or the
                selected one carries no bytes (an item or reference attachment).
            EmailAttachmentAmbiguousError: The name matches several parts.
            EmailAttachmentTooLargeError: The listed size exceeds the bound.
        """
        listing = await self._make_request(
            "GET",
            f"/me/messages/{message_id}/attachments",
            {"$select": "id,name,contentType,size"},
        )
        listed = [
            {
                "attachmentId": item.get("id", ""),
                "filename": item.get("name", ""),
                "mimeType": item.get("contentType", ""),
                "size": item.get("size", 0),
            }
            for item in listing.get("value", [])
        ]
        chosen = select_attachment(listed, attachment_id=attachment_id, filename=filename)
        ensure_within_bound(chosen, max_bytes=max_bytes)
        part = await self._make_request(
            "GET", f"/me/messages/{message_id}/attachments/{chosen['attachmentId']}"
        )
        encoded = part.get("contentBytes")
        if not encoded:
            raise EmailAttachmentNotFoundError(
                f"attachment {chosen['attachmentId']!r} carries no bytes"
            )
        return EmailAttachmentContent(
            filename=str(part.get("name") or chosen.get("filename") or ""),
            mime_type=str(part.get("contentType") or attachment_mime(chosen)),
            data=base64.b64decode(encoded),
        )

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
        attachments: Sequence[OutgoingAttachment] = (),
        *,
        single_attempt: bool = True,
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
            attachments: Files to attach, each carried in the request as a
                ``fileAttachment`` (ADR-321) — ``OUTGOING_FILE_MAX_BYTES`` each.

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
                "toRecipients": build_graph_recipients(to),
            }
        }

        if cc:
            message_body["message"]["ccRecipients"] = build_graph_recipients(cc)
        if bcc:
            message_body["message"]["bccRecipients"] = build_graph_recipients(bcc)
        if attachments:
            message_body["message"]["attachments"] = [
                _file_attachment(attachment) for attachment in attachments
            ]

        await self._make_request(
            "POST",
            "/me/sendMail",
            json_data=message_body,
            max_retries=1,
        )

        # Counts only at INFO: recipients and subject are the person's content.
        logger.info(
            "outlook_email_sent",
            user_id=str(self.user_id),
            recipients=len(message_body["message"]["toRecipients"]),
        )

        return {"id": "", "labelIds": ["SENT"], "threadId": ""}

    async def get_own_address(self) -> str | None:
        """The connected mailbox's address, from Graph ``/me`` (ADR-314).

        ``mail`` is the mailbox's primary address; a personal account leaves it
        null and signs in with its address as ``userPrincipalName``. A principal
        name that is not an address (a work tenant's internal id) vouches for no
        mailbox.
        """
        me = await self._make_request("GET", "/me", params={"$select": "mail,userPrincipalName"})
        for candidate in (me.get("mail"), me.get("userPrincipalName")):
            if isinstance(candidate, str) and "@" in candidate:
                return candidate
        return None

    async def reply_email(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
        to: str | None = None,
    ) -> dict[str, Any]:
        """
        Reply to an email.

        Args:
            message_id: Message ID to reply to.
            body: Reply body content.
            reply_all: Whether to reply to all recipients.
            is_html: Whether body is HTML.
            to: Override recipient address. If None, replies to original sender.

        Returns:
            Dict with reply confirmation.
        """
        action = "replyAll" if reply_all else "reply"
        reply_body: dict[str, Any] = {
            "comment": body,
        }

        # Override recipient if user specified a different one (draft modification)
        if to:
            reply_body["message"] = {
                "toRecipients": build_graph_recipients(to),
            }

        await self._make_request(
            "POST", f"/me/messages/{message_id}/{action}", json_data=reply_body, max_retries=1
        )

        logger.info(
            "outlook_email_replied",
            user_id=str(self.user_id),
            message_id=message_id,
            reply_all=reply_all,
            # Whether, never who: the address is the person's (ADR-317).
            to_override=bool(to),
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
            "toRecipients": build_graph_recipients(to),
        }

        if body:
            forward_body["comment"] = body

        if cc:
            forward_body["ccRecipients"] = build_graph_recipients(cc)

        await self._make_request(
            "POST", f"/me/messages/{message_id}/forward", json_data=forward_body, max_retries=1
        )

        logger.info(
            "outlook_email_forwarded",
            user_id=str(self.user_id),
            message_id=message_id,
            # A count, never the addresses: they are the person's (ADR-317).
            recipients=len(forward_body["toRecipients"]),
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
        # Graph routes a folder by endpoint (``graph_mail_query``), never by
        # a ``$filter`` on parentFolderId, which it does not support.
        return query


def _file_attachment(attachment: OutgoingAttachment) -> dict[str, str]:
    """One file as Graph carries it inside a message (ADR-321).

    Args:
        attachment: The file.

    Returns:
        The ``fileAttachment`` resource, its bytes in base64.
    """
    content_type = attachment.mime_type
    if attachment.charset:
        content_type = f"{content_type}; charset={attachment.charset}"
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": attachment.filename,
        "contentType": content_type,
        "contentBytes": base64.b64encode(attachment.data).decode("ascii"),
    }
