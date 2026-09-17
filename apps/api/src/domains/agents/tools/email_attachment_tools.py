"""``get_email_attachment`` — the assistant reads what was attached to a message.

``get_emails`` lists the attachments of a message and stops there. This tool
downloads ONE of them through the account's own mail client (Gmail, Microsoft
Graph or IMAP: one ``download_attachment``, one shape) and serves its reading
(``agents/emails/attachment_content.py``):

- a document's text, extracted through the knowledge spaces' own pipeline and
  served in PARTS under the e-mail body budget (``emails_body_part_tokens``,
  ADR-287) — a 40-page contract is read part by part, never dumped;
- an image, or a PDF without a text layer, read by the vision slot under a
  page bound — the turn's spend, refused as a refusal when cut (ADR-275),
  stepped aside under a ceiling (``skipped_quota``, ADR-272).

What an attachment holds is what a stranger sent: the text is wrapped as
external content before it reaches the model, on both execution paths.
The size bound is published in the catalogue and stated in the refusal.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    tool_user_id_str,
)
from src.domains.agents.emails.attachment_content import (
    AttachmentReading,
    Route,
    read_attachment,
)
from src.domains.agents.emails.detail_levels import paginate_body
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentAmbiguousError,
    EmailAttachmentContent,
    EmailAttachmentNotFoundError,
    EmailAttachmentTooLargeError,
    attachment_handle,
    attachment_mime,
)
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import ConnectorType
from src.infrastructure.observability.metrics_extractions import email_attachment_reads_total

logger = structlog.get_logger(__name__)

#: Why a reading is refused, told by name — never invented text.
_OUTCOME_CODES: dict[str, ToolErrorCode] = {
    "skipped_quota": ToolErrorCode.RATE_LIMIT_EXCEEDED,
    "truncated": ToolErrorCode.INVALID_RESPONSE_FORMAT,
    "unsupported": ToolErrorCode.INVALID_PARAM_VALUE,
    "empty": ToolErrorCode.EMPTY_RESULT,
    "failed": ToolErrorCode.EXTERNAL_API_ERROR,
}


class GetEmailAttachmentTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """Download one attachment of a message and serve its reading."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="get_email_attachment_tool", operation="read_attachment")

    async def _read(
        self,
        content: EmailAttachmentContent,
        *,
        question: str | None,
        language: str,
        user_id: str | None,
        config: Any,
    ) -> AttachmentReading:
        """The reading — one seam, so a test can hand a reading in."""
        return await read_attachment(
            content,
            question=question,
            language=language,
            user_id=user_id,
            config=config,
            max_pages=settings.email_attachment_vision_max_pages,
            max_edge=settings.email_attachment_image_max_edge,
        )

    async def execute_api_call(
        self,
        client: Any,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Download, bound, read, paginate — or say why not (never raises for a refusal)."""
        message_id = str(kwargs.get("message_id") or "")
        attachment_id = kwargs.get("attachment_id") or None
        filename = kwargs.get("filename") or None
        question = kwargs.get("question") or None
        part = max(int(kwargs.get("part") or 1), 1)
        if not message_id or not (attachment_id or filename):
            return _refusal(
                ToolErrorCode.MISSING_REQUIRED_PARAM,
                "message_id and either attachment_id or filename are required",
            )
        content = await self._download(
            client, message_id=message_id, attachment_id=attachment_id, filename=filename
        )
        if isinstance(content, dict):
            return content
        language, reader_id, config = await self._reader(user_id)
        reading = await self._read(
            content, question=question, language=language, user_id=reader_id, config=config
        )
        email_attachment_reads_total.labels(
            route=reading.route.value, outcome=reading.outcome
        ).inc()
        if reading.outcome != "ok":
            return _refusal(
                _OUTCOME_CODES[reading.outcome],
                f"{content.filename!r} ({reading.mime_type}) could not be read: {reading.outcome}",
            )

        text, parts = paginate_body(
            reading.text, part=part, part_tokens=settings.emails_body_part_tokens
        )
        return {
            "message_id": message_id,
            "filename": content.filename,
            "mime_type": reading.mime_type,
            "size": len(content.data),
            "route": reading.route.value,
            "outcome": reading.outcome,
            "pages_read": reading.pages_read,
            "pages_total": reading.pages_total,
            "part": min(part, parts),
            "parts": parts,
            "text": wrap_external_content(
                text, source_url=content.filename, source_type="email_attachment"
            ),
        }

    async def _download(
        self,
        client: Any,
        *,
        message_id: str,
        attachment_id: str | None,
        filename: str | None,
    ) -> EmailAttachmentContent | dict[str, Any]:
        """The bytes, bounded — or the refusal naming why (stale handle, unknown, too large).

        The bound travels to the client so a part the listing already says is
        too large is never downloaded; the check on the bytes stays the net
        for a listing that knew no size.
        """
        max_bytes = settings.email_attachment_max_mb * 1024 * 1024
        try:
            content: EmailAttachmentContent = await client.download_attachment(
                message_id, attachment_id=attachment_id, filename=filename, max_bytes=max_bytes
            )
        except EmailAttachmentAmbiguousError as exc:
            return _ambiguity_refusal(exc)
        except EmailAttachmentNotFoundError as exc:
            return _refusal(ToolErrorCode.NOT_FOUND, str(exc))
        except EmailAttachmentTooLargeError as exc:
            return _too_large(filename or attachment_id or message_id, exc.size)
        if len(content.data) > max_bytes:
            return _too_large(content.filename, len(content.data))
        return content

    async def _reader(self, user_id: UUID) -> tuple[str, str, Any]:
        """The language, the account and the turn config the reading runs under."""
        runtime = self.runtime
        if runtime is None:
            return settings.default_language, str(user_id), None
        _, language, _ = await get_user_preferences(runtime)
        return language, tool_user_id_str(runtime), getattr(runtime, "config", None)

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """One structured block — no registry item: the wrapper marks it external."""
        if "error_code" in result:
            return UnifiedToolOutput.failure(
                message=str(result["message"]), error_code=str(result["error_code"])
            )
        route = "vision" if result["route"] == Route.VISION.value else "text"
        summary = (
            f"[attachment] {result['filename']} ({result['mime_type']}, {route}), "
            f"part {result['part']}/{result['parts']}"
        )
        return UnifiedToolOutput.data_success(message=summary, structured_data=result)


def _refusal(code: ToolErrorCode, message: str) -> dict[str, Any]:
    return {"error_code": code.value, "message": message}


def _too_large(name: str, size: int) -> dict[str, Any]:
    """Refuse by the bound, counted — before or after the bytes moved."""
    email_attachment_reads_total.labels(route="none", outcome="too_large").inc()
    return _refusal(
        ToolErrorCode.CONSTRAINT_VIOLATION,
        f"{name!r} is {size} bytes; the bound is {settings.email_attachment_max_mb} MB",
    )


def _ambiguity_refusal(exc: EmailAttachmentAmbiguousError) -> dict[str, Any]:
    """Name the CURRENT handles: the one the listing served may have expired."""
    candidates = "; ".join(
        f"attachment_id={attachment_handle(c)!r} ({attachment_mime(c)}, {c.get('size', 0)} bytes)"
        for c in exc.candidates
    )
    return _refusal(
        ToolErrorCode.DISAMBIGUATION_REQUIRED,
        f"{len(exc.candidates)} attachments match {exc.filename!r} (a handle may have "
        f"expired since the listing): pass one of the CURRENT handles, or the "
        f"filename when unique — {candidates}",
    )


# Singleton, like every connector tool; per-call state travels on the runtime.
_get_email_attachment_tool_instance = GetEmailAttachmentTool()


@connector_tool(
    name="get_email_attachment",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    category="read",
    rate_limit_max_calls=lambda: settings.email_attachment_rate_limit_max_calls,
    rate_limit_window_seconds=lambda: settings.email_attachment_rate_limit_window_seconds,
)
async def get_email_attachment_tool(
    message_id: Annotated[str, "The message id (from get_emails)"],
    attachment_id: Annotated[
        str | None,
        "The attachment handle listed by get_emails (attachments[].attachment_id); a Gmail "
        "handle can expire between two reads, so pass filename too when known",
    ] = None,
    filename: Annotated[
        str | None, "The attachment's file name as listed (preferred when unique in the message)"
    ] = None,
    question: Annotated[
        str | None,
        "What to look for in the attachment (guides the reading of an image or a scan)",
    ] = None,
    part: Annotated[int, "1-based part of a long text (see parts)"] = 1,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Read ONE attachment of an e-mail: its text, or a vision reading of an image/scan.

    Use after get_emails listed a message's attachments. Selects the part by
    attachment_id (preferred) or by filename; serves the text in parts
    (pass part=2 for the next one) or the vision slot's reading of an image
    or a PDF without a text layer.

    Args:
        message_id: The message id.
        attachment_id: The listed handle; wins over filename.
        filename: The file name, when unique.
        question: What the reader wants from the attachment.
        part: 1-based part of a long text.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput with the reading, or a refusal told by name.
    """
    return await _get_email_attachment_tool_instance.execute(
        runtime=runtime,
        message_id=message_id,
        attachment_id=attachment_id,
        filename=filename,
        question=question,
        part=part,
    )


__all__ = ["GetEmailAttachmentTool", "get_email_attachment_tool"]
