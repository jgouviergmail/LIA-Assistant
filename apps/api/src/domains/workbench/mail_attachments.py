"""A mail attachment downloaded by the person's own hand (ADR-369).

One download at a time per account (``downloads.one_download``). The ceiling is
HANDED to the client, which refuses a part whose listed size passes it before
reading it (``ensure_within_bound``). A Gmail handle expires between two reads
(ADR-296): the name travels with it, and the client finds the part by name when
the handle is gone.
"""

from __future__ import annotations

from uuid import UUID

from src.core.config import settings
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.downloads import one_download
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.mail import AttachmentRequest

_TOOL = WorkbenchTool.MAIL


async def download_attachment(user_id: UUID, request: AttachmentRequest) -> EmailAttachmentContent:
    """The attachment's bytes, its name and its type.

    Raises:
        BaseAPIException: ``provider_rate_limited`` while another download of
            the account runs; the provider's refusal otherwise (``too_large``
            with the ceiling, ``item_gone``, ``stale_handle``…).
    """
    async with one_download(user_id), open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "download", act=False):
            return await client.download_attachment(
                request.message_id,
                attachment_id=request.attachment_id,
                filename=request.filename,
                max_bytes=settings.workbench_download_max_bytes,
            )
