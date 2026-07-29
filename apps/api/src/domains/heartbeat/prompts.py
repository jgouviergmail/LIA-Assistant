"""
Heartbeat LLM prompts and decision/generation functions.

Two-phase approach:
1. Decision (structured output): LLM evaluates context and decides skip/notify
2. Message Generation: LLM rewrites the draft with user personality and language
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import get_settings
from src.core.i18n_types import get_language_name
from src.domains.agents.prompts import load_prompt
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision
from src.infrastructure.llm.token_capture import TokenCaptureHandler

logger = structlog.get_logger(__name__)


def build_decision_user_prompt(context: HeartbeatContext) -> str:
    """Build the user prompt for the decision LLM call.

    Args:
        context: Aggregated context from all sources.

    Returns:
        Formatted user prompt string.
    """
    parts = [f"CURRENT CONTEXT:\n{context.to_prompt_context()}"]

    # Recent heartbeats for anti-redundancy
    hb_summary = context.recent_heartbeats_summary
    parts.append(
        f"\nRECENT HEARTBEAT NOTIFICATIONS (contents shown — never repeat their "
        f"topics, activities or products):\n{hb_summary or 'None sent recently.'}"
    )

    # Cross-type: recent interest notifications
    int_summary = context.recent_interest_notifications_summary
    parts.append(
        f"\nRECENT INTEREST NOTIFICATIONS (avoid overlapping topics):\n"
        f"{int_summary or 'None sent recently.'}"
    )

    # Cross-surface: reminders, scheduled-action results, call reports (P10)
    other_summary = context.recent_other_notifications_summary
    parts.append(
        f"\nOTHER RECENT PROACTIVE MESSAGES (reminders, automations, call "
        f"reports — the user already received these, do not pile up on the "
        f"same topics):\n{other_summary or 'None sent recently.'}"
    )

    return "\n".join(parts)


async def get_heartbeat_decision(
    context: HeartbeatContext,
    user_language: str,
) -> tuple[HeartbeatDecision, int, int, int]:
    """Execute the LLM decision phase (structured output).

    Uses a cheap/fast model to evaluate context and decide skip/notify.
    Token usage is captured via a LangChain callback since
    get_structured_output() only returns the Pydantic model.

    Args:
        context: Aggregated HeartbeatContext.
        user_language: User's language code (e.g., "fr", "en").

    Returns:
        Tuple of (decision, tokens_in, tokens_out, tokens_cache).
    """
    from langchain_core.runnables import RunnableConfig

    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.structured_output import get_structured_output

    language_name = get_language_name(user_language)
    llm = get_llm("heartbeat_decision")

    # Resolve provider for structured output (needs provider-specific logic)
    config = get_llm_config_for_agent(get_settings(), "heartbeat_decision")

    system_prompt = load_prompt("heartbeat_decision_prompt").format(
        user_language=language_name,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=build_decision_user_prompt(context)),
    ]

    # Use callback to capture tokens (get_structured_output returns only the model)
    token_capture = TokenCaptureHandler()
    runnable_config = RunnableConfig(callbacks=[token_capture])

    decision = await get_structured_output(
        llm=llm,
        messages=messages,
        schema=HeartbeatDecision,
        provider=config.provider,
        node_name="heartbeat_decision",
        config=runnable_config,
    )

    tokens_in = token_capture.tokens_in
    tokens_out = token_capture.tokens_out
    tokens_cache = token_capture.tokens_cache

    logger.info(
        "heartbeat_decision_result",
        action=decision.action,
        reason=decision.reason[:100],
        priority=decision.priority,
        sources_used=decision.sources_used,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )

    return decision, tokens_in, tokens_out, tokens_cache


async def generate_heartbeat_message(
    message_draft: str,
    context: HeartbeatContext,
    user_language: str,
    personality_instruction: str | None = None,
    user_id: str | UUID | None = None,
    facts_block: str | None = None,
) -> tuple[str, int, int, int]:
    """Generate the final notification message (Phase 2).

    Rewrites the decision's message_draft with the user's personality
    and language preferences.

    Args:
        message_draft: Draft from the decision phase.
        context: HeartbeatContext (for additional context if needed).
        user_language: User's language code (e.g., "fr", "en").
        personality_instruction: Personality prompt instruction.
        user_id: User UUID for psyche context injection.
        facts_block: Verified facts fetched for an interest-centered heartbeat
            (ADR-135). When present, the message must be built on named items
            from it instead of staying vague.

    Returns:
        Tuple of (message, tokens_in, tokens_out, tokens_cache).
    """
    from src.domains.personalities.constants import DEFAULT_PERSONALITY_PROMPT
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation

    language_name = get_language_name(user_language)
    current_dt = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")

    # Resolve psyche context before template formatting
    psyche_block = ""
    user_model_block = ""
    if user_id:
        # Psyche injection is best-effort
        with suppress(Exception):
            from src.domains.psyche.service import build_psyche_prompt_block

            psyche_block = await build_psyche_prompt_block(user_id=user_id, user_timezone=None)
        # Journal portrait injection is best-effort
        with suppress(Exception):
            from src.domains.journals.portrait_builder import (
                build_journal_user_model_block,
            )

            user_model_block = await build_journal_user_model_block(
                user_id=user_id, format="brief", flow="heartbeat"
            )

    system_prompt = load_prompt("heartbeat_message_prompt").format(
        personality_instruction=personality_instruction or DEFAULT_PERSONALITY_PROMPT,
        language=language_name,
        current_datetime=current_dt,
        message_draft=message_draft,
        psyche_context=psyche_block,
    )
    if user_model_block:
        system_prompt += "\n\n" + user_model_block

    if facts_block:
        # ADR-135: real, fresh facts for an interest-centered heartbeat. The
        # contract is explicit so the model names concrete items instead of
        # producing another vague "have a look at ..." message.
        system_prompt += (
            "\n\nVERIFIED FACTS about the user's interest (fresh, from web search):\n"
            + facts_block
            + "\n\nYour notification MUST be built on 1-2 concrete items from these "
            "facts, naming them explicitly. Never invent titles or facts. Do not "
            "include raw URLs — source links are appended automatically."
        )

    llm = get_llm("heartbeat_message")

    result = await invoke_with_instrumentation(
        llm=llm,
        llm_type="heartbeat_message_generation",
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content="Generate the notification message."),
        ],
        session_id=f"heartbeat_msg_{uuid4().hex[:8]}",
        user_id="system",
    )

    message = result.text

    # Extract token usage
    tokens_in = 0
    tokens_out = 0
    tokens_cache = 0
    if hasattr(result, "usage_metadata") and result.usage_metadata:
        tokens_in = result.usage_metadata.get("input_tokens", 0)
        tokens_out = result.usage_metadata.get("output_tokens", 0)
        tokens_cache = result.usage_metadata.get("cache_read_input_tokens", 0)

    logger.info(
        "heartbeat_message_generated",
        language=user_language,
        length=len(message),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )

    return message.strip(), tokens_in, tokens_out, tokens_cache
