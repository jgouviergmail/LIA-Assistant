"""What the answers SHOWED — the one record a designation is read on (ADR-367 amendment).

« The second one », « Marc's email »: the person designates something they SAW.
Two records stood in for that and neither was it. The registry holds every item
a turn FETCHED — the lookup an answer only consumed as a means, the candidates
it set aside — and the context list holds what the last lookup of a domain
returned, overwritten by any later one (« show Marc's emails and reply to the
first » left the context list on the lookup, not on the list shown).

The response already declares what its answer presents (``<relevant_ids>``,
both execution modes, every display mode). That declaration is recorded here,
per turn, in the order the person met the items — the cards' order where cards
are drawn, the answer's own order otherwise — for the turns a designation may
reach back to (``ENTITY_RESOLUTION_MAX_TURN_AGE``). A description reads every
item shown (:func:`shown_items`); an ordinal reads the list it counts in
(:func:`ordinal_list`). Pure functions over the graph state; no I/O.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.core.config import settings
from src.domains.agents.constants import STATE_KEY_CURRENT_TURN_ID, STATE_KEY_SHOWN_ITEMS
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.utils.registry_filtering import (
    relevant_ids_declared_in,
    select_registry_in_declared_order,
)

__all__ = [
    "ShownItem",
    "ordinal_list",
    "recorded_shown",
    "registry_parts",
    "shown_items",
    "shown_order",
    "shown_update",
]


@dataclass(frozen=True, slots=True)
class ShownItem:
    """One item an answer showed, as the registry holds it."""

    item_id: str
    turn: int
    domain: str
    payload: Mapping[str, Any]
    #: The registry entry itself, for what is drawn from it (display fields).
    entry: object


def registry_parts(item: object) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """An item's payload and meta, whether a ``RegistryItem`` or its checkpointed dict."""
    if isinstance(item, RegistryItem):
        return item.payload, item.meta.model_dump()
    if not isinstance(item, Mapping):
        return {}, {}
    payload, meta = item.get("payload"), item.get("meta")
    return (
        payload if isinstance(payload, Mapping) else {},
        meta if isinstance(meta, Mapping) else {},
    )


def shown_order(displayed: Mapping[str, Any] | None, answer: str, *, cards: bool) -> list[str]:
    """The registry ids an answer showed, in the order the person met them.

    Args:
        displayed: The answer's registry selection (what the cards draw).
        answer: The answer as the model wrote it, its declaration included.
        cards: Whether this display mode draws the selection as cards.

    Returns:
        The cards' order when cards are drawn; otherwise the order the answer
        declared, then any record it kept without declaring it.
    """
    if not displayed:
        return []
    keys = list(displayed)
    declared = None if cards else relevant_ids_declared_in(answer)
    if not declared:
        return keys
    ordered = list(select_registry_in_declared_order(dict(displayed), declared))
    return ordered + [key for key in keys if key not in ordered]


def _entries(state: Mapping[str, Any]) -> Iterator[tuple[int, list[str]]]:
    """The record as written — forgiving: a malformed entry is skipped."""
    record = state.get(STATE_KEY_SHOWN_ITEMS)
    for entry in record if isinstance(record, list) else ():
        turn = entry.get("turn_id") if isinstance(entry, Mapping) else None
        ids = entry.get("ids") if isinstance(entry, Mapping) else None
        if isinstance(turn, int) and not isinstance(turn, bool) and isinstance(ids, list):
            yield turn, [item_id for item_id in ids if isinstance(item_id, str)]


def recorded_shown(state: Mapping[str, Any], ids: Sequence[str]) -> list[dict[str, Any]] | None:
    """The record once this turn's answer showed ``ids``.

    Args:
        state: The graph state (its turn and the record so far).
        ids: What this turn's answer showed, in order.

    Returns:
        The turns still within reach of the next one, this turn's entry last
        (replacing an earlier entry of the same turn — a resumed turn answers
        again); None when this answer showed nothing — the record is unchanged.
    """
    current = state.get(STATE_KEY_CURRENT_TURN_ID)
    if not ids or not isinstance(current, int):
        return None
    reach = current + 1 - settings.entity_resolution_max_turn_age
    kept = [
        {"turn_id": turn, "ids": entry_ids}
        for turn, entry_ids in _entries(state)
        if reach <= turn < current
    ]
    return [*kept, {"turn_id": current, "ids": list(dict.fromkeys(ids))}]


def shown_update(
    state: Mapping[str, Any], displayed: Mapping[str, Any] | None, answer: str, *, cards: bool
) -> dict[str, Any]:
    """The state update recording what this answer showed (empty when nothing).

    Args:
        state: The graph state.
        displayed: The answer's registry selection.
        answer: The answer as the model wrote it.
        cards: Whether this display mode draws cards.

    Returns:
        ``{shown_items: record}``, or ``{}`` when the record is unchanged.
    """
    record = recorded_shown(state, shown_order(displayed, answer, cards=cards))
    return {} if record is None else {STATE_KEY_SHOWN_ITEMS: record}


def _shown_entries(state: Mapping[str, Any]) -> list[tuple[int, list[ShownItem]]]:
    """Each answer within reach, newest first, with the items it showed still held."""
    current = state.get(STATE_KEY_CURRENT_TURN_ID)
    registry = state.get("registry")
    if not isinstance(current, int) or not isinstance(registry, Mapping):
        return []
    max_age = settings.entity_resolution_max_turn_age
    entries: list[tuple[int, list[ShownItem]]] = []
    for turn, ids in _entries(state):
        if not 1 <= current - turn <= max_age:
            continue
        items: list[ShownItem] = []
        for item_id in dict.fromkeys(ids):
            entry = registry.get(item_id)
            payload, meta = registry_parts(entry)
            domain = meta.get("domain")
            if payload and isinstance(domain, str):
                items.append(ShownItem(item_id, turn, domain, payload, entry))
        entries.append((turn, items))
    return sorted(entries, key=lambda pair: -pair[0])


def shown_items(state: Mapping[str, Any]) -> list[ShownItem]:
    """Every item the answers within reach showed — what a description may designate.

    Args:
        state: The graph state.

    Returns:
        Newest answer first, each answer's own order within it, every item once
        (at the newest answer that showed it).
    """
    seen: set[str] = set()
    items: list[ShownItem] = []
    for _turn, entry_items in _shown_entries(state):
        for item in entry_items:
            if item.item_id not in seen:
                seen.add(item.item_id)
                items.append(item)
    return items


def ordinal_list(state: Mapping[str, Any], domain: str) -> tuple[int | None, list[ShownItem]]:
    """The list « the second one » counts in: the newest one of the domain shown.

    One item shown alone after a list holding it is that list's item opened —
    « open the first », then « and the second? » still counts in the newest
    list that holds it — whereas one item no list shown holds is a list of its
    own.

    Args:
        state: The graph state.
        domain: The context domain (a result key, ``emails``).

    Returns:
        The turn that showed the list and its items in order; ``(None, [])``
        when no answer within reach showed that domain.
    """
    lists = [
        (turn, [item for item in items if item.domain == domain])
        for turn, items in _shown_entries(state)
    ]
    lists = [(turn, items) for turn, items in lists if items]
    if not lists:
        return None, []
    turn, newest = lists[0]
    if len(newest) == 1:
        opened = newest[0].item_id
        holding = (
            (t, items)
            for t, items in lists[1:]
            if len(items) > 1 and any(item.item_id == opened for item in items)
        )
        return next(holding, (turn, newest))
    return turn, newest
