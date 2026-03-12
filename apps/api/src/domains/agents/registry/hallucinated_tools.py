"""
Hallucinated Tools Registry - Auto-enriching reference file.

Architecture v3.2 (2026-01-03)

This module maintains a registry of tool patterns that LLMs commonly
hallucinate (invent) during planning. The registry auto-enriches by
writing to a persistent JSON file every time a new hallucination is detected.

Files:
    - hallucinated_tools.json: Persistent storage of detected patterns
    - Located in same directory as this module

Auto-enrichment:
    When a new hallucinated tool is detected that doesn't match existing
    patterns, it's automatically added to the JSON file for future reference.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# FILE PATHS
# =============================================================================

# JSON file in same directory as this module
_MODULE_DIR = Path(__file__).parent
HALLUCINATIONS_FILE = _MODULE_DIR / "hallucinated_tools.json"

# Thread lock for file operations
_file_lock = threading.Lock()


# =============================================================================
# DEFAULT PATTERNS (initial seed)
# =============================================================================

DEFAULT_PATTERNS: list[str] = [
    "resolve_reference",
    "get_reference",
    "resolve_context",
    "get_context",
    "resolve_item",
    "get_resolved",
    "lookup_reference",
    "dereference",
]

DEFAULT_EXACT_TOOLS: list[str] = [
    "resolve_reference_tool",
    "get_reference_tool",
]


# =============================================================================
# REGISTRY MANAGEMENT
# =============================================================================


def _load_registry() -> dict[str, Any]:
    """Load registry from JSON file, creating if doesn't exist."""
    with _file_lock:
        if not HALLUCINATIONS_FILE.exists():
            # Create initial file
            initial_data = {
                "patterns": DEFAULT_PATTERNS,
                "exact_tools": DEFAULT_EXACT_TOOLS,
                "history": [],
                "stats": {
                    "total_detections": 0,
                    "last_updated": datetime.now(UTC).isoformat(),
                },
            }
            _save_registry_unlocked(initial_data)
            return initial_data

        try:
            with open(HALLUCINATIONS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("hallucination_registry_load_error", error=str(e))
            return {
                "patterns": DEFAULT_PATTERNS,
                "exact_tools": DEFAULT_EXACT_TOOLS,
                "history": [],
                "stats": {"total_detections": 0},
            }


def _save_registry_unlocked(data: dict[str, Any]) -> None:
    """Save registry to JSON file (caller must hold lock)."""
    try:
        data["stats"]["last_updated"] = datetime.now(UTC).isoformat()
        with open(HALLUCINATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("hallucination_registry_save_error", error=str(e))


def _save_registry(data: dict[str, Any]) -> None:
    """Save registry to JSON file (thread-safe)."""
    with _file_lock:
        _save_registry_unlocked(data)


# =============================================================================
# PUBLIC API
# =============================================================================


def is_hallucinated_tool(tool_name: str) -> tuple[bool, str]:
    """
    Check if a tool name matches a known hallucination pattern.

    Args:
        tool_name: The tool name to check.

    Returns:
        Tuple of (is_hallucinated, pattern_matched).
        If not hallucinated, pattern_matched is empty string.
    """
    if not tool_name:
        return False, ""

    registry = _load_registry()
    tool_lower = tool_name.lower()

    # Check exact matches first
    for exact in registry.get("exact_tools", []):
        if tool_lower == exact.lower():
            return True, f"exact:{exact}"

    # Check pattern matches
    for pattern in registry.get("patterns", []):
        if pattern.lower() in tool_lower:
            return True, f"pattern:{pattern}"

    return False, ""


def record_hallucination(
    tool_name: str,
    domain: str = "",
    query: str = "",
    auto_add: bool = True,
) -> None:
    """
    Record a hallucination and auto-enrich the registry.

    This function:
    1. Logs the hallucination to the history
    2. Increments stats
    3. Optionally adds new patterns if not already covered

    Args:
        tool_name: The hallucinated tool name.
        domain: The domain context when hallucination occurred.
        query: The user query (will be truncated for privacy).
        auto_add: If True, add as new exact_tool if not matched by patterns.
    """
    registry = _load_registry()
    tool_lower = tool_name.lower()

    # Check if already covered
    is_covered, pattern = is_hallucinated_tool(tool_name)

    # Add to history (keep last 100)
    history_entry = {
        "tool": tool_name,
        "domain": domain,
        "query_preview": query[:80] if query else "",
        "timestamp": datetime.now(UTC).isoformat(),
        "was_new": not is_covered,
    }
    registry["history"].append(history_entry)
    if len(registry["history"]) > 100:
        registry["history"] = registry["history"][-100:]

    # Update stats
    registry["stats"]["total_detections"] = registry["stats"].get("total_detections", 0) + 1

    # Auto-add if not already covered
    if auto_add and not is_covered:
        # Add as exact tool
        if tool_lower not in [t.lower() for t in registry.get("exact_tools", [])]:
            registry["exact_tools"].append(tool_lower)
            logger.info(
                "hallucination_auto_added",
                tool_name=tool_name,
                domain=domain,
            )

    _save_registry(registry)

    logger.warning(
        "hallucination_recorded",
        tool_name=tool_name,
        domain=domain,
        was_new=not is_covered,
        pattern_matched=pattern if is_covered else "none",
        total=registry["stats"]["total_detections"],
    )


def get_registry() -> dict[str, Any]:
    """
    Get the full registry for inspection.

    Returns:
        Dictionary with patterns, exact_tools, history, and stats.
    """
    return _load_registry()


def add_pattern(pattern: str) -> None:
    """
    Manually add a new pattern to the registry.

    Args:
        pattern: The substring pattern to add.
    """
    registry = _load_registry()
    if pattern.lower() not in [p.lower() for p in registry.get("patterns", [])]:
        registry["patterns"].append(pattern.lower())
        _save_registry(registry)
        logger.info("hallucination_pattern_added", pattern=pattern)


def add_exact_tool(tool_name: str) -> None:
    """
    Manually add an exact tool name to the blacklist.

    Args:
        tool_name: The exact tool name to blacklist.
    """
    registry = _load_registry()
    if tool_name.lower() not in [t.lower() for t in registry.get("exact_tools", [])]:
        registry["exact_tools"].append(tool_name.lower())
        _save_registry(registry)
        logger.info("hallucinated_tool_added", tool_name=tool_name)
