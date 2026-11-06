"""A mail attachment downloaded or read by the person's own hand (ADR-369).

One transfer at a time per account (``downloads.one_transfer``). The ceiling is
HANDED to the client, which refuses a part whose listed size passes it before
reading it (``ensure_within_bound``). A Gmail handle expires between two reads
(ADR-296): the name travels with it, and the client finds the part by name when
the handle is gone. A part is read as a drive's file is (``previews``), under the
same ceiling: all three mailboxes hand it over through the same call.
"""

from __future__ import annotations

from uuid import UUID

from src.core.config import settings
from src.domains.attachments.preview import DocumentPreview
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.downloads import one_preview, one_transfer
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.previews import shown_document
from src.domains.workbench.schemas.mail import AttachmentRequest

_TOOL = WorkbenchTool.MAIL


async def download_attachment(user_id: UUID, request: AttachmentRequest) -> EmailAttachmentContent:
    """The attachment's bytes, its name and its type.

    Raises:
        BaseAPIException: ``provider_rate_limited`` while another download of
            the account runs; the provider's refusal otherwise (``too_large``
            with the ceiling, ``item_gone``, ``stale_handle``…).
    """
    async with one_transfer(user_id), open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "download", act=False):
            return await client.download_attachment(
                request.message_id,
                attachment_id=request.attachment_id,
                filename=request.filename,
                max_bytes=settings.workbench_download_max_bytes,
            )


async def preview_attachment(user_id: UUID, request: AttachmentRequest) -> DocumentPreview:
    """What can be read of an attachment, without saving it.

    Raises:
        BaseAPIException: ``provider_rate_limited`` when another transfer of the account outlasts
            the wait; ``too_large`` past the bound; ``not_supported_by_provider`` when nothing can
            be shown of it; the provider's refusal otherwise.
    """
    async with one_preview(user_id), open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "preview", act=False):
            content = await client.download_attachment(
                request.message_id,
                attachment_id=request.attachment_id,
                filename=request.filename,
                max_bytes=settings.workbench_download_max_bytes,
            )
    return await shown_document(
        content.data, content.mime_type, content.filename or request.filename or ""
    )
