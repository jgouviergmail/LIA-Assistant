"""Recent-entity grounding for the response prompt.

Why this exists
---------------
On a turn where no tool produced registry updates, ``current_turn_registry`` is
empty **by design**: ``registry_filtering.filter_registry_by_current_turn``
returns ``{}`` to prevent cross-turn contamination (a stale photo leaking into
an unrelated answer). ``data_for_filtering`` is derived from that registry, so
it is empty too. Meanwhile ``<History>`` deliberately drops ``ToolMessage`` (see
``message_filters.filter_conversational_messages``), so the authoritative values
never reach the model from there either — it can only echo whatever prose a
previous answer happened to contain. That is how an appointment stated at 11:15
came back as "16h".

The entities themselves are still available: the merged ``state["registry"]``
keeps every item produced by previous turns (the ``merge_registry`` reducer),
and ``agent_results`` records which turn produced which item. This module picks
the items produced in the last few turns and renders them as a clearly
labelled, NON-authoritative context block.

Design notes
------------
- **Recency is the relevance filter, not the current query's domains.** A
  follow-up frequently references an entity from a domain the current query does
  not name (asking about the weather while referring to an appointment), and
  turns routed to the response node often carry no domain at all ("no domains →
  response" fallback in ``RoutingDecider``). Filtering by domain would make this
  grounding inert exactly when it is needed.
- **No I/O.** Everything comes from the graph state already in memory.
- **Same serializer as the nominal channel** (``generate_data_for_filtering``),
  so entities read identically whether they come from this turn or an earlier one.

Safety properties
-----------------
- **Text only.** The HTML/photo/widget path keeps reading the empty current-turn
  registry, so the 2025-12-26 contamination fix stays intact.
- **REFERENCE turns are excluded** (see ``should_ground_from_recent_entities``):
  an empty registry there is a data-leak fail-safe, not a grounding gap.
- **Bounded**: only the last ``response_recent_entities_max_turn_age`` turns, and
  at most ``tool_context_max_items`` entities; any drop is logged.
- **Fail-safe**: malformed state yields ``""``; never raises into the response path.
"""

from __future__ import annotations

from typing import Any

from src.core.config import settings
from src.domains.agents.utils.turn_type import is_reference_turn
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def should_ground_from_recent_entities(
    current_turn_registry: dict[str, Any] | None,
    turn_type: str | None,
) -> bool:
    """Tell whether recent-entity grounding applies to this turn.

    Two exclusions, both deliberate:

    - The turn produced its own registry data → it is already grounded, and
      injecting older entities would compete with authoritative results.
    - The turn is a REFERENCE variant → an empty registry there is the
      *security* fail-safe of ``filter_registry_by_current_turn`` (reference
      resolution found no match; showing other turns' items would leak data).
      Re-injecting would defeat that control.

    Args:
        current_turn_registry: Registry filtered to the current turn (may be None).
        turn_type: Raw turn type from state.

    Returns:
        True when the recent-entity block may be built for this turn.
    """
    if current_turn_registry:
        return False
    if is_reference_turn(turn_type):
        return False
    return True


def _registry_updates_of(result: Any) -> dict[str, Any]:
    """Extract ``registry_updates`` from an agent result (dict or object)."""
    if isinstance(result, dict):
        updates = result.get("registry_updates") or {}
    else:
        updates = getattr(result, "registry_updates", None) or {}
    return updates if isinstance(updates, dict) else {}


def _recent_item_ids(
    agent_results: dict[str, Any],
    current_turn_id: int,
    max_age: int,
) -> list[str]:
    """List registry item ids produced within the last ``max_age`` turns.

    Args:
        agent_results: Mapping of ``"{turn_id}:{agent}"`` → agent result.
        current_turn_id: Current turn id.
        max_age: Maximum age in turns (inclusive).

    Returns:
        Item ids, most recent turn first, de-duplicated.
    """
    by_turn: dict[int, list[str]] = {}
    for key, result in agent_results.items():
        turn_part = str(key).split(":", 1)[0]
        try:
            turn_id = int(turn_part)
        except (TypeError, ValueError):
            continue
        age = current_turn_id - turn_id
        if age < 0 or age > max_age:
            continue
        updates = _registry_updates_of(result)
        if updates:
            by_turn.setdefault(turn_id, []).extend(updates.keys())

    ordered: list[str] = []
    seen: set[str] = set()
    for turn_id in sorted(by_turn, reverse=True):
        for item_id in by_turn[turn_id]:
            if item_id not in seen:
                seen.add(item_id)
                ordered.append(item_id)
    return ordered


def build_recent_entities_context(
    full_registry: dict[str, Any] | None,
    agent_results: dict[str, Any] | None,
    current_turn_id: int | None,
    user_language: str,
) -> str:
    """Build the recent-entity grounding block for the response prompt.

    Args:
        full_registry: The merged, cross-turn registry from state.
        agent_results: Agent results keyed ``"{turn_id}:{agent}"``.
        current_turn_id: Current turn id (None disables the feature — recency
            cannot be established, and injecting unbounded history is unsafe).
        user_language: Language used by the shared payload serializer.

    Returns:
        The serialized entity block, or ``""`` when nothing recent applies.
    """
    max_age = settings.response_recent_entities_max_turn_age
    if max_age <= 0 or not full_registry or not agent_results or current_turn_id is None:
        return ""

    try:
        item_ids = _recent_item_ids(agent_results, current_turn_id, max_age)
    except Exception as exc:  # pragma: no cover - defensive, state is untrusted
        logger.debug("recent_entities_scan_failed", error=str(exc))
        return ""

    max_total = settings.tool_context_max_items
    selected: dict[str, Any] = {}
    for item_id in item_ids:
        if len(selected) >= max_total:
            break
        item = full_registry.get(item_id)
        if item is not None:
            selected[item_id] = item

    if not selected:
        return ""

    dropped = len(item_ids) - len(selected)
    if dropped > 0:
        # No silent caps: a truncated context must be visible in the logs.
        logger.info(
            "recent_entities_truncated",
            injected=len(selected),
            candidates=len(item_ids),
            max_total=max_total,
        )

    # Same serializer as the nominal {data_for_filtering} channel, so an entity
    # reads identically whether it comes from this turn or an earlier one.
    from src.domains.agents.formatters.text_summary import generate_data_for_filtering

    try:
        block = generate_data_for_filtering(selected, user_language)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("recent_entities_serialization_failed", error=str(exc))
        return ""

    if not block:
        return ""

    logger.info(
        "recent_entities_injected",
        entities=len(selected),
        current_turn_id=current_turn_id,
        max_age=max_age,
    )
    return block


__all__ = ["build_recent_entities_context", "should_ground_from_recent_entities"]
