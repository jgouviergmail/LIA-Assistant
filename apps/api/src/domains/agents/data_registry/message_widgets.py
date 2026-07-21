"""Interactive widgets survive a page reload — persisted with their message.

The defect this closes: a `SKILL_APP` / `MCP_APP` payload lived ONLY in the
browser's React state, fed exclusively by the live SSE ``registry_update``. The
assistant message persisted its sentinel
(``<div class="lia-skill-app" data-registry-id="...">``) but not the payload it
points at, and nothing rehydrated it. Any session that had not received the
stream — another device, an F5, a conversation reopened later — resolved the id
to nothing and rendered "Impossible de charger le widget du skill". Measured on
the real production content: two grey error boxes, zero iframes.

Rehydrating from the LangGraph checkpoint was evaluated and rejected by
measurement: the ``registry`` channel is LRU-capped at ``REGISTRY_MAX_ITEMS``
(75 in production, with ~70 already in use), so old widgets are evicted
silently. The payload therefore travels with the message that renders it: one
write, atomic with the message, one lifetime — deleting the message deletes the
widget, CASCADE included.

Two deliberate restrictions:

- **Types.** Only frame-rendering widgets are persisted. ``DRAFT`` is excluded:
  it is HITL state with its own lifecycle, and a stale persisted draft would
  invite the user to confirm an action the graph no longer knows about.
- **Size.** ``html_content`` dominates the payload (a skill frame runs from a
  few kB to tens of kB). Beyond ``widget_persist_max_bytes`` the widget is
  dropped rather than bloating every history page — and the frontend then shows
  its explicit "unavailable" state instead of a silent blank.

Security note — ``is_system_skill`` is NOT trusted on read. It governs the
iframe's ``credentialless`` attribute and ``allow-same-origin`` sandbox flag, so
a skill later demoted from system to user would otherwise keep elevated frame
privileges in every old message. :func:`rehydrate_message_widgets` recomputes it
from the current system-skill set.
"""

from __future__ import annotations

import json
from typing import Any

from src.domains.agents.data_registry.models import RegistryItemType
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: Key under which widgets are stored in ``ConversationMessage.message_metadata``.
MESSAGE_METADATA_WIDGETS_KEY = "widgets"

#: Registry types persisted alongside the message. Frame-rendering widgets only
#: — see the module docstring for why ``DRAFT`` is deliberately absent.
PERSISTED_WIDGET_TYPES: frozenset[str] = frozenset(
    {RegistryItemType.SKILL_APP.value, RegistryItemType.MCP_APP.value}
)


def _item_type(item: Any) -> str | None:
    """Read an item's type from either a serialized dict or a Pydantic model."""
    raw = getattr(item, "type", None)
    if raw is None and isinstance(item, dict):
        raw = item.get("type")
    return getattr(raw, "value", raw) if raw is not None else None


def extract_persistable_widgets(
    serialized_registry: dict[str, Any] | None,
    *,
    max_bytes: int,
) -> dict[str, dict[str, Any]]:
    """Select the widgets worth persisting from an already-serialized registry.

    Args:
        serialized_registry: Registry items in their SSE-serialized form — the
            exact shape the frontend already merges into its registry map, so a
            rehydrated widget is byte-identical to a live one.
        max_bytes: Per-widget budget on the JSON-encoded payload. A widget over
            budget is dropped (and logged), never truncated: half an
            ``html_content`` renders worse than an honest failure state.

    Returns:
        ``{registry_id: serialized_item}``, empty when there is nothing to keep.
    """
    if not serialized_registry:
        return {}

    kept: dict[str, dict[str, Any]] = {}
    for item_id, item in serialized_registry.items():
        if _item_type(item) not in PERSISTED_WIDGET_TYPES:
            continue
        if not isinstance(item, dict):
            continue
        size = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if size > max_bytes:
            logger.warning(
                "widget_persist_skipped_too_large",
                registry_id=item_id,
                size_bytes=size,
                max_bytes=max_bytes,
            )
            continue
        kept[item_id] = item
    return kept


def with_persisted_widgets(
    message_metadata: dict[str, Any],
    widgets: dict[str, dict[str, Any]],
    *,
    run_id: str,
) -> dict[str, Any]:
    """Return ``message_metadata`` carrying ``widgets``, as a NEW dict.

    Branch-free at the call site on purpose: the archive path lives inside an
    already very large streaming function, and every added conditional there
    pushes a complexity ratchet. Symmetric to :func:`with_rehydrated_widgets`.

    Args:
        message_metadata: Metadata being assembled for the assistant message.
        widgets: Widgets captured for this turn; empty is the common case.
        run_id: Correlates the emitted log with the rest of the turn. Required,
            not optional: this line is the only evidence that the capture
            actually reached the archived message, and an uncorrelatable log
            proves nothing — every sibling log in that block carries it.

    Returns:
        The input unchanged (same object) when there is nothing to attach,
        otherwise a new dict with the widgets under
        :data:`MESSAGE_METADATA_WIDGETS_KEY`.
    """
    if not widgets:
        return message_metadata
    logger.info(
        "message_widgets_persisted",
        run_id=run_id,
        count=len(widgets),
        registry_ids=list(widgets),
    )
    return {**message_metadata, MESSAGE_METADATA_WIDGETS_KEY: widgets}


def with_rehydrated_widgets(
    message_metadata: dict[str, Any] | None,
    *,
    system_skill_names: frozenset[str],
) -> dict[str, Any] | None:
    """Return ``message_metadata`` with its widgets re-evaluated, as a NEW dict.

    Convenience wrapper for the history read path. Never mutates the input:
    the caller usually holds the ORM's JSONB dict, and an in-place write there
    is both a SQLAlchemy trap (silently skipped UPDATE) and a way to leak a
    read-time transformation into storage.

    Args:
        message_metadata: Persisted metadata, if any.
        system_skill_names: Skills that are system skills right now.

    Returns:
        The input unchanged (same object) when it carries no widget, otherwise
        a new dict with the widgets replaced.
    """
    rehydrated = rehydrate_message_widgets(message_metadata, system_skill_names=system_skill_names)
    if not rehydrated:
        return message_metadata
    return {**(message_metadata or {}), MESSAGE_METADATA_WIDGETS_KEY: rehydrated}


def rehydrate_message_widgets(
    message_metadata: dict[str, Any] | None,
    *,
    system_skill_names: frozenset[str],
) -> dict[str, dict[str, Any]]:
    """Rebuild a message's widget registry entries, with privileges re-evaluated.

    Args:
        message_metadata: The persisted ``message_metadata`` JSONB, if any.
        system_skill_names: Names of the skills that are system skills **now**.
            ``is_system_skill`` is recomputed against this set rather than
            trusted from the payload — the flag grants the iframe
            ``allow-same-origin`` and the ``credentialless`` attribute, and a
            skill demoted since the message was written must not keep them.

    Returns:
        ``{registry_id: serialized_item}`` ready to merge into the client
        registry, empty when the message carries no widget.
    """
    if not message_metadata:
        return {}
    stored = message_metadata.get(MESSAGE_METADATA_WIDGETS_KEY)
    if not isinstance(stored, dict) or not stored:
        return {}

    rehydrated: dict[str, dict[str, Any]] = {}
    for item_id, item in stored.items():
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if isinstance(payload, dict) and "is_system_skill" in payload:
            skill_name = payload.get("skill_name")
            # New dict, never an in-place mutation: the caller may be handed a
            # structure SQLAlchemy still tracks (JSONB mutation trap).
            item = {
                **item,
                "payload": {
                    **payload,
                    "is_system_skill": bool(
                        isinstance(skill_name, str) and skill_name in system_skill_names
                    ),
                },
            }
        rehydrated[item_id] = item
    return rehydrated
