"""What LIA reads of a file (ADR-372).

A file is read by what it is: its words through the knowledge spaces' own extraction, then the
assists' slot; an image or a scan by sight, on the vision slot, which answers in the reader's
language and is what the run is billed under. The bytes come through the Tools' own doors, under
their ceilings, and only the summary leaves. What a model reads is bounded, and a cut is said.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from src.core.config import settings
from src.core.i18n import get_language_name
from src.domains.agents.emails.attachment_content import LLM_TYPE as VISION_SLOT
from src.domains.agents.emails.attachment_content import (
    AttachmentReading,
    ReadingOutcome,
    Route,
    read_attachment,
)
from src.domains.agents.prompts import load_prompt
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot, assist_line
from src.domains.tool_assists.text import WrittenText
from src.domains.workbench.errors import (
    ASSIST_EMPTY,
    ASSIST_FAILED,
    ASSIST_QUOTA,
    ASSIST_UNREADABLE,
    refuse,
)
from src.domains.workbench.files_service import download_file
from src.domains.workbench.mail_attachments import download_attachment
from src.domains.workbench.schemas.files import DownloadQuery
from src.domains.workbench.schemas.mail import AttachmentRequest

#: How each way a file can stay unread is told; only ``ok`` goes on.
_REFUSALS: Final[dict[ReadingOutcome, str]] = {
    "unsupported": ASSIST_UNREADABLE,
    "empty": ASSIST_EMPTY,
    "skipped_quota": ASSIST_QUOTA,
    "failed": ASSIST_FAILED,
    "truncated": ASSIST_FAILED,
}


@dataclass(frozen=True, slots=True)
class FileSummary:
    """What a file comes to.

    Attributes:
        text: The summary, in the reader's language.
        cut: Only part of the file was read.
    """

    text: str
    cut: bool


async def _summary_of_words(run: AssistRun, words: str, name: str) -> FileSummary:
    """Have the assists' slot summarize what the file says, up to its bound."""
    bound = settings.tool_assist_document_max_chars
    cut = len(words) > bound
    document = wrap_external_content(words[:bound], source_url=name, source_type="document")
    prompt = load_prompt("tool_assist_file_prompt").format(
        language_name=get_language_name(run.language),
        cut_note=assist_line("document_cut") if cut else "",
        text=document,
    )
    answer = await ask_slot(run, prompt, WrittenText)
    summary = answer.text.strip()
    if not summary:
        refuse(ASSIST_FAILED)
    return FileSummary(text=summary, cut=cut)


async def _summary(run: AssistRun, content: EmailAttachmentContent) -> FileSummary:
    """Read the bytes by what they are, and say how that went."""
    reading: AttachmentReading = await read_attachment(
        content,
        question=assist_line("file_question"),
        language=run.language,
        user_id=str(run.user_id),
        config=run.config,
        max_pages=settings.email_attachment_vision_max_pages,
        max_edge=settings.email_attachment_image_max_edge,
    )
    if reading.route is Route.VISION:
        run.slot = VISION_SLOT
    if reading.outcome != "ok":
        refuse(_REFUSALS[reading.outcome])
    if reading.route is Route.VISION:
        return FileSummary(text=reading.text, cut=reading.pages_read < reading.pages_total)
    return await _summary_of_words(run, reading.text, content.filename)


async def summarize_file(run: AssistRun, file_id: str) -> FileSummary:
    """What a drive's file says, in a few lines.

    Args:
        run: The assist's run.
        file_id: The file: a Google document leaves in its first export format.

    Returns:
        Its summary, and whether only part of it was read.

    Raises:
        BaseAPIException: Nothing to read, a ceiling closed, or no usable answer.
    """
    async with run.reading():
        file = await download_file(run.user_id, DownloadQuery(id=file_id))
    return await _summary(run, EmailAttachmentContent(file.filename, file.mime_type, file.data))


async def summarize_attachment(run: AssistRun, request: AttachmentRequest) -> FileSummary:
    """What a message's attachment says, in a few lines.

    Args:
        run: The assist's run.
        request: The attachment.

    Returns:
        Its summary, and whether only part of it was read.

    Raises:
        BaseAPIException: Nothing to read, a ceiling closed, or no usable answer.
    """
    async with run.reading():
        content = await download_attachment(run.user_id, request)
    return await _summary(run, content)
