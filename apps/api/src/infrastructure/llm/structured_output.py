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
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

from src.core.config import settings
from src.core.field_names import FIELD_METADATA
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Generic type variable for Pydantic schema
T = TypeVar("T", bound=BaseModel)


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

    # Enrich config to ensure callbacks receive node_name
    # This is CRITICAL for token tracking - without it, all metrics show node_name="unknown"
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

    try:
        if supports_native:
            # Path 1: Native structured output
            return await _get_native_structured_output(
                llm=llm,
                messages=final_messages,
                schema=schema,
                provider=provider,
                **invoke_kwargs,  # Now includes enriched config
            )
        else:
            # Path 2: JSON mode fallback
            return await _get_json_mode_fallback(
                llm=llm,
                messages=final_messages,
                schema=schema,
                provider=provider,
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


async def _get_native_structured_output[T: BaseModel](
    llm: BaseChatModel,
    messages: list[BaseMessage],
    schema: type[T],
    provider: str,
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
            structured_llm = llm.with_structured_output(schema, method="json_schema", strict=True)
            logger.info(
                "strict_mode_enabled",
                provider=provider,
                schema=schema_name,
            )
        else:
            structured_llm = llm.with_structured_output(schema, method="function_calling")
            if provider == "openai" and not is_strict_compatible:
                logger.debug(
                    "strict_mode_fallback",
                    provider=provider,
                    schema=schema_name,
                    reason=strict_reason,
                )

        # Invoke LLM with messages (use async)
        result = await structured_llm.ainvoke(messages, **invoke_kwargs)

        # LangChain guarantees result is already a Pydantic instance
        # Type checker hint (result should already be type T)
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

        # Invoke LLM directly without response_format binding
        # The augmented prompt is explicit enough to enforce JSON output
        response = await llm.ainvoke(augmented_messages, **invoke_kwargs)

        # Extract text content
        raw_output = response.content if hasattr(response, "content") else str(response)

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
