"""
Validation helpers for agent tools.

This module provides centralized validation utilities to eliminate the duplicate
validation patterns that appear in 20+ tool files.

Design Philosophy:
- DRY (Don't Repeat Yourself): Extract common validation patterns
- Consistency: Standardized error messages across all tools
- Type Safety: Strict type checking with clear error messages
- i18n Ready: Uses APIMessages for multilingual support

Common Validation Patterns Consolidated:
1. Required field validation (20+ occurrences)
2. Email validation (10+ occurrences)
3. Numeric range validation (15+ occurrences)
4. Date/time validation (8+ occurrences)
5. List validation (10+ occurrences)

Usage Example:
    >>> from src.domains.agents.tools.validation_helpers import (
    ...     require_field,
    ...     validate_fields,
    ...     validate_email_field,
    ...     validate_positive_int,
    ... )
    >>>
    >>> # In a tool execute_api_call method:
    >>> async def execute_api_call(self, client, user_id, **kwargs):
    ...     # Validate single required field
    ...     require_field(kwargs, "query", self.tool_name)
    ...
    ...     # Validate multiple required fields
    ...     validate_fields(kwargs, ["title", "start_datetime"], self.tool_name)
    ...
    ...     # Validate email
    ...     email = validate_email_field(kwargs, "to", self.tool_name)
    ...
    ...     # Validate positive integer with max
    ...     max_results = validate_positive_int(
    ...         kwargs.get("max_results", 10),
    ...         field_name="max_results",
    ...         max_value=100,
    ...         tool_name=self.tool_name
    ...     )
"""

from typing import Any

from src.core.i18n_api_messages import APIMessages
from src.core.validators import validate_email
from src.domains.agents.tools.exceptions import ToolValidationError


def require_field(
    data: dict[str, Any],
    field: str,
    tool_name: str | None = None,
) -> Any:
    """
    Validate that a required field exists and is not empty.

    This eliminates the duplicate pattern that appears in 20+ tools:
        if not kwargs.get("field"):
            raise ToolValidationError(
                APIMessages.field_required("field"),
                field="field"
            )

    Args:
        data: Dictionary containing field data (usually kwargs)
        field: Field name to validate
        tool_name: Optional tool name for logging context

    Returns:
        Field value if valid

    Raises:
        ToolValidationError: If field is missing or empty

    Example:
        >>> kwargs = {"query": "john doe"}
        >>> query = require_field(kwargs, "query", "search_contacts_tool")
        >>> # Returns "john doe"

        >>> kwargs = {}
        >>> require_field(kwargs, "query")
        ToolValidationError: Field 'query' is required
    """
    value = data.get(field)
    if not value:
        raise ToolValidationError(
            message=APIMessages.field_required(field),
            field=field,
        )
    return value


def validate_fields(
    data: dict[str, Any],
    required: list[str],
    tool_name: str | None = None,
) -> None:
    """
    Validate that multiple required fields exist and are not empty.

    This is a batch version of require_field() for tools that need to
    validate multiple fields at once. More efficient than calling
    require_field() multiple times.

    Args:
        data: Dictionary containing field data (usually kwargs)
        required: List of required field names
        tool_name: Optional tool name for logging context

    Raises:
        ToolValidationError: If any required field is missing or empty

    Example:
        >>> kwargs = {"title": "Meeting", "start_datetime": "2025-02-01T10:00:00"}
        >>> validate_fields(kwargs, ["title", "start_datetime"], "create_event_tool")
        >>> # Passes validation

        >>> kwargs = {"title": "Meeting"}
        >>> validate_fields(kwargs, ["title", "start_datetime"])
        ToolValidationError: Missing required fields: start_datetime
    """
    missing = [f for f in required if not data.get(f)]
    if missing:
        if len(missing) == 1:
            raise ToolValidationError(
                message=APIMessages.field_required(missing[0]),
                field=missing[0],
            )
        else:
            raise ToolValidationError(
                message=f"Missing required fields: {', '.join(missing)}",
                field=", ".join(missing),
            )


def validate_email_field(
    data: dict[str, Any],
    field: str,
    tool_name: str | None = None,
    required: bool = True,
) -> str | None:
    """
    Validate that a field contains a valid email address.

    Uses the centralized validate_email() from src.core.validators to ensure
    consistency across the application.

    Args:
        data: Dictionary containing field data (usually kwargs)
        field: Field name to validate
        tool_name: Optional tool name for logging context
        required: Whether field is required (default: True)

    Returns:
        Email address if valid, None if not required and missing

    Raises:
        ToolValidationError: If field is missing (when required) or invalid email

    Example:
        >>> kwargs = {"to": "john@example.com"}
        >>> email = validate_email_field(kwargs, "to", "send_email_tool")
        >>> # Returns "john@example.com"

        >>> kwargs = {"to": "invalid"}
        >>> validate_email_field(kwargs, "to")
        ToolValidationError: Invalid email format for 'to'

        >>> kwargs = {}
        >>> validate_email_field(kwargs, "cc", required=False)
        >>> # Returns None (optional field)
    """
    value = data.get(field)

    if not value:
        if required:
            raise ToolValidationError(
                message=APIMessages.field_required(field),
                field=field,
            )
        return None

    if not validate_email(value):
        raise ToolValidationError(
            message=f"Invalid email format for '{field}': {value}",
            field=field,
        )

    return value


def validate_positive_int(
    value: Any,
    field_name: str,
    min_value: int = 1,
    max_value: int | None = None,
    tool_name: str | None = None,
) -> int:
    """
    Validate that a value is a positive integer within optional range.

    This eliminates the duplicate pattern for max_results and similar fields:
        if not isinstance(max_results, int) or max_results <= 0:
            raise ToolValidationError(...)
        if max_results > 100:
            raise ToolValidationError(...)

    Args:
        value: Value to validate
        field_name: Field name for error messages
        min_value: Minimum allowed value (default: 1)
        max_value: Optional maximum allowed value
        tool_name: Optional tool name for logging context

    Returns:
        Validated integer value

    Raises:
        ToolValidationError: If value is not a positive integer or out of range

    Example:
        >>> max_results = validate_positive_int(10, "max_results", max_value=100)
        >>> # Returns 10

        >>> validate_positive_int(0, "max_results")
        ToolValidationError: 'max_results' must be >= 1

        >>> validate_positive_int(200, "max_results", max_value=100)
        ToolValidationError: 'max_results' cannot exceed 100
    """
    if not isinstance(value, int):
        raise ToolValidationError(
            message=f"'{field_name}' must be an integer, got {type(value).__name__}",
            field=field_name,
        )

    if value < min_value:
        raise ToolValidationError(
            message=f"'{field_name}' must be >= {min_value}, got {value}",
            field=field_name,
        )

    if max_value is not None and value > max_value:
        raise ToolValidationError(
            message=f"'{field_name}' cannot exceed {max_value}, got {value}",
            field=field_name,
        )

    return value


def validate_non_empty_list(
    data: dict[str, Any],
    field: str,
    tool_name: str | None = None,
    required: bool = True,
) -> list[Any] | None:
    """
    Validate that a field contains a non-empty list.

    Args:
        data: Dictionary containing field data (usually kwargs)
        field: Field name to validate
        tool_name: Optional tool name for logging context
        required: Whether field is required (default: True)

    Returns:
        List value if valid, None if not required and missing

    Raises:
        ToolValidationError: If field is missing (when required), not a list, or empty

    Example:
        >>> kwargs = {"attendees": ["john@example.com", "jane@example.com"]}
        >>> attendees = validate_non_empty_list(kwargs, "attendees")
        >>> # Returns ["john@example.com", "jane@example.com"]

        >>> kwargs = {"attendees": []}
        >>> validate_non_empty_list(kwargs, "attendees")
        ToolValidationError: 'attendees' cannot be empty

        >>> kwargs = {}
        >>> validate_non_empty_list(kwargs, "cc", required=False)
        >>> # Returns None (optional field)
    """
    value = data.get(field)

    if value is None:
        if required:
            raise ToolValidationError(
                message=APIMessages.field_required(field),
                field=field,
            )
        return None

    if not isinstance(value, list):
        raise ToolValidationError(
            message=f"'{field}' must be a list, got {type(value).__name__}",
            field=field,
        )

    if len(value) == 0:
        raise ToolValidationError(
            message=f"'{field}' cannot be empty",
            field=field,
        )

    return value


def validate_choice(
    value: Any,
    field_name: str,
    choices: list[Any],
    tool_name: str | None = None,
) -> Any:
    """
    Validate that a value is in a list of allowed choices.

    Args:
        value: Value to validate
        field_name: Field name for error messages
        choices: List of allowed values
        tool_name: Optional tool name for logging context

    Returns:
        Validated value

    Raises:
        ToolValidationError: If value is not in choices

    Example:
        >>> status = validate_choice("completed", "status", ["needsAction", "completed"])
        >>> # Returns "completed"

        >>> validate_choice("invalid", "status", ["needsAction", "completed"])
        ToolValidationError: Invalid value for 'status'. Must be one of: needsAction, completed
    """
    if value not in choices:
        choices_str = ", ".join(str(c) for c in choices)
        raise ToolValidationError(
            message=f"Invalid value for '{field_name}'. Must be one of: {choices_str}",
            field=field_name,
        )
    return value


def validate_date_format(
    value: str,
    field_name: str,
    tool_name: str | None = None,
) -> str:
    """
    Validate that a string is a valid ISO 8601 datetime format.

    Basic validation - checks that value looks like a datetime string.
    For more complex parsing, use parse_datetime from time_utils.

    Args:
        value: Date string to validate
        field_name: Field name for error messages
        tool_name: Optional tool name for logging context

    Returns:
        Validated date string

    Raises:
        ToolValidationError: If value is not a valid datetime format

    Example:
        >>> date = validate_date_format("2025-02-01T10:00:00Z", "start_datetime")
        >>> # Returns "2025-02-01T10:00:00Z"

        >>> validate_date_format("not a date", "start_datetime")
        ToolValidationError: Invalid datetime format for 'start_datetime'
    """
    if not isinstance(value, str):
        raise ToolValidationError(
            message=f"'{field_name}' must be a string, got {type(value).__name__}",
            field=field_name,
        )

    # Basic check: datetime should contain 'T' and have reasonable length
    if "T" not in value or len(value) < 10:
        raise ToolValidationError(
            message=(
                f"Invalid datetime format for '{field_name}'. "
                f"Expected ISO 8601 format (e.g., '2025-02-01T10:00:00Z'), got: {value}"
            ),
            field=field_name,
        )

    return value


def validate_positive_int_or_default(
    value: Any,
    default: int,
    field_name: str = "value",
    min_value: int = 1,
    max_value: int | None = None,
) -> int:
    """
    Validate that a value is a positive integer, or return default.

    This eliminates the duplicate pattern that appears in 10+ tools:
        max_results = (
            raw_max_results
            if isinstance(raw_max_results, int) and raw_max_results > 0
            else default_max_results
        )

    Args:
        value: Value to validate
        default: Default value if validation fails
        field_name: Field name for logging (optional)
        min_value: Minimum allowed value (default: 1)
        max_value: Optional maximum allowed value (caps silently)

    Returns:
        Validated integer value or default

    Example:
        >>> max_results = validate_positive_int_or_default(
        ...     raw_max_results, default=10, max_value=100
        ... )
        >>> # Returns raw_max_results if valid int > 0, else 10
        >>> # Caps at 100 if value exceeds max

        >>> radius = validate_positive_int_or_default(
        ...     raw_radius, default=5000, min_value=1, max_value=50000
        ... )
    """
    # Validate type and min value
    if isinstance(value, int) and value >= min_value:
        # Cap at max_value if specified
        if max_value is not None and value > max_value:
            return max_value
        return value

    # Fallback to default
    return default


__all__ = [
    "require_field",
    "validate_fields",
    "validate_email_field",
    "validate_positive_int",
    "validate_positive_int_or_default",
    "validate_non_empty_list",
    "validate_choice",
    "validate_date_format",
]
