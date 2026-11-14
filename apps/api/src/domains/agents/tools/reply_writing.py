"""The reply LIA writes when the person gave no words of their own — one writer, two tools.

« Answer Paul that Friday works » is an instruction, not the reply: both the reply that
is sent after confirmation (``reply_email_tool``) and the one saved in the drafts
(``create_mailbox_reply_draft_tool``) are written by ONE writer, from the received
e-mail, in the person's own voice when LIA knows how they write (ADR-344, ADR-383).
What it could not do is said as the tool's refusal, never guessed: a spending ceiling,
no usable answer, an empty one — each asks for the reply's text instead.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain.tools import ToolRuntime

from src.core.exceptions_domains import UsageLimitExceededError
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.emails.previous_reply import PreviousReply, previous_reply_of
from src.domains.agents.emails.reply_drafting import draft_reply_body
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.agents.tools.runtime_helpers import get_original_user_message
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.infrastructure.llm.structured_output_errors import StructuredOutputError


async def written_reply(
    original: dict[str, Any],
    *,
    instruction: str | None,
    previous: PreviousReply | None,
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    user_id: UUID,
    language: str,
) -> str | dict[str, Any]:
    """The reply the person would send to ``original`` — or the refusal saying why not.

    Args:
        original: The received e-mail, in the ``EmailMessage`` vocabulary.
        instruction: What the reply should say, if the person said it.
        previous: What the person already answered to it, read with its words.
        runtime: The tool's runtime: the person's name and the turn's config.
        user_id: The account, for both spending ceilings and the writing style.
        language: The fallback language when the received e-mail's is unclear.

    Returns:
        The reply's words, stripped; or a refusal as ``execute_api_call`` returns one.
    """
    context = tool_runtime_context(runtime) if runtime is not None else None
    try:
        body = await draft_reply_body(
            original,
            previous_reply=previous,
            instruction=instruction,
            sender_name=context.display_name if context is not None else None,
            user_language=language,
            user_id=str(user_id),
            config=runtime.config if runtime is not None else None,
        )
    except UsageLimitExceededError:
        return refusal(
            ToolErrorCode.RATE_LIMIT_EXCEEDED,
            "A spending ceiling refused writing the reply: give its text, or try later.",
        )
    except StructuredOutputError:
        return refusal(
            ToolErrorCode.EXTERNAL_API_ERROR, "The reply could not be written: give its text."
        )
    if not body.strip():
        return refusal(ToolErrorCode.EMPTY_RESULT, "No reply was written: give its text.")
    return body.strip()


async def reply_words(
    client: EmailClientProtocol,
    original: dict[str, Any],
    *,
    body: str,
    instruction: str | None,
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    user_id: UUID,
    language: str,
) -> tuple[str | dict[str, Any], PreviousReply | None]:
    """The words a reply sends — the person's own, else the writer's — and what was answered.

    Args:
        client: The open mailbox.
        original: The received e-mail being answered.
        body: The words the person dictated, or empty.
        instruction: What the reply must say; with nothing said, the person's own message
            in the turn is.
        runtime: The tool's runtime.
        user_id: The account.
        language: The fallback language.

    Returns:
        The words (or the writer's refusal), and the person's earlier answer to the
        message, read with its words when LIA writes: the new reply continues from it.
    """
    previous = await previous_reply_of(client, original, user_timezone=None, with_words=not body)
    if body:
        return body, previous
    said = instruction or (get_original_user_message(runtime) if runtime is not None else None)
    written = await written_reply(
        original,
        instruction=said,
        previous=previous,
        runtime=runtime,
        user_id=user_id,
        language=language,
    )
    return written, previous


__all__ = ["reply_words", "written_reply"]
