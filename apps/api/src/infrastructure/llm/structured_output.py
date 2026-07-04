"""
Generic Structured Output Helper with Multi-Provider Support.

Provides a unified interface for obtaining structured (Pydantic) outputs from LLMs,
automatically handling provider-specific capabilities:
- Native structured output (OpenAI, Anthropic, DeepSeek) via .with_structured_output()
- JSON mode fallback (Ollama, Perplexity) via manual prompt engineering + parsing
- Strict mode for OpenAI (json_schema with strict=True) for compatible schemas

This abstraction ensures that all nodes (router, planner, etc.) can work seamlessly
with any LLM provider without knowing the underlying implementation details.

Architecture (LangChain v1.1 / LangGraph v1.0 Best Practices):
- Generic, reusable helper for all agents
- Provider-agnostic interface
- Explicit capability checking (no runtime provider detection)
- Conditional strict mode for 100% schema conformance (OpenAI only)
- Proper error handling and fallback mechanisms
- Type-safe with Pydantic models

Strict Mode (OpenAI only):
    When a schema is strict-compatible AND provider is OpenAI, uses:
    - method="json_schema" with strict=True
    - Guarantees 100% schema conformance
    - Incompatible schemas fallback to method="function_calling"

    Strict-incompatible patterns:
    - dict[str, Any] (additionalProperties)
    - >100 properties
    - >5 nesting levels
    - Open-ended unions

Usage:
    >>> from pydantic import BaseModel
    >>> class RouterDecision(BaseModel):
    ...     reasoning: str
    ...     next_node: str
    >>>
    >>> llm = get_llm("router")
    >>> result = get_structured_output(
    ...     llm=llm,
    ...     prompt="Route this message...",
    ...     schema=RouterDecision,
    ...     provider="ollama"
    ... )
    >>> print(result.next_node)  # Pydantic model instance
"""

import json
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

from src.core.config import settings
from src.core.field_names import FIELD_METADATA
from src.infrastructure.llm.invoke_helpers import (
    enrich_config_preserving_callbacks,
    enrich_config_with_node_metadata,
)
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_langgraph import (
    llm_reasoning_stream_double_call_total,
)

logger = get_logger(__name__)

# Generic type variable for Pydantic schema
T = TypeVar("T", bound=BaseModel)


# =============================================================================
# REASONING-STREAM NEGATIVE CACHE (double-call protection)
# =============================================================================
# On the BUFFERED structured-output paths (native with_structured_output and
# JSON-mode), a reasoning stream that yields no terminal output forces a
# SECOND full LLM call — the first call is paid and thrown away. Whether the
# stream capture works depends on the (provider, model, wrapper) combination
# and on the langchain-core version, so instead of a hardcoded capability
# matrix (which would rot), broken combinations are learned at runtime:
# after the first observed failure the stream attempt is skipped for that
# combination (at most ONE double call per combination per worker process).
#
# Fail-safe direction: a spurious entry only disables live reasoning for the
# combination until restart (degraded UX) — it can never add cost.
#
# NOTE: auto-tool misses (model declines the tool) are per-request variability,
# NOT structural — they must never enter this cache.

_reasoning_stream_broken_combos: set[tuple[str, str, str]] = set()


def _llm_model_id(llm: BaseChatModel) -> str:
    """Best-effort model identifier for cache keys and metrics labels."""
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    return str(model) if model else "unknown"


def _reasoning_stream_disabled(provider: str, model: str, path: str) -> bool:
    """True when the (provider, model, path) combination is known-broken."""
    return (provider, model, path) in _reasoning_stream_broken_combos


def _mark_reasoning_stream_broken(provider: str, model: str, path: str, schema_name: str) -> None:
    """Record a broken combination: warn, count, and negative-cache it."""
    _reasoning_stream_broken_combos.add((provider, model, path))
    llm_reasoning_stream_double_call_total.labels(provider=provider, model=model, path=path).inc()
    logger.warning(
        "structured_reasoning_stream_double_call",
        provider=provider,
        model=model,
        path=path,
        schema=schema_name,
        msg=(
            "Reasoning stream yielded no terminal output — a second full LLM "
            "call was made (double cost/latency). Live reasoning is now "
            "disabled for this (provider, model, path) combination."
        ),
    )


def reset_reasoning_stream_negative_cache() -> None:
    """Clear the negative cache (test isolation)."""
    _reasoning_stream_broken_combos.clear()


# =============================================================================
# STRICT MODE SCHEMA ANALYSIS (OpenAI json_schema strict=True)
# =============================================================================
# OpenAI's strict mode guarantees 100% schema conformance but has limitations:
# - No additionalProperties (rejects dict[str, Any])
# - Max 100 properties total
# - Max 5 nesting levels
# - All properties must be explicitly typed
#
# See: https://platform.openai.com/docs/guides/structured-outputs#supported-schemas


def _analyze_schema_strict_compatibility(schema: type[BaseModel]) -> tuple[bool, str]:
    """
    Analyze if a Pydantic schema is compatible with OpenAI strict mode.

    OpenAI's json_schema strict=True mode guarantees 100% schema conformance
    but rejects certain patterns. This function analyzes the schema to determine
    if it can use strict mode.

    Args:
        schema: Pydantic BaseModel class to analyze

    Returns:
        Tuple of (is_compatible, reason)
        - is_compatible: True if schema can use strict mode
        - reason: Human-readable reason (for logging/metrics)

    Incompatible patterns:
        - dict[str, Any] → additionalProperties in JSON schema
        - >100 properties → exceeds OpenAI limit
        - >5 nesting levels → exceeds OpenAI limit
        - Open-ended unions (Union[T, Any])
    """
    try:
        json_schema = schema.model_json_schema()
    except Exception as e:
        return False, f"schema_generation_error: {e}"

    # Check 1: additionalProperties in root or nested definitions
    if _schema_has_additional_properties(json_schema):
        return False, "contains_additional_properties"

    # Check 2: Total property count
    property_count = _count_total_properties(json_schema)
    if property_count > 100:
        return False, f"exceeds_property_limit: {property_count} > 100"

    # Check 3: Nesting depth
    max_depth = _get_max_nesting_depth(json_schema)
    if max_depth > 5:
        return False, f"exceeds_nesting_limit: {max_depth} > 5"

    return True, "compatible"


def _has_type_indicator(schema: dict[str, Any]) -> bool:
    """Return True if a JSON-schema fragment declares a concrete type.

    An ``Any`` / bare ``dict`` field is emitted by Pydantic as ``{}`` (or
    metadata-only, e.g. ``{"description": ...}``) — no type-bearing key. OpenAI
    strict mode rejects such open-ended fields, so the absence of every
    type-indicating keyword marks the fragment as strict-incompatible.

    Args:
        schema: A JSON-schema fragment for a single property.

    Returns:
        True if any type-indicating keyword is present.
    """
    return any(
        key in schema for key in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")
    )


def _schema_has_additional_properties(
    schema: dict[str, Any], visited: set[str] | None = None
) -> bool:
    """
    Recursively check if schema contains additionalProperties or open-ended objects.

    This pattern appears when Pydantic models contain dict[str, Any] fields.
    OpenAI strict mode rejects such schemas.

    IMPORTANT: OpenAI strict mode requires:
    - All object types must have "properties" defined
    - "additionalProperties": false must be set (no extra fields allowed)
    - All properties must be in "required" array

    A schema is incompatible if:
    - It has "additionalProperties": true (explicit)
    - It has "additionalProperties": {} (allows any type)
    - It has "type": "object" WITHOUT "properties" (implicit additionalProperties)
      This is how dict[str, Any] is represented in JSON schema

    Args:
        schema: JSON schema dict
        visited: Set of visited $ref definitions (cycle prevention)

    Returns:
        True if additionalProperties found or schema is open-ended, False otherwise
    """
    if visited is None:
        visited = set()

    # Check root level explicit additionalProperties
    if schema.get("additionalProperties") is True:
        return True

    # Check explicit additionalProperties: {} (allows any)
    additional_props = schema.get("additionalProperties")
    if isinstance(additional_props, dict) and not additional_props.get("type"):
        # additionalProperties: {} or additionalProperties with no constraints
        # This is typical for dict[str, Any]
        return True

    # CRITICAL FIX: Check for "type": "object" without "properties"
    # This is how dict[str, Any] is represented: {"type": "object"}
    # Without properties, it implicitly allows any properties (incompatible with strict mode)
    if schema.get("type") == "object" and "properties" not in schema:
        # This is an open-ended object (like dict[str, Any])
        # Skip if this is a $ref container (those are fine)
        if "$ref" not in schema:
            return True

    # Check properties recursively
    properties = schema.get("properties", {})
    for prop_schema in properties.values():
        if isinstance(prop_schema, dict):
            # An untyped property ({} or metadata-only) is how ``Any`` / bare
            # ``dict`` fields are emitted by Pydantic. It allows arbitrary content
            # and is incompatible with OpenAI strict mode (every field must be
            # explicitly typed). Caught here so such schemas route to
            # function_calling instead of the strict json_schema path.
            if not _has_type_indicator(prop_schema):
                return True
            if _schema_has_additional_properties(prop_schema, visited):
                return True

    # Check $defs (Pydantic v2 nested schemas)
    defs = schema.get("$defs", schema.get("definitions", {}))
    for def_name, def_schema in defs.items():
        if def_name in visited:
            continue
        visited.add(def_name)
        if isinstance(def_schema, dict):
            if _schema_has_additional_properties(def_schema, visited):
                return True

    # Check items (for arrays)
    items = schema.get("items")
    if isinstance(items, dict):
        if _schema_has_additional_properties(items, visited):
            return True

    # Check allOf, anyOf, oneOf
    for keyword in ("allOf", "anyOf", "oneOf"):
        sub_schemas = schema.get(keyword, [])
        for sub_schema in sub_schemas:
            if isinstance(sub_schema, dict):
                if _schema_has_additional_properties(sub_schema, visited):
                    return True

    return False


def _count_total_properties(schema: dict[str, Any], visited: set[str] | None = None) -> int:
    """
    Count total number of properties across all nested schemas.

    OpenAI strict mode limits total properties to 100.

    Args:
        schema: JSON schema dict
        visited: Set of visited $ref definitions (cycle prevention)

    Returns:
        Total property count
    """
    if visited is None:
        visited = set()

    count = 0

    # Count root properties
    properties = schema.get("properties", {})
    count += len(properties)

    # Count nested properties
    for prop_schema in properties.values():
        if isinstance(prop_schema, dict):
            count += _count_total_properties(prop_schema, visited)

    # Count $defs properties
    defs = schema.get("$defs", schema.get("definitions", {}))
    for def_name, def_schema in defs.items():
        if def_name in visited:
            continue
        visited.add(def_name)
        if isinstance(def_schema, dict):
            count += _count_total_properties(def_schema, visited)

    return count


def _get_max_nesting_depth(schema: dict[str, Any], current_depth: int = 0) -> int:
    """
    Calculate maximum nesting depth of schema.

    OpenAI strict mode limits nesting to 5 levels.

    Args:
        schema: JSON schema dict
        current_depth: Current depth in recursion

    Returns:
        Maximum nesting depth
    """
    max_depth = current_depth

    # Check properties
    properties = schema.get("properties", {})
    for prop_schema in properties.values():
        if isinstance(prop_schema, dict):
            depth = _get_max_nesting_depth(prop_schema, current_depth + 1)
            max_depth = max(max_depth, depth)

    # Check items (arrays add depth)
    items = schema.get("items")
    if isinstance(items, dict):
        depth = _get_max_nesting_depth(items, current_depth + 1)
        max_depth = max(max_depth, depth)

    return max_depth


def _is_v4_thinking_enabled(llm: BaseChatModel) -> bool:
    """Detect whether ``llm`` is a DeepSeek V4 instance with thinking ON.

    Inspects the model name and the ``extra_body`` attribute populated by
    our ``_create_deepseek_llm`` adapter. Used to route around the V4
    ``tool_choice`` restriction in ``get_structured_output``.

    Returns False (safe default) for any non-DeepSeek instance, any V3
    model, or any V4 instance with ``reasoning_effort=none`` (thinking
    explicitly disabled by the admin).
    """
    model_name = getattr(llm, "model_name", "") or ""
    if not model_name.startswith("deepseek-v4-"):
        return False

    extra_body = getattr(llm, "extra_body", None) or {}
    thinking_cfg = extra_body.get("thinking") if isinstance(extra_body, dict) else None
    if not isinstance(thinking_cfg, dict):
        # No explicit thinking config: V4 default is enabled.
        return True
    return thinking_cfg.get("type") == "enabled"


class StructuredOutputError(Exception):
    """Raised when structured output generation or parsing fails."""

    def __init__(
        self,
        message: str,
        provider: str,
        schema_name: str,
        raw_output: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.schema_name = schema_name
        self.raw_output = raw_output
        self.original_error = original_error


async def get_structured_output[T: BaseModel](
    llm: BaseChatModel,
    messages: list[BaseMessage] | ChatPromptTemplate,
    schema: type[T],
    provider: str,
    node_name: str | None = None,
    config: RunnableConfig | None = None,
    reasoning_emit: Callable[[str], None] | None = None,
    **invoke_kwargs: Any,
) -> T:
    """
    Get structured output from LLM with automatic provider-specific handling.

    This is the main entry point for obtaining Pydantic-typed responses from any LLM.
    It automatically selects the optimal approach based on provider capabilities:

    - **Native Structured Output (OpenAI, Anthropic, DeepSeek)**:
      Uses `.with_structured_output()` which directly parses Pydantic schemas
      via the provider's native API (e.g., OpenAI's /v1/chat/completions/parse)

    - **JSON Mode Fallback (Ollama, Perplexity)**:
      Augments the prompt with JSON schema instructions, uses `response_format="json_mode"`,
      then manually parses the JSON output into the Pydantic schema

    **Phase 2.1 - Token Tracking Alignment**:
    This function automatically enriches the config with node metadata to ensure
    callbacks receive the correct node_name for token tracking metrics.

    Args:
        llm: LangChain BaseChatModel instance (from get_llm factory)
        messages: Either a list of BaseMessage objects or a ChatPromptTemplate.
            If ChatPromptTemplate, it will be invoked to generate messages.
        schema: Pydantic BaseModel class defining the expected output structure
        provider: Provider name ("openai", "anthropic", "deepseek", "ollama", "perplexity")
        node_name: Optional node identifier for metrics. If None, extracted from config.
        config: Optional RunnableConfig (will be enriched with node_name metadata)
        **invoke_kwargs: Additional keyword arguments passed to llm.invoke()
            (e.g., temperature override, max_tokens override, etc.)

    Returns:
        T: Instance of the Pydantic schema with validated data

    Raises:
        StructuredOutputError: If output generation or parsing fails
        ValidationError: If JSON output doesn't match Pydantic schema

    Examples:
        >>> # Example 1: Native structured output (OpenAI) with node_name
        >>> from pydantic import BaseModel
        >>> class Decision(BaseModel):
        ...     reasoning: str
        ...     action: str
        >>>
        >>> llm = get_llm("router")
        >>> messages = [HumanMessage(content="What should I do?")]
        >>> result = get_structured_output(
        ...     llm=llm,
        ...     messages=messages,
        ...     schema=Decision,
        ...     provider="openai",
        ...     node_name="router",  # For token tracking
        ...     config=config
        ... )
        >>> print(result.action)  # "search"

        >>> # Example 2: Auto-detect node_name from config
        >>> result = get_structured_output(
        ...     llm=llm,
        ...     messages=messages,
        ...     schema=Decision,
        ...     provider="ollama",
        ...     config=config  # node_name extracted from config["metadata"]["langgraph_node"]
        ... )

        >>> # Example 3: Using ChatPromptTemplate
        >>> template = ChatPromptTemplate.from_messages([
        ...     ("system", "You are a helpful assistant"),
        ...     ("human", "{query}")
        ... ])
        >>> result = get_structured_output(
        ...     llm=llm,
        ...     messages=template.invoke({"query": "What's the weather?"}),
        ...     schema=Decision,
        ...     provider="anthropic",
        ...     node_name="response"
        ... )
    """
    schema_name = schema.__name__
    logger.debug(
        "structured_output_request",
        provider=provider,
        schema=schema_name,
        supports_native=settings.provider_supports_structured_output.get(provider, False),
    )

    # **Phase 2.1 - Token Tracking Alignment Fix**
    # Extract node_name from config if not provided explicitly
    if node_name is None and config:
        node_name = config.get(FIELD_METADATA, {}).get("langgraph_node", "unknown")
    elif node_name is None:
        node_name = "unknown"

    # Enrich config to ensure callbacks receive node_name.
    # This is CRITICAL for token tracking - without it, all metrics show node_name="unknown".
    #
    # When live reasoning is requested, the call is consumed via ``astream_events``
    # (see ``stream_reasoning_events``). The standard enrichment flattens
    # ``config["callbacks"]`` into a list, which severs the inherited CallbackManager's
    # parent linkage and makes ``astream_events`` over a tool-bound model double-fire
    # ``on_llm_end`` (double token/cost accounting). The manager-preserving variant keeps
    # a single firing while still setting node metadata + the per-node MetricsCallbackHandler.
    if reasoning_emit is not None:
        enriched_config = enrich_config_preserving_callbacks(config, node_name)
    else:
        enriched_config = enrich_config_with_node_metadata(config, node_name)

    # Merge enriched config into invoke_kwargs
    # This ensures the config is passed to ALL downstream LLM calls
    invoke_kwargs["config"] = enriched_config

    logger.debug(
        "structured_output_config_enriched",
        node_name=node_name,
        node_name_source="explicit" if node_name else "config_metadata",
    )

    # Convert ChatPromptTemplate to messages if needed
    if isinstance(messages, ChatPromptTemplate):
        # Assume template has already been invoked with variables
        # If not, this will raise a clear error
        final_messages = messages.messages
    else:
        final_messages = messages

    # Check provider capabilities
    supports_native = settings.provider_supports_structured_output.get(provider, False)

    # DeepSeek V4 with thinking enabled rejects forced ``tool_choice`` (the
    # mechanism used by LangChain's ``with_structured_output(method="function_calling")``).
    # The DeepSeek API surfaces this as ``400 - 'deepseek-reasoner does not support
    # this tool_choice'`` even when the request targets ``deepseek-v4-flash`` /
    # ``deepseek-v4-pro``, because thinking-mode requests are routed to a
    # reasoner-style backend internally. JSON mode (``response_format={"type":
    # "json_object"}``) does not use ``tool_choice`` and is accepted, so we
    # downgrade to the JSON-mode fallback path for this specific combination.
    # When thinking is OFF (``reasoning_effort=none``), V4 behaves like V3
    # ``deepseek-chat`` and the native ``function_calling`` path works.
    if supports_native and provider == "deepseek" and _is_v4_thinking_enabled(llm):
        logger.info(
            "deepseek_v4_thinking_structured_output_json_fallback",
            provider=provider,
            schema=schema_name,
            msg="DeepSeek V4 with thinking ON rejects forced tool_choice — "
            "downgrading to JSON-mode fallback for structured output",
        )
        supports_native = False

    try:
        if supports_native:
            # Path 1: Native structured output
            return await _get_native_structured_output(
                llm=llm,
                messages=final_messages,
                schema=schema,
                provider=provider,
                reasoning_emit=reasoning_emit,
                **invoke_kwargs,  # Now includes enriched config
            )
        else:
            # Path 2: JSON mode fallback
            return await _get_json_mode_fallback(
                llm=llm,
                messages=final_messages,
                schema=schema,
                provider=provider,
                reasoning_emit=reasoning_emit,
                **invoke_kwargs,  # Now includes enriched config
            )

    except Exception as e:
        logger.error(
            "structured_output_failed",
            provider=provider,
            schema=schema_name,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise


def _anthropic_thinking_on(llm: BaseChatModel) -> bool:
    """True when an Anthropic LLM has extended thinking enabled at construction.

    Anthropic rejects a forced ``tool_choice`` while thinking is enabled
    ("Thinking may not be enabled when tool_choice forces tool use" — HTTP 400),
    and ``with_structured_output`` forces the tool. So structured output on a
    thinking-enabled Claude must go through the auto-tool path instead.
    """
    thinking = getattr(llm, "thinking", None)
    return isinstance(thinking, dict) and thinking.get("type") in ("enabled", "adaptive")


async def _structured_via_auto_tool[T: BaseModel](
    llm: BaseChatModel,
    messages: list[BaseMessage],
    schema: type[T],
    reasoning_emit: Callable[[str], None] | None,
    **invoke_kwargs: Any,
) -> T | None:
    """Structured output via ``tool_choice="auto"`` instead of a forced tool.

    Used for two provider constraints that both break the normal
    ``with_structured_output`` (forced ``tool_choice``) path:

    - **OpenAI** (Responses API): a forced tool suppresses the streamed reasoning
      summary, and the streaming ``json_schema`` path rejects non-strict schemas
      (400). With ``auto`` the reasoning model thinks out loud (streamed live when
      ``reasoning_emit`` is set) and then emits the schema as a tool call.
    - **Anthropic**: a forced tool is *rejected* (400) whenever extended thinking
      is enabled. ``auto`` is the only way to get structured output on a
      thinking-enabled Claude (verified: no 400, valid tool call).

    A short directive is prepended so the model reliably calls the tool under
    ``auto``. When ``reasoning_emit`` is set the call is streamed (live reasoning);
    otherwise it is a plain ``ainvoke``. Returns ``None`` (the caller decides how
    to fall back) when the model declines the tool or the args fail validation.
    Never raises.

    Args:
        llm: The chat model (OpenAI ChatOpenAI or Anthropic ChatAnthropic).
        messages: The structured-output prompt messages.
        schema: Target Pydantic schema.
        reasoning_emit: Coalesced-reasoning callback, or ``None`` to skip streaming.
        **invoke_kwargs: Carries ``config`` for token tracking / tracing.

    Returns:
        A validated ``schema`` instance, or ``None`` to trigger the fallback.
    """
    schema_name = schema.__name__
    # NOTE (prompt impact): unlike the forced-tool path (``with_structured_output``,
    # which adds nothing to the prompt), ``tool_choice="auto"`` needs an explicit
    # nudge so the model reliably calls the tool. This prepends ONE extra
    # SystemMessage to the effective prompt — a deliberate, minor change to the
    # input of structured nodes (e.g. query_analyzer, planner). If a classification
    # drift is ever observed on the auto-tool path, this directive is the first
    # thing to revisit (wording/placement), not the schema itself.
    directive = SystemMessage(
        content=(
            f"Respond by calling the `{schema_name}` tool with your complete "
            "structured analysis. Reason about the input first, then call it."
        )
    )
    bound = llm.bind_tools([schema], tool_choice="auto")
    payload = [directive, *messages]
    try:
        if reasoning_emit is not None:
            from src.infrastructure.llm.reasoning_stream import stream_reasoning_events

            ai_msg = await stream_reasoning_events(
                bound,
                payload,
                emit=reasoning_emit,
                config=invoke_kwargs.get("config"),
            )
        else:
            ai_msg = await bound.ainvoke(payload, **invoke_kwargs)
    except Exception as exc:  # defensive: must never break the node
        logger.warning(
            "structured_auto_tool_failed",
            schema=schema_name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None

    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    if not tool_calls:
        return None
    try:
        return schema(**(tool_calls[0].get("args") or {}))
    except ValidationError as exc:
        logger.warning(
            "structured_auto_tool_parse_failed",
            schema=schema_name,
            error=str(exc),
        )
        return None


def _rescue_structured_from_text[T: BaseModel](
    raw_message: Any,
    schema: type[T],
    provider: str,
    schema_name: str,
) -> T | None:
    """Salvage a structured output from a model that answered in text.

    Some models resolve the conflict between a forced tool call and prompt
    instructions by answering with raw JSON text instead of calling the tool
    (observed on deepseek-v4-flash with legacy "Output JSON only" prompts —
    audit D5). When ``with_structured_output(include_raw=True)`` yields no
    parsed object, this helper tries to recover the payload from the raw
    ``AIMessage`` content before the caller gives up.

    Args:
        raw_message: The raw ``AIMessage`` returned by the model (``None``
            tolerated — returns ``None``).
        schema: Target Pydantic schema.
        provider: Provider name (logging only).
        schema_name: Schema name (logging only).

    Returns:
        A validated schema instance, or ``None`` when no JSON object could
        be extracted and validated from the text content.
    """
    text = coerce_content_to_text(getattr(raw_message, "content", None) or "").strip()
    if not text:
        return None

    # Strip markdown code fences if present (```json ... ```)
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()

    # Extract the outermost JSON object
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None

    try:
        payload = json.loads(text[start : end + 1])
        instance = schema.model_validate(payload)
    except (json.JSONDecodeError, ValidationError):
        return None

    logger.warning(
        "structured_output_rescued_from_text",
        provider=provider,
        schema=schema_name,
        msg="Model answered in raw JSON text instead of calling the forced tool — "
        "payload salvaged; check the prompt for legacy 'output JSON' instructions",
    )
    return instance


async def _get_native_structured_output[T: BaseModel](
    llm: BaseChatModel,
    messages: list[BaseMessage],
    schema: type[T],
    provider: str,
    reasoning_emit: Callable[[str], None] | None = None,
    **invoke_kwargs: Any,
) -> T:
    """
    Get structured output using provider's native Pydantic support.

    Uses LangChain's .with_structured_output() which leverages:
    - OpenAI: json_schema with strict=True (100% conformance) OR function_calling (flexible)
    - Anthropic: Native tool-based structured output
    - DeepSeek: Pydantic schema support (deepseek-chat only)

    **Strict Mode (OpenAI only)**:
    When schema is strict-compatible (no dict[str, Any], <100 props, <5 nesting),
    uses method="json_schema" with strict=True for guaranteed conformance.
    Otherwise falls back to method="function_calling".

    Args:
        llm: LangChain BaseChatModel instance
        messages: List of messages for the conversation
        schema: Pydantic BaseModel class
        provider: Provider name (for logging)
        **invoke_kwargs: Additional invocation parameters

    Returns:
        T: Validated Pydantic model instance

    Raises:
        StructuredOutputError: If LLM call or parsing fails
    """
    schema_name = schema.__name__

    # Auto-tool path (tool_choice="auto" instead of a forced tool):
    # - OpenAI + reasoning requested: a forced tool suppresses the streamed
    #   reasoning summary and the streaming json_schema path rejects non-strict
    #   schemas (400). Auto-tool preserves live reasoning; on miss we fall back to
    #   the buffered (non-streaming) path below.
    # - Anthropic with extended thinking ON: a forced tool is REJECTED (400) —
    #   auto-tool is the ONLY way to do structured output on a thinking-enabled
    #   Claude, so it applies regardless of reasoning_emit and there is no
    #   forced-tool fallback (it would 400).
    anthropic_thinking = provider == "anthropic" and _anthropic_thinking_on(llm)
    if (provider == "openai" and reasoning_emit is not None) or anthropic_thinking:
        auto_result = await _structured_via_auto_tool(
            llm=llm,
            messages=messages,
            schema=schema,
            reasoning_emit=reasoning_emit,
            **invoke_kwargs,
        )
        if auto_result is not None:
            logger.info("structured_auto_tool_success", provider=provider, schema=schema_name)
            return auto_result
        if anthropic_thinking:
            # The buffered with_structured_output path forces a tool → 400 with
            # thinking enabled. No safe fallback: fail with a clear error.
            raise StructuredOutputError(
                f"Anthropic auto-tool structured output produced no valid tool call "
                f"for {schema_name} (thinking enabled, forced-tool fallback unavailable)",
                provider=provider,
                schema_name=schema_name,
            )
        logger.info(
            "openai_auto_tool_stream_fell_back",
            schema=schema_name,
            msg="Model declined the tool or args invalid; using buffered structured output",
        )
        reasoning_emit = None  # buffered fallback must not re-enter streaming

    # Analyze schema for strict mode compatibility (OpenAI only)
    is_strict_compatible, strict_reason = _analyze_schema_strict_compatibility(schema)
    use_strict_mode = is_strict_compatible and provider == "openai"

    logger.debug(
        "using_native_structured_output",
        provider=provider,
        schema=schema_name,
        strict_compatible=is_strict_compatible,
        strict_reason=strict_reason,
        use_strict_mode=use_strict_mode,
    )

    try:
        # Create structured LLM wrapper with conditional strict mode
        #
        # P0 Migration - Strict Mode Conditionnel (Chantier 4):
        # - OpenAI with strict-compatible schema: method="json_schema", strict=True
        #   → Guarantees 100% schema conformance
        #   → Rejects additionalProperties, >100 props, >5 nesting
        #
        # - OpenAI with incompatible schema: method="function_calling"
        #   → More permissive, supports dict[str, Any]
        #   → Used for ExecutionStep.parameters and similar
        #
        # - Other providers (Anthropic, DeepSeek): method="function_calling"
        #   → Universal compatibility
        #
        # See: https://platform.openai.com/docs/guides/structured-outputs#supported-schemas
        if use_strict_mode:
            logger.info(
                "strict_mode_enabled",
                provider=provider,
                schema=schema_name,
            )
        elif provider == "openai" and not is_strict_compatible:
            logger.debug(
                "strict_mode_fallback",
                provider=provider,
                schema=schema_name,
                reason=strict_reason,
            )

        # Invoke LLM with messages (use async).
        # When a reasoning emitter is provided, consume the structured runnable
        # via astream_events so the model's chain-of-thought streams live to the
        # progress UI; the returned (root) output is the same parsed Pydantic
        # instance as ``ainvoke``. If streaming yields no terminal output the
        # call falls back to ``ainvoke`` — a SECOND full LLM call — so the
        # combination is negative-cached and the stream attempt is skipped on
        # subsequent calls (see _reasoning_stream_broken_combos).
        model_id = _llm_model_id(llm)
        if reasoning_emit is not None and _reasoning_stream_disabled(
            provider, model_id, "native_structured"
        ):
            reasoning_emit = None

        # Buffered invocations go through an include_raw wrapper so that when
        # the model answers in text instead of calling the forced tool (prompt
        # conflict — audit D5), the raw AIMessage is available for the
        # text-JSON rescue below instead of an opaque ``None``.
        async def _buffered_invoke() -> Any:
            raw_structured_llm = (
                llm.with_structured_output(
                    schema, method="json_schema", strict=True, include_raw=True
                )
                if use_strict_mode
                else llm.with_structured_output(schema, method="function_calling", include_raw=True)
            )
            bundle = await raw_structured_llm.ainvoke(messages, **invoke_kwargs)
            parsed = bundle.get("parsed") if isinstance(bundle, dict) else bundle
            if isinstance(parsed, schema):
                return parsed
            raw_message = bundle.get("raw") if isinstance(bundle, dict) else None
            rescued = _rescue_structured_from_text(raw_message, schema, provider, schema_name)
            if rescued is not None:
                return rescued
            raw_text = coerce_content_to_text(getattr(raw_message, "content", None) or "")
            raise StructuredOutputError(
                f"Native structured output returned no parsable payload for {schema_name} "
                f"(no tool call, text rescue failed)",
                provider=provider,
                schema_name=schema_name,
                raw_output=raw_text[:2000] or None,
            )

        result: Any
        if reasoning_emit is not None:
            from src.infrastructure.llm.reasoning_stream import stream_reasoning_events

            # Parsed-only wrapper for the streaming path (astream_events).
            structured_llm = (
                llm.with_structured_output(schema, method="json_schema", strict=True)
                if use_strict_mode
                else llm.with_structured_output(schema, method="function_calling")
            )
            result = await stream_reasoning_events(
                structured_llm,
                messages,
                emit=reasoning_emit,
                config=invoke_kwargs.get("config"),
            )
            if result is None:
                _mark_reasoning_stream_broken(provider, model_id, "native_structured", schema_name)
                result = await _buffered_invoke()
        else:
            result = await _buffered_invoke()

        # Both paths above guarantee a validated Pydantic instance
        if not isinstance(result, schema):
            raise StructuredOutputError(
                f"Native structured output returned unexpected type: {type(result)}",
                provider=provider,
                schema_name=schema_name,
            )

        logger.info(
            "native_structured_output_success",
            provider=provider,
            schema=schema_name,
            strict_mode=use_strict_mode,
        )

        return result

    except StructuredOutputError:
        # Already fully qualified (e.g. rescue failure with raw_output attached)
        # — do not re-wrap, it would drop the diagnostic payload.
        raise

    except ValidationError as e:
        # Pydantic validation failed (LLM output didn't match schema)
        raise StructuredOutputError(
            f"Pydantic validation failed for {schema_name}: {e}",
            provider=provider,
            schema_name=schema_name,
            original_error=e,
        ) from e

    except Exception as e:
        # LLM API error or other failure
        raise StructuredOutputError(
            f"Native structured output failed: {e}",
            provider=provider,
            schema_name=schema_name,
            original_error=e,
        ) from e


async def _get_json_mode_fallback[T: BaseModel](
    llm: BaseChatModel,
    messages: list[BaseMessage],
    schema: type[T],
    provider: str,
    reasoning_emit: Callable[[str], None] | None = None,
    **invoke_kwargs: Any,
) -> T:
    """
    Get structured output using JSON mode + manual parsing (fallback for Ollama, Perplexity).

    This approach:
    1. Augments the prompt with JSON schema instructions
    2. Configures LLM to use JSON mode (response_format="json")
    3. Manually parses the JSON string response
    4. Validates against the Pydantic schema

    Args:
        llm: LangChain BaseChatModel instance
        messages: List of messages for the conversation
        schema: Pydantic BaseModel class
        provider: Provider name (for logging)
        **invoke_kwargs: Additional invocation parameters

    Returns:
        T: Validated Pydantic model instance

    Raises:
        StructuredOutputError: If JSON parsing or Pydantic validation fails
    """
    schema_name = schema.__name__
    logger.debug(
        "using_json_mode_fallback",
        provider=provider,
        schema=schema_name,
    )

    # Generate JSON schema from Pydantic model
    # This uses Pydantic v2's model_json_schema() method
    json_schema = schema.model_json_schema()

    # Create augmented prompt with JSON instructions
    augmented_messages = _augment_messages_with_json_instructions(
        messages=messages,
        schema_name=schema_name,
        json_schema=json_schema,
    )

    try:
        # JSON Mode Fallback Strategy:
        # For providers that don't support native structured output, we use prompt engineering
        # to guide the LLM to produce JSON output.
        #
        # CRITICAL: Do NOT use response_format with these providers
        # LangChain's ChatOpenAI detects response_format and automatically tries to call
        # the /v1/chat/completions/parse endpoint (for OpenAI-style structured output),
        # which doesn't exist on providers that only implement basic OpenAI compatibility.
        #
        # Instead, we rely SOLELY on prompt engineering (the augmented system message
        # with explicit JSON schema instructions) to enforce JSON output.
        # This approach works universally across all providers.

        # Invoke LLM directly without response_format binding.
        # The augmented prompt is explicit enough to enforce JSON output.
        # When a reasoning emitter is provided, stream the model's live
        # chain-of-thought via astream_events (this is the proven DeepSeek-V4
        # thinking path — raw LLM, 336 reasoning deltas + parsable content). The
        # returned aggregated message exposes the same ``.content`` as ``ainvoke``.
        # If streaming yields no terminal output the call falls back to
        # ``ainvoke`` — a SECOND full LLM call — so the combination is
        # negative-cached and the stream attempt is skipped on subsequent calls.
        model_id = _llm_model_id(llm)
        if reasoning_emit is not None and _reasoning_stream_disabled(
            provider, model_id, "json_mode"
        ):
            reasoning_emit = None

        if reasoning_emit is not None:
            from src.infrastructure.llm.reasoning_stream import stream_reasoning_events

            response = await stream_reasoning_events(
                llm,
                augmented_messages,
                emit=reasoning_emit,
                config=invoke_kwargs.get("config"),
            )
            if response is None:
                _mark_reasoning_stream_broken(provider, model_id, "json_mode", schema_name)
                response = await llm.ainvoke(augmented_messages, **invoke_kwargs)
        else:
            response = await llm.ainvoke(augmented_messages, **invoke_kwargs)

        # Extract text content. Gemini 3.x returns content as list[dict] blocks;
        # coerce to text so len()/slicing/json.loads below stay str-safe.
        raw_output = (
            coerce_content_to_text(response.content)
            if hasattr(response, "content")
            else str(response)
        )

        logger.debug(
            "json_mode_raw_output",
            provider=provider,
            schema=schema_name,
            output_length=len(raw_output),
            output_preview=raw_output[:200],
        )

        # Parse JSON
        try:
            parsed_json = json.loads(raw_output)
        except json.JSONDecodeError as e:
            raise StructuredOutputError(
                f"Failed to parse JSON from {provider}: {e}",
                provider=provider,
                schema_name=schema_name,
                raw_output=raw_output,
                original_error=e,
            ) from e

        # Validate with Pydantic schema
        try:
            result = schema.model_validate(parsed_json)
        except ValidationError as e:
            raise StructuredOutputError(
                f"Pydantic validation failed for {schema_name}: {e}",
                provider=provider,
                schema_name=schema_name,
                raw_output=raw_output,
                original_error=e,
            ) from e

        logger.info(
            "json_mode_fallback_success",
            provider=provider,
            schema=schema_name,
        )

        return result

    except StructuredOutputError:
        # Re-raise our custom errors
        raise

    except Exception as e:
        # Catch-all for unexpected errors
        raise StructuredOutputError(
            f"JSON mode fallback failed: {e}",
            provider=provider,
            schema_name=schema_name,
            original_error=e,
        ) from e


def _augment_messages_with_json_instructions(
    messages: list[BaseMessage],
    schema_name: str,
    json_schema: dict[str, Any],
) -> list[BaseMessage]:
    """
    Augment conversation messages with JSON output instructions.

    Adds a system message with:
    - Clear instructions to output ONLY valid JSON
    - The JSON schema definition
    - Examples of correct formatting

    This ensures the LLM understands it must produce structured JSON output
    even when using providers that don't have native structured output support.

    Args:
        messages: Original conversation messages
        schema_name: Name of the Pydantic schema (for reference)
        json_schema: JSON schema dict (from Pydantic model_json_schema())

    Returns:
        list[BaseMessage]: Augmented messages with JSON instructions prepended
    """
    # Format JSON schema for readability
    schema_str = json.dumps(json_schema, indent=2)

    # Create instruction message
    instruction = f"""You MUST respond with ONLY valid JSON that matches this schema:

Schema name: {schema_name}

```json
{schema_str}
```

CRITICAL RULES:
1. Output ONLY valid JSON - no markdown, no explanations, no additional text
2. Follow the schema exactly - all required fields must be present
3. Use correct data types (strings, numbers, booleans, arrays, objects)
4. Do not include comments in the JSON

Example of CORRECT output:
{{"field1": "value1", "field2": 123, "field3": true}}

Example of INCORRECT output (DO NOT DO THIS):
Here is the JSON: {{"field1": "value1"}}
```json
{{"field1": "value1"}}
```

Begin your response now with ONLY the JSON object:"""

    # Create system message with instructions
    json_instruction_msg = SystemMessage(content=instruction)

    # Prepend instruction to existing messages
    # This ensures the instruction is the first thing the LLM sees
    return [json_instruction_msg] + messages


# ============================================================================
# Convenience Functions for Common Use Cases
# ============================================================================


async def get_structured_output_with_retry[T: BaseModel](
    llm: BaseChatModel,
    messages: list[BaseMessage] | ChatPromptTemplate,
    schema: type[T],
    provider: str,
    node_name: str | None = None,
    config: RunnableConfig | None = None,
    max_retries: int = 3,
    **invoke_kwargs: Any,
) -> T:
    """
    Get structured output with automatic retry on transient failures.

    Useful for production environments where LLM API calls may occasionally fail
    due to network issues, rate limits, or temporary service outages.

    Args:
        llm: LangChain BaseChatModel instance
        messages: Messages or template for the conversation
        schema: Pydantic BaseModel class
        provider: Provider name
        node_name: Optional node identifier for metrics
        config: Optional RunnableConfig (will be enriched with node_name metadata)
        max_retries: Maximum number of retry attempts (default: 3)
        **invoke_kwargs: Additional invocation parameters

    Returns:
        T: Validated Pydantic model instance

    Raises:
        StructuredOutputError: If all retries fail
    """
    schema_name = schema.__name__
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            return await get_structured_output(
                llm=llm,
                messages=messages,
                schema=schema,
                provider=provider,
                node_name=node_name,
                config=config,
                **invoke_kwargs,
            )
        except StructuredOutputError as e:
            last_error = e
            logger.warning(
                "structured_output_retry",
                attempt=attempt,
                max_retries=max_retries,
                provider=provider,
                schema=schema_name,
                error=str(e),
            )

            if attempt == max_retries:
                # Final attempt failed
                logger.error(
                    "structured_output_all_retries_failed",
                    provider=provider,
                    schema=schema_name,
                    attempts=max_retries,
                )
                raise

    # Should never reach here, but type checker needs it
    if last_error:
        raise last_error
    raise StructuredOutputError(
        "Unexpected error in retry loop",
        provider=provider,
        schema_name=schema_name,
    )
