"""
LangChain Agent Middleware Configuration.

Factory functions for creating middleware stacks for LangGraph agents.
Provides standardized middleware configuration with feature flags for
summarization, retry, fallback, and other agent enhancements.

Architecture (LangChain v1.1 / LangGraph v1.0):
- Middleware runs on every LLM invocation within agents
- Order matters: CallLimit > Retry > Fallback > ToolRetry > Summarization > ContextEditing
- Each middleware is optional via settings flags
- Custom middleware (MessageHistoryMiddleware) remains unchanged

Available LangChain Middleware (v1.1+):
- ModelRetryMiddleware: Automatic retry on transient LLM failures
- SummarizationMiddleware: Context compression to manage token limits
- ModelFallbackMiddleware: Automatic provider failover on errors
- ToolRetryMiddleware: Retry failed tool executions
- ModelCallLimitMiddleware: Prevent infinite loops and cost explosion
- ContextEditingMiddleware: Prune verbose tool results

Usage:
    >>> from src.infrastructure.llm.middleware_config import create_agent_middleware_stack
    >>> middleware = create_agent_middleware_stack("contacts_agent")
    >>> agent = create_agent(model=llm, tools=tools, middleware=middleware)
"""

import importlib.util
from typing import Any

from langchain.chat_models import init_chat_model

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# MIDDLEWARE AVAILABILITY CHECK
# =============================================================================
# LangChain v1.1+ middleware may not be available in all installations.
# We check availability at import time using importlib.util.find_spec
# and gracefully degrade if missing.


def _check_middleware_available(class_name: str) -> bool:
    """Check if a middleware class is available in langchain.agents.middleware."""
    if importlib.util.find_spec("langchain.agents.middleware") is None:
        return False
    try:
        from langchain.agents import middleware

        return hasattr(middleware, class_name)
    except ImportError:
        return False


_RETRY_MIDDLEWARE_AVAILABLE = _check_middleware_available("ModelRetryMiddleware")
_SUMMARIZATION_MIDDLEWARE_AVAILABLE = _check_middleware_available("SummarizationMiddleware")
_FALLBACK_MIDDLEWARE_AVAILABLE = _check_middleware_available("ModelFallbackMiddleware")
_TOOL_RETRY_MIDDLEWARE_AVAILABLE = _check_middleware_available("ToolRetryMiddleware")
_CALL_LIMIT_MIDDLEWARE_AVAILABLE = _check_middleware_available("ModelCallLimitMiddleware")
_CONTEXT_EDITING_MIDDLEWARE_AVAILABLE = _check_middleware_available("ContextEditingMiddleware")

# Log availability status
for middleware_name, available in [
    ("ModelRetryMiddleware", _RETRY_MIDDLEWARE_AVAILABLE),
    ("SummarizationMiddleware", _SUMMARIZATION_MIDDLEWARE_AVAILABLE),
    ("ModelFallbackMiddleware", _FALLBACK_MIDDLEWARE_AVAILABLE),
    ("ToolRetryMiddleware", _TOOL_RETRY_MIDDLEWARE_AVAILABLE),
    ("ModelCallLimitMiddleware", _CALL_LIMIT_MIDDLEWARE_AVAILABLE),
    ("ContextEditingMiddleware", _CONTEXT_EDITING_MIDDLEWARE_AVAILABLE),
]:
    if available:
        logger.debug("langchain_middleware_available", middleware=middleware_name)
    else:
        logger.debug(
            "langchain_middleware_not_available",
            middleware=middleware_name,
            msg=f"{middleware_name} not available",
        )


def create_agent_middleware_stack(
    agent_name: str,
    *,
    enable_retry: bool | None = None,
    enable_summarization: bool | None = None,
    enable_fallback: bool | None = None,
    enable_tool_retry: bool | None = None,
    enable_call_limit: bool | None = None,
    enable_context_editing: bool | None = None,
    primary_model: str | None = None,
) -> list[Any]:
    """
    Create middleware stack for an agent based on settings.

    Returns a list of LangChain middleware instances configured per settings.
    Order: CallLimit > Retry > Fallback > ToolRetry > Summarization > ContextEditing

    Args:
        agent_name: Agent identifier for logging (e.g., "contacts_agent")
        enable_retry: Override retry middleware setting (default: from settings)
        enable_summarization: Override summarization setting (default: from settings)
        enable_fallback: Override fallback middleware setting (default: from settings)
        enable_tool_retry: Override tool retry setting (default: from settings)
        enable_call_limit: Override call limit setting (default: from settings)
        enable_context_editing: Override context editing setting (default: from settings)
        primary_model: Primary model for fallback middleware and context window calculation
                       (required if fallback enabled, used for summarization trigger)

    Returns:
        List of middleware instances to pass to create_agent()

    Example:
        >>> middleware = create_agent_middleware_stack(
        ...     "contacts_agent",
        ...     primary_model="gpt-4.1-mini"
        ... )
        >>> # Returns full middleware stack based on settings
    """
    middleware_stack: list[Any] = []

    # Resolve settings with overrides (all middleware enabled by default)
    use_retry = enable_retry if enable_retry is not None else True
    use_summarization = enable_summarization if enable_summarization is not None else True
    use_fallback = enable_fallback if enable_fallback is not None else True
    use_tool_retry = enable_tool_retry if enable_tool_retry is not None else True
    use_call_limit = enable_call_limit if enable_call_limit is not None else True
    use_context_editing = enable_context_editing if enable_context_editing is not None else True

    # 1. Call Limit Middleware (first - prevents infinite loops at highest level)
    if use_call_limit and _CALL_LIMIT_MIDDLEWARE_AVAILABLE:
        call_limit_middleware = _create_call_limit_middleware()
        if call_limit_middleware:
            middleware_stack.append(call_limit_middleware)
            logger.debug(
                "middleware_added",
                agent_name=agent_name,
                middleware="ModelCallLimitMiddleware",
                thread_limit=settings.model_call_thread_limit,
                run_limit=settings.model_call_run_limit,
            )
    elif use_call_limit and not _CALL_LIMIT_MIDDLEWARE_AVAILABLE:
        logger.debug(
            "middleware_not_available",
            agent_name=agent_name,
            middleware="ModelCallLimitMiddleware",
            msg="Using agent_max_iterations as fallback",
        )

    # 2. Retry Middleware (retries wrap model calls)
    if use_retry and _RETRY_MIDDLEWARE_AVAILABLE:
        retry_middleware = _create_retry_middleware()
        if retry_middleware:
            middleware_stack.append(retry_middleware)
            logger.debug(
                "middleware_added",
                agent_name=agent_name,
                middleware="ModelRetryMiddleware",
                max_retries=settings.retry_max_attempts,
                backoff_factor=settings.retry_backoff_factor,
            )
    elif use_retry and not _RETRY_MIDDLEWARE_AVAILABLE:
        logger.warning(
            "middleware_not_available",
            agent_name=agent_name,
            middleware="ModelRetryMiddleware",
            msg="Retry middleware enabled in settings but not available in LangChain",
        )

    # 3. Fallback Middleware (provider failover after retry exhaustion)
    if use_fallback and _FALLBACK_MIDDLEWARE_AVAILABLE and primary_model:
        fallback_middleware = _create_fallback_middleware(primary_model)
        if fallback_middleware:
            middleware_stack.append(fallback_middleware)
            logger.debug(
                "middleware_added",
                agent_name=agent_name,
                middleware="ModelFallbackMiddleware",
                primary_model=primary_model,
                fallback_models=settings.fallback_models,
            )
    elif use_fallback and not _FALLBACK_MIDDLEWARE_AVAILABLE:
        logger.debug(
            "middleware_not_available",
            agent_name=agent_name,
            middleware="ModelFallbackMiddleware",
            msg="Fallback middleware not available - single provider mode",
        )

    # 4. Tool Retry Middleware (retries failed tool executions)
    if use_tool_retry and _TOOL_RETRY_MIDDLEWARE_AVAILABLE:
        tool_retry_middleware = _create_tool_retry_middleware()
        if tool_retry_middleware:
            middleware_stack.append(tool_retry_middleware)
            logger.debug(
                "middleware_added",
                agent_name=agent_name,
                middleware="ToolRetryMiddleware",
                max_retries=settings.tool_retry_max_attempts,
            )
    elif use_tool_retry and not _TOOL_RETRY_MIDDLEWARE_AVAILABLE:
        logger.debug(
            "middleware_not_available",
            agent_name=agent_name,
            middleware="ToolRetryMiddleware",
            msg="Tool retry middleware not available",
        )

    # 5. Summarization Middleware (compresses context before LLM call)
    if use_summarization and _SUMMARIZATION_MIDDLEWARE_AVAILABLE:
        summarization_middleware = _create_summarization_middleware(agent_model=primary_model)
        if summarization_middleware:
            middleware_stack.append(summarization_middleware)
            logger.debug(
                "middleware_added",
                agent_name=agent_name,
                middleware="SummarizationMiddleware",
                agent_model=primary_model,
                messages_to_keep=settings.summarization_keep_messages,
            )
    elif use_summarization and not _SUMMARIZATION_MIDDLEWARE_AVAILABLE:
        logger.warning(
            "middleware_not_available",
            agent_name=agent_name,
            middleware="SummarizationMiddleware",
            msg="Summarization middleware enabled in settings but not available in LangChain",
        )

    # 6. Context Editing Middleware (prunes tool results)
    if use_context_editing and _CONTEXT_EDITING_MIDDLEWARE_AVAILABLE:
        context_editing_middleware = _create_context_editing_middleware()
        if context_editing_middleware:
            middleware_stack.append(context_editing_middleware)
            logger.debug(
                "middleware_added",
                agent_name=agent_name,
                middleware="ContextEditingMiddleware",
                max_tokens=settings.context_edit_max_tool_result_tokens,
            )
    elif use_context_editing and not _CONTEXT_EDITING_MIDDLEWARE_AVAILABLE:
        logger.debug(
            "middleware_not_available",
            agent_name=agent_name,
            middleware="ContextEditingMiddleware",
            msg="Context editing middleware not available",
        )

    logger.info(
        "middleware_stack_created",
        agent_name=agent_name,
        middleware_count=len(middleware_stack),
        call_limit_enabled=use_call_limit and _CALL_LIMIT_MIDDLEWARE_AVAILABLE,
        retry_enabled=use_retry and _RETRY_MIDDLEWARE_AVAILABLE,
        fallback_enabled=use_fallback and _FALLBACK_MIDDLEWARE_AVAILABLE,
        tool_retry_enabled=use_tool_retry and _TOOL_RETRY_MIDDLEWARE_AVAILABLE,
        summarization_enabled=use_summarization and _SUMMARIZATION_MIDDLEWARE_AVAILABLE,
        context_editing_enabled=use_context_editing and _CONTEXT_EDITING_MIDDLEWARE_AVAILABLE,
    )

    return middleware_stack


def _create_retry_middleware() -> Any | None:
    """
    Create ModelRetryMiddleware with settings configuration.

    LangChain ModelRetryMiddleware API (v1.1+):
    - max_retries: int (default: 2) - retry attempts after initial call
    - retry_on: tuple[Exception] | callable (default: (Exception,))
    - on_failure: "continue" | "error" | callable (default: "continue")
    - backoff_factor: float (default: 2.0) - exponential backoff multiplier
    - initial_delay: float (default: 1.0) - initial delay in seconds
    - max_delay: float (default: 60.0) - maximum delay cap
    - jitter: bool (default: True) - add random variation ±25%

    See: https://docs.langchain.com/oss/python/langchain/middleware/built-in

    Returns:
        ModelRetryMiddleware instance or None if creation fails
    """
    if not _RETRY_MIDDLEWARE_AVAILABLE:
        return None

    try:
        from langchain.agents.middleware import ModelRetryMiddleware

        middleware = ModelRetryMiddleware(
            max_retries=settings.retry_max_attempts,
            backoff_factor=settings.retry_backoff_factor,
            initial_delay=settings.retry_initial_delay,
            max_delay=settings.retry_max_delay,
            jitter=settings.retry_jitter,
            on_failure="continue",  # Return AIMessage on failure instead of raising
        )

        logger.info(
            "retry_middleware_created",
            max_retries=settings.retry_max_attempts,
            backoff_factor=settings.retry_backoff_factor,
        )

        return middleware

    except TypeError as e:
        # API mismatch - try minimal config
        logger.warning(
            "retry_middleware_api_mismatch",
            error=str(e),
            msg="Trying minimal ModelRetryMiddleware configuration",
        )
        try:
            from langchain.agents.middleware import ModelRetryMiddleware

            return ModelRetryMiddleware(max_retries=settings.retry_max_attempts)
        except (TypeError, ImportError, ValueError, RuntimeError):
            return None
    except (ImportError, ValueError, RuntimeError, AttributeError) as e:
        logger.error(
            "middleware_creation_failed",
            middleware="ModelRetryMiddleware",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _create_summarization_middleware(agent_model: str | None = None) -> Any | None:
    """
    Create SummarizationMiddleware with settings configuration.

    LangChain SummarizationMiddleware API (v1.0.x):
    - model: str | BaseChatModel (required) - model for generating summaries
    - max_tokens_before_summary: int | None - token threshold to trigger summarization
    - messages_to_keep: int (default: 20) - number of recent messages to preserve
    - token_counter: optional custom token counter
    - summary_prompt: optional custom prompt template
    - summary_prefix: str - prefix for summary messages

    Args:
        agent_model: The LLM model used by the agent (for context window calculation).
                     If None, falls back to response_llm_model from settings.

    Returns:
        SummarizationMiddleware instance or None if creation fails
    """
    if not _SUMMARIZATION_MIDDLEWARE_AVAILABLE:
        return None

    try:
        from langchain.agents.middleware import SummarizationMiddleware

        from src.core.config.llm import get_model_context_window
        from src.core.llm_config_helper import get_llm_config_for_agent

        # Determine context window based on agent's model
        # The summarization trigger should be based on the agent's LLM context, not the summarizer's
        effective_model = agent_model or get_llm_config_for_agent(settings, "response").model
        context_window = get_model_context_window(effective_model)

        # Convert fraction-based trigger to absolute token count
        trigger_value = settings.summarization_trigger_fraction
        if trigger_value <= 1.0:
            # Fraction mode - convert to absolute tokens based on model's context window
            max_tokens = int(context_window * trigger_value)
        else:
            # Already an absolute token count
            max_tokens = int(trigger_value)

        # Create summarization LLM with proper API key injection.
        # SummarizationMiddleware accepts str | BaseChatModel. Passing a string
        # causes init_chat_model(model) without API key — breaks when OPENAI_API_KEY
        # is not in .env (keys are now DB-only via LLM Config Admin).
        # Solution: pass a pre-configured BaseChatModel instance.
        from src.infrastructure.llm.providers.adapter import _require_api_key

        summarization_model_name = settings.summarization_model
        summarization_llm = init_chat_model(
            model=summarization_model_name,
            openai_api_key=_require_api_key("openai"),
        )

        middleware = SummarizationMiddleware(
            model=summarization_llm,
            max_tokens_before_summary=max_tokens,
            messages_to_keep=settings.summarization_keep_messages,
        )

        logger.info(
            "summarization_middleware_created",
            model=summarization_model_name,
            agent_model=effective_model,
            context_window=context_window,
            trigger_fraction=trigger_value,
            max_tokens_before_summary=max_tokens,
            messages_to_keep=settings.summarization_keep_messages,
        )

        return middleware

    except TypeError as e:
        # API mismatch - try minimal config
        logger.warning(
            "summarization_middleware_api_mismatch",
            error=str(e),
            msg="Trying minimal SummarizationMiddleware configuration",
        )
        try:
            from langchain.agents.middleware import SummarizationMiddleware

            from src.infrastructure.llm.providers.adapter import _require_api_key

            summarization_llm_fallback = init_chat_model(
                model=settings.summarization_model,
                openai_api_key=_require_api_key("openai"),
            )
            return SummarizationMiddleware(
                model=summarization_llm_fallback,
                messages_to_keep=settings.summarization_keep_messages,
            )
        except (TypeError, ImportError, ValueError, RuntimeError):
            return None
    except (ImportError, ValueError, RuntimeError, AttributeError) as e:
        logger.error(
            "middleware_creation_failed",
            middleware="SummarizationMiddleware",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _create_fallback_middleware(primary_model: str) -> Any | None:
    """
    Create ModelFallbackMiddleware for multi-provider resilience.

    LangChain ModelFallbackMiddleware API (v1.1+):
    - first_model: str | BaseChatModel (required) - primary model to use
    - *additional_models: str | BaseChatModel - fallback models in priority order

    Falls back to alternative models on:
    - Rate limit errors (429)
    - API errors (500, 502, 503, 504)
    - Timeout errors
    - Authentication errors

    See: https://docs.langchain.com/oss/python/langchain/middleware/built-in

    Args:
        primary_model: Primary model identifier (e.g., "gpt-4.1-mini")

    Returns:
        ModelFallbackMiddleware instance or None if creation fails
    """
    if not _FALLBACK_MIDDLEWARE_AVAILABLE:
        return None

    try:
        from langchain.agents.middleware import ModelFallbackMiddleware

        # Parse fallback models from settings (comma-separated)
        fallback_models_str = settings.fallback_models
        fallback_models = [m.strip() for m in fallback_models_str.split(",") if m.strip()]

        if not fallback_models:
            logger.warning(
                "fallback_middleware_no_fallbacks",
                primary_model=primary_model,
                msg="No fallback models configured - middleware disabled",
            )
            return None

        # Create middleware with primary + fallbacks
        middleware = ModelFallbackMiddleware(primary_model, *fallback_models)

        logger.info(
            "fallback_middleware_created",
            primary_model=primary_model,
            fallback_models=fallback_models,
            total_models=1 + len(fallback_models),
        )

        return middleware

    except TypeError as e:
        # API mismatch - log and disable
        logger.warning(
            "fallback_middleware_api_mismatch",
            error=str(e),
            msg="ModelFallbackMiddleware API doesn't match expected signature",
        )
        return None
    except (ImportError, ValueError, RuntimeError, AttributeError) as e:
        logger.error(
            "middleware_creation_failed",
            middleware="ModelFallbackMiddleware",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _create_tool_retry_middleware() -> Any | None:
    """
    Create ToolRetryMiddleware for tool execution resilience.

    LangChain ToolRetryMiddleware API (v1.1+):
    - max_retries: int (default: 3) - retry attempts after initial call
    - backoff_factor: float (default: 1.5) - exponential backoff multiplier
    - retry_on: tuple[Exception] | callable - exceptions to retry on
    - on_failure: "continue" | "error" | callable (default: "error")

    Retries failed tool executions on:
    - ConnectionError, TimeoutError
    - Rate limit errors
    - Transient API failures (Google Calendar, Gmail, etc.)

    See: https://docs.langchain.com/oss/python/langchain/middleware/built-in

    Returns:
        ToolRetryMiddleware instance or None if creation fails
    """
    if not _TOOL_RETRY_MIDDLEWARE_AVAILABLE:
        return None

    try:
        from langchain.agents.middleware import ToolRetryMiddleware

        middleware = ToolRetryMiddleware(
            max_retries=settings.tool_retry_max_attempts,
            backoff_factor=settings.tool_retry_backoff_factor,
            on_failure="error",  # Raise after exhausting retries
        )

        logger.info(
            "tool_retry_middleware_created",
            max_retries=settings.tool_retry_max_attempts,
            backoff_factor=settings.tool_retry_backoff_factor,
        )

        return middleware

    except TypeError as e:
        # API mismatch - try minimal config
        logger.warning(
            "tool_retry_middleware_api_mismatch",
            error=str(e),
            msg="Trying minimal ToolRetryMiddleware configuration",
        )
        try:
            from langchain.agents.middleware import ToolRetryMiddleware

            return ToolRetryMiddleware(max_retries=settings.tool_retry_max_attempts)
        except (TypeError, ImportError, ValueError, RuntimeError):
            return None
    except (ImportError, ValueError, RuntimeError, AttributeError) as e:
        logger.error(
            "middleware_creation_failed",
            middleware="ToolRetryMiddleware",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _create_call_limit_middleware() -> Any | None:
    """
    Create ModelCallLimitMiddleware for cost and loop protection.

    LangChain ModelCallLimitMiddleware API (v1.1+):
    - thread_limit: int - max calls per conversation thread
    - run_limit: int - max calls per single agent run
    - exit_behavior: "error" | "continue" (default: "error")

    Prevents:
    - Infinite loops in agent execution
    - Runaway token consumption
    - Cost explosion from buggy agents

    See: https://docs.langchain.com/oss/python/langchain/middleware/built-in

    Returns:
        ModelCallLimitMiddleware instance or None if creation fails
    """
    if not _CALL_LIMIT_MIDDLEWARE_AVAILABLE:
        return None

    try:
        from langchain.agents.middleware import ModelCallLimitMiddleware

        middleware = ModelCallLimitMiddleware(
            thread_limit=settings.model_call_thread_limit,
            run_limit=settings.model_call_run_limit,
            exit_behavior="error",  # Raise exception when limit hit
        )

        logger.info(
            "call_limit_middleware_created",
            thread_limit=settings.model_call_thread_limit,
            run_limit=settings.model_call_run_limit,
        )

        return middleware

    except TypeError as e:
        # API mismatch - try minimal config
        logger.warning(
            "call_limit_middleware_api_mismatch",
            error=str(e),
            msg="Trying minimal ModelCallLimitMiddleware configuration",
        )
        try:
            from langchain.agents.middleware import ModelCallLimitMiddleware

            return ModelCallLimitMiddleware(run_limit=settings.model_call_run_limit)
        except (TypeError, ImportError, ValueError, RuntimeError):
            return None
    except (ImportError, ValueError, RuntimeError, AttributeError) as e:
        logger.error(
            "middleware_creation_failed",
            middleware="ModelCallLimitMiddleware",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _create_context_editing_middleware() -> Any | None:
    """
    Create ContextEditingMiddleware for tool result pruning.

    LangChain ContextEditingMiddleware API (v1.1+):
    - edits: list[ContextEdit] - editing rules to apply
    - token_count_method: "approximate" | "exact" (default: "approximate")

    ContextEdit types:
    - TruncateToolResult: Limit tool output tokens
    - RemoveOldMessages: Remove messages beyond threshold
    - SummarizeToolResult: Summarize verbose outputs

    Useful for:
    - Large contact lists from Google Contacts
    - Email threads from Gmail
    - Calendar event details

    See: https://docs.langchain.com/oss/python/langchain/middleware/built-in

    Returns:
        ContextEditingMiddleware instance or None if creation fails
    """
    if not _CONTEXT_EDITING_MIDDLEWARE_AVAILABLE:
        return None

    try:
        from langchain.agents.middleware import ContextEditingMiddleware

        # Configure editing rules - truncate tool results that exceed limit
        max_tokens = settings.context_edit_max_tool_result_tokens

        # Try to use TruncateToolResult if available
        try:
            from langchain.agents.middleware import TruncateToolResult

            edits = [TruncateToolResult(max_tokens=max_tokens)]
        except ImportError:
            # Fall back to dict-based config
            edits = [{"type": "truncate_tool_result", "max_tokens": max_tokens}]

        middleware = ContextEditingMiddleware(
            edits=edits,
            token_count_method="approximate",  # Faster than exact
        )

        logger.info(
            "context_editing_middleware_created",
            max_tool_result_tokens=max_tokens,
        )

        return middleware

    except TypeError as e:
        # API mismatch - log and disable
        logger.warning(
            "context_editing_middleware_api_mismatch",
            error=str(e),
            msg="ContextEditingMiddleware API doesn't match expected signature",
        )
        return None
    except (ImportError, ValueError, RuntimeError, AttributeError) as e:
        logger.error(
            "middleware_creation_failed",
            middleware="ContextEditingMiddleware",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def is_retry_middleware_available() -> bool:
    """Check if ModelRetryMiddleware is available in LangChain."""
    return _RETRY_MIDDLEWARE_AVAILABLE


def is_summarization_middleware_available() -> bool:
    """Check if SummarizationMiddleware is available in LangChain."""
    return _SUMMARIZATION_MIDDLEWARE_AVAILABLE


def is_fallback_middleware_available() -> bool:
    """Check if ModelFallbackMiddleware is available in LangChain."""
    return _FALLBACK_MIDDLEWARE_AVAILABLE


def is_tool_retry_middleware_available() -> bool:
    """Check if ToolRetryMiddleware is available in LangChain."""
    return _TOOL_RETRY_MIDDLEWARE_AVAILABLE


def is_call_limit_middleware_available() -> bool:
    """Check if ModelCallLimitMiddleware is available in LangChain."""
    return _CALL_LIMIT_MIDDLEWARE_AVAILABLE


def is_context_editing_middleware_available() -> bool:
    """Check if ContextEditingMiddleware is available in LangChain."""
    return _CONTEXT_EDITING_MIDDLEWARE_AVAILABLE


def get_middleware_availability() -> dict[str, bool]:
    """
    Get availability status of all LangChain middleware.

    Returns:
        Dict mapping middleware name to availability status

    Example:
        >>> get_middleware_availability()
        {"ModelRetryMiddleware": True, "SummarizationMiddleware": True, ...}
    """
    return {
        "ModelRetryMiddleware": _RETRY_MIDDLEWARE_AVAILABLE,
        "SummarizationMiddleware": _SUMMARIZATION_MIDDLEWARE_AVAILABLE,
        "ModelFallbackMiddleware": _FALLBACK_MIDDLEWARE_AVAILABLE,
        "ToolRetryMiddleware": _TOOL_RETRY_MIDDLEWARE_AVAILABLE,
        "ModelCallLimitMiddleware": _CALL_LIMIT_MIDDLEWARE_AVAILABLE,
        "ContextEditingMiddleware": _CONTEXT_EDITING_MIDDLEWARE_AVAILABLE,
    }
