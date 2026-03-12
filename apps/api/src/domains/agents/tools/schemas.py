"""
Pydantic schemas for tool responses.

Phase 3.2.4: Define type-safe schemas for tool response validation.

.. deprecated:: 2025-12-29
    ToolResponse, ToolResponseSuccess, and ToolResponseError are deprecated.
    Use UnifiedToolOutput from src.domains.agents.tools.output instead.

    UnifiedToolOutput provides:
    - Factory methods: action_success(), data_success(), failure()
    - LangChain structured output compatibility (str(output) = message)
    - Registry integration via summary_for_llm property
    - Consistent error handling with error_code field

    Migration example:
    - Before: ToolResponse(success=True, data={"count": 5})
    - After: UnifiedToolOutput.action_success(message="5 items", structured_data={"count": 5})
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """
    Standard response format for all LangChain tools.

    .. deprecated:: 2025-12-29
        Use UnifiedToolOutput from src.domains.agents.tools.output instead.

    Phase 3.2.4: Pydantic schema for tool response validation.

    All tools in the system should return JSON strings that conform to this schema.
    This ensures consistency, enables runtime validation, and facilitates debugging.

    Attributes:
        success: Whether the tool execution succeeded.
        data: Tool-specific result data (only present if success=True).
        error: Error code if execution failed (only present if success=False).
        message: Human-readable error or info message.
        metadata: Optional metadata (turn_id, timestamps, etc.).

    Examples:
        >>> # Success response
        >>> response = ToolResponse(
        ...     success=True,
        ...     data={"contacts": [{"name": "Jean"}], "total": 1}
        ... )
        >>> response.model_dump_json()
        '{"success":true,"data":{"contacts":[{"name":"Jean"}],"total":1}}'

        >>> # Error response
        >>> response = ToolResponse(
        ...     success=False,
        ...     error="NOT_FOUND",
        ...     message="Contact not found"
        ... )
        >>> response.model_dump_json()
        '{"success":false,"error":"NOT_FOUND","message":"Contact not found"}'

    Usage in tools:
        ```python
        from src.domains.agents.tools.schemas import ToolResponse

        @tool
        async def my_tool(query: str) -> str:
            try:
                result = await do_something(query)
                response = ToolResponse(
                    success=True,
                    data={"result": result}
                )
                return response.model_dump_json()
            except Exception as e:
                response = ToolResponse(
                    success=False,
                    error="INTERNAL_ERROR",
                    message=str(e)
                )
                return response.model_dump_json()
        ```

    Validation:
        - If success=True, data field is required
        - If success=False, error field is required
        - message field is always optional
        - metadata field is always optional

    Note:
        This schema replaces ad-hoc dict/JSON construction in tools,
        providing compile-time type checking and runtime validation.
    """

    success: bool = Field(description="Whether tool execution succeeded")
    data: dict[str, Any] | None = Field(
        default=None, description="Tool result data (required if success=True)"
    )
    error: str | None = Field(default=None, description="Error code (required if success=False)")
    message: str | None = Field(default=None, description="Human-readable message")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional metadata")

    def model_dump_json(self, **kwargs: Any) -> str:
        """
        Serialize to JSON string, excluding None values by default.

        This produces clean JSON output without null fields.

        Args:
            **kwargs: Additional arguments passed to BaseModel.model_dump_json()

        Returns:
            JSON string representation of the response.

        Example:
            >>> response = ToolResponse(success=True, data={"count": 5})
            >>> response.model_dump_json()
            '{"success":true,"data":{"count":5}}'
        """
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)

    @classmethod
    def success_response(
        cls,
        data: dict[str, Any],
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResponse":
        """
        Create a success response.

        Args:
            data: Tool result data.
            message: Optional success message.
            metadata: Optional metadata.

        Returns:
            ToolResponse with success=True.

        Example:
            >>> response = ToolResponse.success_response(
            ...     data={"contacts": [{"name": "Jean"}]},
            ...     message="Found 1 contact"
            ... )
            >>> response.success
            True
        """
        return cls(success=True, data=data, message=message, metadata=metadata)

    @classmethod
    def error_response(
        cls, error: str, message: str, metadata: dict[str, Any] | None = None
    ) -> "ToolResponse":
        """
        Create an error response.

        Args:
            error: Error code (e.g., "NOT_FOUND", "VALIDATION_ERROR").
            message: Human-readable error message.
            metadata: Optional metadata.

        Returns:
            ToolResponse with success=False.

        Example:
            >>> response = ToolResponse.error_response(
            ...     error="NOT_FOUND",
            ...     message="Contact 'Jean' not found"
            ... )
            >>> response.success
            False
        """
        return cls(success=False, error=error, message=message, metadata=metadata)


class ToolResponseSuccess(ToolResponse):
    """
    Success-only variant of ToolResponse.

    Enforces success=True and requires data field.
    Use this when you want strict type checking for success responses.

    Example:
        >>> response = ToolResponseSuccess(
        ...     success=True,
        ...     data={"count": 5}
        ... )
    """

    success: Literal[True] = Field(default=True, description="Always True for success responses")
    data: dict[str, Any] = Field(description="Tool result data (required)")


class ToolResponseError(ToolResponse):
    """
    Error-only variant of ToolResponse.

    Enforces success=False and requires error field.
    Use this when you want strict type checking for error responses.

    Example:
        >>> response = ToolResponseError(
        ...     success=False,
        ...     error="NOT_FOUND",
        ...     message="Resource not found"
        ... )
    """

    success: Literal[False] = Field(default=False, description="Always False for error responses")
    error: str = Field(description="Error code (required)")


__all__ = [
    "ToolResponse",
    "ToolResponseError",
    "ToolResponseSuccess",
]
