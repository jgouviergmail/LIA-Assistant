"""The content of an outgoing e-mail — ONE resolution for every send tool (ADR-314).

``send_email_tool`` (a draft the person confirms) and ``send_email_to_me_tool``
(a message to the person's own mailbox, no draft) both take a subject and a
body, or a creative instruction, or neither — in which case the person's own
message is the instruction. That resolution used to live inside
``send_email_tool``; it lives here so the two tools cannot drift apart.

Two cleanups travelled with it: the INFO logs carried the instruction and a
subject preview (the person's words) — they now carry counts only — and the
generator is public, reached by name rather than as a private of another module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

import structlog
from langchain.tools import ToolRuntime
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.i18n import get_language_name, normalize_language
from src.core.i18n_api_messages import APIMessages, SupportedLanguage
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    tool_runtime_context,
    tool_user_id_str,
)
from src.domains.agents.prompts import load_prompt
from src.domains.agents.tools.exceptions import ContentGenerationError
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_original_user_message
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.message_text import coerce_content_to_text

logger = structlog.get_logger(__name__)

#: The RECIPIENT value that tells the generation prompt the message is a note
#: the person sends to their own mailbox (no salutation, no call to action).
#: A data marker the versioned prompt matches, never prose.
NOTE_TO_SELF_RECIPIENT: Final = "SELF"


@dataclass(frozen=True)
class EmailContent:
    """A subject and a body, both non-empty."""

    subject: str
    body: str


async def generate_email_content(
    instruction: str,
    recipient: str,
    user_language: str,
    existing_body: str | None = None,
    config: RunnableConfig | None = None,
    sender_name: str | None = None,
) -> dict[str, str]:
    """Generate an e-mail's subject and/or body from an instruction.

    When ``existing_body`` is provided only the subject is generated, from a
    dedicated prompt that reads the body.

    Args:
        instruction: Creative instruction (e.g., "a humorous love poem about Excel").
        recipient: The recipient, or :data:`NOTE_TO_SELF_RECIPIENT`.
        user_language: Target language of the generated content.
        existing_body: If provided, only the subject is generated.
        config: The run's RunnableConfig, so the turn's tracker bills the call.
        sender_name: The sender's first name, for an explicitly requested
            signature (None = unknown).

    Returns:
        ``{"subject": ...}`` always, ``"body"`` only when it was generated.

    Raises:
        ContentGenerationError: If generation fails or returns an invalid format.
    """
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    language_name = get_language_name(user_language)
    if existing_body:
        prompt = load_prompt("email_subject_generation_prompt").format(
            instruction=instruction,
            recipient=recipient,
            body=existing_body,
            user_language=language_name,
        )
        required_fields = ["subject"]
    else:
        prompt = load_prompt("email_content_generation_prompt").format(
            instruction=instruction,
            recipient=recipient,
            sender_name=sender_name or "unknown",
            user_language=language_name,
        )
        required_fields = ["subject", "body"]
    logger.debug(
        "email_content_generation_mode",
        mode="subject_only" if existing_body else "full",
    )

    llm = get_llm("email_agent")
    enriched_config = (
        enrich_config_with_node_metadata(config, "email_content_generation") if config else None
    )
    result = await llm.ainvoke(prompt, config=enriched_config)

    # Gemini 3.x returns content as list[dict] blocks; coerce to text so the
    # string operations and json.loads below stay str-safe.
    content = coerce_content_to_text(result.content) if hasattr(result, "content") else str(result)
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("email_content_parse_error", content_chars=len(content), error_type="json")
        raise ContentGenerationError(f"Invalid JSON from LLM: {e}") from e
    for field in required_fields:
        if field not in parsed:
            raise ContentGenerationError(f"Missing '{field}' in LLM response")
    generated = {"subject": parsed["subject"]}
    if "body" in parsed:
        generated["body"] = parsed["body"]
    return generated


def _user_language(runtime: ToolRuntime[LiaRuntimeContext, Any] | None) -> SupportedLanguage:
    """The person's language from the tool's own runtime, else the default."""
    context = tool_runtime_context(runtime) if runtime is not None else None
    return normalize_language(
        context.language if context is not None else settings.default_language
    )


async def resolve_email_content(
    *,
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    recipient: str,
    subject: str | None,
    body: str | None,
    content_instruction: str | None,
) -> EmailContent | UnifiedToolOutput:
    """Settle the subject and body an e-mail tool will send.

    Planner-provided values are kept; only what is missing is generated, from
    ``content_instruction`` or — when neither it nor the subject/body pair is
    complete — from the person's original message.

    Args:
        runtime: The tool's runtime (language, sender name, config, message).
        recipient: The recipient, or :data:`NOTE_TO_SELF_RECIPIENT`.
        subject: The subject the planner gave, if any.
        body: The body the planner gave, if any.
        content_instruction: A creative instruction, if any.

    Returns:
        The content, or the failure to hand back to the model.
    """
    user_language = _user_language(runtime)
    instruction = content_instruction
    if not content_instruction and (not subject or not body) and runtime is not None:
        user_message = get_original_user_message(runtime)
        if user_message:
            instruction = user_message
            logger.info(
                "email_content_instruction_fallback_to_user_message",
                user_message_chars=len(user_message),
                will_generate_subject=not subject,
                will_generate_body=not body,
            )

    final_subject = subject or ""
    final_body = body or ""
    if instruction and (not subject or not body):
        context = tool_runtime_context(runtime) if runtime is not None else None
        try:
            generated = await generate_email_content(
                instruction=instruction,
                recipient=recipient,
                user_language=user_language,
                existing_body=body if body and not subject else None,
                config=runtime.config if runtime is not None else None,
                sender_name=context.display_name if context is not None else None,
            )
        except ContentGenerationError as e:
            logger.error("email_content_generation_failed", error_type=type(e).__name__)
            return UnifiedToolOutput.failure(
                message=APIMessages.content_generation_failed(str(e), user_language),
                error_code="CONTENT_GENERATION_FAILED",
            )
        final_subject = subject or generated.get("subject", "")
        final_body = body or generated.get("body", "")
        # Counts only at INFO: the instruction and the subject are the person's words.
        logger.info(
            "email_content_generated",
            user_id=tool_user_id_str(runtime) if runtime is not None else None,
            instruction_chars=len(instruction),
            subject_generated=not subject,
            body_generated=not body,
        )

    if not final_subject or not final_body:
        return UnifiedToolOutput.failure(
            message=APIMessages.email_content_missing(user_language),
            error_code="MISSING_CONTENT",
        )
    return EmailContent(subject=final_subject, body=final_body)


__all__ = [
    "NOTE_TO_SELF_RECIPIENT",
    "EmailContent",
    "generate_email_content",
    "resolve_email_content",
]
