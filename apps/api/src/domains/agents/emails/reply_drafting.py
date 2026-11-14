"""The words of a reply the person saves as a mailbox draft (ADR-344).

« Prepare a draft replying to this e-mail » carries no text: LIA writes it from
the received message. That message reaches the model as EXTERNAL content — data,
never instructions — cut to its first part under the budget the e-mail reading
uses (``emails_body_part_tokens``). One structured call on the e-mail slot, its
static rules sent as the system message (ADR-309), billed to the turn through
the runtime's config (ADR-272). Nothing leaves the mailbox: the draft is the
person's to read before sending. The reply is written in the person's own voice
when LIA knows how they write (ADR-383, ``writing_style``), read just before the
received e-mail, where it was measured.
"""

from __future__ import annotations

from typing import Any, Final

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import EMAIL_RECIPIENTS_READ_MAX_CHARS
from src.core.i18n import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_layout import single_call_messages
from src.domains.agents.emails import writing_style
from src.domains.agents.emails.detail_levels import paginate_body
from src.domains.agents.emails.previous_reply import PreviousReply
from src.domains.agents.prompts import load_prompt
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.structured_output import get_structured_output

logger = structlog.get_logger(__name__)

#: The slot that writes the person's e-mails (``email_content_generation``).
LLM_TYPE: Final = "email_agent"
NODE_NAME: Final = "mailbox_reply_draft"


class DraftedReply(BaseModel):
    """The reply a draft will hold, above the quoted original."""

    body: str = Field(
        description=(
            "The reply's own words, plain text with line breaks, ready to send: no subject, "
            "no quoted copy of the received e-mail."
        )
    )


def _addressed(header: str) -> str:
    """A recipients header as a model reads it: whole, or cut after its last whole address."""
    if len(header) <= EMAIL_RECIPIENTS_READ_MAX_CHARS:
        return header
    kept = header[:EMAIL_RECIPIENTS_READ_MAX_CHARS]
    return f"{kept[: kept.rfind(', ')] if ', ' in kept else kept}, …"


def _recipient_lines(original: dict[str, Any]) -> list[str]:
    """Whom the e-mail went to and the files it carries: only the lines that say something."""
    files = ", ".join(
        str(item.get("filename") or "")
        for item in original.get("attachments") or []
        if isinstance(item, dict) and item.get("filename")
    )
    said = [
        ("To", _addressed(str(original.get("to") or ""))),
        ("Cc", _addressed(str(original.get("cc") or ""))),
        ("Attachments", files),
    ]
    return [f"{name}: {value}" for name, value in said if value]


def received_as_external(original: dict[str, Any], *, recipients: bool = False) -> str:
    """The received e-mail as external content: its headers, then its first part.

    Args:
        original: The received e-mail, in the ``EmailMessage`` vocabulary.
        recipients: Whom it went to and the names of its files are said too: a form reads its
            guests and what a task must send back there.

    Returns:
        The e-mail, wrapped as data a model never obeys.
    """
    first_part, _parts = paginate_body(
        str(original.get("body") or ""), part=1, part_tokens=settings.emails_body_part_tokens
    )
    text = "\n".join(
        [
            f"From: {original.get('from') or ''}",
            *(_recipient_lines(original) if recipients else []),
            f"Date: {original.get('date') or ''}",
            f"Subject: {original.get('subject') or ''}",
            "",
            first_part,
        ]
    )
    return wrap_external_content(
        text, source_url=str(original.get("id") or "email"), source_type="email"
    )


def earlier_answer_as_external(original: dict[str, Any], previous: PreviousReply | None) -> str:
    """What the person already answered to ``original``, as a model reads it (ADR-379).

    Args:
        original: The received e-mail being answered again.
        previous: The earlier answer, or None when the message is not known answered.

    Returns:
        ``none`` for a first reply; that an answer exists when only the mailbox's mark
        says so; else the answer's instant and its first part, wrapped as data.
    """
    if previous is None:
        return "none"
    if not previous.words:
        return "answered already; its words were not found in the conversation"
    first_part, _parts = paginate_body(
        previous.words, part=1, part_tokens=settings.emails_body_part_tokens
    )
    sent = f"Sent on {previous.at.isoformat(timespec='minutes')}\n\n" if previous.at else ""
    return wrap_external_content(
        f"{sent}{first_part}", source_url=str(original.get("id") or "email"), source_type="email"
    )


async def draft_reply_body(
    original: dict[str, Any],
    *,
    instruction: str | None,
    sender_name: str | None,
    user_language: str,
    user_id: str | None,
    config: RunnableConfig | None,
    previous_reply: PreviousReply | None = None,
    style_reading: writing_style.Reading | None = None,
) -> str:
    """Write the reply to ``original`` the person will find in their drafts.

    Args:
        original: The received e-mail, in the ``EmailMessage`` vocabulary.
        instruction: What the person said the reply should say, if anything.
        sender_name: The person's first name, for a signature they asked for.
        user_language: The language when the received e-mail's is unclear.
        user_id: The account, for both spending ceilings (ADR-272).
        config: The turn's RunnableConfig — it carries the tracking callback.
        previous_reply: What the person already answered to it, when the mailbox says
            they did: the new reply continues from it (ADR-379).
        style_reading: How a caller outside a turn files a read of the person's mailbox,
            should their writing style have to be learned first (ADR-383).

    Returns:
        The reply's own words, stripped (possibly empty: the caller refuses it).

    Raises:
        StructuredOutputError: The model gave no usable answer.
        UsageLimitExceededError: A spending ceiling refused the call.
    """
    style = await writing_style.writing_style_for(user_id, config=config, reading=style_reading)
    rendered = load_prompt("mailbox_reply_draft_prompt").format(
        instruction=instruction or "",
        original=received_as_external(original),
        previous_reply=earlier_answer_as_external(original, previous_reply),
        sender_name=sender_name or "unknown",
        user_language=get_language_name(user_language),
        writing_style=writing_style.reply_block(style),
    )
    llm = get_llm(LLM_TYPE)
    provider = get_llm_config_for_agent(settings, LLM_TYPE).provider
    answer = await get_structured_output(
        llm,
        single_call_messages(rendered),
        DraftedReply,
        provider,
        node_name=NODE_NAME,
        user_id=user_id,
        config=config,
    )
    body = answer.body.strip()
    # Counts only: the reply is the person's words (ADR-317).
    logger.info(
        "mailbox_reply_drafted",
        reply_chars=len(body),
        instructed=bool(instruction),
        styled=style is not None,
    )
    return body


__all__ = [
    "DraftedReply",
    "draft_reply_body",
    "earlier_answer_as_external",
    "received_as_external",
]
