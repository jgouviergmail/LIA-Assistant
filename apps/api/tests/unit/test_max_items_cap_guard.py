"""Systemic guard: every connector item search/list call enforces the global cap.

The global per-request volumetry ceiling ``settings.api_max_items_per_request`` is
what guarantees we control how many items each domain API can return (cost,
latency, prompt tokens). It MUST be applied to every item-returning search/list
call, via the centralized helper ``apply_max_items_limit`` (or ``_paginate`` /
``_paginate_list``, which call it internally).

A client that builds a pagination request (``{"maxResults": n}``,
``{"pageSize": n}``, ``{"$top": n}``), passes ``limit=max_results`` to an
external fetch, or slices ``items[:max_results]`` WITHOUT routing the size
through the helper silently bypasses the ceiling — exactly the class of bug that
let Google Calendar and the Apple clients return unbounded volumes.

This test enforces the invariant statically:

1. It walks every connector client module AST.
2. For each top-level method / function it detects a pagination "sink" (a
   ``maxResults``/``pageSize``/``$top`` dict key, a ``limit=<size>`` keyword, or
   a ``[:<size>]`` slice) and a "cap marker" (a call to ``apply_max_items_limit``
   or ``*._paginate*``).
3. Any function with a sink but no marker is a violation.

Metadata-enumeration methods (listing calendars / labels / task-lists for
name→ID resolution, NOT item volumetry) are intentionally exempt via
``ALLOWED``. To exempt a new one, add ``(module_name, func_name)`` with a
justification — do not weaken the scan.

Context: 2026-07 full-codebase audit, wave 4 (calendar search hardening).
"""

import ast
from pathlib import Path

import pytest

CLIENTS_DIR = Path(__file__).parents[2] / "src" / "domains" / "connectors" / "clients"

# Dict keys that set an external API page/result size.
PAGINATION_KEYS = {"maxResults", "pageSize", "$top"}
# Variable names that carry a caller-controlled result size (as slice upper bound
# or ``limit=`` keyword). Constants (``limit=10``) are already bounded.
PAGINATION_VARS = {"max_results", "effective_max_results", "page_size"}
# Calls proving the size was routed through the centralized ceiling.
CAP_MARKER_NAMES = {"apply_max_items_limit"}
CAP_MARKER_ATTRS = {"_paginate", "_paginate_list"}

# (module filename, function name) exempt because they enumerate STRUCTURAL
# metadata (few, bounded), not item volumetry — capping them at the global
# ceiling would break name→ID resolution for power users.
ALLOWED: set[tuple[str, str]] = {
    # Metadata enumeration for name→ID resolution (few, bounded) — capping at the
    # item ceiling would break resolution for users with many calendars/labels.
    ("google_calendar_client.py", "list_calendars"),
    ("apple_calendar_client.py", "_list_calendars_impl"),
    ("microsoft_calendar_client.py", "list_calendars"),
    ("microsoft_outlook_client.py", "list_labels"),
    ("microsoft_tasks_client.py", "_resolve_list_id"),
    # Bulk contact sync that fills the Redis cache via its OWN page_token
    # pagination (fetches every contact across pages, then local search returns
    # capped results). Not an agent-facing search — must not be ceiling-capped.
    ("google_people_client.py", "list_connections"),
}


def _top_level_functions(tree: ast.Module):
    """Yield module-level functions and class methods (not nested closures)."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                    yield member


def _has_sink(func: ast.AST) -> bool:
    """True if the function (incl. nested closures) builds a pagination request."""
    for node in ast.walk(func):
        # {"maxResults": n} / {"pageSize": n} / {"$top": n}
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value in PAGINATION_KEYS:
                    return True
        # some_params["$top"] = n  (subscript assignment)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value in PAGINATION_KEYS:
                return True
        # fetch(..., limit=max_results)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "limit"
                    and isinstance(kw.value, ast.Name)
                    and kw.value.id in PAGINATION_VARS
                ):
                    return True
        # items[:max_results]
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            upper = node.slice.upper
            if isinstance(upper, ast.Name) and upper.id in PAGINATION_VARS:
                return True
    return False


def _has_cap_marker(func: ast.AST) -> bool:
    """True if the function routes a size through the centralized ceiling."""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            called = node.func
            if isinstance(called, ast.Name) and called.id in CAP_MARKER_NAMES:
                return True
            if isinstance(called, ast.Attribute) and called.attr in CAP_MARKER_ATTRS:
                return True
    return False


def _client_files() -> list[Path]:
    return sorted(p for p in CLIENTS_DIR.rglob("*.py") if p.name != "__init__.py")


def test_clients_directory_exists() -> None:
    assert CLIENTS_DIR.is_dir(), f"clients dir not found: {CLIENTS_DIR}"
    assert _client_files(), "no client modules discovered"


def test_every_item_search_enforces_global_cap() -> None:
    """No connector item search/list call may bypass the global volumetry cap."""
    violations: list[str] = []
    for path in _client_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for func in _top_level_functions(tree):
            if (path.name, func.name) in ALLOWED:
                continue
            if _has_sink(func) and not _has_cap_marker(func):
                violations.append(f"{path.name}::{func.name} (line {func.lineno})")

    assert not violations, (
        "These connector methods build a pagination request without routing the "
        "size through apply_max_items_limit / _paginate (global volumetry cap "
        "bypass). Fix by calling `max_results = apply_max_items_limit(max_results)` "
        "before the request, or add a justified entry to ALLOWED if it is a "
        "metadata enumeration:\n  - " + "\n  - ".join(violations)
    )


def test_allowlist_entries_are_real() -> None:
    """Guard against stale ALLOWED entries (renamed/removed methods)."""
    seen: set[tuple[str, str]] = set()
    for path in _client_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for func in _top_level_functions(tree):
            seen.add((path.name, func.name))
    stale = ALLOWED - seen
    assert not stale, f"stale ALLOWED entries (method no longer exists): {stale}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
