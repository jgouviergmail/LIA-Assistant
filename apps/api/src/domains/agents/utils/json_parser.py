"""
Robust JSON parsing utilities for LLM responses.

This module provides utilities for extracting and parsing JSON from LLM responses,
which may be wrapped in markdown code blocks or contain other formatting.

Benefits:
- Centralized JSON extraction logic
- Robust handling of various LLM output formats
- Comprehensive error handling with context
- Metrics and logging for observability
- Reusable across all agents services

Usage:
    from src.domains.agents.utils.json_parser import extract_json_from_llm_response

    result = extract_json_from_llm_response(
        response_text=llm_output,
        expected_type=dict,
        required_fields=["primary_domain", "confidence"],
        context="hierarchical_stage1",
    )

    if result.success:
        data = result.data
    else:
        logger.error("parse_failed", error=result.error)

Phase: Multi-Domain Architecture v1.0
Created: 2025-11-19
"""

import json
import re
from dataclasses import dataclass
from typing import Any

import structlog

from src.infrastructure.observability.metrics_agents import (
    agent_llm_json_parse_errors_total,
    agent_llm_json_parse_success_total,
)

logger = structlog.get_logger(__name__)


@dataclass
class JSONParseResult:
    """Result of JSON parsing operation."""

    success: bool
    data: Any | None
    error: str | None = None
    raw_text: str | None = None  # For debugging
    extracted_json: str | None = None  # JSON text before parsing


class JSONParseError(Exception):
    """Exception raised when JSON parsing fails."""

    def __init__(self, message: str, raw_text: str | None = None):
        super().__init__(message)
        self.raw_text = raw_text


def extract_json_from_llm_response(
    response_text: str,
    expected_type: type = dict,
    required_fields: list[str] | None = None,
    context: str = "unknown",
    run_id: str = "unknown",
) -> JSONParseResult:
    """
    Extract and parse JSON from LLM response text.

    Handles various LLM output formats:
    - Plain JSON
    - JSON wrapped in ```json ... ``` blocks
    - JSON wrapped in ``` ... ``` blocks
    - JSON with leading/trailing text

    Args:
        response_text: Raw text from LLM response
        expected_type: Expected Python type (dict, list, etc.)
        required_fields: List of required field names (for dict only)
        context: Context string for logging (e.g., "hierarchical_stage1")
        run_id: Run identifier for tracing

    Returns:
        JSONParseResult with success status and parsed data or error

    Examples:
        >>> result = extract_json_from_llm_response('{"key": "value"}', dict)
        >>> result.success
        True
        >>> result.data
        {'key': 'value'}

        >>> result = extract_json_from_llm_response('```json\\n{"key": "value"}\\n```', dict)
        >>> result.success
        True
    """
    if not response_text:
        error = "Empty response text"
        logger.warning(
            "json_parse_empty_response",
            context=context,
            run_id=run_id,
        )
        agent_llm_json_parse_errors_total.labels(
            context=context,
            error_type="empty_response",
        ).inc()
        return JSONParseResult(
            success=False,
            data=None,
            error=error,
            raw_text=response_text,
        )

    # Try to extract JSON from the response
    json_text = _extract_json_text(response_text)

    # Attempt to parse the extracted JSON
    try:
        data = json.loads(json_text)

        # Validate expected type
        if not isinstance(data, expected_type):
            error = f"Expected {expected_type.__name__}, got {type(data).__name__}"
            logger.warning(
                "json_parse_type_mismatch",
                context=context,
                run_id=run_id,
                expected_type=expected_type.__name__,
                actual_type=type(data).__name__,
            )
            agent_llm_json_parse_errors_total.labels(
                context=context,
                error_type="type_mismatch",
            ).inc()
            return JSONParseResult(
                success=False,
                data=None,
                error=error,
                raw_text=response_text,
                extracted_json=json_text,
            )

        # Validate required fields for dict
        if required_fields and isinstance(data, dict):
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                error = f"Missing required fields: {missing_fields}"
                logger.warning(
                    "json_parse_missing_fields",
                    context=context,
                    run_id=run_id,
                    missing_fields=missing_fields,
                    available_fields=list(data.keys()),
                )
                agent_llm_json_parse_errors_total.labels(
                    context=context,
                    error_type="missing_fields",
                ).inc()
                return JSONParseResult(
                    success=False,
                    data=data,  # Return partial data for debugging
                    error=error,
                    raw_text=response_text,
                    extracted_json=json_text,
                )

        # Success
        logger.debug(
            "json_parse_success",
            context=context,
            run_id=run_id,
            data_type=type(data).__name__,
            data_keys=list(data.keys()) if isinstance(data, dict) else None,
        )
        agent_llm_json_parse_success_total.labels(context=context).inc()

        return JSONParseResult(
            success=True,
            data=data,
            error=None,
            raw_text=response_text,
            extracted_json=json_text,
        )

    except json.JSONDecodeError as e:
        error = f"JSON decode error: {e}"
        logger.warning(
            "json_parse_decode_error",
            context=context,
            run_id=run_id,
            error=str(e),
            json_text_preview=json_text[:200] if json_text else None,
            raw_text_preview=response_text[:200] if response_text else None,
        )
        agent_llm_json_parse_errors_total.labels(
            context=context,
            error_type="decode_error",
        ).inc()
        return JSONParseResult(
            success=False,
            data=None,
            error=error,
            raw_text=response_text,
            extracted_json=json_text,
        )


def _extract_json_text(response_text: str) -> str:
    """
    Extract JSON text from various LLM response formats.

    Handles:
    - ```json ... ``` blocks
    - ``` ... ``` blocks
    - Plain JSON with/without surrounding text
    - Multiple JSON blocks (returns first valid one)

    Args:
        response_text: Raw LLM response

    Returns:
        Extracted JSON string ready for parsing
    """
    text = response_text.strip()

    # Strategy 1: Extract from ```json ... ``` block
    if "```json" in text:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1).strip()

    # Strategy 2: Extract from ``` ... ``` block (may or may not have json label)
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            extracted = match.group(1).strip()
            # Remove "json" if it's on the first line
            if extracted.lower().startswith("json"):
                extracted = extracted[4:].strip()
            return extracted

    # Strategy 3: Find JSON object/array boundaries
    # Look for outermost { } or [ ]
    first_brace = text.find("{")
    first_bracket = text.find("[")

    if first_brace == -1 and first_bracket == -1:
        # No JSON structure found, return as-is
        return text

    # Determine if it starts with object or array
    if first_bracket == -1 or (first_brace != -1 and first_brace < first_bracket):
        # Starts with {
        start = first_brace
    else:
        # Starts with [
        start = first_bracket

    # Find matching closing bracket/brace
    depth = 0
    in_string = False
    escape_next = False
    end = start

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{" or char == "[":
            depth += 1
        elif char == "}" or char == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if depth != 0:
        # Unbalanced brackets, return from start to end of text
        return text[start:]

    return text[start:end]


def validate_json_structure(
    data: dict[str, Any],
    schema: dict[str, type],
    context: str = "unknown",
) -> tuple[bool, list[str]]:
    """
    Validate JSON data structure against a simple schema.

    Args:
        data: Parsed JSON data
        schema: Dict mapping field names to expected types
        context: Context for logging

    Returns:
        Tuple of (is_valid, list of error messages)

    Example:
        >>> schema = {"name": str, "count": int, "items": list}
        >>> valid, errors = validate_json_structure(data, schema)
    """
    errors = []

    for field, expected_type in schema.items():
        if field not in data:
            errors.append(f"Missing field: {field}")
        elif not isinstance(data[field], expected_type):
            errors.append(
                f"Field '{field}': expected {expected_type.__name__}, "
                f"got {type(data[field]).__name__}"
            )

    if errors:
        logger.debug(
            "json_structure_validation_failed",
            context=context,
            errors=errors,
        )

    return len(errors) == 0, errors


__all__ = [
    "JSONParseResult",
    "JSONParseError",
    "extract_json_from_llm_response",
    "validate_json_structure",
]
