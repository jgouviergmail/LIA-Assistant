"""
Reference Validator - Validate $steps.X.field.path references against tool schemas.

Validates cross-step references BEFORE execution to detect schema mismatches ($0 cost).
Uses ToolSchemaRegistry for schema lookup and returns actionable error messages for LLM retry.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

import structlog

from src.domains.agents.tools.common import ToolErrorCode

logger = structlog.get_logger(__name__)


# ============================================================================
# Reference Validation Errors
# ============================================================================


@dataclass
class ReferenceValidationError:
    """Error from reference validation with structured info for LLM retry."""

    code: ToolErrorCode
    message: str
    step_id: str
    step_index: int
    parameter_name: str
    reference: str
    invalid_path: str
    tool_name: str | None = None
    context: dict[str, Any] | None = None
    # Phase 2.4 - Enhanced error information for LLM retry
    invalid_field: str | None = None
    available_fields: list[str] | None = None
    field_types: dict[str, str] | None = None
    suggestions: list[str] | None = None
    correct_examples: list[str] | None = None


# ============================================================================
# Reference Validator
# ============================================================================


class ReferenceValidator:
    """Validator for $steps.X.field.path references against tool schemas."""

    # Pattern to extract $steps.X.field.path references
    # Captures: step_id, field_path
    # Examples:
    #   $steps.search.contacts[0].emailAddresses[0].value
    #   -> step_id="search", field_path="contacts[0].emailAddresses[0].value"
    STEPS_REFERENCE_PATTERN = re.compile(
        r"\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_\[\]\.\*]+)"
    )

    def validate_references_in_step(
        self,
        step_id: str,
        step_index: int,
        parameters: dict[str, Any],
        step_tools: dict[str, str],
        condition: str | None = None,
        step_results: dict[str, dict[str, Any]] | None = None,  # Phase 2.4 - Issue #40
    ) -> list[ReferenceValidationError]:
        """
        Validate all $steps references in a single step's parameters and condition.

        Phase 2.4 - Issue #40: Extended with runtime array bounds validation.

        Args:
            step_id: ID of current step being validated
            step_index: Index of step in plan
            parameters: Step parameters (may contain $steps references)
            step_tools: Mapping step_id -> tool_name for schema lookup
            condition: Optional condition string (for CONDITIONAL steps)
            step_results: Optional actual data from previous steps (for bounds checking)

        Returns:
            List of ReferenceValidationError (empty if all valid)

        Examples:
            >>> validator = ReferenceValidator()
            >>> errors = validator.validate_references_in_step(
            ...     step_id="send_email",
            ...     step_index=1,
            ...     parameters={
            ...         "to": "$steps.search.contacts[0].emailAddresses[0].value",
            ...         "subject": "Hello"
            ...     },
            ...     step_tools={"search": "search_contacts_tool"}
            ... )
            >>> assert not errors  # Valid
            >>>
            >>> # Invalid reference (wrong field name)
            >>> errors = validator.validate_references_in_step(
            ...     step_id="send_email",
            ...     step_index=1,
            ...     parameters={
            ...         "to": "$steps.search.contacts[0].emails[0].value"  # Wrong!
            ...     },
            ...     step_tools={"search": "search_contacts_tool"}
            ... )
            >>> assert len(errors) == 1
            >>> assert "emailAddresses" in errors[0].message
        """
        errors: list[ReferenceValidationError] = []

        # Validate parameters
        for param_name, param_value in parameters.items():
            if isinstance(param_value, str):
                param_errors = self._validate_reference_string(
                    reference_string=param_value,
                    step_id=step_id,
                    step_index=step_index,
                    parameter_name=param_name,
                    step_tools=step_tools,
                    step_results=step_results,  # Phase 2.4 - Issue #40
                )
                errors.extend(param_errors)

        # Validate condition (if present)
        if condition:
            condition_errors = self._validate_reference_string(
                reference_string=condition,
                step_id=step_id,
                step_index=step_index,
                parameter_name="condition",
                step_tools=step_tools,
                step_results=step_results,  # Phase 2.4 - Issue #40
            )
            errors.extend(condition_errors)

        return errors

    def _validate_reference_string(
        self,
        reference_string: str,
        step_id: str,
        step_index: int,
        parameter_name: str,
        step_tools: dict[str, str],
        step_results: dict[str, dict[str, Any]] | None = None,
    ) -> list[ReferenceValidationError]:
        """Validate all $steps references in a string (parameter value or condition)."""
        errors: list[ReferenceValidationError] = []

        # Extract all $steps.X.field.path references
        matches = self.STEPS_REFERENCE_PATTERN.findall(reference_string)

        for referenced_step_id, field_path in matches:
            # Get tool_name for referenced step
            tool_name = step_tools.get(referenced_step_id)

            if not tool_name:
                # Step not found - this should be caught by PlanValidator._validate_step_references()
                # But log for debugging
                logger.debug(
                    "reference_validation_step_not_found",
                    step_id=step_id,
                    step_index=step_index,
                    parameter_name=parameter_name,
                    referenced_step_id=referenced_step_id,
                    message=f"Referenced step '{referenced_step_id}' not found in step_tools",
                )
                continue

            # Validate field path against tool schema (+ runtime bounds if step_results provided)
            # Phase 2.4 - Issue #40: Propagate step_results for array bounds validation
            path_errors = self._validate_field_path(
                tool_name=tool_name,
                field_path=field_path,
                full_reference=f"$steps.{referenced_step_id}.{field_path}",
                step_id=step_id,
                step_index=step_index,
                parameter_name=parameter_name,
                step_results=step_results,  # Phase 2.4 - Issue #40
            )
            errors.extend(path_errors)

        return errors

    def _validate_field_path(
        self,
        tool_name: str,
        field_path: str,
        full_reference: str,
        step_id: str,
        step_index: int,
        parameter_name: str,
        step_results: dict[str, dict[str, Any]] | None = None,
    ) -> list[ReferenceValidationError]:
        """Validate field path against tool schema and runtime data (if available)."""
        # Phase 2.5: Validate against reference_examples FIRST (fail-fast, $0 cost)
        # This catches common errors like "email" instead of "emailAddresses[0].value"
        ref_errors = self._validate_against_reference_examples(
            tool_name=tool_name,
            field_path=field_path,
            full_reference=full_reference,
            step_id=step_id,
            step_index=step_index,
            parameter_name=parameter_name,
        )
        if ref_errors:
            # reference_examples validation failed - return immediately (fail-fast)
            logger.info(
                "reference_validation_ref_examples_failed",
                step_id=step_id,
                full_reference=full_reference,
                tool_name=tool_name,
                field_path=field_path,
                errors_count=len(ref_errors),
                message="Path validation against reference_examples failed",
            )
            return ref_errors

        # Phase 2.4 - Issue #40: Runtime validation SECOND (fail-fast)
        # Check array bounds against actual data BEFORE schema validation
        if step_results:
            bounds_errors = self._validate_array_bounds(
                field_path=field_path,
                full_reference=full_reference,
                step_results=step_results,
                step_id=step_id,
                step_index=step_index,
                parameter_name=parameter_name,
            )
            if bounds_errors:
                # Runtime validation failed - return immediately (fail-fast)
                logger.info(
                    "reference_validation_bounds_check_failed",
                    step_id=step_id,
                    full_reference=full_reference,
                    errors_count=len(bounds_errors),
                    message="Array bounds validation failed - indices out of range",
                )
                return bounds_errors

        # Get schema from registry
        from src.domains.agents.tools.schema_registry import ToolSchemaRegistry

        registry = ToolSchemaRegistry.get_instance()
        schema_data = registry.get_schema(tool_name)

        if not schema_data:
            # Schema not found - tool not registered
            # This is a warning, not an error (fail-safe: allow if no schema)
            logger.warning(
                "reference_validation_no_schema",
                tool_name=tool_name,
                step_id=step_id,
                step_index=step_index,
                parameter_name=parameter_name,
                message=f"No schema registered for tool '{tool_name}' - skipping validation",
            )
            return []

        response_schema = schema_data["response_schema"]

        # Parse field path into segments
        # Example: "contacts[0].emailAddresses[0].value"
        # Segments: ["contacts", "[0]", "emailAddresses", "[0]", "value"]
        segments = self._parse_field_path(field_path)

        # Traverse schema following segments
        errors = self._traverse_schema_path(
            schema=response_schema,
            segments=segments,
            tool_name=tool_name,
            field_path=field_path,
            full_reference=full_reference,
            step_id=step_id,
            step_index=step_index,
            parameter_name=parameter_name,
        )

        return errors

    def _validate_against_reference_examples(
        self,
        tool_name: str,
        field_path: str,
        full_reference: str,
        step_id: str,
        step_index: int,
        parameter_name: str,
    ) -> list[ReferenceValidationError]:
        """Validate field path against reference_examples from manifest (fast, cheap, actionable)."""
        try:
            from src.domains.agents.registry.agent_registry import AgentRegistry

            registry = AgentRegistry.get_instance()
            manifest = registry.get_tool_manifest(tool_name)

            if not manifest or not hasattr(manifest, "reference_examples"):
                # No manifest or no reference_examples - skip validation
                return []

            reference_examples = manifest.reference_examples or []
            if not reference_examples:
                # No reference_examples defined - skip validation
                return []

            # Normalize field_path for pattern matching
            # Replace numeric indices [0], [1], etc. with [*] for pattern comparison
            normalized_path = self._normalize_path_for_matching(field_path)

            # Check if path matches any reference_example pattern
            if self._path_matches_reference_examples(normalized_path, reference_examples):
                return []  # Valid path

            # Path doesn't match - generate helpful error
            # Find most similar reference_example for suggestion
            suggestions = self._find_similar_reference_examples(normalized_path, reference_examples)

            # Build error message with correct paths
            error_message = (
                f"Invalid reference path: '{field_path}' is not a documented path for {tool_name}.\n\n"
                f"Reference: {full_reference}\n\n"
                f"Valid paths from manifest (reference_examples):\n"
            )
            for ref_ex in reference_examples[:8]:  # Show up to 8 examples
                error_message += f"  [OK] {ref_ex}\n"

            if suggestions:
                error_message += f"\nDid you mean: {suggestions[0]}?\n"

            error_message += (
                f"\nContext: Step '{step_id}', parameter '{parameter_name}'\n"
                f"Fix: Use one of the documented paths above."
            )

            return [
                ReferenceValidationError(
                    code=ToolErrorCode.INVALID_INPUT,
                    message=error_message,
                    step_id=step_id,
                    step_index=step_index,
                    parameter_name=parameter_name,
                    reference=full_reference,
                    invalid_path=field_path,
                    tool_name=tool_name,
                    context={
                        "reference_examples": reference_examples,
                        "normalized_path": normalized_path,
                    },
                    invalid_field=field_path,
                    available_fields=reference_examples,
                    suggestions=suggestions,
                    correct_examples=[f"$steps.STEP_ID.{ex}" for ex in reference_examples[:5]],
                )
            ]

        except Exception as e:
            # Fail-safe: if manifest lookup fails, skip validation
            logger.debug(
                "reference_examples_validation_error",
                tool_name=tool_name,
                field_path=field_path,
                error=str(e),
                message="Failed to validate against reference_examples - skipping",
            )
            return []

    def _normalize_path_for_matching(self, path: str) -> str:
        """Normalize field path for pattern matching (replace [0], [1] with [*])."""
        # Replace [0], [1], [2], etc. with [*]
        return re.sub(r"\[\d+\]", "[*]", path)

    def _path_matches_reference_examples(
        self, normalized_path: str, reference_examples: list[str]
    ) -> bool:
        """Check if normalized path matches any reference_example pattern."""
        for ref_example in reference_examples:
            # Normalize the reference example too
            normalized_ref = self._normalize_path_for_matching(ref_example)

            # Exact match
            if normalized_path == normalized_ref:
                return True

            # Path is more specific (has more segments but starts with example)
            # e.g., path="contacts[*].emailAddresses[*].value" matches ref="contacts[*].emailAddresses"
            if normalized_path.startswith(normalized_ref + "."):
                return True

            # Path is prefix of example (valid if example goes deeper)
            # e.g., path="contacts" matches ref="contacts[*].resource_name"
            if normalized_ref.startswith(normalized_path + ".") or normalized_ref.startswith(
                normalized_path + "["
            ):
                return True

        return False

    def _find_similar_reference_examples(
        self, normalized_path: str, reference_examples: list[str]
    ) -> list[str]:
        """Find most similar reference_examples using difflib (max 3)."""
        if not reference_examples:
            return []

        # Normalize all reference examples for comparison
        normalized_refs = [self._normalize_path_for_matching(ref) for ref in reference_examples]

        # Use difflib to find similar paths (cutoff=0.5 for broader matching)
        similar_normalized = difflib.get_close_matches(
            normalized_path.lower(),
            [ref.lower() for ref in normalized_refs],
            n=3,
            cutoff=0.5,
        )

        # Map back to original reference examples
        result = []
        for similar in similar_normalized:
            for idx, normalized_ref in enumerate(normalized_refs):
                if normalized_ref.lower() == similar:
                    result.append(reference_examples[idx])
                    break

        return result

    def _parse_field_path(self, field_path: str) -> list[str]:
        """Parse field path into segments (field names and array indices)."""
        segments = []

        # Split by dots, but preserve array indices
        # Example: "contacts[0].emailAddresses[0].value"
        # -> ["contacts[0]", "emailAddresses[0]", "value"]
        parts = field_path.split(".")

        for part in parts:
            # Check if part contains array index
            # Example: "contacts[0]" -> ["contacts", "[0]"]
            if "[" in part:
                # Split on first [
                field_name, array_part = part.split("[", 1)
                segments.append(field_name)
                segments.append(f"[{array_part}")  # Re-add [ for consistency
            else:
                segments.append(part)

        return segments

    def _traverse_schema_path(
        self,
        schema: dict[str, Any],
        segments: list[str],
        tool_name: str,
        field_path: str,
        full_reference: str,
        step_id: str,
        step_index: int,
        parameter_name: str,
    ) -> list[ReferenceValidationError]:
        """Traverse JSON Schema following field path segments."""
        current_schema = schema
        path_so_far = []

        for _i, segment in enumerate(segments):
            path_so_far.append(segment)

            # Handle array index [0], [1], [*]
            if segment.startswith("["):
                # Check current schema is array
                if current_schema.get("type") != "array":
                    return [
                        ReferenceValidationError(
                            code=ToolErrorCode.INVALID_INPUT,
                            message=(
                                f"Invalid reference: '{'.'.join(path_so_far[:-1])}' is not an array. "
                                f"Cannot use array index {segment}."
                            ),
                            step_id=step_id,
                            step_index=step_index,
                            parameter_name=parameter_name,
                            reference=full_reference,
                            invalid_path=".".join(path_so_far),
                            tool_name=tool_name,
                            context={
                                "actual_type": current_schema.get("type", "unknown"),
                                "segment": segment,
                            },
                        )
                    ]

                # Move into array items schema
                if "items" not in current_schema:
                    # Array without items schema - cannot validate further
                    logger.debug(
                        "reference_validation_array_no_items",
                        tool_name=tool_name,
                        field_path=field_path,
                        message="Array schema has no 'items' - cannot validate further",
                    )
                    return []  # Fail-safe: allow

                current_schema = current_schema["items"]

            # Handle field name
            else:
                # Check current schema is object
                if current_schema.get("type") != "object":
                    return [
                        ReferenceValidationError(
                            code=ToolErrorCode.INVALID_INPUT,
                            message=(
                                f"Invalid reference: '{'.'.join(path_so_far[:-1])}' is not an object. "
                                f"Cannot access field '{segment}'."
                            ),
                            step_id=step_id,
                            step_index=step_index,
                            parameter_name=parameter_name,
                            reference=full_reference,
                            invalid_path=".".join(path_so_far),
                            tool_name=tool_name,
                            context={
                                "actual_type": current_schema.get("type", "unknown"),
                                "segment": segment,
                            },
                        )
                    ]

                # Check field exists in properties
                properties = current_schema.get("properties", {})

                if segment not in properties:
                    # Phase 2.4 - Enhanced error message with types and registry examples
                    available_fields = list(properties.keys())
                    suggestions = self._suggest_field_names(segment, available_fields)
                    field_types = self._get_field_info_with_types(current_schema)
                    registry_examples = self._get_registry_examples(tool_name, segment)

                    # Build enhanced error message
                    enhanced_message = self._build_enhanced_error_message(
                        invalid_field=segment,
                        available_fields=available_fields,
                        field_types=field_types,
                        suggestions=suggestions,
                        full_reference=full_reference,
                        tool_name=tool_name,
                        step_id=step_id,
                        parameter_name=parameter_name,
                        registry_examples=registry_examples,
                    )

                    return [
                        ReferenceValidationError(
                            code=ToolErrorCode.INVALID_INPUT,
                            message=enhanced_message,
                            step_id=step_id,
                            step_index=step_index,
                            parameter_name=parameter_name,
                            reference=full_reference,
                            invalid_path=".".join(path_so_far),
                            tool_name=tool_name,
                            context={
                                "invalid_field": segment,
                                "available_fields": available_fields,
                                "suggestions": suggestions,
                            },
                            # Phase 2.4 - Enhanced fields
                            invalid_field=segment,
                            available_fields=available_fields,
                            field_types=field_types,
                            suggestions=suggestions,
                            correct_examples=registry_examples,
                        )
                    ]

                # Move into field's schema
                current_schema = properties[segment]

        # All segments valid
        return []

    def _suggest_field_names(self, invalid_field: str, available_fields: list[str]) -> list[str]:
        """Suggest correct field names based on similarity using difflib (max 3)."""
        if not available_fields:
            return []

        # Use difflib for similarity matching (cutoff=0.6 for reasonable matches)
        suggestions = difflib.get_close_matches(
            invalid_field.lower(),
            [f.lower() for f in available_fields],
            n=3,
            cutoff=0.6,
        )

        # Map back to original case
        result = []
        for suggestion in suggestions:
            for original_field in available_fields:
                if original_field.lower() == suggestion:
                    result.append(original_field)
                    break

        return result

    def _get_field_info_with_types(self, schema: dict[str, Any]) -> dict[str, str]:
        """Extract field names with their types from JSON Schema (field_name -> type_string)."""
        field_types: dict[str, str] = {}

        if schema.get("type") != "object":
            return field_types

        properties = schema.get("properties", {})

        for field_name, field_schema in properties.items():
            field_type = field_schema.get("type", "unknown")

            if field_type == "array":
                # Check array items type
                items = field_schema.get("items", {})
                items_type = items.get("type", "unknown")

                if items_type == "object":
                    field_types[field_name] = "array<object>"
                elif items_type == "string":
                    field_types[field_name] = "array<string>"
                elif items_type == "number":
                    field_types[field_name] = "array<number>"
                else:
                    field_types[field_name] = "array"
            else:
                field_types[field_name] = field_type

        return field_types

    def _build_enhanced_error_message(
        self,
        invalid_field: str,
        available_fields: list[str],
        field_types: dict[str, str],
        suggestions: list[str],
        full_reference: str,
        tool_name: str,
        step_id: str,
        parameter_name: str,
        registry_examples: list[str] | None = None,
    ) -> str:
        """
        Build enhanced error message for LLM retry.

        Args:
            invalid_field: The invalid field name
            available_fields: Valid field names
            field_types: Field name -> type mapping
            suggestions: Suggested field names
            full_reference: Full $steps reference
            tool_name: Tool name
            step_id: Step ID
            parameter_name: Parameter name
            registry_examples: Registry examples

        Returns:
            Error message string
        """
        parts = [
            f"Invalid reference '{full_reference}': field '{invalid_field}' not found in '{tool_name}'."
        ]

        # Suggestion (most important)
        if suggestions:
            fix = f"Use '{suggestions[0]}'" + (
                f" or {', '.join(suggestions[1:])}" if len(suggestions) > 1 else ""
            )
            parts.append(f"Suggestion: {fix} instead.")

        # Registry examples (if available)
        if registry_examples:
            examples_str = ", ".join(f"'{ex}'" for ex in registry_examples[:3])
            parts.append(f"Examples: {examples_str}")

        # Available fields (concise list)
        fields_str = ", ".join(f"'{f}'" for f in available_fields[:8])
        if len(available_fields) > 8:
            fields_str += f" (+{len(available_fields) - 8} more)"
        parts.append(f"Available fields: {fields_str}")

        # Context
        parts.append(f"Context: step '{step_id}', parameter '{parameter_name}'")

        return " ".join(parts)

    def _get_registry_examples(self, tool_name: str, invalid_field: str) -> list[str]:
        """Get relevant examples from ToolSchemaRegistry."""
        try:
            from src.domains.agents.tools.schema_registry import ToolSchemaRegistry

            registry = ToolSchemaRegistry.get_instance()
            schema_info = registry.get_schema(tool_name)

            if not schema_info or "examples" not in schema_info:
                return []

            examples = schema_info["examples"]
            relevant_examples = []

            # Extract all example references (up to 5)
            for example in examples[:5]:
                if isinstance(example, dict) and "reference" in example:
                    relevant_examples.append(example["reference"])

            return relevant_examples

        except Exception as e:
            logger.debug(
                "reference_validator_registry_examples_error",
                tool_name=tool_name,
                invalid_field=invalid_field,
                error=str(e),
                message="Failed to retrieve registry examples",
            )
            return []

    def _extract_array_indices(self, field_path: str) -> list[tuple[str, int]]:
        """Extract array field names and indices from field path (generic parser)."""
        indices = []

        # Pattern: field_name[index]
        # Example: contacts[2]
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]"

        matches = re.findall(pattern, field_path)

        for field_name, index_str in matches:
            indices.append((field_name, int(index_str)))

        return indices

    def _extract_step_id(self, full_reference: str) -> str:
        """Extract step_id from $steps.X.field.path reference (generic)."""
        # Pattern: $steps.step_id.
        pattern = r"\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)\."

        match = re.search(pattern, full_reference)

        if match:
            return match.group(1)

        return ""

    def _validate_array_bounds(
        self,
        field_path: str,
        full_reference: str,
        step_results: dict[str, dict[str, Any]],
        step_id: str,
        step_index: int,
        parameter_name: str,
    ) -> list[ReferenceValidationError]:
        """Validate array indices against actual result data (generic, works for all domains)."""
        errors = []

        # Parse field_path to extract array indices (GENERIC)
        indices = self._extract_array_indices(field_path)

        if not indices:
            # No array indices to validate
            return []

        # Extract referenced step ID from full_reference
        referenced_step_id = self._extract_step_id(full_reference)

        if not referenced_step_id:
            # Cannot extract step ID - skip validation (fail-safe)
            logger.debug(
                "array_bounds_validation_skipped_no_step_id",
                full_reference=full_reference,
                message="Could not extract step ID from reference",
            )
            return []

        if referenced_step_id not in step_results:
            # Step not found in results - skip validation (fail-safe)
            # This could happen if validating before step execution
            logger.debug(
                "array_bounds_validation_skipped_step_not_found",
                referenced_step_id=referenced_step_id,
                available_steps=list(step_results.keys()),
                message="Referenced step not found in step_results",
            )
            return []

        result_data = step_results[referenced_step_id].get("data", {})

        # Traverse data structure following field_path (GENERIC)
        current_data = result_data
        path_segments = []

        for field_name, index in indices:
            path_segments.append(field_name)

            # Navigate to field
            if field_name not in current_data:
                # Field not found - structural issue (should be caught by schema validator)
                logger.debug(
                    "array_bounds_validation_field_not_found",
                    field_name=field_name,
                    path_so_far=".".join(path_segments),
                    message="Field not found in data structure",
                )
                break

            field_value = current_data[field_name]

            # Check if field is array
            if not isinstance(field_value, list):
                # Not an array - structural issue (should be caught by schema validator)
                logger.debug(
                    "array_bounds_validation_not_array",
                    field_name=field_name,
                    actual_type=type(field_value).__name__,
                    message="Field is not an array",
                )
                break

            actual_length = len(field_value)

            # Validate index bounds
            if index >= actual_length:
                errors.append(
                    ReferenceValidationError(
                        code=ToolErrorCode.INVALID_INPUT,
                        message=(
                            f"Array index out of bounds: {field_name}[{index}] "
                            f"but only {actual_length} element(s) available. "
                            f"Valid indices: 0-{actual_length - 1}. "
                            f"Referenced from step '{step_id}', parameter '{parameter_name}'."
                        ),
                        step_id=step_id,
                        step_index=step_index,
                        parameter_name=parameter_name,
                        reference=full_reference,
                        invalid_path=f"{'.'.join(path_segments)}[{index}]",
                        context={
                            "field_name": field_name,
                            "index": index,
                            "actual_length": actual_length,
                            "valid_range": f"0-{actual_length - 1}",
                        },
                    )
                )
                break  # Stop traversal on first error

            # Move to array element for next iteration
            if index < actual_length:
                current_data = field_value[index]

        return errors

    def validate_runtime_array_bounds(
        self,
        step_id: str,
        step_index: int,
        parameters: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
        condition: str | None = None,
    ) -> list[ReferenceValidationError]:
        """
        Validate array bounds in step references using actual runtime data.

        Phase 2.4 - Issue #40: Runtime-only validation (no schema check).
        This is a fail-fast validation that runs BEFORE reference resolution to detect
        array index out of bounds errors early and provide clear error messages.

        GENERIC: Works for ALL domains (contacts, emails, calendar, tasks, drive, etc.).

        Args:
            step_id: ID of current step being validated
            step_index: Index of step in plan
            parameters: Step parameters potentially containing $steps references
            step_results: Actual execution results from completed steps
            condition: Optional condition string to validate

        Returns:
            List of ReferenceValidationError for array bounds violations

        Examples:
            >>> validator = ReferenceValidator()
            >>> # Scenario: search returned 2 contacts, but step references contacts[2]
            >>> params = {
            ...     "resource_names": [
            ...         "$steps.search_contacts.contacts[0].resource_name",
            ...         "$steps.search_contacts.contacts[1].resource_name",
            ...         "$steps.search_contacts.contacts[2].resource_name",  # OUT OF BOUNDS
            ...     ]
            ... }
            >>> step_results = {
            ...     "search_contacts": {
            ...         "data": {"contacts": [obj1, obj2]}  # Only 2 elements (indices 0-1)
            ...     }
            ... }
            >>> errors = validator.validate_runtime_array_bounds(
            ...     step_id="get_contact_details",
            ...     step_index=1,
            ...     parameters=params,
            ...     step_results=step_results,
            ... )
            >>> # Returns 1 error: "Array index out of bounds: contacts[2] but only 2 element(s) available"
        """
        errors: list[ReferenceValidationError] = []

        # Validate references in parameters
        for param_name, param_value in parameters.items():
            param_errors = self._validate_reference_string_runtime(
                reference_string=param_value,
                step_id=step_id,
                step_index=step_index,
                parameter_name=param_name,
                step_results=step_results,
            )
            errors.extend(param_errors)

        # Validate references in condition (if present)
        if condition:
            condition_errors = self._validate_reference_string_runtime(
                reference_string=condition,
                step_id=step_id,
                step_index=step_index,
                parameter_name="condition",
                step_results=step_results,
            )
            errors.extend(condition_errors)

        return errors

    def _validate_reference_string_runtime(
        self,
        reference_string: str | list | dict | Any,
        step_id: str,
        step_index: int,
        parameter_name: str,
        step_results: dict[str, dict[str, Any]],
    ) -> list[ReferenceValidationError]:
        """Validate array bounds in $steps references (runtime only, handles strings/lists/dicts recursively)."""
        errors: list[ReferenceValidationError] = []

        # Handle strings (direct references)
        if isinstance(reference_string, str):
            # Extract all $steps.X.field.path references
            matches = self.STEPS_REFERENCE_PATTERN.findall(reference_string)

            for referenced_step_id, field_path in matches:
                # Validate array bounds (no schema check needed)
                full_reference = f"$steps.{referenced_step_id}.{field_path}"
                bounds_errors = self._validate_array_bounds(
                    field_path=field_path,
                    full_reference=full_reference,
                    step_results=step_results,
                    step_id=step_id,
                    step_index=step_index,
                    parameter_name=parameter_name,
                )
                errors.extend(bounds_errors)

        # Handle lists (e.g., resource_names = [ref1, ref2, ref3])
        elif isinstance(reference_string, list):
            for idx, item in enumerate(reference_string):
                item_errors = self._validate_reference_string_runtime(
                    reference_string=item,
                    step_id=step_id,
                    step_index=step_index,
                    parameter_name=f"{parameter_name}[{idx}]",
                    step_results=step_results,
                )
                errors.extend(item_errors)

        # Handle dicts (nested parameters)
        elif isinstance(reference_string, dict):
            for key, value in reference_string.items():
                nested_errors = self._validate_reference_string_runtime(
                    reference_string=value,
                    step_id=step_id,
                    step_index=step_index,
                    parameter_name=f"{parameter_name}.{key}",
                    step_results=step_results,
                )
                errors.extend(nested_errors)

        return errors


__all__ = [
    "ReferenceValidator",
    "ReferenceValidationError",
]
