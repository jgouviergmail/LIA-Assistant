"""
HITL Validation Framework (PHASE 3.2.1 - Centralized validation).

Eliminates 8+ duplications of tool name extraction and provides
type-safe, centralized validation for all HITL flows.

This framework replaces scattered validation logic across:
- hitl_management.py (8 duplications)
- service.py (DoS protection)
- resumption_strategies.py (tool extraction)
- hitl_classifier.py (args extraction)

Design Principles:
- Single Source of Truth: All validation constants and logic centralized
- Type Safety: Explicit type coercion and null checks
- i18n Support: All error messages support 6 languages
- Fail Fast: Raise ValidationError immediately on critical failures
- Defensive Programming: Return ValidationResult for recoverable errors

Usage:
    >>> validator = HitlValidator()
    >>> tool_name = validator.extract_tool_name(action)  # Raises on missing name
    >>> result = validator.validate_action_count(actions)  # Returns ValidationResult
"""

from dataclasses import dataclass
from typing import Any, Literal

from src.core.constants import MAX_HITL_ACTIONS_PER_REQUEST
from src.core.field_names import FIELD_TOOL_NAME
from src.domains.agents.constants import (
    HITL_ACTION_ARGS,
    HITL_ACTION_NAME,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationError:
    """
    Single validation error with structured context.

    Attributes:
        field: Field name that failed validation (e.g., "tool_name", "action_count")
        message: Human-readable error message (English, for logging)
        error_code: Machine-readable error code (e.g., "MISSING_TOOL_NAME")
        context: Optional additional context for debugging
    """

    field: str
    message: str
    error_code: str
    context: dict[str, Any] | None = None


@dataclass
class ValidationResult:
    """
    Result of HITL validation operation.

    Attributes:
        is_valid: True if validation passed
        errors: List of validation errors (empty if valid)
        warnings: Non-critical warnings (validation still passes)

    Example:
        >>> result = validator.validate_action_count(actions)
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         logger.error("validation_failed", field=error.field, code=error.error_code)
    """

    is_valid: bool
    errors: list[ValidationError]
    warnings: list[str]


class HitlValidator:
    """
    Centralized HITL validation framework (PHASE 3.2.1).

    Responsibilities:
    - Tool name/args extraction with type safety
    - DoS protection (max actions validation)
    - Tool call ID validation with null safety
    - Parameter validation (empty strings, required fields)
    - Error message generation with i18n support

    This class eliminates 8+ duplications across 4 files and provides
    a single, tested, type-safe API for all HITL validation needs.

    Example:
        >>> validator = HitlValidator(max_actions=10)
        >>>
        >>> # Extract tool data safely
        >>> tool_name = validator.extract_tool_name(action)  # str
        >>> tool_args = validator.extract_tool_args(action)  # dict
        >>>
        >>> # Validate action count (DoS protection)
        >>> result = validator.validate_action_count(actions)
        >>> if not result.is_valid:
        ...     raise ValueError(result.errors[0].message)
        >>>
        >>> # Validate edited params
        >>> result = validator.validate_edited_params(edited_params, "EDIT")
        >>> assert result.is_valid
    """

    def __init__(self, max_actions: int = MAX_HITL_ACTIONS_PER_REQUEST):
        """
        Initialize validator with security limits.

        Args:
            max_actions: Maximum allowed actions per HITL request (DoS protection)
                        Default from settings: MAX_HITL_ACTIONS_PER_REQUEST
        """
        self.max_actions = max_actions

    # ============================================================================
    # TOOL EXTRACTION UTILITIES (Replaces 8+ duplications)
    # ============================================================================

    @staticmethod
    def extract_tool_name(action: dict) -> str:
        """
        Extract tool name from action request with type safety (PHASE 3.2.1).

        Replaces 8+ duplicated implementations across:
        - hitl_management.py (5 locations)
        - service.py (1 location)
        - resumption_strategies.py (1 location)
        - hitl_classifier.py (1 location)

        Handles LangChain v1.0 format variations:
        - action["name"] (primary key, from HITL_ACTION_NAME constant)
        - action["tool"] (fallback for legacy format)
        - action["tool_name"] (alternative format)

        Args:
            action: Action request dict from HumanInTheLoopMiddleware or classification

        Returns:
            Tool name as string (guaranteed non-empty)

        Raises:
            ValueError: If tool name is missing or None

        Example:
            >>> action = {"name": "search_contacts", "args": {"query": "John"}}
            >>> validator = HitlValidator()
            >>> tool_name = validator.extract_tool_name(action)
            >>> assert tool_name == "search_contacts"
            >>> assert isinstance(tool_name, str)
        """
        # Try primary key first (HITL_ACTION_NAME = "name")
        name_raw = action.get(HITL_ACTION_NAME) or action.get("tool") or action.get(FIELD_TOOL_NAME)

        if name_raw is None:
            raise ValueError(
                f"Tool name is missing from action request. "
                f"Expected keys: '{HITL_ACTION_NAME}', 'tool', or '{FIELD_TOOL_NAME}'. "
                f"Received keys: {list(action.keys())}"
            )

        # Force string type (action.get("name") can return int in edge cases)
        # This handles malformed requests from legacy systems
        tool_name = str(name_raw)

        if not tool_name:  # Empty string check
            raise ValueError("Tool name is empty after type coercion")

        return tool_name

    @staticmethod
    def extract_tool_args(action: dict) -> dict[str, Any]:
        """
        Extract tool arguments from action request with format normalization.

        Handles LangChain v1.0 and legacy format variations:
        - action["args"] (primary key, from HITL_ACTION_ARGS constant)
        - action["tool_input"] (legacy LangChain < 0.2)
        - action["tool_args"] (alternative format)

        Args:
            action: Action request dict

        Returns:
            Tool arguments dict (empty dict if missing, never None)

        Example:
            >>> action = {"name": "search", "args": {"query": "test"}}
            >>> validator = HitlValidator()
            >>> args = validator.extract_tool_args(action)
            >>> assert args == {"query": "test"}
            >>>
            >>> # Missing args returns empty dict
            >>> action_no_args = {"name": "search"}
            >>> args = validator.extract_tool_args(action_no_args)
            >>> assert args == {}
        """
        return (
            action.get(HITL_ACTION_ARGS)
            or action.get("tool_input")  # Legacy LangChain format
            or action.get("tool_args")  # Alternative format
            or {}  # Defensive fallback
        )

    # ============================================================================
    # DoS PROTECTION (Consolidates 3 duplicate implementations)
    # ============================================================================

    def validate_action_count(
        self, action_requests: list[dict], raise_on_error: bool = True
    ) -> ValidationResult:
        """
        Validate action count for DoS protection (PHASE 3.2.1).

        Consolidates 3 separate implementations:
        - hitl_management.py:434-466 (validate_hitl_security)
        - service.py:499-536 (inline validation with error stream)
        - service.py:1301 (delegation to mixin)

        Security Context:
        - MAX_HITL_ACTIONS_PER_REQUEST = 10 (validated with POC usage patterns)
        - Protects against malicious/buggy agents requesting 100+ approvals
        - Logs security events for monitoring (hitl_security_events_total metric)

        Args:
            action_requests: List of action dicts from HumanInTheLoopMiddleware interrupt
            raise_on_error: If True, raise ValueError on validation failure (default)
                           If False, return ValidationResult with errors

        Returns:
            ValidationResult with status and errors

        Raises:
            ValueError: If raise_on_error=True and action count exceeds limit

        Example:
            >>> validator = HitlValidator(max_actions=10)
            >>> actions = [{"name": f"tool_{i}"} for i in range(5)]
            >>>
            >>> # Validation passes
            >>> result = validator.validate_action_count(actions)
            >>> assert result.is_valid
            >>>
            >>> # Too many actions
            >>> many_actions = [{"name": f"tool_{i}"} for i in range(15)]
            >>> try:
            ...     validator.validate_action_count(many_actions)
            ... except ValueError as e:
            ...     print(f"DoS protection triggered: {e}")
        """
        action_count = len(action_requests)

        if action_count > self.max_actions:
            error = ValidationError(
                field="action_count",
                message=(
                    f"Too many HITL actions ({action_count} actions). "
                    f"Maximum allowed: {self.max_actions}. "
                    "This limit protects the system from overload."
                ),
                error_code="HITL_MAX_ACTIONS_EXCEEDED",
                context={
                    "action_count": action_count,
                    "max_allowed": self.max_actions,
                    "exceeded_by": action_count - self.max_actions,
                },
            )

            logger.error(
                "hitl_dos_protection_triggered",
                action_count=action_count,
                max_allowed=self.max_actions,
                error_code=error.error_code,
            )

            if raise_on_error:
                raise ValueError(error.message)

            return ValidationResult(is_valid=False, errors=[error], warnings=[])

        return ValidationResult(is_valid=True, errors=[], warnings=[])

    # ============================================================================
    # PARAMETER VALIDATION
    # ============================================================================

    def validate_edited_params(
        self,
        edited_params: dict[str, Any] | None,
        decision_type: Literal["APPROVE", "REJECT", "EDIT", "AMBIGUOUS"],
    ) -> ValidationResult:
        """
        Validate that EDIT decisions have edited_params.

        Replaces inline validation in hitl_management.py:268-284.

        Args:
            edited_params: Parameters edited by user (can be None)
            decision_type: Classification decision type

        Returns:
            ValidationResult with status and errors

        Example:
            >>> validator = HitlValidator()
            >>>
            >>> # EDIT requires edited_params
            >>> result = validator.validate_edited_params(None, "EDIT")
            >>> assert not result.is_valid
            >>> assert result.errors[0].error_code == "EDIT_MISSING_PARAMS"
            >>>
            >>> # APPROVE doesn't require edited_params
            >>> result = validator.validate_edited_params(None, "APPROVE")
            >>> assert result.is_valid
        """
        if decision_type == "EDIT" and not edited_params:
            error = ValidationError(
                field="edited_params",
                message=(
                    "EDIT decision requires edited_params. "
                    "Classification should be AMBIGUOUS if params cannot be extracted."
                ),
                error_code="EDIT_MISSING_PARAMS",
                context={"decision_type": decision_type},
            )

            logger.error(
                "hitl_edit_missing_params",
                decision_type=decision_type,
                error_code=error.error_code,
            )

            return ValidationResult(is_valid=False, errors=[error], warnings=[])

        return ValidationResult(is_valid=True, errors=[], warnings=[])

    # ============================================================================
    # TOOL CALL ID VALIDATION (Fixes null safety gap)
    # ============================================================================

    @staticmethod
    def extract_tool_call_id(tool_call: dict | Any) -> str | None:
        """
        Extract tool_call_id with null safety (PHASE 3.2.1).

        Fixes null safety gap in:
        - hitl_management.py:137 (direct access without check)
        - resumption_strategies.py:442 (fallback to 0 index)

        Handles both dict and object formats from LangChain:
        - Dict format: {"id": "call_abc123", "name": "search", "args": {...}}
        - Object format: ToolCall(id="call_abc123", name="search", args={...})

        Args:
            tool_call: ToolCall from AIMessage.tool_calls (dict or object)

        Returns:
            Tool call ID (str) or None if missing

        Example:
            >>> # Dict format
            >>> tc_dict = {"id": "call_123", "name": "search"}
            >>> validator = HitlValidator()
            >>> tc_id = validator.extract_tool_call_id(tc_dict)
            >>> assert tc_id == "call_123"
            >>>
            >>> # Object format
            >>> from langchain_core.messages import ToolCall
            >>> tc_obj = ToolCall(id="call_456", name="search", args={})
            >>> tc_id = validator.extract_tool_call_id(tc_obj)
            >>> assert tc_id == "call_456"
            >>>
            >>> # Missing ID returns None
            >>> tc_no_id = {"name": "search"}
            >>> tc_id = validator.extract_tool_call_id(tc_no_id)
            >>> assert tc_id is None
        """
        # Handle dict format (most common in HITL context)
        if isinstance(tool_call, dict):
            return tool_call.get("id")

        # Handle object format (from AIMessage.tool_calls)
        if hasattr(tool_call, "id"):
            return tool_call.id

        # Missing ID (should not happen in well-formed requests)
        logger.warning(
            "tool_call_missing_id",
            tool_call_type=type(tool_call).__name__,
            has_dict_id=isinstance(tool_call, dict) and "id" in tool_call,
            has_attr_id=hasattr(tool_call, "id"),
        )

        return None

    # ============================================================================
    # ERROR MESSAGE GENERATION (i18n support)
    # ============================================================================

    @staticmethod
    def format_validation_errors(errors: list[ValidationError], language: str = "fr") -> str:
        """
        Format validation errors into user-friendly message with i18n (PHASE 3.2.1).

        Replaces hardcoded English error in hitl_management.py:842-846.

        Supports 6 languages: fr, en, es, de, it, zh-CN

        Args:
            errors: List of ValidationError objects
            language: Target language code (default: "fr")

        Returns:
            Formatted error message with header, bullet list, and footer

        Example:
            >>> errors = [
            ...     ValidationError("query", "Query is required", "MISSING_QUERY"),
            ...     ValidationError("limit", "Limit must be positive", "INVALID_LIMIT")
            ... ]
            >>> validator = HitlValidator()
            >>> msg = validator.format_validation_errors(errors, language="en")
            >>> assert "I couldn't apply your edits" in msg
            >>> assert "query" in msg
            >>> assert "limit" in msg
        """
        from src.domains.agents.api.error_messages import SSEErrorMessages

        if not errors:
            return ""

        # Build error list using i18n validation_error messages
        error_lines = [SSEErrorMessages.validation_error(err.field, language) for err in errors]

        # Header messages (i18n)
        headers = {
            "fr": "Je n'ai pas pu appliquer tes modifications à cause des erreurs suivantes :",
            "en": "I couldn't apply your edits due to the following errors:",
            "es": "No pude aplicar tus ediciones debido a los siguientes errores:",
            "de": "Ich konnte Ihre Änderungen aufgrund der folgenden Fehler nicht anwenden:",
            "it": "Non sono riuscito ad applicare le tue modifiche a causa dei seguenti errori:",
            "zh-CN": "由于以下错误，我无法应用您的编辑：",
        }

        # Footer messages (i18n)
        footers = {
            "fr": "Veuillez réessayer avec des paramètres valides.",
            "en": "Please try again with valid parameters.",
            "es": "Por favor, inténtelo de nuevo con parámetros válidos.",
            "de": "Bitte versuchen Sie es mit gültigen Parametern erneut.",
            "it": "Si prega di riprovare con parametri validi.",
            "zh-CN": "请使用有效参数重试。",
        }

        header = headers.get(language, headers["en"])
        footer = footers.get(language, footers["en"])

        # Format: Header + bullet list + footer
        return f"{header}\n\n" + "\n".join(f"- {err}" for err in error_lines) + f"\n\n{footer}"
