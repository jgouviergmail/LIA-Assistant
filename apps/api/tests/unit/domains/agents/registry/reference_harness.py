"""Shared oracle for "a published reference path is one the tool produces".

Two suites use it, because tools come in two shapes:

* ``test_manifest_reference_examples_truthful`` — tools whose output can be
  built without a provider (a mixin builder, or a ``format_registry_response``
  fed the client's already-parsed result);
* ``test_manifest_reference_examples_provider_tools`` — tools that build their
  output inside the ``@tool`` body, reachable only by driving the real coroutine
  with a mocked client.

The oracle is the same in both: rebuild what ``completed_steps`` holds when a
``$steps`` reference resolves, then resolve the published paths against it with
the production ``ReferenceResolver``.

Kept in one place so the two suites cannot drift into disagreeing about what a
step result looks like — the drift ADR-194 exists to prevent.
"""

from __future__ import annotations

import re
from typing import Any

from src.core.field_names import FIELD_REGISTRY_ID, FIELD_RESULT
from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.output import UnifiedToolOutput

#: JSON-schema type name -> the Python type the execution must actually yield.
DECLARED_TYPE_TO_PYTHON: dict[str, Any] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def completed_step(output: UnifiedToolOutput) -> dict[str, Any]:
    """Mirror ``parallel_executor._execute_tool_step``'s structured_data build.

    Registry payloads are grouped under ``meta.domain`` and enriched with their
    registry id; the tool's own ``structured_data`` is then merged WITHOUT
    overwriting a registry-derived key (the "gentle merge").

    Args:
        output: What the tool returned.

    Returns:
        The mapping a ``$steps.<step_id>.<path>`` reference resolves against.
    """
    structured: dict[str, Any] = {FIELD_RESULT: output.summary_for_llm}
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for item_id, item in (output.registry_updates or {}).items():
        item_dict = item.model_dump() if hasattr(item, "model_dump") else item
        payload = item_dict.get("payload", {})
        meta = item_dict.get("meta", {})
        item_type = item_dict.get("type", "")
        key = meta.get("domain") or (f"{item_type.lower()}s" if item_type else "unknown")
        if payload:
            by_domain.setdefault(key, []).append({**payload, FIELD_REGISTRY_ID: item_id})
    structured.update(by_domain)
    if output.structured_data:
        for key, value in output.structured_data.items():
            structured.setdefault(key, value)
    return structured


def _resolves(path: str, completed: dict[str, Any]) -> tuple[bool, Any]:
    """Resolve one path against a single-step result.

    Args:
        path: A field path, without the ``$steps.<id>.`` prefix.
        completed: The step results, keyed by step id.

    Returns:
        ``(resolved, value)`` — ``value`` is None when the path does not resolve,
        which callers must not confuse with a resolved None.
    """
    try:
        return True, ReferenceResolver().resolve(f"$steps.step_1.{path}", completed, None)
    except (KeyError, ValueError):
        return False, None


def unresolved_reference_examples(manifest: ToolManifest, completed: dict[str, Any]) -> list[str]:
    """Published `reference_examples` the execution does not produce.

    Args:
        manifest: The manifest as the planner reads it.
        completed: The step result the tool actually produced.

    Returns:
        The published examples that fail to resolve; empty when the manifest
        tells the truth.
    """
    return [
        example
        for example in (manifest.reference_examples or [])
        if not _resolves(example, completed)[0]
    ]


def unresolved_top_level_outputs(manifest: ToolManifest, completed: dict[str, Any]) -> list[str]:
    """Declared top-level `outputs` the execution does not produce.

    Paths carrying ``[]`` describe a per-item field and are skipped: an empty
    collection is a legitimate result, so "each item has X" cannot be asserted
    from one sample.

    Args:
        manifest: The manifest as the planner reads it.
        completed: The step result the tool actually produced.

    Returns:
        The declared top-level paths that fail to resolve.
    """
    return [
        field.path
        for field in (manifest.outputs or [])
        if "[]" not in field.path and not _resolves(field.path, completed)[0]
    ]


def type_mismatches(manifest: ToolManifest, completed: dict[str, Any]) -> list[str]:
    """Declared output types the execution contradicts.

    A path can resolve and still lie: the planner reads the declared type to
    decide what it may chain a value into.

    Args:
        manifest: The manifest as the planner reads it.
        completed: The step result the tool actually produced.

    Returns:
        One human-readable line per contradiction, empty when types hold.
    """
    mismatches: list[str] = []
    for field in manifest.outputs or []:
        expected = DECLARED_TYPE_TO_PYTHON.get(field.type)
        if expected is None:
            continue
        # `[]` marks "each item of"; probe the first one.
        resolved, value = _resolves(field.path.replace("[]", "[0]"), completed)
        if resolved and value is not None and not isinstance(value, expected):
            mismatches.append(
                f"{field.path}: declared '{field.type}', produced {type(value).__name__}"
            )
    return mismatches


def root_key(path: str) -> str:
    """The top-level key a reference path addresses.

    Args:
        path: A field path such as ``contacts[0].name`` or ``count``.

    Returns:
        Its first segment (``contacts``, ``count``).
    """
    return re.split(r"[.\[]", path, maxsplit=1)[0]
