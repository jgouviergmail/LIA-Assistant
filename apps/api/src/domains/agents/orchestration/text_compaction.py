"""
Text Compaction - Token Optimization for Embedded Data Structures.

Post-Jinja evaluation compaction of embedded data structures in text parameters.
When the planner uses $steps.X.places in content_instruction, Jinja evaluates it
to full Python repr of raw Google Places data (~2000 tokens/place). This module
detects and compacts these embedded structures using payload_to_text() (~60 tokens/place).

Architecture:
    Jinja2 evaluates parameters → Text compaction detects embedded data → Compacts to
    concise format → LLM receives optimized tokens instead of raw API payloads.

Example:
    Input (after Jinja evaluation):
        "Write email about these hotels: [{'displayName': {'text': 'Hotel A', ...}, ...}]"

    Output (after compaction):
        "Write email about these hotels: [Hotel A | rating: 4.5 | address: 123 Main St]"

Token savings: ~97% reduction (2000 tokens → 60 tokens per entity)

Used by:
    - parallel_executor.py: Called after Jinja2 evaluation, before tool execution

References:
    - llm_serializer.py: payload_to_text() for generic data serialization
    - constants.py: TEXT_COMPACTION_PARAMS for targetable parameters

Created: 2026-01-21
"""

from __future__ import annotations

import ast
import re
from typing import Any

import structlog

from src.core.config import get_settings
from src.core.constants import TEXT_COMPACTION_PARAMS
from src.domains.agents.display.llm_serializer import payload_to_text

logger = structlog.get_logger(__name__)

# ============================================================================
# PRE-COMPILED REGEX PATTERNS (Performance optimization)
# ============================================================================
# Compile regex patterns at module load time to avoid recompilation overhead
# during hot paths (execute_plan_parallel may call this multiple times per request)

# Pattern to detect start of Python list: [ followed by { (possibly with whitespace)
# Matches: "[{", "[ {", "[\n{", etc.
PATTERN_LIST_START = re.compile(r"\[\s*\{")

# Pattern to detect start of Python dict: { followed by key quote
# Matches: "{'key", '{"key', etc.
PATTERN_DICT_START = re.compile(r"\{\s*['\"]")


# ============================================================================
# MAIN API
# ============================================================================


def compact_text_params(
    parameters: dict[str, Any],
    tool_name: str,
) -> dict[str, Any]:
    """
    Compact embedded data structures in text parameters.

    Post-processes evaluated parameters after Jinja2 template evaluation.
    Detects Python data structures (lists, dicts) embedded in text parameters
    and compacts them using payload_to_text() for token optimization.

    Args:
        parameters: Evaluated parameters dict from Jinja2 evaluator
        tool_name: Name of the tool (for logging context)

    Returns:
        Parameters dict with compacted text values (original dict modified in place)

    Example:
        >>> params = {"content_instruction": "Hotels: [{'displayName': ...}]"}
        >>> compact_text_params(params, "send_email_tool")
        {"content_instruction": "Hotels: [Hotel A | rating: 4.5 | ...]"}
    """
    settings = get_settings()

    # Feature flag check
    if not settings.text_compaction_enabled:
        return parameters

    # Quick check: any targetable parameters present?
    targetable_params = set(parameters.keys()) & TEXT_COMPACTION_PARAMS
    if not targetable_params:
        return parameters

    # Process each targetable parameter
    total_chars_saved = 0
    compacted_count = 0

    for param_name in targetable_params:
        value = parameters[param_name]

        # Only process string values
        if not isinstance(value, str):
            continue

        # Skip if too short to contain meaningful data
        if len(value) < settings.text_compaction_min_size:
            continue

        # Attempt compaction
        compacted_value, chars_saved = _compact_embedded_data(
            text=value,
            max_items=settings.text_compaction_max_items,
            max_field_length=settings.text_compaction_max_field_length,
            min_size=settings.text_compaction_min_size,
        )

        if chars_saved > 0:
            parameters[param_name] = compacted_value
            total_chars_saved += chars_saved
            compacted_count += 1

    # Log if any compaction occurred
    if compacted_count > 0:
        logger.info(
            "text_compaction_applied",
            tool_name=tool_name,
            params_compacted=compacted_count,
            chars_saved=total_chars_saved,
            estimated_tokens_saved=total_chars_saved // 4,  # Rough estimate: 4 chars per token
        )

    return parameters


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _compact_embedded_data(
    text: str,
    max_items: int = 3,
    max_field_length: int = 40,
    min_size: int = 200,
) -> tuple[str, int]:
    """
    Detect and compact embedded data structures in text.

    Finds Python data structures (lists of dicts, single dicts) embedded in
    text and replaces them with compacted text representations.

    Args:
        text: Input text that may contain embedded data
        max_items: Max items to show per list in compacted format
        max_field_length: Max length for field values in compacted format
        min_size: Minimum size for a data block to be worth compacting

    Returns:
        Tuple of (compacted_text, chars_saved)
        If no compaction occurred, returns (text, 0)
    """
    # Find all data blocks
    data_blocks = _find_data_blocks(text)

    if not data_blocks:
        return text, 0

    # Process blocks in reverse order to preserve positions
    result = text
    total_saved = 0

    for start_pos, end_pos in sorted(data_blocks, reverse=True):
        block = text[start_pos:end_pos]

        # Skip if block is too small
        if len(block) < min_size:
            continue

        # Try to parse and compact
        compacted = _try_compact_block(block, max_items, max_field_length)
        if compacted and len(compacted) < len(block):
            saved = len(block) - len(compacted)
            result = result[:start_pos] + compacted + result[end_pos:]
            total_saved += saved

    return result, total_saved


def _find_data_blocks(text: str) -> list[tuple[int, int]]:
    """
    Find Python data structure blocks (lists, dicts) in text.

    Identifies the start and end positions of embedded data structures
    that can be safely parsed and compacted.

    Args:
        text: Text that may contain embedded data structures

    Returns:
        List of (start_pos, end_pos) tuples for each data block found

    Note:
        Only finds top-level structures - nested structures are handled
        by the compaction process itself.
    """
    blocks = []

    # Find list of dicts: [{"key": ...}, ...]
    for match in PATTERN_LIST_START.finditer(text):
        start_pos = match.start()
        end_pos = _find_matching_bracket(text, start_pos, "[", "]")
        if end_pos > start_pos:
            blocks.append((start_pos, end_pos))

    # Find single dicts: {"key": ...}
    # Only if not already inside a list block
    for match in PATTERN_DICT_START.finditer(text):
        start_pos = match.start()

        # Skip if this position is inside an existing block
        if any(start <= start_pos < end for start, end in blocks):
            continue

        end_pos = _find_matching_bracket(text, start_pos, "{", "}")
        if end_pos > start_pos:
            blocks.append((start_pos, end_pos))

    return blocks


def _find_matching_bracket(
    text: str,
    start_pos: int,
    open_bracket: str,
    close_bracket: str,
) -> int:
    """
    Find the position after the matching closing bracket.

    Handles nested brackets properly. Returns -1 if no matching bracket found.

    Args:
        text: Text to search
        start_pos: Position of opening bracket
        open_bracket: Opening bracket character ('[' or '{')
        close_bracket: Closing bracket character (']' or '}')

    Returns:
        Position after the closing bracket, or -1 if not found

    Example:
        >>> _find_matching_bracket("[{a: [1,2]}, {b: 3}]", 0, "[", "]")
        20  # Position after the final ]
    """
    if start_pos >= len(text) or text[start_pos] != open_bracket:
        return -1

    depth = 0
    in_string = False
    string_char = None
    escape_next = False
    pos = start_pos

    while pos < len(text):
        char = text[pos]

        if escape_next:
            escape_next = False
            pos += 1
            continue

        if char == "\\":
            escape_next = True
            pos += 1
            continue

        if char in ('"', "'"):
            if in_string:
                if char == string_char:
                    in_string = False
                    string_char = None
            else:
                in_string = True
                string_char = char
            pos += 1
            continue

        if in_string:
            pos += 1
            continue

        if char == open_bracket:
            depth += 1
        elif char == close_bracket:
            depth -= 1
            if depth == 0:
                return pos + 1  # Position after closing bracket

        pos += 1

    return -1  # No matching bracket found


def _try_compact_block(
    block: str,
    max_items: int,
    max_field_length: int,
) -> str | None:
    """
    Try to parse and compact a data block.

    Safely parses Python literal and applies payload_to_text() compaction.
    Returns None if parsing fails or data is not compactable.

    Args:
        block: Python literal string (e.g., "[{'key': 'value'}]")
        max_items: Max items to show per list
        max_field_length: Max length for field values

    Returns:
        Compacted string representation, or None if failed
    """
    try:
        # Safe literal evaluation (no code execution)
        data = ast.literal_eval(block)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        # Invalid Python literal - cannot compact
        return None

    # Check if data is compactable
    if not _is_compactable(data):
        return None

    # Compact the data
    return _compact_data_structure(data, max_items, max_field_length)


def _is_compactable(data: Any) -> bool:
    """
    Check if data structure is suitable for compaction.

    Returns True for:
    - List of dicts (common API response format)
    - Single dict with nested structure
    - List of scalars (converted to comma-separated)

    Returns False for:
    - Empty collections
    - Single scalars (no compaction benefit)
    - Deeply nested structures that might lose important info

    Args:
        data: Parsed Python data structure

    Returns:
        True if data should be compacted, False otherwise
    """
    if data is None:
        return False

    if isinstance(data, list):
        if not data:
            return False
        # List of dicts - ideal for compaction
        if isinstance(data[0], dict):
            return True
        # List of scalars - minimal benefit but still compact
        return len(data) > 3

    if isinstance(data, dict):
        # Dict with meaningful content
        return len(data) > 1

    # Scalars - no benefit
    return False


def _compact_data_structure(
    data: Any,
    max_items: int,
    max_field_length: int,
) -> str:
    """
    Compact a data structure to concise text format.

    Uses payload_to_text() for dict compaction and formats lists
    with numbered items for clarity.

    Args:
        data: Parsed Python data structure
        max_items: Max items to show per list
        max_field_length: Max length for field values

    Returns:
        Compacted string representation

    Example:
        >>> _compact_data_structure([{"name": "A"}, {"name": "B"}], 3, 40)
        "[1. A | ..., 2. B | ...]"
    """
    if isinstance(data, list):
        if not data:
            return "[]"

        # List of dicts - compact each item
        if isinstance(data[0], dict):
            items = []
            for i, item in enumerate(data[:max_items], 1):
                compacted = payload_to_text(item, max_items=max_items, max_length=max_field_length)
                items.append(f"{i}. {compacted}")

            result = ", ".join(items)
            if len(data) > max_items:
                result += f" (+{len(data) - max_items} more)"
            return f"[{result}]"

        # List of scalars - simple comma join
        items = [str(x)[:max_field_length] for x in data[:max_items]]
        result = ", ".join(items)
        if len(data) > max_items:
            result += f" (+{len(data) - max_items})"
        return f"[{result}]"

    if isinstance(data, dict):
        return payload_to_text(data, max_items=max_items, max_length=max_field_length)

    # Fallback for unexpected types
    return str(data)[:200]


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "compact_text_params",
]
