"""
OpenAI Responses API Adapter.

Provides a LangChain-compatible wrapper around OpenAI's Responses API,
which offers 40-80% better cache utilization compared to Chat Completions.

Architecture:
- Extends LangChain BaseChatModel for compatibility with existing infrastructure
- Uses OpenAI SDK's responses.create() endpoint
- Automatic fallback to Chat Completions on API errors (404, unsupported model)
- Converts LangChain messages to Responses API format and back

Key Features:
- Prompt caching via `store=True` and `prompt_cache_key`
- Multi-turn conversation via `previous_response_id`
- Native tool support
- Streaming support

Usage:
    >>> from src.infrastructure.llm.providers.responses_adapter import ResponsesLLM
    >>> llm = ResponsesLLM(model="gpt-4.1-mini", api_key="sk-...")
    >>> result = llm.invoke([HumanMessage(content="Hello")])

References:
    - https://platform.openai.com/docs/api-reference/responses
    - https://developers.openai.com/blog/responses-api/
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Iterator
from typing import Any, Literal

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from openai import NotFoundError, OpenAI
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, PrivateAttr, ValidationError

from src.core.constants import REASONING_MODELS_PATTERN
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# Models eligible for Responses API (GPT-4.1+ series, GPT-5.x, o-series)
RESPONSES_API_ELIGIBLE_MODELS = {
    # GPT-4.1 series
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-nano-2025-04-14",
    # GPT-5 series
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.1",
    "gpt-5.2",
    "gpt-5.1-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    "gpt-5-chat-latest",
    "gpt-5.1-chat-latest",
    "gpt-5.2-chat-latest",
    "gpt-5.3-chat-latest",
    # o-series reasoning models
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
}


def is_responses_api_eligible(model: str) -> bool:
    """
    Check if a model is eligible for Responses API.

    Args:
        model: Model identifier

    Returns:
        True if model supports Responses API
    """
    model_lower = model.lower()
    # Check exact match first
    if model_lower in RESPONSES_API_ELIGIBLE_MODELS:
        return True

    # Check versioned model match (e.g., "gpt-4.1-mini-2025-04-14")
    # Only match if model starts with eligible name followed by "-YYYY" (date pattern)
    for eligible in RESPONSES_API_ELIGIBLE_MODELS:
        if model_lower.startswith(eligible + "-"):
            # Verify it's a date suffix (e.g., "-2025-04-14") not another model variant
            suffix = model_lower[len(eligible) + 1 :]
            if suffix and suffix[0].isdigit():
                return True
    return False


class ResponsesLLM(BaseChatModel):
    """
    LangChain-compatible wrapper for OpenAI Responses API.

    Provides automatic caching (40-80% improvement), multi-turn support,
    and native tool integration. Falls back to Chat Completions on errors.

    Attributes:
        model: OpenAI model identifier (gpt-4.1-mini, gpt-5, etc.)
        api_key: OpenAI API key
        organization_id: OpenAI organization ID (optional)
        temperature: Sampling temperature (0.0-2.0)
        max_tokens: Maximum output tokens
        top_p: Nucleus sampling parameter
        store: Enable response storage for caching (default: True)
        fallback_enabled: Fall back to Chat Completions on error (default: True)
    """

    model: str = Field(description="OpenAI model identifier")
    api_key: str = Field(default="", description="OpenAI API key")
    organization_id: str = Field(default="", description="OpenAI organization ID")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, description="Max output tokens")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    store: bool = Field(default=True, description="Enable caching via storage")
    fallback_enabled: bool = Field(
        default=True, description="Fall back to Chat Completions on error"
    )
    streaming: bool = Field(default=False, description="Enable streaming")
    reasoning_effort: str | None = Field(
        default=None,
        description="Reasoning effort for reasoning models (o-series, gpt-5): minimal, low, medium, high",
    )

    # Private attributes
    _client: OpenAI = PrivateAttr()
    _last_response_id: str | None = PrivateAttr(default=None)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = OpenAI(
            api_key=self.api_key or None,
            organization=self.organization_id or None,
        )
        self._last_response_id = None

    @property
    def _llm_type(self) -> str:
        return "openai-responses"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        params = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "store": self.store,
        }
        if self.reasoning_effort:
            params["reasoning_effort"] = self.reasoning_effort
        return params

    def _is_reasoning_model(self) -> bool:
        """Check if model is a reasoning model (o-series, gpt-5) that doesn't support sampling params."""
        return bool(re.match(REASONING_MODELS_PATTERN, self.model, re.IGNORECASE))

    def _supports_sampling_params(self) -> bool:
        """Check if sampling params (temperature, top_p) are supported.

        Standard models always support them. Reasoning models don't, EXCEPT
        gpt-5.1/5.2+ with reasoning_effort='none' which disables reasoning
        and re-enables sampling parameters per OpenAI API docs.
        """
        if not self._is_reasoning_model():
            return True
        # gpt-5.1/5.2+ with effort=none behave as standard models
        is_gpt51_plus = bool(re.match(r"^gpt-5\.[1-9]", self.model, re.IGNORECASE))
        return is_gpt51_plus and self.reasoning_effort == "none"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate response using Responses API with fallback.

        Args:
            messages: LangChain messages
            stop: Stop sequences (not supported by Responses API)
            run_manager: Callback manager
            **kwargs: Additional parameters

        Returns:
            ChatResult with generated response
        """
        # Check model eligibility
        if not is_responses_api_eligible(self.model):
            logger.info(
                "responses_api_model_not_eligible",
                model=self.model,
                msg="Model not eligible for Responses API, using Chat Completions",
            )
            return self._fallback_to_chat_completions(messages, stop, run_manager, **kwargs)

        # Tool calling: route to Chat Completions which has full tool_calls support.
        # The Responses API path does not yet extract function_call output items
        # from responses, so tool_calls would be silently lost.
        if kwargs.get("tools"):
            logger.info(
                "responses_api_tools_chat_completions_redirect",
                model=self.model,
                tool_count=len(kwargs["tools"]),
                msg="Tools provided, using Chat Completions for full tool_calls support",
            )
            return self._fallback_to_chat_completions(messages, stop, run_manager, **kwargs)

        # Check if messages have user input (Responses API requires 'input' parameter)
        # System-only messages would result in empty input, causing API error
        has_user_input = any(
            isinstance(msg, HumanMessage | AIMessage | ToolMessage) for msg in messages
        )
        if not has_user_input:
            logger.debug(
                "responses_api_no_user_input",
                model=self.model,
                message_count=len(messages),
                msg="No user input in messages, using Chat Completions directly",
            )
            return self._fallback_to_chat_completions(messages, stop, run_manager, **kwargs)

        try:
            return self._call_responses_api(messages, stop, run_manager, **kwargs)
        except NotFoundError as e:
            # API not available for this model/region - fallback
            if self.fallback_enabled:
                logger.warning(
                    "responses_api_not_found_fallback",
                    model=self.model,
                    error=str(e),
                    msg="Responses API returned 404, falling back to Chat Completions",
                )
                return self._fallback_to_chat_completions(messages, stop, run_manager, **kwargs)
            raise
        except Exception as e:
            if self.fallback_enabled:
                logger.warning(
                    "responses_api_error_fallback",
                    model=self.model,
                    error=str(e),
                    error_type=type(e).__name__,
                    msg="Responses API error, falling back to Chat Completions",
                )
                return self._fallback_to_chat_completions(messages, stop, run_manager, **kwargs)
            raise

    def _call_responses_api(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Call OpenAI Responses API directly.

        Args:
            messages: LangChain messages
            stop: Stop sequences (ignored - not supported)
            run_manager: Callback manager
            **kwargs: Additional parameters

        Returns:
            ChatResult with generated response
        """
        # Convert messages to Responses API format
        input_items, instructions = self._convert_messages_to_input(messages)

        # Generate cache key from input for prompt caching
        cache_key = self._generate_cache_key(messages)

        # Build API call parameters
        api_params: dict[str, Any] = {
            "model": self.model,
            "store": self.store,
            "prompt_cache_key": cache_key,
        }

        # Sampling params: standard models always, gpt-5.1/5.2 with effort=none
        if self._supports_sampling_params():
            api_params["temperature"] = self.temperature
            api_params["top_p"] = self.top_p

        # Reasoning effort for reasoning models (Responses API syntax)
        # Default to "low" if unconfigured, to prevent the model from consuming
        # the entire output budget on thinking tokens and producing empty content
        if self._is_reasoning_model():
            effort = self.reasoning_effort or "low"
            api_params["reasoning"] = {"effort": effort}
            if not self.reasoning_effort:
                logger.info(
                    "reasoning_effort_defaulted",
                    model=self.model,
                    default_effort="low",
                    msg="No reasoning_effort configured for reasoning model, defaulting to 'low'",
                )

        # Add input
        api_params["input"] = input_items  # Always send (guard at L229 ensures non-empty)

        # Add instructions (system message)
        if instructions:
            api_params["instructions"] = instructions

        # Add max_tokens if specified
        if self.max_tokens:
            api_params["max_output_tokens"] = self.max_tokens

        # Add previous response ID for multi-turn
        if self._last_response_id and kwargs.get("use_previous_response", False):
            api_params["previous_response_id"] = self._last_response_id

        # Add tools if provided (from bind_tools)
        tools = kwargs.get("tools")
        if tools:
            api_params["tools"] = self._convert_tools(tools)
            tool_choice = kwargs.get("tool_choice", "auto")
            if tool_choice:
                api_params["tool_choice"] = tool_choice

        logger.debug(
            "responses_api_call",
            model=self.model,
            input_items_count=len(input_items) if input_items else 0,
            has_instructions=bool(instructions),
            has_tools=bool(tools),
            tool_choice=kwargs.get("tool_choice"),
            store=self.store,
            cache_key=cache_key[:20] + "..." if cache_key else None,
            reasoning_effort=self.reasoning_effort,
        )

        # Call Responses API
        response = self._client.responses.create(**api_params)

        # Store response ID for multi-turn
        self._last_response_id = response.id

        # Convert response to LangChain format
        content = self._extract_response_content(response)

        # Extract usage metadata from response for token tracking
        usage_metadata = None
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            cached_tokens = 0
            if hasattr(usage, "input_tokens_details") and usage.input_tokens_details:
                cached_tokens = getattr(usage.input_tokens_details, "cached_tokens", 0) or 0
            usage_metadata = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_token_details": {"cache_read": cached_tokens},
            }

        logger.info(
            "responses_api_success",
            model=self.model,
            response_id=response.id,
            output_length=len(content) if content else 0,
            cached=getattr(response, "cached", None),
            usage=usage_metadata,
        )

        # Create AIMessage with usage metadata for token tracking
        ai_message = AIMessage(content=content)
        if usage_metadata:
            ai_message.usage_metadata = usage_metadata
            ai_message.response_metadata = {"model_name": self.model}

        generation = ChatGeneration(
            message=ai_message,
            generation_info={
                "response_id": response.id,
                "model": self.model,
                "api": "responses",
            },
        )

        return ChatResult(generations=[generation])

    def _fallback_to_chat_completions(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Fallback to Chat Completions API.

        Args:
            messages: LangChain messages
            stop: Stop sequences
            run_manager: Callback manager
            **kwargs: Additional parameters

        Returns:
            ChatResult from Chat Completions
        """
        # Convert messages to Chat Completions format
        # CRITICAL: Preserve tool_calls from AIMessage and tool_call_id from ToolMessage
        chat_messages = []
        for msg in messages:
            role = self._get_message_role(msg)
            chat_msg: dict[str, Any] = {"role": role, "content": msg.content or ""}

            # Handle AIMessage with tool_calls
            if isinstance(msg, AIMessage) and msg.tool_calls:
                # Convert LangChain tool_calls format to OpenAI format
                chat_msg["content"] = msg.content or None  # Can be null when tool_calls present
                chat_msg["tool_calls"] = [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("args", {})),
                        },
                    }
                    for i, tc in enumerate(msg.tool_calls)
                ]

            # Handle ToolMessage
            if isinstance(msg, ToolMessage):
                chat_msg["tool_call_id"] = msg.tool_call_id

            chat_messages.append(chat_msg)

        api_params: dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
        }

        # Sampling params: standard models always, gpt-5.1/5.2 with effort=none
        if self._supports_sampling_params():
            api_params["temperature"] = self.temperature
            api_params["top_p"] = self.top_p

        # Reasoning models always use max_completion_tokens (even with effort=none)
        if self.max_tokens:
            if self._is_reasoning_model():
                api_params["max_completion_tokens"] = self.max_tokens
            else:
                api_params["max_tokens"] = self.max_tokens

        # Reasoning effort for reasoning models (Chat Completions syntax)
        # Default to "low" if unconfigured (same guard as Responses API path)
        if self._is_reasoning_model():
            api_params["reasoning_effort"] = self.reasoning_effort or "low"

        if stop:
            api_params["stop"] = stop

        # Add tools if provided (from bind_tools)
        tools = kwargs.get("tools")
        if tools:
            api_params["tools"] = tools
            tool_choice = kwargs.get("tool_choice", "auto")
            if tool_choice:
                api_params["tool_choice"] = tool_choice

        response = self._client.chat.completions.create(**api_params)

        # Handle tool calls in response
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = None

        if hasattr(message, "tool_calls") and message.tool_calls:
            # LangChain format: {"id": str, "name": str, "args": dict}
            # NOT OpenAI format: {"id": str, "type": "function", "function": {...}}
            tool_calls = []
            for tc in message.tool_calls:
                # Parse arguments from JSON string to dict
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": args,
                    }
                )

        logger.info(
            "chat_completions_fallback_success",
            model=self.model,
            response_id=response.id,
            output_length=len(content),
            has_tool_calls=bool(tool_calls),
        )

        # Create AIMessage with tool_calls via constructor (not attribute assignment!)
        # LangChain requires tool_calls to be passed at construction time
        ai_message = AIMessage(content=content, tool_calls=tool_calls or [])

        generation = ChatGeneration(
            message=ai_message,
            generation_info={
                "response_id": response.id,
                "model": self.model,
                "api": "chat_completions",
                "fallback": True,
            },
        )

        return ChatResult(generations=[generation])

    def _convert_messages_to_input(
        self, messages: list[BaseMessage]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Convert LangChain messages to Responses API input format.

        Responses API uses:
        - instructions: System prompt (separate from input)
        - input: List of message items or single string

        Args:
            messages: LangChain messages

        Returns:
            Tuple of (input_items, instructions)
        """
        instructions: str | None = None
        input_items: list[dict[str, Any]] = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                # System messages become instructions
                instructions = str(msg.content)
            elif isinstance(msg, HumanMessage):
                input_items.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": self._convert_content_for_responses_api(msg.content),
                    }
                )
            elif isinstance(msg, AIMessage):
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": str(msg.content),
                    }
                )
            elif isinstance(msg, ToolMessage):
                # Tool results
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg.tool_call_id,
                        "output": str(msg.content),
                    }
                )

        return input_items, instructions

    @staticmethod
    def _convert_content_for_responses_api(
        content: str | list[dict[str, Any]],
    ) -> str | list[dict[str, Any]]:
        """
        Convert LangChain message content to Responses API format.

        LangChain multimodal format:
          [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:...", "detail": "auto"}}]

        Responses API format:
          [{"type": "input_text", "text": "..."}, {"type": "input_image", "image_url": "data:...", "detail": "auto"}]

        For plain string content, returns the string unchanged.
        """
        if isinstance(content, str):
            return content

        if not isinstance(content, list):
            return str(content)

        converted: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                converted.append({"type": "input_text", "text": str(block)})
                continue

            block_type = block.get("type", "")

            if block_type == "text":
                converted.append(
                    {
                        "type": "input_text",
                        "text": block.get("text", ""),
                    }
                )
            elif block_type == "image_url":
                image_data = block.get("image_url", {})
                if isinstance(image_data, str):
                    converted.append(
                        {
                            "type": "input_image",
                            "image_url": image_data,
                        }
                    )
                elif isinstance(image_data, dict):
                    item: dict[str, Any] = {
                        "type": "input_image",
                        "image_url": image_data.get("url", ""),
                    }
                    if "detail" in image_data:
                        item["detail"] = image_data["detail"]
                    converted.append(item)
            else:
                # Pass through unknown types as-is
                converted.append(block)

        return converted

    def _extract_response_content(self, response: Any) -> str:
        """
        Extract text content from Responses API response.

        Responses API returns polymorphic items. We extract text from message items.

        Args:
            response: OpenAI Response object

        Returns:
            Extracted text content
        """
        content_parts: list[str] = []

        # Check for output_text helper (if available)
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text

        # Extract from output items
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "type"):
                    if item.type == "message":
                        # Message item - extract content
                        if hasattr(item, "content") and item.content:
                            for content_item in item.content:
                                if hasattr(content_item, "text"):
                                    content_parts.append(content_item.text)
                    elif item.type == "text":
                        # Direct text item
                        if hasattr(item, "text"):
                            content_parts.append(item.text)

        return "\n".join(content_parts)

    def _get_message_role(
        self, message: BaseMessage
    ) -> Literal["system", "user", "assistant", "tool"]:
        """Get role string for a message."""
        if isinstance(message, SystemMessage):
            return "system"
        elif isinstance(message, HumanMessage):
            return "user"
        elif isinstance(message, ToolMessage):
            return "tool"
        else:
            return "assistant"

    def _generate_cache_key(self, messages: list[BaseMessage]) -> str:
        """
        Generate a cache key for prompt caching based on STATIC PREFIX only.

        OpenAI's prompt caching works on PREFIX matching - the first 1024+ identical
        tokens are cached. The `prompt_cache_key` helps route requests with similar
        prefixes to the same cache node.

        Strategy:
        - Extract only the STATIC PORTION of system messages (before dynamic content)
        - Dynamic content markers: "## DYNAMIC CONTEXT", "## INPUT CONTEXT (Dynamic"
        - This ensures requests with the same prompt type get the same cache key
        - Different user messages don't affect the cache key (they're handled by prefix matching)

        Args:
            messages: LangChain messages

        Returns:
            SHA256 hash of static system message prefix (32 chars)
        """
        static_parts = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                # Extract static prefix from system message
                content = str(msg.content)
                static_prefix = self._extract_static_prefix(content)
                static_parts.append(f"system:{static_prefix}")
            # Skip user/assistant messages - they're dynamic by nature
            # The prefix matching handles them automatically

        if not static_parts:
            # Fallback: no system message, use model name for minimal grouping
            static_parts.append(f"model:{self.model}")

        combined = "|".join(static_parts)
        cache_key = hashlib.sha256(combined.encode()).hexdigest()[:32]

        logger.debug(
            "cache_key_generated",
            cache_key=cache_key[:12] + "...",
            static_parts_count=len(static_parts),
            static_prefix_length=len(combined),
        )

        return cache_key

    def _extract_static_prefix(self, content: str) -> str:
        """
        Extract the static prefix from a prompt, stopping at dynamic content markers.

        Dynamic content markers (in order of precedence):
        - "## DYNAMIC CONTEXT" - Planner and Response prompts
        - "## INPUT CONTEXT (Dynamic" - Router prompt
        - "---\\n## DYNAMIC" - Alternative format

        Everything BEFORE these markers is considered static and cacheable.

        Args:
            content: Full prompt content

        Returns:
            Static prefix (content before first dynamic marker)
        """
        # Dynamic content markers - order matters (most specific first)
        # Must match the actual separators used in prompt .txt files
        from src.core.constants import DYNAMIC_CONTEXT_MARKER

        dynamic_markers = [
            DYNAMIC_CONTEXT_MARKER,  # Standard separator in all prompt templates
            "## DYNAMIC CONTEXT",  # Legacy format (kept for backward compat)
            "## INPUT CONTEXT (Dynamic",
            "<TemporalContext>",  # Fallback marker if section headers not found
            "<UserRequest>",  # Another fallback
        ]

        # Find the earliest dynamic marker
        earliest_pos = len(content)
        for marker in dynamic_markers:
            pos = content.find(marker)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos

        # Extract static prefix (everything before the marker)
        static_prefix = content[:earliest_pos].strip()

        # Truncate to reasonable length for hashing (first 8KB should be enough)
        # This covers all static instructions + semi-static context (catalogue)
        max_prefix_length = 8192
        if len(static_prefix) > max_prefix_length:
            static_prefix = static_prefix[:max_prefix_length]

        return static_prefix

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """
        Convert tools to Responses API format.

        Supports:
        - Dict format (from bind_tools/_format_tools_for_binding): passed through
        - LangChain tool objects (with .name, .description): converted

        Args:
            tools: Tool definitions in various formats

        Returns:
            Responses API tool format
        """
        converted = []
        for tool in tools:
            if isinstance(tool, dict):
                # Already in dict format (from bind_tools) — pass through
                converted.append(tool)
            elif hasattr(tool, "name") and hasattr(tool, "description"):
                # LangChain tool object — convert to dict
                tool_def: dict[str, Any] = {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                    },
                }
                if hasattr(tool, "args_schema") and tool.args_schema:
                    tool_def["function"]["parameters"] = tool.args_schema.model_json_schema()
                converted.append(tool_def)
            else:
                logger.warning(
                    "responses_api_unknown_tool_format",
                    tool_type=type(tool).__name__,
                )
        return converted

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """
        Stream response using Responses API with true streaming support.

        CRITICAL: Must return ChatGenerationChunk (not ChatGeneration) to support
        LangChain's streaming aggregation which uses += operator on chunks.
        ChatGeneration does NOT support +=, causing TypeError.

        Uses OpenAI Responses API stream=True for real-time token delivery.
        Falls back to Chat Completions streaming if Responses API fails.
        """
        # WORKAROUND: Use Chat Completions for streaming
        # DEBUG: Log that _stream is being called
        logger.info("responses_llm_stream_called", model=self.model, messages_count=len(messages))

        # Responses API `instructions` parameter doesn't make the model follow
        # few-shot formatting as well as Chat Completions system messages.
        # TODO: Investigate if there's a way to make Responses API respect formatting
        yield from self._stream_chat_completions(messages, stop, run_manager, **kwargs)

        # Old disabled code:
        # # Check model eligibility
        # if not is_responses_api_eligible(self.model):
        #     # Fallback to Chat Completions streaming
        #     yield from self._stream_chat_completions(messages, stop, run_manager, **kwargs)
        #     return
        #
        # try:
        #     yield from self._stream_responses_api(messages, stop, run_manager, **kwargs)
        # except Exception as e:
        #     if self.fallback_enabled:
        #         logger.warning(
        #             "responses_api_stream_fallback",
        #             model=self.model,
        #             error=str(e),
        #             error_type=type(e).__name__,
        #             msg="Responses API streaming failed, falling back to Chat Completions",
        #         )
        #         yield from self._stream_chat_completions(messages, stop, run_manager, **kwargs)
        #     else:
        #         raise

    def _stream_responses_api(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """
        Stream using OpenAI Responses API with stream=True.

        Yields ChatGenerationChunk for each text delta received.
        """
        # Convert messages to Responses API format
        input_items, instructions = self._convert_messages_to_input(messages)

        # Generate cache key
        cache_key = self._generate_cache_key(messages)

        # Build API call parameters
        api_params: dict[str, Any] = {
            "model": self.model,
            "store": self.store,
            "prompt_cache_key": cache_key,
            "stream": True,  # Enable streaming
        }

        # Sampling params: standard models always, gpt-5.1/5.2 with effort=none
        if self._supports_sampling_params():
            api_params["temperature"] = self.temperature
            api_params["top_p"] = self.top_p

        # Reasoning effort for reasoning models (Responses API syntax)
        # Default to "low" if unconfigured (same guard as _call_responses_api)
        if self._is_reasoning_model():
            effort = self.reasoning_effort or "low"
            api_params["reasoning"] = {"effort": effort}

        api_params["input"] = input_items
        if instructions:
            api_params["instructions"] = instructions
        if self.max_tokens:
            api_params["max_output_tokens"] = self.max_tokens

        logger.info(
            "responses_api_stream_start",
            model=self.model,
            input_items_count=len(input_items) if input_items else 0,
            msg="Using Responses API streaming",
        )

        # Stream from Responses API
        response_stream = self._client.responses.create(**api_params)

        accumulated_text = ""
        response_id = None

        for event in response_stream:
            # Handle different event types from Responses API streaming
            event_type = getattr(event, "type", None)

            if event_type == "response.created":
                # event.response is an object, not a dict - use getattr
                resp_obj = getattr(event, "response", None)
                response_id = getattr(resp_obj, "id", None) if resp_obj else None
                self._last_response_id = response_id

            elif event_type == "response.output_item.added":
                # New output item started
                pass

            elif event_type == "response.content_part.added":
                # Content part started
                pass

            elif event_type == "response.output_text.delta":
                # Text delta - this is the main streaming content
                delta = getattr(event, "delta", "")
                # INFO: Log every delta to investigate emoji issue
                logger.info(
                    "responses_api_delta",
                    delta=delta,
                    delta_repr=repr(delta),
                    delta_len=len(delta) if delta else 0,
                    has_emoji=any(ord(c) > 127 for c in delta) if delta else False,
                )
                if delta:
                    accumulated_text += delta
                    yield ChatGenerationChunk(
                        message=AIMessageChunk(content=delta),
                        generation_info={"chunk": True, "response_id": response_id},
                    )
                    # Notify callback manager if present
                    if run_manager:
                        run_manager.on_llm_new_token(delta)

            elif event_type == "response.output_text.done":
                # Text output complete
                pass

            elif event_type == "response.done":
                # Response complete - extract usage for token tracking
                resp_obj = getattr(event, "response", None)

                # Extract usage from response object
                usage_metadata = None
                model_name = self.model
                if resp_obj:
                    usage = getattr(resp_obj, "usage", None)
                    if usage:
                        input_tokens = getattr(usage, "input_tokens", 0)
                        output_tokens = getattr(usage, "output_tokens", 0)

                        # Extract cached tokens from input_tokens_details
                        input_details = getattr(usage, "input_tokens_details", None)
                        cached_tokens = 0
                        if input_details:
                            cached_tokens = getattr(input_details, "cached_tokens", 0)

                        usage_metadata = {
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                            "input_token_details": {"cache_read": cached_tokens},
                        }

                    # Get actual model name from response
                    model_name = getattr(resp_obj, "model", self.model)

                logger.info(
                    "responses_api_stream_complete",
                    model=self.model,
                    response_id=response_id,
                    total_length=len(accumulated_text),
                    usage=usage_metadata,
                )

                # Final chunk with usage_metadata for token tracking
                # CRITICAL: This chunk enables TokenExtractor to capture usage from streaming
                # The empty content ensures it doesn't affect the response text
                if usage_metadata:
                    yield ChatGenerationChunk(
                        message=AIMessageChunk(
                            content="",
                            usage_metadata=usage_metadata,
                            response_metadata={"model_name": model_name},
                        ),
                        generation_info={
                            "chunk": True,
                            "response_id": response_id,
                            "finish_reason": "stop",
                        },
                    )

            # Handle legacy/alternative event structures
            elif hasattr(event, "choices"):
                # Chat Completions-style event (fallback compatibility)
                for choice in event.choices:
                    if hasattr(choice, "delta") and choice.delta.content:
                        content = choice.delta.content
                        accumulated_text += content
                        yield ChatGenerationChunk(
                            message=AIMessageChunk(content=content),
                            generation_info={"chunk": True},
                        )
                        if run_manager:
                            run_manager.on_llm_new_token(content)

    def _stream_chat_completions(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """
        Stream using Chat Completions API as fallback.

        Uses OpenAI's native streaming with stream=True and yields proper
        ChatGenerationChunk objects for LangChain compatibility.
        """
        # Convert messages to Chat Completions format
        # CRITICAL: Preserve tool_calls from AIMessage and tool_call_id from ToolMessage
        chat_messages = []
        for msg in messages:
            role = self._get_message_role(msg)
            chat_msg: dict[str, Any] = {"role": role, "content": msg.content or ""}

            # Handle AIMessage with tool_calls
            if isinstance(msg, AIMessage) and msg.tool_calls:
                chat_msg["content"] = msg.content or None
                chat_msg["tool_calls"] = [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("args", {})),
                        },
                    }
                    for i, tc in enumerate(msg.tool_calls)
                ]

            # Handle ToolMessage
            if isinstance(msg, ToolMessage):
                chat_msg["tool_call_id"] = msg.tool_call_id

            chat_messages.append(chat_msg)

        api_params: dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "stream": True,
            "stream_options": {"include_usage": True},  # Get token usage in stream
        }
        logger.info("stream_chat_completions_started", model=self.model)

        # Sampling params: standard models always, gpt-5.1/5.2 with effort=none
        if self._supports_sampling_params():
            api_params["temperature"] = self.temperature
            api_params["top_p"] = self.top_p

        # Reasoning models always use max_completion_tokens (even with effort=none)
        if self.max_tokens:
            if self._is_reasoning_model():
                api_params["max_completion_tokens"] = self.max_tokens
            else:
                api_params["max_tokens"] = self.max_tokens

        # Reasoning effort for reasoning models (Chat Completions syntax)
        # Default to "low" if unconfigured (same guard as Responses API path)
        if self._is_reasoning_model():
            api_params["reasoning_effort"] = self.reasoning_effort or "low"

        if stop:
            api_params["stop"] = stop

        # Add tools if provided (from bind_tools)
        tools = kwargs.get("tools")
        if tools:
            api_params["tools"] = tools
            tool_choice = kwargs.get("tool_choice", "auto")
            if tool_choice:
                api_params["tool_choice"] = tool_choice

        # Stream from Chat Completions API
        response_stream = self._client.chat.completions.create(**api_params)

        for chunk in response_stream:
            # DEBUG: Log every chunk structure
            logger.info(
                "stream_chunk_received",
                has_choices=bool(chunk.choices),
                has_usage=hasattr(chunk, "usage") and chunk.usage is not None,
                chunk_id=getattr(chunk, "id", None),
            )

            # CRITICAL FIX: Check for usage BEFORE skipping empty choices
            # The usage chunk from OpenAI has choices=[] but usage populated
            if hasattr(chunk, "usage") and chunk.usage:
                usage = chunk.usage
                cached_tokens = 0
                logger.info(
                    "streaming_usage_chunk_found",
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                )
                if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
                    cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

                usage_metadata = {
                    "input_tokens": usage.prompt_tokens,
                    "output_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "input_token_details": {"cache_read": cached_tokens},
                }
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        usage_metadata=usage_metadata,
                        response_metadata={"model_name": chunk.model},
                    ),
                    generation_info={"chunk": True, "finish_reason": "stop"},
                )
                # Don't continue - let the rest of the loop run in case there are also choices

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Content chunks
            if delta.content:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content=delta.content),
                    generation_info={"chunk": True},
                )

            # Tool call chunks (streamed incrementally)
            # Yield each delta as tool_call_chunks on AIMessageChunk (like ChatOpenAI)
            # so that callers using astream() can capture progressive tool args.
            # LangChain's AIMessageChunk accumulation automatically merges them
            # and populates tool_calls from the accumulated tool_call_chunks.
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc_chunk in delta.tool_calls:
                    yield ChatGenerationChunk(
                        message=AIMessageChunk(
                            content="",
                            tool_call_chunks=[
                                {
                                    "name": (
                                        tc_chunk.function.name
                                        if tc_chunk.function and tc_chunk.function.name
                                        else None
                                    ),
                                    "args": (
                                        tc_chunk.function.arguments
                                        if tc_chunk.function and tc_chunk.function.arguments
                                        else ""
                                    ),
                                    "id": tc_chunk.id or None,
                                    "index": tc_chunk.index,
                                }
                            ],
                        ),
                        generation_info={"chunk": True},
                    )

    def bind_tools(
        self,
        tools: list[Any],
        *,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Runnable[list[BaseMessage], BaseMessage]:
        """
        Bind tools to the model for function calling.

        Creates a new runnable with tools bound, enabling the model to call
        functions during generation. Uses LangChain's bind() pattern.

        Args:
            tools: List of tools (LangChain tools, dicts, or Pydantic schemas)
            tool_choice: Control which tool is called:
                - "auto": Model decides (default)
                - "none": No tools called
                - "required": Must call a tool
                - {"type": "function", "function": {"name": "..."}} : Specific tool
            **kwargs: Additional arguments passed to bind()

        Returns:
            Runnable with tools bound

        Example:
            >>> llm_with_tools = llm.bind_tools([search_tool], tool_choice="auto")
            >>> result = llm_with_tools.invoke(messages)
        """
        # Convert tools to standardized format
        formatted_tools = self._format_tools_for_binding(tools)

        bind_kwargs: dict[str, Any] = {"tools": formatted_tools, **kwargs}

        if tool_choice is not None:
            bind_kwargs["tool_choice"] = tool_choice

        logger.debug(
            "responses_llm_bind_tools",
            tool_count=len(tools),
            tool_choice=tool_choice,
            tool_names=[t.get("function", {}).get("name", "?") for t in formatted_tools],
        )

        return self.bind(**bind_kwargs)

    def _format_tools_for_binding(self, tools: list[Any]) -> list[dict[str, Any]]:
        """
        Format tools for binding, handling various input formats.

        Supports:
        - LangChain tools (with name, description, args_schema)
        - Dict format (already formatted)
        - Pydantic models (converted to function schema)

        Args:
            tools: Tools in various formats

        Returns:
            List of tools in OpenAI function format
        """
        formatted = []
        for tool in tools:
            if isinstance(tool, dict):
                # Already formatted - use as-is
                formatted.append(tool)
            elif hasattr(tool, "name") and hasattr(tool, "description"):
                # LangChain tool format
                tool_def: dict[str, Any] = {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                    },
                }
                if hasattr(tool, "args_schema") and tool.args_schema:
                    tool_def["function"]["parameters"] = tool.args_schema.model_json_schema()
                formatted.append(tool_def)
            elif hasattr(tool, "model_json_schema"):
                # Pydantic model - convert to function
                schema = tool.model_json_schema()
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": schema.get("title", tool.__name__),
                        "description": schema.get("description", ""),
                        "parameters": schema,
                    },
                }
                formatted.append(tool_def)
            else:
                logger.warning(
                    "responses_llm_unknown_tool_format",
                    tool_type=type(tool).__name__,
                    msg="Skipping unknown tool format",
                )
        return formatted

    def with_structured_output(
        self,
        schema: type[PydanticBaseModel],
        *,
        method: Literal["function_calling", "json_schema"] = "json_schema",
        strict: bool = True,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[list[BaseMessage], PydanticBaseModel | dict[str, Any]]:
        """
        Create a runnable that returns structured output using Responses API native support.

        Uses OpenAI Responses API's text.format parameter for structured output,
        preserving the 40-80% cache improvement over Chat Completions.

        The Responses API uses this format:
            text = {
                "format": {
                    "type": "json_schema",
                    "name": "schema_name",
                    "schema": {...},
                    "strict": True
                }
            }

        Args:
            schema: Pydantic model class defining the expected output structure
            method: Output method - only "json_schema" is supported natively
            strict: Use strict mode (default: True for guaranteed schema compliance)
            include_raw: Include raw LLM output alongside parsed result
            **kwargs: Additional arguments

        Returns:
            Runnable that produces structured output matching schema
        """
        logger.info(
            "responses_llm_structured_output_native",
            model=self.model,
            schema=schema.__name__,
            method=method,
            strict=strict,
            msg="Using Responses API native structured output (text.format)",
        )

        return _StructuredResponsesRunnable(
            llm=self,
            schema=schema,
            strict=strict,
            include_raw=include_raw,
        )


class _StructuredResponsesRunnable(Runnable[list[BaseMessage], PydanticBaseModel | dict[str, Any]]):
    """
    Runnable that uses OpenAI Responses API native structured output.

    Uses text.format parameter with json_schema for guaranteed schema compliance
    while preserving Responses API caching benefits (40-80% improvement).
    """

    def __init__(
        self,
        llm: ResponsesLLM,
        schema: type[PydanticBaseModel],
        strict: bool = True,
        include_raw: bool = False,
    ) -> None:
        self.llm = llm
        self.schema = schema
        self.strict = strict
        self.include_raw = include_raw
        self._schema_name = schema.__name__

    def invoke(
        self,
        input: list[BaseMessage],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> PydanticBaseModel | dict[str, Any]:
        """
        Invoke structured output using Responses API text.format.

        Args:
            input: List of LangChain messages
            config: Runnable config (for callbacks, metadata, etc.)
            **kwargs: Additional arguments

        Returns:
            Parsed Pydantic model or dict with raw output if include_raw=True
        """
        import asyncio

        # Run async version synchronously
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context - create new task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.ainvoke(input, config, **kwargs))
                    return future.result()
            else:
                return loop.run_until_complete(self.ainvoke(input, config, **kwargs))
        except RuntimeError:
            # No event loop - create one
            return asyncio.run(self.ainvoke(input, config, **kwargs))

    async def ainvoke(
        self,
        input: list[BaseMessage],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> PydanticBaseModel | dict[str, Any]:
        """
        Async invoke structured output using Responses API.

        Now properly triggers LangChain callbacks for token tracking.
        """
        from uuid import uuid4

        from langchain_core.outputs import ChatGeneration, LLMResult

        # Convert messages to Responses API format
        input_items, instructions = self.llm._convert_messages_to_input(input)

        # Check if messages have user input (Responses API requires 'input' parameter)
        if not input_items:
            logger.debug(
                "structured_responses_api_no_user_input",
                model=self.llm.model,
                message_count=len(input),
                msg="No user input in messages, using Chat Completions directly",
            )
            return self._fallback_to_chat_completions(input, config)

        # Generate cache key
        cache_key = self.llm._generate_cache_key(input)

        # Build JSON schema from Pydantic model
        json_schema = self.schema.model_json_schema()

        # Ensure additionalProperties is False for strict mode (OpenAI requirement)
        if self.strict:
            json_schema = self._ensure_strict_schema(json_schema)

        # Build API parameters with text.format for structured output
        api_params: dict[str, Any] = {
            "model": self.llm.model,
            "store": self.llm.store,
            "prompt_cache_key": cache_key,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": self._schema_name,
                    "schema": json_schema,
                    "strict": self.strict,
                }
            },
        }

        # Sampling params: standard models always, gpt-5.1/5.2 with effort=none
        if self.llm._supports_sampling_params():
            api_params["temperature"] = self.llm.temperature
            api_params["top_p"] = self.llm.top_p

        # Reasoning effort for reasoning models (Responses API syntax)
        # Default to "low" if unconfigured (same guard as _call_responses_api)
        if self.llm._is_reasoning_model():
            effort = self.llm.reasoning_effort or "low"
            api_params["reasoning"] = {"effort": effort}

        api_params["input"] = input_items  # Always send (early return at L1349 ensures non-empty)
        if instructions:
            api_params["instructions"] = instructions
        if self.llm.max_tokens:
            api_params["max_output_tokens"] = self.llm.max_tokens

        logger.debug(
            "structured_responses_api_call",
            model=self.llm.model,
            schema=self._schema_name,
            strict=self.strict,
            input_count=len(input_items) if input_items else 0,
        )

        # Extract callbacks from config for token tracking
        # CRITICAL: Handle AsyncCallbackManager/CallbackManager (not just list)
        callbacks = []
        metadata = {}
        if config:
            raw_callbacks = config.get("callbacks", [])
            if raw_callbacks is None:
                callbacks = []
            elif not isinstance(raw_callbacks, list):
                # Handle AsyncCallbackManager or CallbackManager - extract handlers
                callbacks = list(getattr(raw_callbacks, "handlers", [raw_callbacks]))
            else:
                callbacks = raw_callbacks
            metadata = config.get("metadata", {})

        # Generate run_id for callback correlation
        run_id = uuid4()

        # Debug: Log callback extraction
        logger.info(
            "structured_responses_callbacks_extracted",
            callbacks_count=len(callbacks),
            callback_types=[type(cb).__name__ for cb in callbacks],
            has_config=config is not None,
            raw_callbacks_type=type(config.get("callbacks")) if config else None,
        )

        # Call on_llm_start callbacks
        for callback in callbacks:
            if hasattr(callback, "on_llm_start"):
                try:
                    result = callback.on_llm_start(
                        serialized={"name": "ResponsesLLM"},
                        prompts=[str(input)],
                        run_id=run_id,
                        metadata=metadata,
                    )
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.warning(
                        "structured_output_callback_on_llm_start_error",
                        error=str(e),
                    )

        try:
            # Call Responses API with structured output
            response = self.llm._client.responses.create(**api_params)

            # Extract raw JSON text from response
            raw_text = self._extract_text_content(response)

            # Extract usage metadata from response for token tracking
            usage_metadata = self._extract_usage_metadata(response)

            logger.info(
                "structured_responses_api_success",
                model=self.llm.model,
                response_id=response.id,
                schema=self._schema_name,
                cached=getattr(response, "cached", None),
                usage=usage_metadata,
            )

            # Call on_llm_end callbacks with usage metadata
            if callbacks:
                # Create LLMResult for callbacks
                ai_message = AIMessage(
                    content=raw_text,
                    response_metadata={"model_name": self.llm.model},
                )
                if usage_metadata:
                    ai_message.usage_metadata = usage_metadata

                llm_result = LLMResult(
                    generations=[[ChatGeneration(message=ai_message)]],
                    llm_output={"model_name": self.llm.model},
                )

                for callback in callbacks:
                    if hasattr(callback, "on_llm_end"):
                        try:
                            result = callback.on_llm_end(
                                response=llm_result,
                                run_id=run_id,
                                metadata=metadata,
                            )
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.warning(
                                "structured_output_callback_on_llm_end_error",
                                error=str(e),
                            )

            # Parse JSON and validate against schema
            return self._parse_response(raw_text, response.id)

        except NotFoundError as e:
            # Call on_llm_error callbacks
            for callback in callbacks:
                if hasattr(callback, "on_llm_error"):
                    try:
                        result = callback.on_llm_error(error=e, run_id=run_id)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as exc:
                        logger.debug("llm_callback_error", error=str(exc))

            if self.llm.fallback_enabled:
                logger.warning(
                    "structured_responses_api_fallback",
                    model=self.llm.model,
                    error=str(e),
                    msg="Responses API 404, falling back to Chat Completions",
                )
                return self._fallback_to_chat_completions(input, config)
            raise
        except Exception as e:
            # Call on_llm_error callbacks
            for callback in callbacks:
                if hasattr(callback, "on_llm_error"):
                    try:
                        result = callback.on_llm_error(error=e, run_id=run_id)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as exc:
                        logger.debug("llm_callback_error", error=str(exc))

            if self.llm.fallback_enabled:
                logger.warning(
                    "structured_responses_api_error_fallback",
                    model=self.llm.model,
                    error=str(e),
                    error_type=type(e).__name__,
                    msg="Responses API error, falling back to Chat Completions",
                )
                return self._fallback_to_chat_completions(input, config)
            raise

    def _extract_usage_metadata(self, response: Any) -> dict[str, Any] | None:
        """Extract usage metadata from Responses API response."""
        if not hasattr(response, "usage") or not response.usage:
            return None

        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        # Extract cached tokens if available
        cached_tokens = 0
        if hasattr(usage, "input_tokens_details") and usage.input_tokens_details:
            cached_tokens = getattr(usage.input_tokens_details, "cached_tokens", 0) or 0

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_token_details": {"cache_read": cached_tokens},
        }

    def _extract_text_content(self, response: Any) -> str:
        """Extract text content from Responses API response."""
        # Check for output_text helper first
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text

        # Fall back to manual extraction
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if hasattr(item, "type") and item.type == "message":
                    if hasattr(item, "content") and item.content:
                        for content_item in item.content:
                            if hasattr(content_item, "text"):
                                return content_item.text

        return ""

    def _parse_response(
        self, raw_text: str, response_id: str
    ) -> PydanticBaseModel | dict[str, Any]:
        """Parse JSON response and validate against Pydantic schema."""
        try:
            # Parse JSON
            data = json.loads(raw_text)

            # Validate and create Pydantic model
            parsed = self.schema.model_validate(data)

            if self.include_raw:
                return {
                    "raw": raw_text,
                    "parsed": parsed,
                    "response_id": response_id,
                }
            return parsed

        except json.JSONDecodeError as e:
            logger.error(
                "structured_output_json_parse_error",
                raw_text=raw_text[:200],
                error=str(e),
            )
            raise ValueError(f"Failed to parse JSON response: {e}") from e
        except ValidationError as e:
            logger.error(
                "structured_output_validation_error",
                raw_text=raw_text[:200],
                schema=self._schema_name,
                error=str(e),
            )
            raise ValueError(f"Response does not match schema {self._schema_name}: {e}") from e

    def _ensure_strict_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Ensure schema is compatible with OpenAI strict mode.

        OpenAI strict mode requires:
        - additionalProperties: false on all objects
        - required: array containing ALL property keys
        - No unsupported keywords (format for dates, etc.)
        - $ref CANNOT have sibling keywords (description, title, etc.)
        """
        schema = schema.copy()

        def process_object(obj: dict[str, Any]) -> dict[str, Any]:
            """Recursively process objects for strict mode compliance."""
            if not isinstance(obj, dict):
                return obj

            result = obj.copy()

            # CRITICAL: OpenAI requires $ref to be STANDALONE (no sibling keywords)
            # If $ref exists, remove description, title, and other annotations
            if "$ref" in result:
                # Keep only $ref - remove all other keywords
                ref_value = result["$ref"]
                result = {"$ref": ref_value}
                return result

            # For objects with properties, ensure strict mode compliance
            if result.get("type") == "object" or "properties" in result:
                # Add additionalProperties: false
                result["additionalProperties"] = False

                # CRITICAL: OpenAI strict mode requires ALL properties in 'required'
                if "properties" in result:
                    all_props = list(result["properties"].keys())
                    result["required"] = all_props

            # Process nested properties
            if "properties" in result:
                result["properties"] = {
                    k: process_object(v) for k, v in result["properties"].items()
                }

            # Process items in arrays
            if "items" in result:
                result["items"] = process_object(result["items"])

            # Process anyOf/oneOf/allOf
            for key in ["anyOf", "oneOf", "allOf"]:
                if key in result:
                    result[key] = [process_object(item) for item in result[key]]

            # Process $defs
            if "$defs" in result:
                result["$defs"] = {k: process_object(v) for k, v in result["$defs"].items()}

            return result

        return process_object(schema)

    def _fallback_to_chat_completions(
        self, messages: list[BaseMessage], config: RunnableConfig | None = None
    ) -> PydanticBaseModel | dict[str, Any]:
        """Fallback to Chat Completions with_structured_output."""
        from langchain_openai import ChatOpenAI

        # Build kwargs, filtering for reasoning models
        chat_kwargs: dict[str, Any] = {
            "model": self.llm.model,
            "api_key": self.llm.api_key,
            "organization": self.llm.organization_id or None,
        }

        # Sampling params: standard models always, gpt-5.1/5.2 with effort=none
        if self.llm._supports_sampling_params():
            chat_kwargs["temperature"] = self.llm.temperature

        # max_tokens - LangChain ChatOpenAI handles the conversion
        if self.llm.max_tokens:
            chat_kwargs["max_tokens"] = self.llm.max_tokens

        # Reasoning effort for reasoning models (LangChain ChatOpenAI native field)
        # Default to "low" if unconfigured (same guard as Responses API path)
        if self.llm._is_reasoning_model():
            chat_kwargs["reasoning_effort"] = self.llm.reasoning_effort or "low"

        chat_llm = ChatOpenAI(**chat_kwargs)

        structured = chat_llm.with_structured_output(
            self.schema,
            method="json_schema",
            strict=self.strict,
            include_raw=self.include_raw,
        )

        # Pass config for callback propagation (token tracking)
        return structured.invoke(messages, config=config)


def create_responses_llm(
    model: str,
    api_key: str,
    organization_id: str = "",
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float = 1.0,
    store: bool = True,
    fallback_enabled: bool = True,
    streaming: bool = False,
) -> ResponsesLLM:
    """
    Factory function to create ResponsesLLM instance.

    Args:
        model: OpenAI model identifier
        api_key: OpenAI API key
        organization_id: OpenAI organization ID (optional)
        temperature: Sampling temperature
        max_tokens: Maximum output tokens
        top_p: Nucleus sampling parameter
        store: Enable caching (default: True)
        fallback_enabled: Fall back to Chat Completions on error
        streaming: Enable streaming

    Returns:
        Configured ResponsesLLM instance

    Example:
        >>> llm = create_responses_llm(
        ...     model="gpt-4.1-mini",
        ...     api_key="sk-...",
        ...     temperature=0.7,
        ...     store=True,
        ... )
    """
    return ResponsesLLM(
        model=model,
        api_key=api_key,
        organization_id=organization_id,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        store=store,
        fallback_enabled=fallback_enabled,
        streaming=streaming,
    )
