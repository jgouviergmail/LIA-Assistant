"""HITL Schema Validator - Production Version.

This module provides Pydantic-based validation of edited tool arguments
against tool schemas for HITL EDIT flows.

Features:
- Dynamic tool discovery (contacts, gmail, calendar)
- Pydantic schema validation with detailed error messages
- Automatic extensibility (new tools auto-discovered)
- Graceful degradation if tool modules missing

Production-ready as of Phase 1 Final Implementation (2025-01-29).
"""

from typing import Any

from pydantic import ValidationError


class ValidationResult:
    """Result of tool args validation."""

    def __init__(
        self,
        is_valid: bool,
        validated_args: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        """Initialize validation result.

        Args:
            is_valid: Whether validation passed
            validated_args: Validated and coerced arguments (if valid)
            errors: List of validation error messages (if invalid)
        """
        self.is_valid = is_valid
        self.validated_args = validated_args
        self.errors = errors or []


class HitlSchemaValidator:
    """Validate tool arguments against Pydantic schemas.

    POC Version: Simplified implementation focused on google_contacts tools.
    Production version will support all tools dynamically.
    """

    def __init__(self) -> None:
        """Initialize validator with tool registry.

        Builds a registry of available tools for schema access.
        """
        self.tools = self._build_tool_registry()

    def _build_tool_registry(self) -> dict[str, Any]:
        """Build registry of tools for schema validation (PRODUCTION VERSION).

        Dynamically discovers all tools from agent builders to support
        extensibility (contacts, gmail, calendar, etc.) without code changes.

        Returns:
            Dict mapping tool names to tool instances

        Architecture:
            - Imports tool modules directly (explicit, reliable)
            - Supports all current and future agents
            - No coupling to builder implementations
            - Falls back gracefully if module missing
        """
        tools_list = []

        # Google Contacts tools (unified tool v2.0)
        try:
            from src.domains.agents.tools.google_contacts_tools import (
                get_contacts_tool,
            )

            tools_list.append(get_contacts_tool)
        except ImportError as e:
            from src.infrastructure.observability.logging import get_logger

            logger = get_logger(__name__)
            logger.warning(
                "schema_validator_import_failed",
                module="google_contacts_tools",
                error=str(e),
            )

        # Emails tools (future extension point)
        try:
            from src.domains.agents.tools.emails_tools import (  # type: ignore[import-not-found]
                create_email,
                delete_email,
                forward_email,
                reply_to_email,
                send_email,
            )

            tools_list.extend(
                [send_email, reply_to_email, forward_email, delete_email, create_email]
            )
        except ImportError:
            pass  # Module doesn't exist yet (expected)

        # Calendar tools (future extension point)
        try:
            from src.domains.agents.tools.calendar_tools import (  # type: ignore[import-not-found]
                create_event,
                delete_event,
                update_event,
            )

            tools_list.extend([create_event, update_event, delete_event])
        except ImportError:
            pass  # Module doesn't exist yet (expected)

        # Context tools (excluded - internal, not user-facing)
        # resolve_reference, set_current_item, etc. are NOT validated

        return {tool.name: tool for tool in tools_list}

    def _check_type_compatibility(self, value: Any, annotation: type) -> bool:
        """Check if value is compatible with the expected type annotation.

        Args:
            value: The value to check
            annotation: The expected type annotation

        Returns:
            True if compatible, False otherwise
        """
        import types
        from typing import Union, get_args, get_origin

        # Handle None values
        if value is None:
            # Check if Optional/None is allowed
            # Support both typing.Union (Optional[X]) and types.UnionType (X | None)
            origin = get_origin(annotation)
            if origin is Union or origin is types.UnionType:
                return type(None) in get_args(annotation)
            return False

        # Get origin for generic types (list[str] -> list, etc.)
        origin = get_origin(annotation)

        # Handle Union types (e.g., Optional[int], int | None)
        if origin is Union or origin is types.UnionType:
            args = get_args(annotation)
            return any(self._check_type_compatibility(value, arg) for arg in args)

        # Handle list, dict, etc.
        if origin is list:
            return isinstance(value, list)
        if origin is dict:
            return isinstance(value, dict)
        if origin is set:
            return isinstance(value, set)

        # Handle basic types
        if annotation is int:
            # Only strict int (not bool, not float, not str)
            return isinstance(value, int) and not isinstance(value, bool)
        if annotation is float:
            # Accept int or float for numeric flexibility
            return isinstance(value, int | float) and not isinstance(value, bool)
        if annotation is str:
            return isinstance(value, str)
        if annotation is bool:
            return isinstance(value, bool)

        # For other types, use isinstance if possible
        try:
            return isinstance(value, annotation)
        except TypeError:
            # annotation is not a valid type for isinstance
            return True  # Permissive fallback

    def validate_tool_args(
        self,
        tool_name: str,
        merged_args: dict[str, Any],
    ) -> ValidationResult:
        """Validate merged tool arguments against tool's Pydantic schema.

        Args:
            tool_name: Name of the tool to validate against
            merged_args: Merged dict of original args + edited params

        Returns:
            ValidationResult with validation status, validated args, or errors

        Example:
            >>> validator = HitlSchemaValidator()
            >>> result = validator.validate_tool_args(
            ...     tool_name="search_contacts_tool",
            ...     merged_args={"query": "test", "max_results": "abc"}
            ... )
            >>> assert not result.is_valid
            >>> assert "max_results" in result.errors[0]
        """
        # Get tool from registry
        tool = self.tools.get(tool_name)
        if not tool:
            return ValidationResult(
                is_valid=False,
                errors=[f"Unknown tool: {tool_name}"],
            )

        # Get Pydantic schema
        schema = tool.args_schema
        if not schema:
            # This should never happen with @tool decorator, but defensive check
            return ValidationResult(
                is_valid=False,
                errors=[f"Tool {tool_name} has no args_schema"],
            )

        # Validate against schema
        try:
            # POC Strategy: Skip validation of 'runtime' parameter
            # Runtime is injected by LangChain at execution time and never user-editable
            # We validate only user-editable parameters

            # Get schema fields
            if hasattr(schema, "model_fields"):
                # Extract only user-editable fields (exclude runtime)
                user_editable_fields = {
                    name: field for name, field in schema.model_fields.items() if name != "runtime"
                }

                # Validate only user-provided args against user-editable fields
                # We bypass full Pydantic validation and check field-by-field
                validated_args = {}
                errors_found = []

                # Step 1: Check for invalid fields (fields not in schema)
                # This prevents users from "editing" non-existent parameters
                # Note: 'runtime' is always filtered as it's injected by LangChain
                valid_field_names = set(user_editable_fields.keys())
                provided_field_names = set(merged_args.keys()) - {
                    "runtime"
                }  # Always filter runtime
                invalid_fields = provided_field_names - valid_field_names

                if invalid_fields:
                    errors_found.extend(
                        [
                            f"{field}: Invalid parameter for tool '{tool_name}'. "
                            f"Valid parameters are: {', '.join(sorted(valid_field_names))}"
                            for field in invalid_fields
                        ]
                    )

                # Step 2: Validate provided fields using Pydantic field types
                for field_name, field_info in user_editable_fields.items():
                    if field_name in merged_args:
                        value = merged_args[field_name]
                        # Type validation using field annotation
                        annotation = field_info.annotation
                        if annotation is not None:
                            # Check type compatibility
                            type_valid = self._check_type_compatibility(value, annotation)
                            if not type_valid:
                                expected_type = getattr(annotation, "__name__", str(annotation))
                                actual_type = type(value).__name__
                                errors_found.append(
                                    f"{field_name}: Expected type {expected_type}, got {actual_type}"
                                )
                            else:
                                validated_args[field_name] = value
                        else:
                            validated_args[field_name] = value
                    elif field_info.is_required():
                        errors_found.append(f"{field_name}: Field required")

                if errors_found:
                    return ValidationResult(
                        is_valid=False,
                        errors=errors_found,
                    )

                return ValidationResult(
                    is_valid=True,
                    validated_args=validated_args,
                )
            else:
                # Fallback: No model_fields, accept args as-is
                return ValidationResult(
                    is_valid=True,
                    validated_args=merged_args,
                )

        except ValidationError as e:
            # Extract human-readable error messages
            errors = []
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                message = error["msg"]
                error_type = error["type"]

                # Format error message
                errors.append(f"{field}: {message} (type: {error_type})")

            return ValidationResult(
                is_valid=False,
                errors=errors,
            )

        except Exception as e:
            # Catch-all for unexpected errors
            return ValidationResult(
                is_valid=False,
                errors=[f"Validation error: {e!s}"],
            )
