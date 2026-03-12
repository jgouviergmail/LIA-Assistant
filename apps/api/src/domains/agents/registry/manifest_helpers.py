"""
Manifest Helpers - Utility functions for tool manifest management.

This module provides generic, reusable helpers for working with tool manifests,
including compact example formatting for LLM prompts.

Best Practices (LangChain v1.0 / LangGraph v1.0):
- Generic and domain-agnostic (works for contacts, email, calendar, etc.)
- Token-optimized output formats
- Consistent formatting across all tools
"""

from typing import Any


def format_compact_examples(
    examples: list[dict[str, Any]],
    max_examples: int = 2,
    format_style: str = "minimal",
) -> str:
    """
    Format tool examples in ultra-compact style for LLM prompt inclusion.

    This helper generates concise example strings suitable for tool descriptions,
    minimizing token usage while maintaining clarity for the planner LLM.

    Args:
        examples: List of example dicts with "input" and "output" keys
        max_examples: Maximum number of examples to include (default: 2)
        format_style: Formatting style:
            - "minimal": Ultra-compact 1-line per example (~30 tokens/example)
            - "structured": Multi-line with clear structure (~50 tokens/example)

    Returns:
        Formatted example string ready for inclusion in tool description

    Examples:
        >>> examples = [
        ...     {
        ...         "input": {"query": "john", "max_results": 5},
        ...         "output": {"contacts": [...], "total": 1}
        ...     }
        ... ]
        >>> formatted = format_compact_examples(examples, format_style="minimal")
        >>> print(formatted)
        **Examples**:
        • query='john', max_results=5 → contacts=[...], total=1

        >>> formatted = format_compact_examples(examples, format_style="structured")
        >>> print(formatted)
        **Examples**:
        1. Search by name:
           Input: query='john', max_results=5
           Output: contacts=[{name, emails}], total=1
    """
    if not examples:
        return ""

    # Limit number of examples
    examples = examples[:max_examples]

    if format_style == "minimal":
        return _format_minimal(examples)
    elif format_style == "structured":
        return _format_structured(examples)
    else:
        raise ValueError(f"Unknown format_style: {format_style}")


def _format_minimal(examples: list[dict[str, Any]]) -> str:
    """
    Format examples in minimal style (1 line per example).

    Ultra-compact format optimized for token efficiency:
    • param1=value1, param2=value2 → output_summary

    Token usage: ~25-35 tokens per example
    """
    lines = ["**Examples**:"]

    for ex in examples:
        input_data = ex.get("input", {})
        output_data = ex.get("output", {})

        # Format input as key=value pairs
        input_parts = []
        for key, value in input_data.items():
            # Compact repr for common types
            if isinstance(value, str):
                input_parts.append(f"{key}='{value}'")
            elif isinstance(value, int | float | bool):
                input_parts.append(f"{key}={value}")
            elif isinstance(value, list):
                input_parts.append(f"{key}=[{len(value)} items]")
            elif isinstance(value, dict):
                input_parts.append(f"{key}={{...}}")
            else:
                input_parts.append(f"{key}={repr(value)}")

        input_str = ", ".join(input_parts)

        # Format output as summary
        output_str = _summarize_output(output_data)

        lines.append(f"• {input_str} → {output_str}")

    return "\n".join(lines)


def _format_structured(examples: list[dict[str, Any]]) -> str:
    """
    Format examples in structured style (multi-line per example).

    Clearer format with numbered examples and explicit Input/Output labels:
    1. Description:
       Input: param1=value1, param2=value2
       Output: output_summary

    Token usage: ~45-60 tokens per example
    """
    lines = ["**Examples**:"]

    for i, ex in enumerate(examples, 1):
        input_data = ex.get("input", {})
        output_data = ex.get("output", {})
        description = ex.get("description", f"Example {i}")

        lines.append(f"{i}. {description}:")

        # Format input
        input_parts = []
        for key, value in input_data.items():
            if isinstance(value, str):
                input_parts.append(f"{key}='{value}'")
            else:
                input_parts.append(f"{key}={value}")

        input_str = ", ".join(input_parts)
        lines.append(f"   Input: {input_str}")

        # Format output
        output_str = _summarize_output(output_data)
        lines.append(f"   Output: {output_str}")

    return "\n".join(lines)


def _summarize_output(output: dict[str, Any]) -> str:
    """
    Summarize output dict into compact string.

    Intelligently formats output based on common patterns:
    - Arrays: show count and preview
    - Objects: show key structure
    - Primitives: show value
    """
    parts = []

    for key, value in output.items():
        if isinstance(value, list):
            if len(value) == 0:
                parts.append(f"{key}=[]")
            elif len(value) == 1:
                # Single item array - show structure
                if isinstance(value[0], dict):
                    keys = list(value[0].keys())[:3]  # First 3 keys
                    parts.append(f"{key}=[{{{', '.join(keys)}}}]")
                else:
                    parts.append(f"{key}=[{value[0]}]")
            else:
                # Multi-item array - show count
                parts.append(f"{key}=[{len(value)} items]")
        elif isinstance(value, dict):
            keys = list(value.keys())[:3]
            parts.append(f"{key}={{{', '.join(keys)}}}")
        elif isinstance(value, str):
            # Truncate long strings
            if len(value) > 30:
                parts.append(f"{key}='{value[:27]}...'")
            else:
                parts.append(f"{key}='{value}'")
        elif isinstance(value, int | float | bool):
            parts.append(f"{key}={value}")
        else:
            parts.append(f"{key}={type(value).__name__}")

    return ", ".join(parts)


def enrich_description_with_examples(
    base_description: str,
    examples: list[dict[str, Any]],
    max_examples: int = 2,
    format_style: str = "minimal",
) -> str:
    """
    Enrich a tool description with compact examples.

    Convenience function that appends formatted examples to an existing description,
    ensuring consistent formatting across all tools.

    Args:
        base_description: Original tool description
        examples: List of example dicts
        max_examples: Max examples to include (default: 2)
        format_style: "minimal" or "structured" (default: "minimal")

    Returns:
        Enriched description with examples appended

    Example:
        >>> desc = "Search contacts by name or email."
        >>> examples = [{"input": {"query": "john"}, "output": {"total": 1}}]
        >>> enriched = enrich_description_with_examples(desc, examples)
        >>> print(enriched)
        Search contacts by name or email.

        **Examples**:
        • query='john' → total=1
    """
    if not examples:
        return base_description

    formatted_examples = format_compact_examples(
        examples,
        max_examples=max_examples,
        format_style=format_style,
    )

    # Add spacing before examples
    return f"{base_description}\n\n{formatted_examples}"
