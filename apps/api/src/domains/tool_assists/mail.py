"""What LIA does on an open message (ADR-372).

The message is read fresh, through the Tools' own door, by its id: what the model reads is what the
mailbox holds, never what a page sent. A summary is the assistant's digest, under its key and its
schema, so the two never pay twice and never disagree; a reply is the assistant's own writer. The
mailbox is closed again before the model answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from src.core.config import settings
from src.core.field_names import FIELD_BODY
from src.core.i18n import get_language_name
from src.domains.agents.emails.content_generation import generate_email_content
from src.domains.agents.emails.digest import (
    DIGEST_FIELDS,
    DIGEST_STATUS_FIELD,
    EmailDigest,
    EmailDigestService,
    read_cached_digest,
)
from src.domains.agents.emails.reply_drafting import draft_reply_body
from src.domains.agents.prompts import load_prompt
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot, assist_line
from src.domains.tool_assists.text import WrittenText, translate_text
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import ASSIST_EMPTY, ASSIST_FAILED, ASSIST_QUOTA, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.mail_projection import received_at

_TOOL = WorkbenchTool.MAIL

#: The word a message's own ``_provider`` carries: what the digest's cache is keyed on.
PROVIDER_WORDS: Final[dict[ConnectorType, str]] = {
    ConnectorType.GOOGLE_GMAIL: "google",
    ConnectorType.MICROSOFT_OUTLOOK: "microsoft",
    ConnectorType.APPLE_EMAIL: "apple",
}

HELD_STATUSES: Final = frozenset({"computed", "cached"})


def _one_line(subject: str) -> str:
    """A subject as a message carries it: a line break would be refused at the save."""
    return " ".join(subject.split())


async def read_message(run: AssistRun, opened: ActiveClient, message_id: str) -> dict[str, Any]:
    """The message as the mailbox holds it now, in the assistant's vocabulary (ADR-287)."""
    client: EmailClientProtocol = opened.client
    async with run.reading(), provider_call(_TOOL, "read", act=False):
        message: dict[str, Any] = await client.get_message(message_id, use_cache=False)
    return message


async def summarize_message(run: AssistRun, message_id: str) -> EmailDigest:
    """The digest of a message: what the assistant holds, else one short call.

    Args:
        run: The assist's run.
        message_id: The message.

    Returns:
        Its digest.

    Raises:
        BaseAPIException: Nothing to read, a ceiling closed, or no usable answer.
    """
    async with open_tool_client(_TOOL, run.user_id) as opened:
        held = await read_cached_digest(
            str(run.user_id), PROVIDER_WORDS[opened.connector_type], message_id, run.language
        )
        if held is not None:
            return held
        message = await read_message(run, opened, message_id)
    await EmailDigestService().digest_many(
        user_id=str(run.user_id), emails=[message], language=run.language, config=run.config
    )
    return _digest_of(message)


def _digest_of(message: dict[str, Any]) -> EmailDigest:
    """What the digest stamped on the message; what it could not do is a refusal."""
    status = message.get(DIGEST_STATUS_FIELD)
    if status in HELD_STATUSES:
        return EmailDigest.model_validate({field: message[field] for field in DIGEST_FIELDS})
    if status == "skipped_empty":
        refuse(ASSIST_EMPTY)
    if status == "skipped_quota":
        refuse(ASSIST_QUOTA)
    refuse(ASSIST_FAILED)


async def propose_reply(
    run: AssistRun, message_id: str, instruction: str | None, sender_name: str | None
) -> str:
    """The reply the assistant would write, as a proposal: nothing is sent or saved.

    Args:
        run: The assist's run.
        message_id: The message answered.
        instruction: What the person said it should say, if anything.
        sender_name: The person's first name, for a signature they asked for.

    Returns:
        The reply's words.

    Raises:
        BaseAPIException: The message cannot be read, or no usable answer came.
    """
    async with open_tool_client(_TOOL, run.user_id) as opened:
        original = await read_message(run, opened, message_id)
    if not (str(original.get(FIELD_BODY) or "").strip() or original.get("subject")):
        refuse(ASSIST_EMPTY)
    words = await draft_reply_body(
        original,
        instruction=instruction,
        sender_name=sender_name,
        user_language=run.language,
        user_id=str(run.user_id),
        config=run.config,
    )
    if not words:
        refuse(ASSIST_FAILED)
    return words


@dataclass(frozen=True, slots=True)
class ComposedMessage:
    """A message written from an instruction."""

    subject: str
    body: str


async def compose_message(
    run: AssistRun, instruction: str, recipient: str | None, sender_name: str | None
) -> ComposedMessage:
    """A whole message from the person's instruction, as the assistant writes one.

    Args:
        run: The assist's run.
        instruction: What it should say.
        recipient: Who it is for, as typed, if anyone yet.
        sender_name: The person's first name, for a signature they asked for.

    Returns:
        Its subject and body.
    """
    written = await generate_email_content(
        instruction,
        recipient or "",
        run.language,
        config=run.config,
        sender_name=sender_name,
    )
    subject, body = _one_line(written["subject"]), written.get("body", "").strip()
    if not body:
        refuse(ASSIST_FAILED)
    return ComposedMessage(subject=subject, body=body)


async def propose_subject(run: AssistRun, body: str, recipient: str | None) -> str:
    """A subject for words already written.

    Args:
        run: The assist's run.
        body: The message's words.
        recipient: Who it is for, as typed, if anyone yet.

    Returns:
        The subject.
    """
    written = await generate_email_content(
        "", recipient or "", run.language, existing_body=body, config=run.config
    )
    subject = _one_line(written["subject"])
    if not subject:
        refuse(ASSIST_FAILED)
    return subject


@dataclass(frozen=True, slots=True)
class TranslatedMessage:
    """A message in the reader's language; `cut`: only its beginning was read."""

    text: str
    cut: bool


async def translate_message(run: AssistRun, message_id: str) -> TranslatedMessage:
    """A received message in the reader's language.

    Its text is cut at the bound every writing helper publishes, and the cut is said (ADR-185): the
    slot's output must hold the translation whole, or it is refused.

    Args:
        run: The assist's run.
        message_id: The message.

    Returns:
        The translation, and whether it stopped short of the end.
    """
    async with open_tool_client(_TOOL, run.user_id) as opened:
        message = await read_message(run, opened, message_id)
    body = str(message.get(FIELD_BODY) or "").strip()
    if not body:
        refuse(ASSIST_EMPTY)
    bound = settings.tool_assist_text_max_chars
    received = wrap_external_content(body[:bound], source_url=message_id, source_type="email")
    words = await translate_text(run, received, get_language_name(run.language))
    return TranslatedMessage(text=words, cut=len(body) > bound)


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Where a conversation stands.

    Attributes:
        text: The summary, in the reader's language.
        cut: It starts earlier than what was read.
    """

    text: str
    cut: bool


def _said(message: dict[str, Any]) -> str:
    """One message as the model reads it: who, when, what."""
    sent = received_at(message.get("internalDate"))
    return "\n".join(
        (
            f"From: {message.get('from') or ''}",
            f"Date: {sent.isoformat() if sent else ''}",
            f"Subject: {message.get('subject') or ''}",
            "",
            str(message.get(FIELD_BODY) or "").strip(),
        )
    )


def _latest_within(said: list[str], bound: int) -> list[str]:
    """The newest messages that fit, oldest first; the newest alone is cut if it must be."""
    kept: list[str] = []
    room = bound
    for words in reversed(said):
        if len(words) > room:
            if not kept:
                kept.append(words[:bound])
            break
        kept.append(words)
        room -= len(words)
    return kept[::-1]


async def summarize_conversation(run: AssistRun, message_id: str) -> ConversationSummary:
    """Where the conversation of a message stands: its latest messages, read whole.

    Args:
        run: The assist's run.
        message_id: Any message of it.

    Returns:
        Its summary, and whether it starts earlier than what was read.

    Raises:
        BaseAPIException: Nothing to read, a ceiling closed, or no usable answer.
    """
    limit = settings.tool_assist_conversation_max_messages
    async with open_tool_client(_TOOL, run.user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with run.reading(), provider_call(_TOOL, "read_conversation", act=False):
            found = await client.get_conversation(message_id, limit)
            messages = [
                await client.get_message(str(item["id"]), use_cache=False)
                for item in found["messages"]
            ]
    said = [_said(message) for message in messages]
    if not said:
        refuse(ASSIST_EMPTY)
    kept = _latest_within(said, settings.tool_assist_document_max_chars)
    cut = bool(found["truncated"]) or kept != said
    prompt = load_prompt("tool_assist_conversation_prompt").format(
        language_name=get_language_name(run.language),
        cut_note=assist_line("conversation_cut") if cut else "",
        messages=wrap_external_content(
            "\n\n---\n\n".join(kept), source_url=message_id, source_type="email"
        ),
    )
    answer = await ask_slot(run, prompt, WrittenText)
    summary = answer.text.strip()
    if not summary:
        refuse(ASSIST_FAILED)
    return ConversationSummary(text=summary, cut=cut)
