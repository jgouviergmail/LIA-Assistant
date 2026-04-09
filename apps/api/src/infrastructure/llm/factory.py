"""
LLM Factory with Multi-Provider Support.

Central factory for creating LLM instances with:
- Multi-provider support (OpenAI, Anthropic, DeepSeek, Perplexity, Ollama)
- Optional configuration overrides per instance
- Automatic metrics callback attachment
- Provider selection from settings (per LLM type)

Migration notes:
- Refactored to use ProviderAdapter for multi-provider support
- Preserves existing config override pattern (backward compatible)
- Preserves metrics callback attachment
- Return type changed from ChatOpenAI to BaseChatModel (more generic)
"""

from typing import TYPE_CHECKING, Any, Literal

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.config import settings
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_llm_config_for_agent
from src.infrastructure.llm.providers.adapter import ProviderAdapter
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.graphs.base_agent_builder import LLMConfig

logger = get_logger(__name__)


# ============================================================================
# Langfuse Integration (Phase 6 - LLM Observability)
# ============================================================================

# REMOVED (Phase 2.1.2 - LangFuse Duplication Fix):
#
# The _get_langfuse_callback_handler() function was removed because:
#
# 1. **Never called**: Grep shows no invocations in the codebase
# 2. **Signature mismatch**: Attempted to pass tags/metadata/trace_name to
#    create_callbacks(), but that method accepts zero parameters per SDK v3.9+
# 3. **Wrong pattern**: Similar to MetricsCallbackHandler, LangFuse callbacks
#    should be added DYNAMICALLY via create_instrumented_config(), not statically
#    at LLM creation time
# 4. **Duplication risk**: If used, would cause same accumulation bug as
#    MetricsCallbackHandler (llm.callbacks + config["callbacks"] merge)
#
# Correct pattern (aligned with Phase 2.1.1 Metrics fix):
#   - LLM instance: llm.callbacks = [] (empty, no static callbacks)
#   - Graph-level: create_instrumented_config() adds LangFuse handler
#   - Node-level: Filtering prevents handler accumulation (invoke_helpers.py + instrumentation.py)
#
# This ensures ONE LangFuse handler per request, regardless of call depth.
#
# References:
#   - callback_factory.py:253 (create_callbacks signature - zero params)
#   - instrumentation.py:63 (correct usage - create_instrumented_config)
#   - invoke_helpers.py:191-208 (LangFuse handler filtering)
#
# Date removed: 2025-01-10
# Reason: Dead code elimination + prevent potential duplication bug


LLMType = Literal[
    "router",
    "response",
    # New unified agent names (domain_agent pattern)
    "contact_agent",
    "email_agent",
    "event_agent",
    "file_agent",
    "task_agent",
    "weather_agent",
    "wikipedia_agent",
    "perplexity_agent",
    "place_agent",
    "route_agent",
    "query_agent",
    "brave_agent",
    "web_search_agent",
    "web_fetch_agent",
    "browser_agent",
    # Backward compatibility aliases (deprecated - will be removed in v4)
    "contacts_agent",  # @deprecated: use contact_agent
    "emails_agent",  # @deprecated: use email_agent
    "calendar_agent",  # @deprecated: use event_agent
    "drive_agent",  # @deprecated: use file_agent
    "tasks_agent",  # @deprecated: use task_agent
    "places_agent",  # @deprecated: use place_agent
    "routes_agent",  # @deprecated: use route_agent
    # System agents
    "query_analyzer",
    "planner",
    "hitl_classifier",
    "hitl_question_generator",
    "hitl_plan_approval_question_generator",
    "semantic_validator",  # Phase 2 OPTIMPLAN - Semantic validation
    "context_resolver",  # LLM-Native Semantic Architecture - Phase 0
    "semantic_pivot",  # Semantic Pivot: translate queries to English for embedding matching
    "memory_reference_resolution",  # Pre-planner entity resolution from memory facts
    "voice_comment",  # Voice comment generation for TTS
    "broadcast_translator",  # Broadcast message translation to user's language
    # Previously special types (now unified via LLM_DEFAULTS)
    "heartbeat_decision",  # Heartbeat: decide whether to send proactive notification
    "heartbeat_message",  # Heartbeat: generate proactive message
    "mcp_app_react_agent",  # MCP App: ReAct agent for MCP servers with interactive widgets
    "mcp_description",  # MCP: LLM-based domain description auto-generation
    "memory_extraction",  # Memory: extract facts from conversations
    "interest_extraction",  # Interests: extract user interests
    "interest_content",  # Interests: generate interest-based content
    "skill_description_translator",  # Skills: translate skill descriptions to all 6 languages
    "evaluator",  # Observability: LLM-as-Judge evaluation pipeline
    "compaction",  # Context compaction: summarize old conversation history
    "subagent",  # F6: Sub-agent delegated task execution
    # Personal Journals (Carnets de Bord)
    "journal_extraction",  # Journals: extract entries from conversations
    "journal_consolidation",  # Journals: periodic review and maintenance
    # ADR-062: Initiative Phase + MCP ReAct
    "initiative",  # Initiative: post-execution read-only enrichment evaluation
    "mcp_react_agent",  # MCP ReAct: iterative multi-step MCP interaction
    # ADR-070: ReAct Execution Mode
    "react_agent",  # ReAct Agent: autonomous reasoning loop with tools (pipeline alternative)
    # ADR-068: Psyche Engine
    "psyche_summary",  # Psyche: LLM-generated natural language state summary
    # 3-Phase Memory Reference Resolution
    "memory_reference_extraction",  # Memory: extract personal references from query for targeted search
]


def get_llm(
    llm_type: LLMType,
    config_override: "LLMConfig | LLMAgentConfig | None" = None,
) -> BaseChatModel:
    """
    Factory function to get LLM instance by type with optional config override.

    Multi-Provider Support:
    - Provider selection is configured per LLM type in settings
      (e.g., ROUTER_LLM_PROVIDER=openai, RESPONSE_LLM_PROVIDER=anthropic)
    - Supports OpenAI, Anthropic, DeepSeek, Perplexity, Ollama

    This factory supports per-agent LLM customization via config_override parameter.
    When config_override is provided, it overrides global settings for that LLM instance.
    Supports partial overrides (e.g., only override temperature, keep other settings).

    Configuration Patterns (Phase X - LLM Config Refactoring):
    - NEW: config_override as LLMAgentConfig (Pydantic model with validation)
    - OLD: config_override as TypedDict (backward compatible)
    - None: Uses centralized settings via get_llm_config_for_agent()

    Args:
        llm_type: Type of LLM ("router", "response", "contacts_agent", "planner", "hitl_classifier")
        config_override: Optional LLM configuration override. Accepts:
            - LLMAgentConfig (Pydantic model, recommended)
            - TypedDict (backward compatible)
            - None (uses settings)

    Returns:
        BaseChatModel: Configured LLM instance with metrics callback attached

    Raises:
        ValueError: If llm_type is invalid or provider/model combination is unsupported

    Examples:
        >>> # Default behavior (uses centralized config from settings)
        >>> router_llm = get_llm("router")

        >>> # NEW pattern: LLMAgentConfig override
        >>> from src.core.llm_agent_config import LLMAgentConfig
        >>> custom_config = LLMAgentConfig(
        ...     provider="openai",
        ...     model="gpt-4.1-mini",
        ...     temperature=0.9,
        ...     max_tokens=5000,
        ... )
        >>> custom_llm = get_llm("contacts_agent", config_override=custom_config)

        >>> # OLD pattern: TypedDict override (backward compatible)
        >>> contacts_llm = get_llm("contacts_agent", config_override={"temperature": 0.8})
    """
    logger.debug("llm_factory_request", llm_type=llm_type, has_override=config_override is not None)

    # ========================================================================
    # Phase X: LLM Config Refactoring - Support both old and new config types
    # ========================================================================

    # If config_override is None, create LLMAgentConfig from settings
    if config_override is None:
        agent_config = get_llm_config_for_agent(settings, llm_type)
        logger.debug(
            "llm_factory_using_centralized_config",
            llm_type=llm_type,
            provider=agent_config.provider,
            model=agent_config.model,
        )
    # If config_override is LLMAgentConfig (new pattern), use directly
    elif isinstance(config_override, LLMAgentConfig):
        agent_config = config_override
        logger.debug(
            "llm_factory_using_override_config_new",
            llm_type=llm_type,
            provider=agent_config.provider,
            model=agent_config.model,
        )
    # If config_override is TypedDict (old pattern), convert to LLMAgentConfig
    else:
        # Backward compatibility: TypedDict → LLMAgentConfig
        base_config = get_llm_config_for_agent(settings, llm_type)

        # Apply overrides from TypedDict
        override_dict = base_config.model_dump()
        for key in [
            "model",
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "reasoning_effort",  # OpenAI o-series/GPT-5 only
        ]:
            if key in config_override:
                value = config_override.get(key)  # type: ignore[misc]
                if value is not None:
                    override_dict[key] = value

        agent_config = LLMAgentConfig(**override_dict)
        logger.debug(
            "llm_factory_using_override_config_legacy",
            llm_type=llm_type,
            override_keys=list(config_override.keys()),  # type: ignore[union-attr]
            converted=True,
        )

    # 1. Extract provider from agent_config (no longer read from settings directly)
    provider = agent_config.provider

    # 2. Extract parameters from LLMAgentConfig
    merged_config = {
        "model": agent_config.model,
        "temperature": agent_config.temperature,
        "max_tokens": agent_config.max_tokens,
        "top_p": agent_config.top_p,
        "frequency_penalty": agent_config.frequency_penalty,
        "presence_penalty": agent_config.presence_penalty,
        "reasoning_effort": agent_config.reasoning_effort,  # OpenAI o-series/GPT-5 only
    }

    # 3. Determine streaming based on LLM type (default), but allow config_override
    streaming = llm_type in [
        "response",
        "hitl_question_generator",
        "hitl_plan_approval_question_generator",
    ]  # Response node + HITL question streaming (both tool and plan level)

    # Allow explicit streaming override via config_override (e.g., for reminders needing usage_metadata)
    if config_override is not None and "streaming" in config_override:
        streaming = bool(config_override.get("streaming"))  # type: ignore[union-attr]
        logger.debug("streaming_override_applied", llm_type=llm_type, streaming=streaming)

    # 4. Create LLM via ProviderAdapter
    llm = ProviderAdapter.create_llm(
        provider=provider,
        model=merged_config["model"],
        temperature=merged_config["temperature"],
        max_tokens=merged_config["max_tokens"],
        streaming=streaming,
        llm_type=llm_type,
        # Pass additional provider-specific params
        top_p=merged_config.get("top_p"),
        frequency_penalty=merged_config.get("frequency_penalty"),
        presence_penalty=merged_config.get("presence_penalty"),
        reasoning_effort=merged_config.get("reasoning_effort"),  # OpenAI o-series/GPT-5 only
        provider_config=agent_config.provider_config,  # Advanced JSON config
    )

    # 5. Attach callbacks (metrics + Langfuse)
    # Phase 6 - LLM Observability: Callbacks are added dynamically at invoke time
    #
    # IMPORTANT (Phase 2.1.1 - Metrics Double Counting Fix):
    # MetricsCallbackHandler is NOT attached here to prevent double counting.
    #
    # Background:
    #   - Previously, we attached a static MetricsCallbackHandler here: llm.callbacks = [MetricsCallbackHandler(...)]
    #   - We also add a dynamic MetricsCallbackHandler in enrich_config_with_node_metadata() (invoke_helpers.py)
    #   - LangChain automatically MERGES both sources: llm.callbacks + config["callbacks"]
    #   - Result: Two handlers invoked per LLM call → 2x token counting
    #
    # Root Cause:
    #   Even though enrich_config_with_node_metadata() filters existing MetricsCallbackHandler
    #   from config["callbacks"], it cannot filter llm.callbacks (instance attribute).
    #   LangChain's merge happens AFTER filtering, so both handlers execute.
    #
    # Solution:
    #   - MetricsCallbackHandler is added ONLY in enrich_config_with_node_metadata() (dynamic)
    #   - This allows proper node_name tracking (critical for token attribution)
    #   - No static callback needed here
    #
    # Note:
    #   Langfuse callbacks are also added dynamically via create_instrumented_config()
    #   to ensure proper session/user context propagation.
    #
    # References:
    #   - invoke_helpers.py lines 172-188 (dynamic MetricsCallbackHandler injection)
    #   - CORRECTIONS_HITL_TOKENS_SUMMARY.md (metrics discrepancy analysis)
    #   - LangChain callbacks merge behavior: https://python.langchain.com/docs/concepts/callbacks/
    callbacks: list[BaseCallbackHandler] = []

    llm.callbacks = callbacks

    # 6. Anthropic prompt caching: split system prompt into static + dynamic blocks
    #
    # Anthropic's prompt caching is PREFIX-based with EXACT byte matching:
    #   - The cache key = all content blocks up to and including the one with cache_control
    #   - If ANY byte differs in that prefix, it's a cache miss
    #
    # Problem: Our system prompts contain both static instructions AND dynamic context
    # (datetime, user_query, history) in a SINGLE text block. Putting cache_control on
    # this block means the entire text (including changing dynamic parts) is the cache
    # key → cache miss every time.
    #
    # Solution: Split system prompt at "--- DYNAMIC CONTEXT" marker into TWO blocks:
    #   Block 1: Static instructions (with cache_control) → CACHED across requests
    #   Block 2: Dynamic context (no cache_control) → fresh each request
    #
    # All 11 major prompts (query_analyzer, planner, response, hitl, router, etc.)
    # use this marker. Static portions are 67-90% of the prompt (well above the
    # 1024-token minimum for Anthropic caching).
    #
    # Instance-level patching survives .with_structured_output() because it reuses
    # the same ChatAnthropic instance internally.
    #
    # Cost: cache reads at 10% of input price, writes at 125% (amortized quickly).
    from src.core.constants import DYNAMIC_CONTEXT_MARKER

    if provider == "anthropic" and hasattr(llm, "_get_request_payload"):
        _original_get_request_payload = llm._get_request_payload

        def _get_request_payload_with_cache(input_: Any, stop: Any = None, **kwargs: Any) -> dict:
            # Remove cache_control from kwargs to prevent it going to last message
            kwargs.pop("cache_control", None)
            payload = _original_get_request_payload(input_, stop=stop, **kwargs)

            system = payload.get("system")
            if not system:
                return payload

            cache_ctrl = {"type": "ephemeral"}

            if isinstance(system, str):
                # Split at dynamic marker to separate cacheable static prefix
                marker_pos = system.find(DYNAMIC_CONTEXT_MARKER)
                if marker_pos > 0:
                    static_part = system[:marker_pos].rstrip()
                    dynamic_part = system[marker_pos:]
                    # Estimate tokens (~3.5 chars/token for mixed content)
                    estimated_tokens = len(static_part) // 3
                    if estimated_tokens < 4096:
                        logger.debug(
                            "anthropic_cache_prefix_small",
                            estimated_tokens=estimated_tokens,
                            chars=len(static_part),
                            min_required=4096,
                            msg="Static prefix likely below Opus 4096-token minimum — cache_control may be ignored",
                        )
                    payload["system"] = [
                        {"type": "text", "text": static_part, "cache_control": cache_ctrl},
                        {"type": "text", "text": dynamic_part},
                    ]
                else:
                    # No marker: cache entire system (best effort for small prompts)
                    payload["system"] = [
                        {"type": "text", "text": system, "cache_control": cache_ctrl}
                    ]
            elif isinstance(system, list):
                # Already structured as blocks: add cache_control to last block
                for block in reversed(system):
                    if isinstance(block, dict):
                        block["cache_control"] = cache_ctrl
                        break

            return payload

        llm._get_request_payload = _get_request_payload_with_cache  # type: ignore[method-assign]

    logger.info(
        "llm_created",
        llm_type=llm_type,
        provider=provider,
        model=merged_config["model"],
        streaming=streaming,
        factory_callbacks_count=len(callbacks),
        note="langfuse_callbacks_added_via_config_enrichment",
    )

    return llm
