"""
Common Pydantic models for tool normalization.

This module provides the base models used by all tools to ensure:
- Input validation (parameters)
- JSON serialization/deserialization of outputs
- Consistency with catalogue manifests
- Validator and orchestrator support

Architecture:
- ToolResponse: Standardized response for all tools
- ToolErrorModel: Structured error with codes and context
- Helpers: Utility functions for parsing and validation

Usage:
    from src.domains.agents.tools.common import ToolResponse, ToolErrorModel

    # In a tool
    async def my_tool(...) -> dict:
        try:
            result = await do_something()
            return ToolResponse(
                success=True,
                data=result,
                metadata={"source": "api"}
            ).model_dump()
        except Exception as e:
            return ToolErrorModel.from_exception(e, context={"tool": "my_tool"}).to_response()

Compliance: Pydantic v2, LangChain v1.0 ToolRuntime pattern
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

import structlog
from pydantic import BaseModel, Field, field_validator

from src.core.field_names import FIELD_ERROR_CODE, FIELD_TIMESTAMP

if TYPE_CHECKING:
    from collections.abc import Awaitable

logger = structlog.get_logger(__name__)

# ============================================================================
# Error Codes
# ============================================================================


class ToolErrorCode(str, Enum):
    """Standardized error codes for tools."""

    # Validation errors
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED_PARAM = "MISSING_REQUIRED_PARAM"
    INVALID_PARAM_VALUE = "INVALID_PARAM_VALUE"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"

    # Runtime errors
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"

    # Data errors
    EMPTY_RESULT = "EMPTY_RESULT"
    INVALID_RESPONSE_FORMAT = "INVALID_RESPONSE_FORMAT"

    # Template errors (Data Registry LOT 5.3)
    TEMPLATE_EMPTY_RESULT = "TEMPLATE_EMPTY_RESULT"
    TEMPLATE_RECURSION_LIMIT = "TEMPLATE_RECURSION_LIMIT"
    TEMPLATE_EVALUATION_FAILED = "TEMPLATE_EVALUATION_FAILED"  # Jinja evaluation error

    # Feature errors
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


# ============================================================================
# Base Response Models
# ============================================================================


class ToolResponse(BaseModel):
    """
    Standardized response for all tools.

    Ensures a consistent structure for the orchestrator and validator.
    All tools must return this format via .model_dump().

    Attributes:
        success: True if execution succeeded, False otherwise
        data: Returned data (structure depends on the tool)
        error: Error message if success=False
        error_code: Standardized error code if success=False
        metadata: Additional metadata (source, timing, etc.)
        timestamp: UTC timestamp of the response

    Examples:
        >>> # Success case
        >>> response = ToolResponse(
        ...     success=True,
        ...     data={"contacts": [...]},
        ...     metadata={"count": 5, "source": "cache"}
        ... )
        >>> response.model_dump()

        >>> # Error case
        >>> response = ToolResponse(
        ...     success=False,
        ...     error="Contact not found",
        ...     error_code=ToolErrorCode.NOT_FOUND,
        ...     metadata={"resource_name": "people/c123"}
        ... )
    """

    success: bool
    data: Any | None = None
    error: str | None = None
    error_code: ToolErrorCode | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("error", FIELD_ERROR_CODE)
    @classmethod
    def validate_error_consistency(cls, v: Any, info: Any) -> Any:
        """Validate that error and error_code are consistent with success"""
        if info.data.get("success") is False and v is None:
            # If success=False, error or error_code should be provided
            pass  # We allow None, the validator will call to_error() if needed
        return v

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to ensure LangChain-compatible dict format"""
        data = super().model_dump(**kwargs)
        # Convert timestamp to ISO string for JSON serialization
        if FIELD_TIMESTAMP in data and isinstance(data[FIELD_TIMESTAMP], datetime):
            data[FIELD_TIMESTAMP] = data[FIELD_TIMESTAMP].isoformat()
        # Convert error_code enum to string
        if data.get(FIELD_ERROR_CODE):
            data[FIELD_ERROR_CODE] = str(data[FIELD_ERROR_CODE].value)
        return data


class ToolErrorModel(BaseModel):
    """
    Structured error for tools.

    Provides a standardized way to represent errors with:
    - Typed error code
    - Human-readable message
    - Additional context for debugging
    - Automatic conversion to ToolResponse

    Attributes:
        code: Standardized error code
        message: Descriptive error message
        context: Additional context (params, stack, etc.)
        recoverable: If True, recoverable error (retry possible)

    Examples:
        >>> # Validation error
        >>> error = ToolErrorModel(
        ...     code=ToolErrorCode.INVALID_INPUT,
        ...     message="Parameter 'query' must not be empty",
        ...     context={"param": "query", "value": ""},
        ...     recoverable=False
        ... )
        >>> error.to_response()

        >>> # From exception
        >>> try:
        ...     await api_call()
        ... except Exception as e:
        ...     error = ToolErrorModel.from_exception(e, context={"tool": "search"})
        ...     return error.to_response()
    """

    code: ToolErrorCode
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    recoverable: bool = False

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        code: ToolErrorCode = ToolErrorCode.INTERNAL_ERROR,
        context: dict[str, Any] | None = None,
        recoverable: bool = False,
    ) -> ToolErrorModel:
        """
        Create ToolErrorModel from an exception.

        Args:
            exc: Python exception
            code: Error code (default INTERNAL_ERROR)
            context: Additional context
            recoverable: Whether the error is recoverable

        Returns:
            ToolErrorModel instance

        Examples:
            >>> try:
            ...     result = await api_call()
            ... except TimeoutError as e:
            ...     error = ToolErrorModel.from_exception(
            ...         e,
            ...         code=ToolErrorCode.TIMEOUT,
            ...         context={"endpoint": "/contacts"},
            ...         recoverable=True
            ...     )
        """
        ctx = context or {}
        ctx["exception_type"] = type(exc).__name__

        # Add stack trace for internal errors
        if code == ToolErrorCode.INTERNAL_ERROR:
            import traceback

            ctx["traceback"] = traceback.format_exc()

        return cls(
            code=code,
            message=str(exc),
            context=ctx,
            recoverable=recoverable,
        )

    def to_response(self) -> dict[str, Any]:
        """
        Convert ToolErrorModel to ToolResponse.

        Returns:
            Dict compatible with ToolResponse.model_dump()

        Examples:
            >>> error = ToolErrorModel(
            ...     code=ToolErrorCode.NOT_FOUND,
            ...     message="Contact not found"
            ... )
            >>> response_dict = error.to_response()
            >>> # Can be returned directly by the tool
        """
        return ToolResponse(
            success=False,
            error=self.message,
            error_code=self.code,
            metadata={
                "context": self.context,
                "recoverable": self.recoverable,
            },
        ).model_dump()


# ============================================================================
# Helper Functions
# ============================================================================

T = TypeVar("T", bound=BaseModel)


class ToolInputValidationError(Exception):
    """Exception raised during input validation"""

    def __init__(self, tool_error: ToolErrorModel) -> None:
        self.tool_error = tool_error
        super().__init__(tool_error.message)


def validate_tool_input[T: BaseModel](model_class: type[T], params: dict[str, Any]) -> T:
    """
    Valide et parse les paramètres d'entrée avec Pydantic.

    Args:
        model_class: Classe Pydantic (ex: SearchContactsInput)
        params: Paramètres bruts depuis runtime

    Returns:
        Instance validée du model

    Raises:
        ToolInputValidationError: Si validation échoue

    Examples:
        >>> from pydantic import BaseModel
        >>> class MyInput(BaseModel):
        ...     query: str
        ...     limit: int = 10
        >>> params = {"query": "test"}
        >>> validated = validate_tool_input(MyInput, params)
        >>> validated.query
        'test'
        >>> validated.limit
        10
    """
    try:
        return model_class(**params)
    except Exception as e:
        tool_error = ToolErrorModel(
            code=ToolErrorCode.INVALID_INPUT,
            message=f"Invalid input parameters: {e}",
            context={"params": params, "model": model_class.__name__},
            recoverable=False,
        )
        raise ToolInputValidationError(tool_error) from e


def create_success_response(
    data: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a standardized success response.

    Utility function to simplify ToolResponse success creation.

    Args:
        data: Data to return
        metadata: Optional metadata

    Returns:
        ToolResponse-compatible dict

    Examples:
        >>> result = {"contacts": [...]}
        >>> return create_success_response(
        ...     data=result,
        ...     metadata={"count": len(result["contacts"]), "source": "cache"}
        ... )
    """
    return ToolResponse(
        success=True,
        data=data,
        metadata=metadata or {},
    ).model_dump()


def create_error_response(
    message: str,
    code: ToolErrorCode = ToolErrorCode.INTERNAL_ERROR,
    context: dict[str, Any] | None = None,
    recoverable: bool = False,
) -> dict[str, Any]:
    """
    Create a standardized error response.

    Utility function to simplify ToolResponse error creation.

    Args:
        message: Error message
        code: Error code
        context: Additional context
        recoverable: Whether the error is recoverable

    Returns:
        ToolResponse-compatible dict

    Examples:
        >>> return create_error_response(
        ...     message="API rate limit exceeded",
        ...     code=ToolErrorCode.RATE_LIMIT_EXCEEDED,
        ...     context={"retry_after": 60},
        ...     recoverable=True
        ... )
    """
    return ToolErrorModel(
        code=code,
        message=message,
        context=context or {},
        recoverable=recoverable,
    ).to_response()


# ============================================================================
# JSON Parsing Helpers (DRY - eliminates 30+ duplications)
# ============================================================================


def safe_parse_json(
    response: str | dict[str, Any] | list[Any],
    context: str = "response",
) -> dict[str, Any] | list[Any]:
    """
    Parse JSON with standardized error handling.

    Eliminates 30+ duplicated try-except blocks across tools, clients, and cache.

    Args:
        response: JSON string or already parsed dict/list
        context: Description for error messages (e.g., "API response", "cache data")

    Returns:
        Parsed dict or list

    Raises:
        ValueError: If JSON parsing fails (with context in message)

    Examples:
        >>> data = safe_parse_json('{"name": "test"}', context="contacts API")
        >>> data
        {'name': 'test'}

        >>> data = safe_parse_json({"already": "parsed"})
        >>> data
        {'already': 'parsed'}
    """
    if isinstance(response, dict | list):
        return response
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {context}: {e}") from e


def safe_parse_json_strict(
    response: str | dict[str, Any],
    context: str = "response",
) -> dict[str, Any]:
    """
    Parse JSON and ensure result is a dict.

    Same as safe_parse_json but raises if result is not a dict.

    Args:
        response: JSON string or already parsed dict
        context: Description for error messages

    Returns:
        Parsed dict (never list)

    Raises:
        ValueError: If JSON parsing fails or result is not a dict
    """
    result = safe_parse_json(response, context)
    if not isinstance(result, dict):
        raise ValueError(f"Expected dict in {context}, got {type(result).__name__}")
    return result


# ============================================================================
# Generic List Parser Factory (DRY - eliminates contact parser duplications)
# ============================================================================

M = TypeVar("M", bound=BaseModel)


def parse_list_field(
    data: list[dict[str, Any]] | None,
    model_class: type[M],
    required_key: str | None = None,
) -> list[M]:
    """
    Generic factory to parse lists into Pydantic models.

    Eliminates 6+ nearly-identical _parse_contact_* functions.

    Args:
        data: List of raw dicts (can be None)
        model_class: Target Pydantic class (e.g., ContactEmail, ContactPhone)
        required_key: Required key in each item (e.g., "value"). If None, accepts all dicts.

    Returns:
        List of model instances, empty if data is None

    Examples:
        >>> from pydantic import BaseModel
        >>> class ContactEmail(BaseModel):
        ...     value: str
        ...     type: str | None = None
        >>> data = [{"value": "test@example.com", "type": "work"}]
        >>> emails = parse_list_field(data, ContactEmail, required_key="value")
        >>> emails[0].value
        'test@example.com'

        >>> # Without required_key
        >>> parse_list_field([{"name": "Test"}], SomeModel)
    """
    if not data:
        return []

    items: list[M] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if required_key is not None and required_key not in item:
            continue
        try:
            items.append(model_class(**item))
        except Exception:
            # Skip invalid items silently (matches existing behavior)
            continue

    return items


# ============================================================================
# Error Handling Decorator (DRY - standardizes exception handling)
# ============================================================================


def handle_tool_errors(
    tool_name: str | None = None,
    reraise_tool_errors: bool = True,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    Decorateur standardise pour la gestion d'erreurs des tools async.

    Centralise le pattern try-except repete 420+ fois dans la codebase.
    Transforme les exceptions en logs structures et peut les re-raise
    ou les convertir en ToolResponse.

    Args:
        tool_name: Nom du tool pour les logs (defaut: nom de la fonction)
        reraise_tool_errors: Si True, re-raise ToolError et ses sous-classes

    Returns:
        Decorated async function

    Usage:
        >>> from src.domains.agents.tools.exceptions import ToolError, ToolValidationError
        >>>
        >>> @handle_tool_errors(tool_name="search_contacts")
        ... async def search_contacts(query: str) -> dict:
        ...     # ToolValidationError sera re-raised
        ...     # json.JSONDecodeError sera logged et wrapped
        ...     # KeyError sera logged et wrapped
        ...     return await do_search(query)

    Exceptions handled:
        - ToolError subclasses: Re-raised if reraise_tool_errors=True
        - json.JSONDecodeError: Logged + wrapped in ValueError
        - KeyError: Logged + wrapped in ValueError
        - Exception: Logged with full context + re-raised
    """
    # Import here to avoid circular imports
    from src.domains.agents.tools.exceptions import ToolError as ToolErrorException

    def decorator(
        func: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        name = tool_name or func.__name__

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except ToolErrorException:
                # Tool-specific errors: re-raise for proper handling upstream
                if reraise_tool_errors:
                    raise
                # If not re-raising, log and let it propagate
                logger.warning(
                    "tool_error_caught",
                    tool=name,
                    error_type="ToolError",
                )
                raise
            except json.JSONDecodeError as e:
                logger.warning(
                    "tool_json_parse_error",
                    tool=name,
                    error=str(e),
                    position=e.pos,
                )
                raise ValueError(f"Invalid JSON in {name}: {e}") from e
            except KeyError as e:
                logger.warning(
                    "tool_missing_field",
                    tool=name,
                    field=str(e),
                )
                raise ValueError(f"Missing required field in {name}: {e}") from e
            except Exception as e:
                logger.exception(
                    "tool_unexpected_error",
                    tool=name,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                raise

        return wrapper

    return decorator


__all__ = [
    "ToolErrorModel",
    "ToolErrorCode",
    "ToolResponse",
    "ToolInputValidationError",
    "create_error_response",
    "create_success_response",
    "handle_tool_errors",
    "parse_list_field",
    "safe_parse_json",
    "safe_parse_json_strict",
    "validate_tool_input",
]
