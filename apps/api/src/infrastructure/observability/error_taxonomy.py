"""The closed vocabulary of LLM API failures, and the classifier that assigns it.

One declaration, two consumers: the Prometheus label
``llm_api_errors_total{error_type=...}`` and the ``token_usage_logs.failure_kind``
column (ADR-244). A second copy would drift, and a new kind could silently
exceed the column's ``String(32)``.

The taxonomy follows the OpenAI / Anthropic / Google error codes:

- ``rate_limit`` -- 429 Too Many Requests, quota exceeded
- ``timeout`` -- request or connection timeout
- ``invalid_request`` -- 400 Bad Request, malformed parameters
- ``context_length_exceeded`` -- prompt exceeds the model's context window
- ``authentication`` -- 401 Unauthorized, invalid API key
- ``content_filter`` -- content policy violation
- ``model_not_found`` -- 404, or a model the provider retired
- ``api_error`` -- 5xx from the provider
- ``unknown`` -- anything else
"""

from __future__ import annotations

from langchain_core.exceptions import ContextOverflowError

#: The closed set. Shared by the metric label and the persisted column, so a
#: new kind is added here once and both follow.
LLM_FAILURE_KINDS: frozenset[str] = frozenset(
    {
        "rate_limit",
        "timeout",
        "invalid_request",
        "context_length_exceeded",
        "authentication",
        "content_filter",
        "model_not_found",
        "api_error",
        "unknown",
    }
)


def classify_llm_error(error: BaseException) -> str:
    """
    Classify LLM API errors into standardized categories for metrics.

    Error taxonomy based on OpenAI/Anthropic/Google API error codes:
    - rate_limit: 429 Too Many Requests, quota exceeded
    - timeout: Request timeout, connection timeout
    - invalid_request: 400 Bad Request, malformed parameters
    - context_length_exceeded: Prompt exceeds model's context window
    - authentication: 401 Unauthorized, invalid API key
    - content_filter: Content policy violation (safety filters)
    - model_not_found: 404 Model not found or deprecated
    - api_error: 500+ Server errors from provider
    - unknown: Other errors

    Args:
        error: Exception from LLM API call

    Returns:
        Error type string for metrics labeling
    """
    # Type-safe checks first -- they take priority over string matching.
    if isinstance(error, ContextOverflowError):
        return "context_length_exceeded"

    # Python's built-in TimeoutError (which asyncio.wait_for raises, and which
    # asyncio.TimeoutError aliases since 3.11) carries neither "APITimeoutError"
    # in its type name nor "timeout" in its message, so the string rules below
    # classified every one of them as ``unknown`` (measured 2026-08-24). That
    # matters beyond a mislabelled metric: ``failure_kind="timeout"`` is what a
    # model policy steps up on, and a timeout it cannot see is a timeout it
    # cannot react to.
    if isinstance(error, TimeoutError):
        return "timeout"

    error_type_name = type(error).__name__
    error_msg = str(error).lower()

    # OpenAI/LangChain error types
    if "RateLimitError" in error_type_name or "rate_limit" in error_msg:
        return "rate_limit"

    if "APITimeoutError" in error_type_name or "timeout" in error_msg:
        return "timeout"

    if (
        "InvalidRequestError" in error_type_name
        or "invalid_request" in error_msg
        or "bad request" in error_msg
    ):
        return "invalid_request"

    # Context length errors (various providers)
    if any(
        keyword in error_msg
        for keyword in [
            "context_length_exceeded",
            "maximum context length",
            "context window",
            "too many tokens",
            "token limit",
        ]
    ):
        return "context_length_exceeded"

    # Authentication errors
    if (
        "AuthenticationError" in error_type_name
        or "authentication" in error_msg
        or "invalid api key" in error_msg
        or "unauthorized" in error_msg
    ):
        return "authentication"

    # Content filter violations
    if any(
        keyword in error_msg
        for keyword in [
            "content_filter",
            "content policy",
            "safety",
            "responsible ai",
            "harmful content",
        ]
    ):
        return "content_filter"

    # Model not found
    if (
        "NotFoundError" in error_type_name
        or "model not found" in error_msg
        or "model does not exist" in error_msg
    ):
        return "model_not_found"

    # API errors (5xx from provider)
    if (
        "APIError" in error_type_name
        or "APIConnectionError" in error_type_name
        or "server error" in error_msg
        or "service unavailable" in error_msg
    ):
        return "api_error"

    return "unknown"
