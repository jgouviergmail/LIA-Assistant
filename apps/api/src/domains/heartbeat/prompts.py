"""
Heartbeat LLM prompts and decision/generation functions.

Two-phase approach:
1. Decision (structured output): LLM evaluates context and decides skip/notify
2. Message Generation: LLM rewrites the draft with user personality and language
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from functools import lru_cache
from uuid import UUID, uuid4

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import get_settings
from src.core.i18n import get_language_name
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.prompts import load_prompt
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import tokens_from_response

logger = structlog.get_logger(__name__)


def build_decision_user_prompt(context: HeartbeatContext) -> str:
    """Build the user prompt for the decision LLM call.

    Args:
        context: Aggregated context from all sources.

    Returns:
        Formatted user prompt string.
    """
    # Three anti-redundancy blocks (own heartbeats, interest notifications,
    # other proactive surfaces — P10); an empty summary reads as the store's
    # « none » line rather than a blank the model could misread.
    none = _heartbeat_lines()["none_sent_recently"]
    return load_prompt("heartbeat_decision_user_prompt").format(
        context=context.to_prompt_context(),
        recent_heartbeats=context.recent_heartbeats_summary or none,
        recent_interests=context.recent_interest_notifications_summary or none,
        recent_other=context.recent_other_notifications_summary or none,
    )


def render_verified_facts(facts_block: str) -> str:
    """The ADR-135 verified-facts contract appended to an interest heartbeat.

    Args:
        facts_block: The fresh facts, one per line.

    Returns:
        The block from ``heartbeat_verified_facts_prompt``.
    """
    return load_prompt("heartbeat_verified_facts_prompt").format(facts_block=facts_block)


@lru_cache(maxsize=1)
def _heartbeat_lines() -> dict[str, str]:
    """One-line scaffolds of the heartbeat prompts, read once from the store."""
    return dict(parse_prompt_sections(read_prompt_file("heartbeat_prompt_lines"), 2))


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


def message_clock(context: HeartbeatContext) -> tuple[str, str | None]:
    """The clock the message prompt is written against: the PERSON's.

    The decision prompt has always received the local time (``TIME: … 11:40``)
    while the message prompt received UTC — measured 2026-09-11: « Il est 9h43
    et il brille toujours par son absence » delivered at 11:43 Paris. The
    aggregator computes ``user_local_time`` for every context; a context
    without one (tests, a degraded aggregation) falls back to UTC, named.

    Args:
        context: The aggregated heartbeat context.

    Returns:
        ``(label, timezone_name)`` — the formatted local instant and the IANA
        name for the psyche block, or ``None`` when only UTC is known.
    """
    local = context.user_local_time
    if local is None or local.tzinfo is None:
        return datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M"), None
    return local.strftime("%d/%m/%Y %H:%M"), str(local.tzinfo)


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
    current_dt, user_timezone = message_clock(context)

    # Resolve psyche context before template formatting
    psyche_block = ""
    user_model_block = ""
    if user_id:
        # Psyche injection is best-effort
        with suppress(Exception):
            from src.domains.psyche.service import build_psyche_prompt_block

            psyche_block = await build_psyche_prompt_block(
                user_id=user_id, user_timezone=user_timezone
            )
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
        system_prompt += "\n\n" + render_verified_facts(facts_block)

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

    # ONE reader for every provider's spelling (ADR-272 corollary): the prompt
    # count excludes what was read from cache, which the tracker prices apart.
    tokens = tokens_from_response(result)
    tokens_in, tokens_out, tokens_cache = tokens.prompt, tokens.completion, tokens.cached

    logger.info(
        "heartbeat_message_generated",
        language=user_language,
        length=len(message),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )

    return message.strip(), tokens_in, tokens_out, tokens_cache
