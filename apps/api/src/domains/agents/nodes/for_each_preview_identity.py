"""Bind displayed bulk-action previews to their persisted original positions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import structlog

from src.domains.agents.nodes.for_each_hitl_prep import (
    extract_item_previews_for_hitl,
    filter_registry_by_items,
)
from src.domains.agents.orchestration.for_each_utils import parse_for_each_reference
from src.domains.agents.tools.runtime_helpers import extract_value_by_path

logger = structlog.get_logger(__name__)


def prepare_preview_context(
    registry: dict[str, Any], steps: list[dict], completed: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    indices: list[int] = []
    previews = extract_item_previews_for_hitl(registry, steps, completed, original_indices=indices)
    return {"item_previews": previews, "item_preview_indices": indices, "filtered_indices": None}


def snapshot_preview_identity(ctx: dict[str, Any]) -> dict[str, Any]:
    """Detach only the persisted source and its preview correspondence."""
    return deepcopy(
        {
            key: ctx.get(key)
            for key in (
                "steps",
                "pre_executed_steps",
                "pre_exec_registry",
                "item_previews",
                "item_preview_indices",
                "filtered_indices",
            )
        }
    )


def approved_preview_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """A stale or ambiguous edited checkpoint must be reconfirmed unchanged."""
    if ctx.get("filtered_indices") is None:
        return {**ctx, "approved": True}
    indices = resolve_item_preview_indices(ctx)
    return {
        **ctx,
        "approved": indices is not None,
        "filtered_indices": indices if indices is not None else ctx["filtered_indices"],
        "item_preview_indices": indices if indices is not None else ctx.get("item_preview_indices"),
    }


def _source_signature(steps: list[dict]) -> list[tuple[Any, Any, Any]]:
    return [
        (step.get("step_id"), step.get("tool_name"), step.get("for_each_source")) for step in steps
    ]


def _single_source(steps: list[dict]) -> str | None:
    sources = [step.get("for_each_source") for step in steps]
    if not sources or any(not isinstance(source, str) or not source for source in sources):
        return None
    if len(set(sources)) != 1:
        return None
    return sources[0]


def original_selection_after_approval(ctx: dict[str, Any], steps: list[dict]) -> list[int] | None:
    """The executor uses only a correspondence still proven at consumption."""
    if _source_signature(ctx.get("steps") or []) != _source_signature(steps):
        raise ValueError("Approved source no longer matches plan")
    if ctx.get("filtered_indices") is None:
        return None
    indices = resolve_item_preview_indices(ctx)
    if indices is None:
        raise ValueError("Unproven approved preview identity")
    return indices


def apply_filtered_source_items(
    completed: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    steps: list[dict],
    indices: list[int],
    run_id: str,
) -> dict[str, Any]:
    """No filtered approval may silently fall through to the unfiltered source."""
    source = _single_source(steps)
    if source is None:
        raise ValueError("Ambiguous approved sources")
    provider, path = parse_for_each_reference(source)
    if not provider or not path or provider not in completed:
        raise ValueError("Missing approved source")
    result_data = completed[provider]
    originals = extract_value_by_path(result_data, path)
    if not isinstance(originals, list) or not valid_preview_selection(indices, len(originals)):
        raise ValueError("Invalid approved source list")
    filtered = [originals[index] for index in indices]
    replace_filtered_source_items(result_data, path, originals, filtered)
    logger.info(
        "for_each_data_filtered_in_pre_executed_steps",
        run_id=run_id,
        provider_id=provider,
        field_path=path,
        original_count=len(originals),
        filtered_count=len(filtered),
        filtered_indices=indices,
    )
    return filter_registry_by_items(registry, filtered, path.rsplit(".", 1)[-1], run_id)


def replace_filtered_source_items(
    result_data: dict[str, Any], field_path: str, originals: list[Any], filtered: list[Any]
) -> None:
    """Replace only the exact saved list, including supported dict/list paths."""
    parent_path, separator, key = field_path.rpartition(".")
    parent = extract_value_by_path(result_data, parent_path) if separator else result_data
    if isinstance(parent, dict) and parent.get(key) is originals:
        parent[key] = filtered
        return
    if isinstance(parent, list) and key.isdecimal():
        index = int(key)
        if index < len(parent) and parent[index] is originals:
            parent[index] = filtered
            return
    raise ValueError("Unproven filtered source path")


def valid_preview_selection(indices: Any, count: int) -> bool:
    """A selector cannot invent, repeat, or address an undisplayed item."""
    return (
        isinstance(indices, list)
        and all(type(index) is int and 0 <= index < count for index in indices)
        and len(set(indices)) == len(indices)
    )


def selection_matches_snapshot(
    indices: Any, count: int, snapshot: dict[str, Any], ctx: dict[str, Any]
) -> bool:
    return valid_preview_selection(indices, count) and snapshot == snapshot_preview_identity(ctx)


def _legacy_indices(
    ctx: dict[str, Any],
    previews: list[dict[str, Any]],
    originals: list[dict[str, Any]],
    original_indices: list[int],
) -> list[int] | None:
    """Recover old checkpoints only from an exact, unambiguous projection."""
    if ctx.get("filtered_indices") is None and previews == originals:
        return original_indices
    indices: list[int] = []
    for preview in previews:
        matches = [index for index, original in enumerate(originals) if preview == original]
        if len(matches) != 1:
            return None
        indices.append(original_indices[matches[0]])
    return indices


def resolve_item_preview_indices(ctx: dict[str, Any]) -> list[int] | None:
    """Prove correspondence against the saved provider data, without fetching it."""
    if _single_source(ctx.get("steps") or []) is None:
        return None
    previews = ctx.get("item_previews") or []
    original_indices: list[int] = []
    originals = extract_item_previews_for_hitl(
        ctx.get("pre_exec_registry") or {},
        ctx.get("steps") or [],
        ctx.get("pre_executed_steps") or {},
        original_indices=original_indices,
    )
    indices = ctx.get("item_preview_indices")
    if indices is None:
        indices = _legacy_indices(ctx, previews, originals, original_indices)
    by_index = dict(zip(original_indices, originals, strict=True))
    if not isinstance(indices, list) or len(indices) != len(previews):
        return None
    if not valid_preview_selection(indices, max(original_indices, default=-1) + 1):
        return None
    if any(
        by_index.get(index) != preview for index, preview in zip(indices, previews, strict=True)
    ):
        return None
    return indices
