"""Preserve the identity selected by an actual scalar reference resolution."""

import re
from collections.abc import Iterator, Mapping

from langchain_core.runnables import RunnableConfig

from src.domains.agents.semantic.registry_value_bindings import config_with_registry_bindings

_REFERENCE = re.compile(r"\$(steps|context)\.([A-Za-z_][A-Za-z_0-9]*)(\..+)")
_PATH_PART = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)(?:\[(\d+)\])?")
_TEMPLATE = re.compile(r"\{\{\s*((?:steps|context)\.[A-Za-z_][A-Za-z_0-9]*\..+?)\s*\}\}")


def _raw_reference(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    template = _TEMPLATE.fullmatch(value)
    return f"${template[1]}" if template else value if value.startswith("$") else None


def _reference_leaves(value: object, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield from _reference_leaves(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _reference_leaves(child, f"{path}[{index}]")
    elif (reference := _raw_reference(value)) is not None:
        yield path, reference


def _read_part(value: object, part: re.Match[str]) -> object:
    if not isinstance(value, dict):
        return None
    child = value.get(part[1])
    if part[2] is None:
        return child
    index = int(part[2])
    return child[index] if isinstance(child, list) and index < len(child) else None


def _canonical_leaf_reference(value: object, path: str) -> str | None:
    parts = path.removeprefix(".").split(".")
    if len(parts) > 48:
        return None
    identity: str | None = None
    tail: list[str] = []
    for field in parts:
        part = _PATH_PART.fullmatch(field)
        if part is None:
            return None
        if isinstance(value, dict) and isinstance(value.get("_registry_id"), str):
            identity = value["_registry_id"]
            tail = []
        if identity:
            tail.append(field)
        value = _read_part(value, part)
    return f"$registry.{identity}.{'.'.join(tail)}" if identity and tail else None


def selected_reference_sources(
    arguments: Mapping[str, object],
    completed_steps: Mapping[str, object],
    context: Mapping[str, object],
) -> dict[str, str]:
    """Only plain references retain provenance; transformed text is not a typed fact."""
    selected: dict[str, str] = {}
    for path, reference in _reference_leaves(arguments):
        match = _REFERENCE.fullmatch(reference)
        if match is None:
            continue
        root = completed_steps if match[1] == "steps" else context
        canonical = _canonical_leaf_reference(root.get(match[2]), match[3])
        if canonical is not None:
            selected[path] = canonical
    return selected


def config_with_resolved_bindings(
    config: RunnableConfig,
    *,
    tool_name: str,
    original_arguments: Mapping[str, object],
    resolved_arguments: Mapping[str, object],
    completed_steps: Mapping[str, object],
    context: Mapping[str, object],
    registry: Mapping[str, object],
) -> RunnableConfig:
    """Attach proof selected before interpolation, checked against canonical payloads."""
    return config_with_registry_bindings(
        config,
        registry,
        tool_name,
        resolved_arguments,
        selected_sources=selected_reference_sources(original_arguments, completed_steps, context),
    )
