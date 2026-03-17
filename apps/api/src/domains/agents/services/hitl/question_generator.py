"""HITL Question Generator - Multi-Provider Version.

This module provides LLM-powered generation of contextual confirmation questions
for Human-in-the-Loop workflows.

Features:
- Multi-provider support (OpenAI, Anthropic, DeepSeek, Perplexity, Ollama)
- Configured via environment variables (no hardcoded models)
- Uses factory pattern for LLM instantiation
- Token tracking support
- Streaming support for progressive question rendering (TTFT optimization)
- Markdown normalization for proper rendering
- No PII masking (future enhancement)
"""

import json
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_CONTENT, FIELD_TOOL_NAME
from src.core.i18n_hitl import HitlMessages
from src.domains.agents.prompts import format_with_current_datetime, load_prompt
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _merge_tracker_callback(
    config: RunnableConfig,
    tracker: Any | None,
) -> RunnableConfig:
    """Safely merge a token tracker callback into RunnableConfig.

    This function validates that the tracker is a valid LangChain callback
    before adding it to prevent AttributeError when LangChain tries to call
    callback methods like run_inline, on_llm_start, etc.

    IMPORTANT: TrackingContext (from chat.service) is NOT a callback.
    Token tracking for HITL questions is handled via Langfuse callbacks
    in create_instrumented_config().

    Args:
        config: RunnableConfig to merge into
        tracker: Optional callback to add. Must be a BaseCallbackHandler.

    Returns:
        Updated config (same reference, modified in-place if tracker valid)

    Example:
        >>> config = create_instrumented_config(llm_type="hitl_question")
        >>> config = _merge_tracker_callback(config, callback_handler)
    """
    if tracker is None:
        return config

    if isinstance(tracker, BaseCallbackHandler):
        existing_callbacks = config.get("callbacks", [])
        config["callbacks"] = existing_callbacks + [tracker]
    else:
        # Log warning but don't fail - graceful degradation
        # This prevents "'TrackingContext' object has no attribute 'run_inline'" errors
        logger.warning(
            "hitl_tracker_not_callback_skipped",
            tracker_type=type(tracker).__name__,
            expected_type="BaseCallbackHandler",
            msg="Tracker is not a LangChain callback, skipping to prevent AttributeError. "
            "Token tracking is handled via Langfuse callbacks in create_instrumented_config().",
        )

    return config


def _normalize_markdown(text: str) -> str:
    """Normalize LLM-generated Markdown for proper ReactMarkdown rendering.

    LLMs often generate Markdown without proper spacing, which breaks parsing:
    - "text--- ## Header" → "text\n\n---\n\n## Header\n\n"
    - "text## Header" → "text\n\n## Header\n\n"
    - "- Item1- Item2" → "- Item1\n- Item2"

    This function ensures proper spacing around Markdown block elements
    so ReactMarkdown (CommonMark) can parse them correctly.

    Args:
        text: Raw LLM-generated text with potentially malformed Markdown

    Returns:
        Normalized Markdown with proper spacing around block elements

    Example:
        >>> text = "Je vais chercher...--- ## Question Tu confirmes ?"
        >>> normalized = _normalize_markdown(text)
        >>> print(normalized)
        Je vais chercher...

        ---

        ## Question

        Tu confirmes ?
    """
    if not text:
        return text

    # 1. Add newlines before horizontal rules (---)
    # Matches: "text---" → "text\n\n---"
    text = re.sub(r"([^\n])(---+)", r"\1\n\n\2", text)

    # 2. Add newlines after horizontal rules
    # Matches: "---text" → "---\n\ntext"
    text = re.sub(r"(---+)([^\n])", r"\1\n\n\2", text)

    # 3. Add newlines before headers (##, ###, etc.)
    # Matches: "text## Header" → "text\n\n## Header"
    text = re.sub(r"([^\n])(#{1,6}\s)", r"\1\n\n\2", text)

    # 4. Add newlines after headers
    # Matches: "## Header\ntext" → "## Header\n\ntext" (if not already double)
    text = re.sub(r"(#{1,6}[^\n]+)\n([^\n])", r"\1\n\n\2", text)

    # 5. Fix list items that are glued together
    # Matches: "- Item1- Item2" → "- Item1\n- Item2"
    text = re.sub(r"([^\n])(\n?-\s)", r"\1\n\2", text)
    text = re.sub(r"([^\n])(\n?\d+\.\s)", r"\1\n\2", text)

    # 6. Collapse excessive newlines (max 2 consecutive)
    # Matches: "\n\n\n\n" → "\n\n"
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 7. Trim leading/trailing whitespace
    text = text.strip()

    return text


class HitlQuestionGenerator:
    """Generate contextual HITL confirmation questions using LLM.

    This class uses the factory pattern to support multiple LLM providers,
    configured entirely through environment variables.
    """

    def __init__(self) -> None:
        """Initialize question generator with LLMs from factory.

        Uses two dedicated LLM types:
        1. 'hitl_question_generator' for tool-level questions (short, fast):
           - HITL_QUESTION_GENERATOR_LLM_PROVIDER (openai, anthropic, etc.)
           - HITL_QUESTION_GENERATOR_LLM_MODEL (model name)
           - HITL_QUESTION_GENERATOR_LLM_TEMPERATURE (default: 0.3)
           - HITL_QUESTION_GENERATOR_LLM_MAX_TOKENS (default: 200 - intentionally low)

        2. 'hitl_plan_approval_question_generator' for plan-level questions (detailed):
           - HITL_PLAN_APPROVAL_QUESTION_LLM_PROVIDER (openai, anthropic, etc.)
           - HITL_PLAN_APPROVAL_QUESTION_LLM_MODEL (model name)
           - HITL_PLAN_APPROVAL_QUESTION_LLM_TEMPERATURE (default: 0.3)
           - HITL_PLAN_APPROVAL_QUESTION_LLM_MAX_TOKENS (default: 300 - intentionally low)
        """
        # Tool-level question generator (short, simple confirmations)
        # Issue #60 Fix: Removed hardcoded max_tokens override
        # Now uses HITL_QUESTION_GENERATOR_LLM_MAX_TOKENS from config (default: 200)
        self.tool_question_llm = get_llm(
            llm_type="hitl_question_generator",
        )

        # Plan-level approval question generator (detailed explanations)
        # Issue #60 Fix: Removed hardcoded max_tokens override
        # Now uses HITL_PLAN_APPROVAL_QUESTION_LLM_MAX_TOKENS from config (default: 300)
        self.plan_approval_llm = get_llm(
            llm_type="hitl_plan_approval_question_generator",
        )

    async def generate_confirmation_question(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        user_language: str = "fr",
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
    ) -> str:
        """Generate a contextual confirmation question for a tool action.

        Args:
            tool_name: Name of the tool to be executed
            tool_args: Arguments that will be passed to the tool
            user_language: Language code for the question (default: "fr")
            user_timezone: User's IANA timezone for datetime context (default: "Europe/Paris")
            tracker: Optional TokenTrackingCallback for token tracking

        Returns:
            Generated confirmation question string

        Example:
            >>> generator = HitlQuestionGenerator()
            >>> question = await generator.generate_confirmation_question(
            ...     tool_name="search_contacts_tool",
            ...     tool_args={"query": "jean"},
            ...     user_language="fr"
            ... )
            >>> print(question)
            "Je vais rechercher les contacts correspondant à 'jean'. Dois-je continuer ?"
        """
        prompt = self._build_prompt(tool_name, tool_args, user_language, user_timezone)

        # Phase 6 - LLM Observability: Use instrumented config for Langfuse tracing
        from src.infrastructure.llm.instrumentation import create_instrumented_config
        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        # Create instrumented config with Langfuse callbacks
        config = create_instrumented_config(
            llm_type="hitl_question_generator",
            # session_id and user_id would be passed from caller if available
            tags=["hitl", "question_generation"],
            metadata={
                FIELD_TOOL_NAME: tool_name,
                "user_language": user_language,
                "args_count": len(tool_args),
            },
        )

        # Merge token tracker if provided (for accurate cost tracking)
        if tracker:
            existing_callbacks = config.get("callbacks", [])
            config["callbacks"] = existing_callbacks + [tracker]

        # **Phase 2.1 - Token Tracking Alignment Fix**
        # Enrich config to ensure node_name propagates to callbacks
        config = enrich_config_with_node_metadata(config, "hitl_question_generator")

        # Invoke LLM with instrumented config (Langfuse + TokenTracking + node_name)
        response = await self.tool_question_llm.ainvoke(prompt, config=config)

        # Ensure we return a string (content can be str or list in some cases)
        content = response.content
        raw_question = content if isinstance(content, str) else str(content)

        # Normalize Markdown for proper ReactMarkdown rendering
        # LLMs often generate Markdown without proper spacing (e.g., "text--- ## Header")
        # This ensures CommonMark compliance for frontend parsing
        normalized_question = _normalize_markdown(raw_question)

        logger.debug(
            "hitl_question_markdown_normalized",
            tool_name=tool_name,
            raw_length=len(raw_question),
            normalized_length=len(normalized_question),
            has_headers=bool(re.search(r"#{1,6}\s", normalized_question)),
            has_separators=bool(re.search(r"---+", normalized_question)),
        )

        return normalized_question

    async def generate_confirmation_question_stream(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        user_language: str = "fr",
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream HITL question tokens progressively (TTFT optimization).

        This method uses LLM streaming to provide progressive rendering of confirmation
        questions, significantly improving perceived latency (TTFT < 200ms vs 2-4s blocking).

        Args:
            tool_name: Name of the tool to be executed
            tool_args: Arguments that will be passed to the tool
            user_language: Language code for the question (default: "fr")
            user_timezone: User's IANA timezone for datetime context (default: "Europe/Paris")
            tracker: Optional TokenTrackingCallback for token tracking

        Yields:
            str: Question tokens as they are generated by the LLM

        Example:
            >>> generator = HitlQuestionGenerator()
            >>> async for token in generator.generate_confirmation_question_stream(
            ...     tool_name="search_contacts_tool",
            ...     tool_args={"query": "jean"},
            ...     user_language="fr"
            ... ):
            ...     print(token, end="", flush=True)
            "Je vais rechercher les contacts correspondant à 'jean'. Dois-je continuer ?"

        Performance:
            - TTFT (Time To First Token): ~200-300ms (vs 2-4s blocking)
            - Total duration: ~2-4s (same as blocking, but perceived faster)
            - Token tracking: Works identically via callbacks (on_llm_end)
            - Cost tracking: Preserved via OpenAI stream_options
        """
        prompt = self._build_prompt(tool_name, tool_args, user_language, user_timezone)

        # Import metrics here to avoid circular dependency
        # Phase 6 - LLM Observability: Use instrumented config for Langfuse tracing
        from src.infrastructure.llm.instrumentation import create_instrumented_config
        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
        from src.infrastructure.observability.metrics_agents import hitl_question_ttft_seconds

        # Create instrumented config with Langfuse callbacks (same as blocking version)
        config = create_instrumented_config(
            llm_type="hitl_question_generator",
            tags=["hitl", "question_generation", "streaming"],
            metadata={
                FIELD_TOOL_NAME: tool_name,
                "user_language": user_language,
                "args_count": len(tool_args),
                "streaming": True,  # Mark as streaming for observability
            },
        )

        # Merge token tracker if provided (for accurate cost tracking)
        if tracker:
            existing_callbacks = config.get("callbacks", [])
            config["callbacks"] = existing_callbacks + [tracker]

        # Enrich config to ensure node_name propagates to callbacks
        config = enrich_config_with_node_metadata(config, "hitl_question_generator")

        # Streaming invocation with TTFT measurement
        start_time = time.time()
        first_token = True
        full_question = ""

        try:
            # Stream tokens from LLM (callbacks work identically to ainvoke)
            async for chunk in self.tool_question_llm.astream(prompt, config=config):
                # Track TTFT (Time To First Token) - critical UX metric
                if first_token:
                    ttft = time.time() - start_time
                    hitl_question_ttft_seconds.observe(ttft)
                    first_token = False
                    logger.info(
                        "hitl_question_first_token",
                        ttft_seconds=ttft,
                        tool_name=tool_name,
                    )

                # Extract and yield token content
                content = chunk.content if chunk.content else ""
                full_question += content
                yield content

            # Normalize Markdown AFTER streaming is complete
            # Note: For streaming, we yield raw tokens then the backend consumer
            # should normalize the final result. Since streaming happens token-by-token,
            # we can't normalize mid-stream without breaking the flow.
            # The normalization will be applied when the question is finalized.
            normalized_full_question = _normalize_markdown(full_question)

            # Log completion metrics
            total_duration = time.time() - start_time
            logger.info(
                "hitl_question_generated_stream",
                tool_name=tool_name,
                question_length=len(full_question),
                normalized_length=len(normalized_full_question),
                duration_seconds=total_duration,
                user_language=user_language,
            )

            logger.debug(
                "hitl_question_stream_markdown_normalized",
                tool_name=tool_name,
                raw_length=len(full_question),
                normalized_length=len(normalized_full_question),
                has_headers=bool(re.search(r"#{1,6}\s", normalized_full_question)),
                has_separators=bool(re.search(r"---+", normalized_full_question)),
            )

        except Exception as e:
            logger.error(
                "hitl_question_streaming_failed",
                tool_name=tool_name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise

    async def generate_plan_approval_question(
        self,
        plan_summary: Any,  # PlanSummary from orchestration.approval_schemas
        approval_reasons: list[str],
        user_language: str = "fr",
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
        personality_instruction: str | None = None,
    ) -> str:
        """Generate a contextual approval question for an execution plan.

        This method generates LLM-powered questions that explain WHAT actions will be
        executed and WITH WHAT data/parameters, helping users make informed decisions.

        Args:
            plan_summary: PlanSummary object containing plan details (steps, total_steps, etc.)
            approval_reasons: List of reasons why approval is required
            user_language: Language code for the question (default: "fr")
            user_timezone: User's IANA timezone for datetime context (default: "Europe/Paris")
            tracker: Optional TokenTrackingCallback for token tracking

        Returns:
            Generated approval question string

        Example:
            >>> generator = HitlQuestionGenerator()
            >>> question = await generator.generate_plan_approval_question(
            ...     plan_summary=plan_summary,
            ...     approval_reasons=["Plan contains tools requiring HITL approval"],
            ...     user_language="fr"
            ... )
            >>> print(question)
            "Je vais rechercher les contacts contenant 'jean' (max 10 résultats).
             Cette action nécessite ton approbation. Je lance ?"
        """
        prompt = self._build_plan_prompt(
            plan_summary, approval_reasons, user_language, user_timezone, personality_instruction
        )

        # Phase 6 - LLM Observability: Use instrumented config for Langfuse tracing
        from src.infrastructure.llm.instrumentation import create_instrumented_config
        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        # Create instrumented config with Langfuse callbacks
        config = create_instrumented_config(
            llm_type="hitl_question_generator",
            tags=["hitl", "plan_approval", "question_generation"],
            metadata={
                "plan_id": plan_summary.plan_id,
                "total_steps": plan_summary.total_steps,
                "user_language": user_language,
                "approval_reasons_count": len(approval_reasons),
            },
        )

        # Merge token tracker if provided (for accurate cost tracking)
        if tracker:
            existing_callbacks = config.get("callbacks", [])
            config["callbacks"] = existing_callbacks + [tracker]

        # Enrich config to ensure node_name propagates to callbacks
        config = enrich_config_with_node_metadata(config, "hitl_plan_approval_question_generator")

        # Invoke LLM with instrumented config (Langfuse + TokenTracking + node_name)
        response = await self.plan_approval_llm.ainvoke(prompt, config=config)

        # Ensure we return a string (content can be str or list in some cases)
        content = response.content
        raw_question = content if isinstance(content, str) else str(content)

        # Normalize Markdown for proper ReactMarkdown rendering
        # LLMs often generate Markdown without proper spacing (e.g., "text--- ## Header")
        # This ensures CommonMark compliance for frontend parsing
        normalized_question = _normalize_markdown(raw_question)

        logger.debug(
            "hitl_plan_approval_markdown_normalized",
            plan_id=plan_summary.plan_id,
            raw_length=len(raw_question),
            normalized_length=len(normalized_question),
            has_headers=bool(re.search(r"#{1,6}\s", normalized_question)),
            has_separators=bool(re.search(r"---+", normalized_question)),
        )

        return normalized_question

    async def generate_plan_approval_question_stream(
        self,
        plan_summary: Any,  # PlanSummary from orchestration.approval_schemas
        approval_reasons: list[str],
        user_language: str = "fr",
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
        personality_instruction: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream plan approval question tokens progressively (TTFT optimization).

        This method uses LLM streaming to provide progressive rendering of plan approval
        questions, significantly improving perceived latency (TTFT < 500ms vs 2-4s blocking).

        This is the core method for Phase 1 HITL Streaming (OPTIMPLAN).
        It generates the question AFTER the interrupt, in the StreamingService,
        instead of blocking in approval_gate_node.

        Args:
            plan_summary: PlanSummary object containing plan details (steps, total_steps, etc.)
            approval_reasons: List of reasons why approval is required
            user_language: Language code for the question (default: "fr")
            user_timezone: User's IANA timezone for datetime context (default: "Europe/Paris")
            tracker: Optional TokenTrackingCallback for token tracking

        Yields:
            str: Question tokens as they are generated by the LLM

        Example:
            >>> generator = HitlQuestionGenerator()
            >>> async for token in generator.generate_plan_approval_question_stream(
            ...     plan_summary=plan_summary,
            ...     approval_reasons=["Plan contains tools requiring HITL approval"],
            ...     user_language="fr"
            ... ):
            ...     print(token, end="", flush=True)
            "Je vais rechercher les contacts contenant 'jean'..."

        Performance:
            - TTFT (Time To First Token): ~200-400ms (vs 2-4s blocking)
            - Total duration: ~2-4s (same as blocking, but perceived faster)
            - Token tracking: Works identically via callbacks (on_llm_end)
            - Cost tracking: Preserved via OpenAI stream_options

        References:
            - OPTIMPLAN/PLAN.md Section 3: Phase 1 HITL Streaming
            - LangChain v1.0 astream() documentation
            - Issue #56: Architecture Planning Agentique
        """
        prompt = self._build_plan_prompt(
            plan_summary, approval_reasons, user_language, user_timezone, personality_instruction
        )

        # Phase 6 - LLM Observability: Use instrumented config for Langfuse tracing
        from src.infrastructure.llm.instrumentation import create_instrumented_config
        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
        from src.infrastructure.observability.metrics_agents import (
            hitl_plan_approval_question_duration,
            hitl_question_ttft_seconds,
        )

        # Create instrumented config with Langfuse callbacks
        config = create_instrumented_config(
            llm_type="hitl_plan_approval_question_generator",
            tags=["hitl", "plan_approval", "question_generation", "streaming"],
            metadata={
                "plan_id": plan_summary.plan_id,
                "total_steps": plan_summary.total_steps,
                "user_language": user_language,
                "approval_reasons_count": len(approval_reasons),
                "streaming": True,  # Mark as streaming for observability
            },
            trace_name="hitl_plan_approval_question_streaming",
        )

        # Merge token tracker if provided (only if it's a valid LangChain callback)
        # This prevents "'TrackingContext' object has no attribute 'run_inline'" errors
        # Token tracking is already handled via Langfuse callbacks in create_instrumented_config()
        config = _merge_tracker_callback(config, tracker)

        # Enrich config to ensure node_name propagates to callbacks
        config = enrich_config_with_node_metadata(config, "hitl_plan_approval_question_generator")

        # Streaming invocation with TTFT measurement
        start_time = time.time()
        first_token = True
        full_question = ""

        try:
            # Stream tokens from LLM (callbacks work identically to ainvoke)
            async for chunk in self.plan_approval_llm.astream(prompt, config=config):
                # Track TTFT (Time To First Token) - critical UX metric
                if first_token:
                    ttft = time.time() - start_time
                    hitl_question_ttft_seconds.labels(type="plan_approval").observe(ttft)
                    first_token = False
                    logger.info(
                        "hitl_plan_approval_question_first_token",
                        ttft_seconds=ttft,
                        plan_id=plan_summary.plan_id,
                    )

                # Extract and yield token content
                content = chunk.content if chunk.content else ""
                full_question += content
                yield content

            # Track total duration after streaming is complete
            total_duration = time.time() - start_time
            hitl_plan_approval_question_duration.observe(total_duration)

            # Normalize Markdown AFTER streaming is complete
            # Note: For streaming, we yield raw tokens. The normalization is applied
            # when the question is finalized in the StreamingService.
            normalized_full_question = _normalize_markdown(full_question)

            # Log completion metrics
            logger.info(
                "hitl_plan_approval_question_generated_stream",
                plan_id=plan_summary.plan_id,
                question_length=len(full_question),
                normalized_length=len(normalized_full_question),
                duration_seconds=total_duration,
                user_language=user_language,
            )

            logger.debug(
                "hitl_plan_approval_question_stream_markdown_normalized",
                plan_id=plan_summary.plan_id,
                raw_length=len(full_question),
                normalized_length=len(normalized_full_question),
                has_headers=bool(re.search(r"#{1,6}\s", normalized_full_question)),
                has_separators=bool(re.search(r"---+", normalized_full_question)),
            )

        except Exception as e:
            # Import fallback metric
            from src.infrastructure.observability.metrics_agents import (
                hitl_streaming_fallback_total,
            )

            error_type = type(e).__name__
            hitl_streaming_fallback_total.labels(type="plan_approval", error_type=error_type).inc()

            logger.error(
                "hitl_plan_approval_question_streaming_failed",
                plan_id=plan_summary.plan_id,
                error=str(e),
                error_type=error_type,
                exc_info=True,
            )
            raise

    def _build_plan_prompt(
        self,
        plan_summary: Any,  # PlanSummary from orchestration.approval_schemas
        approval_reasons: list[str],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        personality_instruction: str | None = None,
    ) -> list[dict[str, str]]:
        """Build prompt messages for plan approval question generation.

        Uses OpenAI prompt caching pattern (system message >1024 tokens for auto-caching).

        Args:
            plan_summary: PlanSummary object with plan details
            approval_reasons: List of reasons why approval is required
            user_language: Target language code
            user_timezone: User's IANA timezone for datetime context
            personality_instruction: Optional LLM personality instruction

        Returns:
            List of message dicts for LLM invocation
        """
        # Load versioned prompt dynamically (cached by load_prompt LRU)
        from src.core.config import get_settings
        from src.domains.agents.prompts import get_current_datetime_context

        settings = get_settings()

        # Load prompt template
        prompt_template = load_prompt(
            "hitl_plan_approval_question_prompt",
            version=settings.hitl_plan_approval_question_prompt_version,
        )

        # Get default personality in user's language if none provided (i18n)
        default_personality = HitlMessages.get_default_personality(user_language)

        # Build concise action summary for the system prompt
        tool_names = [step.tool_name for step in plan_summary.steps]
        sub_agent_count = sum(1 for t in tool_names if t == "delegate_to_sub_agent_tool")
        action_parts: list[str] = []
        for step in plan_summary.steps:
            if step.tool_name == "delegate_to_sub_agent_tool":
                expertise = step.parameters.get("expertise", "specialist")
                action_parts.append(f"sub-agent: {expertise}")
            else:
                desc = step.description or step.tool_name
                action_parts.append(desc)
        action_summary = (
            f"{plan_summary.total_steps} steps "
            f"({sub_agent_count} sub-agent(s)). "
            f"Actions: {'; '.join(action_parts)}"
            if sub_agent_count > 0
            else f"{plan_summary.total_steps} steps. " f"Actions: {'; '.join(action_parts)}"
        )

        # Replace placeholders using .replace() to avoid issues with JSON braces
        hitl_plan_approval_system_prompt = (
            prompt_template.replace(
                "{current_datetime}",
                get_current_datetime_context(user_timezone, user_language),
            )
            .replace(
                "{personnalite}",
                personality_instruction or default_personality,
            )
            .replace(
                "{user_language}",
                user_language,
            )
            .replace(
                "{action_summary}",
                action_summary,
            )
        )

        # Build human-readable step descriptions
        steps_description = []
        for idx, step in enumerate(plan_summary.steps, start=1):
            step_desc = f"{idx}. Tool: {step.tool_name}\n"
            step_desc += f"   Args: {json.dumps(step.parameters, indent=6, ensure_ascii=False)}\n"
            step_desc += f'   Description: "{step.description}"'
            steps_description.append(step_desc)

        steps_text = "\n".join(steps_description)
        reasons_text = json.dumps(approval_reasons, ensure_ascii=False)

        # User message with specific plan details
        user = f"""Steps:
{steps_text}

Approval reasons: {reasons_text}

Generate the approval question:"""

        return [
            {"role": "system", FIELD_CONTENT: hitl_plan_approval_system_prompt},
            {"role": "user", FIELD_CONTENT: user},
        ]

    def _build_prompt(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        personality_instruction: str | None = None,
    ) -> list[dict[str, str]]:
        """Build prompt messages for question generation.

        Uses OpenAI prompt caching pattern (system message >1024 tokens for auto-caching).

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            user_language: Target language code
            user_timezone: User's IANA timezone for datetime context
            personality_instruction: Optional LLM personality instruction

        Returns:
            List of message dicts for LLM invocation
        """
        # Load versioned prompt dynamically (cached by load_prompt LRU)
        from src.core.config import get_settings

        settings = get_settings()

        # Get default personality in user's language if none provided (i18n)
        default_personality = HitlMessages.get_default_personality(user_language)

        hitl_question_system_prompt = (
            format_with_current_datetime(
                load_prompt(
                    "hitl_question_generator_prompt",
                    version=settings.hitl_question_generator_prompt_version,
                ),
                user_timezone=user_timezone,
                user_language=user_language,
            )
            .replace(
                "{user_language}",
                user_language,
            )
            .replace(
                "{personnalite}",
                personality_instruction or default_personality,
            )
        )

        # User message with specific action details
        user = f"""Tool: {tool_name}
Arguments: {json.dumps(tool_args, indent=2, ensure_ascii=False)}

Generate the confirmation question:"""

        return [
            {"role": "system", FIELD_CONTENT: hitl_question_system_prompt},
            {"role": "user", FIELD_CONTENT: user},
        ]
