"""
Fallback Response Service - Elegant LLM-based fallback responses.

Provides graceful fallback responses when the pipeline fails to generate content.
Instead of hardcoded messages, generates contextual responses via LLM.

Usage:
    from src.domains.agents.services.fallback_response import generate_fallback_response

    async for chunk, content in generate_fallback_response(user_query, run_id):
        yield chunk
"""

from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any

from src.domains.agents.prompts import load_prompt
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.api.schemas import ChatStreamChunk

logger = get_logger(__name__)


def get_simple_fallback_message(language: str | None = None) -> str:
    """Localized last-resort message when the fallback LLM also fails.

    Delegates to the central SSE error-message i18n mechanism (6 languages)
    — never an inline hardcoded string (audit wave 2, N-99).

    Args:
        language: Raw user locale; defaults to the configured default language.

    Returns:
        Localized fallback message.
    """
    from src.core.config import settings
    from src.domains.agents.api.error_messages import SSEErrorMessages
    from src.domains.agents.utils.i18n_location import normalize_language

    lang = normalize_language(language or settings.default_language)
    return SSEErrorMessages.simple_fallback(lang)


async def generate_fallback_response(
    user_query: str,
    run_id: str,
    format_chunk_fn: Callable[..., Any],
    config: Any = None,
    user_id: str | None = None,
    language: str | None = None,
) -> AsyncGenerator[tuple["ChatStreamChunk", str], None]:
    """
    Generate an elegant fallback response via LLM.

    When the pipeline fails to produce a response (e.g., wrong intent classification,
    no data found), this generates a contextual, helpful response that:
    - Acknowledges the user's query
    - Explains the situation naturally
    - Suggests next steps

    Args:
        user_query: The original user query
        run_id: For logging/tracing context
        format_chunk_fn: Function to format content into ChatStreamChunk (e.g., service.format_token_chunk)
        config: Optional RunnableConfig with TokenTrackingCallback for billing tracking
        user_id: User UUID string for psyche context.
        language: User's language for the localized last-resort message.

    Yields:
        tuple[ChatStreamChunk, str]: (formatted chunk, content fragment)

    Example:
        async for chunk, content in generate_fallback_response(
            user_query="where does John live?",
            run_id="abc123",
            format_chunk_fn=streaming_service.format_token_chunk,
            config=runnable_config,  # For token tracking
        ):
            yield chunk
            total_content += content
    """
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    logger.info(
        "fallback_response_generating",
        run_id=run_id,
        query_preview=user_query[:50] if user_query else "empty",
    )

    # Resolve psyche context before template formatting
    psyche_block = ""
    user_model_block = ""
    if user_id:
        try:
            from src.domains.psyche.service import build_psyche_prompt_block

            psyche_block = await build_psyche_prompt_block(user_id=user_id, user_timezone=None)
        except Exception:
            pass  # Psyche injection is best-effort
        try:
            from src.domains.journals.portrait_builder import (
                build_journal_user_model_block,
            )

            user_model_block = await build_journal_user_model_block(
                user_id=user_id, format="brief", flow="fallback"
            )
        except Exception:
            pass  # Journal portrait injection is best-effort

    # Build the prompt
    prompt = load_prompt("fallback_response_prompt").format(
        user_query=user_query or "unavailable query",
        psyche_context=psyche_block,
    )
    if user_model_block:
        prompt += "\n\n" + user_model_block

    try:
        # Use response LLM for consistency with main response generation
        llm = get_llm("response")

        # Enrich config with node metadata for token tracking
        enriched_config = (
            enrich_config_with_node_metadata(config, "fallback_response") if config else None
        )

        async for chunk in llm.astream(prompt, config=enriched_config):
            if hasattr(chunk, "content") and chunk.content:
                # Gemini 3.x streams list[dict] content blocks; normalize to text.
                text = coerce_content_to_text(chunk.content)
                if not text:
                    continue
                formatted_chunk = format_chunk_fn(text)
                yield (formatted_chunk, text)

        logger.info(
            "fallback_response_completed",
            run_id=run_id,
        )

    except Exception as e:
        # If LLM fails, emit a simple graceful message
        logger.warning(
            "fallback_response_llm_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        simple_message = get_simple_fallback_message(language)
        formatted_chunk = format_chunk_fn(simple_message)
        yield (formatted_chunk, simple_message)


async def generate_fallback_response_sync(
    user_query: str,
    run_id: str,
    config: Any = None,
    user_id: str | None = None,
    language: str | None = None,
) -> str:
    """
    Generate a fallback response synchronously (non-streaming).

    Useful when streaming is not needed and a complete response is required.

    Args:
        user_query: The original user query
        run_id: For logging/tracing context
        config: Optional RunnableConfig with TokenTrackingCallback for billing tracking
        user_id: User UUID string for psyche context.
        language: User's language for the localized last-resort message.

    Returns:
        str: The complete fallback response
    """
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

    logger.info(
        "fallback_response_sync_generating",
        run_id=run_id,
        query_preview=user_query[:50] if user_query else "empty",
    )

    # Resolve psyche context before template formatting
    psyche_block = ""
    user_model_block = ""
    if user_id:
        try:
            from src.domains.psyche.service import build_psyche_prompt_block

            psyche_block = await build_psyche_prompt_block(user_id=user_id, user_timezone=None)
        except Exception:
            pass  # Psyche injection is best-effort
        try:
            from src.domains.journals.portrait_builder import (
                build_journal_user_model_block,
            )

            user_model_block = await build_journal_user_model_block(
                user_id=user_id, format="brief", flow="fallback"
            )
        except Exception:
            pass  # Journal portrait injection is best-effort

    prompt = load_prompt("fallback_response_prompt").format(
        user_query=user_query or "unavailable query",
        psyche_context=psyche_block,
    )
    if user_model_block:
        prompt += "\n\n" + user_model_block

    try:
        llm = get_llm("response")

        # Enrich config with node metadata for token tracking
        enriched_config = (
            enrich_config_with_node_metadata(config, "fallback_response") if config else None
        )

        response = await llm.ainvoke(prompt, config=enriched_config)

        content = response.content if hasattr(response, "content") else str(response)

        logger.info(
            "fallback_response_sync_completed",
            run_id=run_id,
            content_length=len(content),
        )

        return content  # type: ignore

    except Exception as e:
        logger.warning(
            "fallback_response_sync_llm_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return get_simple_fallback_message(language)


__all__ = [
    "generate_fallback_response",
    "generate_fallback_response_sync",
    "get_simple_fallback_message",
]
