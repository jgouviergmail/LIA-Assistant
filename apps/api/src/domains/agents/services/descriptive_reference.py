"""A shown item designated by WHAT it is — resolved by code, asked when several fit (ADR-367).

Production, 2026-10-29: after « my last 5 emails », « reply to jerome's email »
was planned as a new mailbox search (``from:jerome``, ``max_results=1``, then
``[0]``) and drafted a reply to a message the person had never been shown —
Gmail's ``from:`` does not fold accents, and nothing tied the request to the
list on screen. The analyzer now says HOW an item is designated
(``reference_type="descriptive"``) and with which words (``descriptor``); THIS
module decides which shown items those words designate:

- what was SHOWN is what the last answers declared they presented — the
  record ``context/shown_items.py`` keeps, both execution modes — never the
  tool-context list, which any later lookup overwrites, nor the registry, which
  holds every item a turn fetched;
- only a turn the person follows may designate them (:func:`turn_follows_the_
  conversation`): a routine, a ticket or a relayed call shares the account's
  thread without having seen its list;
- one fitting item is resolved, several are CANDIDATES the person is asked to
  choose among (the reference-disambiguation node), none is a new lookup —
  the path every request took before.

The outcome is DERIVED from the matching, never from the analyzer's flag
alone: a description nothing shown carries changes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import structlog

from src.core.config import settings
from src.core.text_clip import one_line
from src.domains.agents.context.descriptor_match import items_matching, strings_at
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.shown_items import shown_items
from src.domains.agents.effects.gate import turn_follows_the_conversation
from src.domains.agents.services.analysis.query_analysis_schemas import (
    DESCRIPTIVE_SELECTION_LATEST,
    ContextReferenceOutput,
)
from src.domains.agents.services.reference_resolver import ResolvedContext
from src.domains.agents.utils.type_domain_mapping import (
    TOOL_PATTERN_TO_DOMAIN_MAP,
    get_domain_from_result_key,
)
from src.infrastructure.observability.metrics_agents import context_descriptive_reference_total

logger = structlog.get_logger(__name__)

__all__ = ["candidate_label", "render_shown_items", "resolve_descriptive_reference"]

#: One value of a shown item, as the analyzer reads it.
SHOWN_VALUE_MAX_CHARS: Final = 60
#: One shown item, as the analyzer reads it.
SHOWN_LINE_MAX_CHARS: Final = 140
#: One option of « which one? », as the person reads it.
CANDIDATE_LINE_MAX_CHARS: Final = 180
#: The key every provider's e-mail carries its reception instant under (epoch ms).
_RECEIVED_KEY: Final = "internalDate"


def _shown(state: Mapping[str, Any]) -> list[tuple[str, int, Mapping[str, Any]]]:
    """``(context domain, turn, payload)`` of what the last answers showed.

    Newest answer first, and the order an answer presented its items within it.
    """
    return [(item.domain, item.turn, item.payload) for item in shown_items(state)]


def _values(payload: Mapping[str, Any], fields: Sequence[str]) -> list[str]:
    """The distinct values of fields, each on one bounded line, in order."""
    parts: list[str] = []
    for field in fields:
        for text in strings_at(payload, field):
            value = one_line(text)[:SHOWN_VALUE_MAX_CHARS]
            if value and value.casefold() not in {part.casefold() for part in parts}:
                parts.append(value)
    return parts


def _line(domain: str, payload: Mapping[str, Any]) -> str | None:
    """One shown item as the analyzer reads it: its identity fields, one line."""
    definition = ContextTypeRegistry.find(domain)
    parts = _values(payload, definition.reference_fields) if definition else []
    if not parts:
        return None
    label = get_domain_from_result_key(domain) or domain
    return f"- [{label}] {' · '.join(parts)}"[:SHOWN_LINE_MAX_CHARS]


def candidate_label(payload: Mapping[str, Any], definition: ContextTypeDefinition) -> str:
    """One option of « which one? »: what tells it apart from the others, one line.

    Raw text — a third party's words (a sender, a subject): every surface that
    draws it escapes it for itself.

    Args:
        payload: The candidate item's payload.
        definition: Its context type, declaring its ``candidate_fields``.

    Returns:
        The values joined by « · », bounded; empty when none is carried.
    """
    fields = definition.candidate_fields or definition.reference_fields
    return " · ".join(_values(payload, fields))[:CANDIDATE_LINE_MAX_CHARS]


def render_shown_items(state: Mapping[str, Any]) -> str:
    """The recently shown items, one line each, for the query analyzer's prompt.

    Args:
        state: The graph state (``registry``, ``current_turn_id``).

    Returns:
        The lines, most recent answer first, at most
        ``entity_resolution_shown_items_max`` of them; empty when the turn may
        designate nothing shown or nothing was shown.
    """
    if not settings.entity_resolution_enabled or not turn_follows_the_conversation():
        return ""
    lines = [line for domain, _, payload in _shown(state) if (line := _line(domain, payload))]
    return "\n".join(lines[: settings.entity_resolution_shown_items_max])


def _newest(items: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The most recently received item, when every one says when it was received."""
    received = [str(item.get(_RECEIVED_KEY) or "") for item in items]
    if not all(value.isdigit() for value in received):
        return None
    return max(zip(received, items, strict=True), key=lambda pair: int(pair[0]))[1]


def _outcome(method: str, outcome: str, **fields: Any) -> ResolvedContext:
    context_descriptive_reference_total.labels(outcome=outcome).inc()
    logger.info("descriptive_reference_resolved", outcome=outcome)
    return ResolvedContext(
        items=fields.get("items", []),
        confidence=1.0,
        method=method,
        source_turn_id=fields.get("source_turn_id"),
        source_domain=fields.get("source_domain"),
        candidates=fields.get("candidates", []),
        descriptor=fields.get("descriptor", ""),
    )


def resolve_descriptive_reference(
    reference: ContextReferenceOutput, state: Mapping[str, Any]
) -> ResolvedContext:
    """Which shown item a description designates (ADR-367).

    Args:
        reference: The analyzer's descriptive reference (``descriptor``,
            ``reference_domain`` in its singular form, ``selection``).
        state: The graph state.

    Returns:
        One resolved item; or CANDIDATES when several fit (the person is
        asked); or nothing — the request is then planned as a new lookup.
    """
    if not settings.entity_resolution_enabled:
        return _outcome("descriptive_disabled", "disabled")
    if not turn_follows_the_conversation():
        return _outcome("descriptive_not_followed", "not_followed")
    domain = TOOL_PATTERN_TO_DOMAIN_MAP.get(reference.reference_domain, reference.reference_domain)
    definition = ContextTypeRegistry.find(domain)
    shown = [(turn, payload) for kind, turn, payload in _shown(state) if kind == domain]
    if definition is None or not shown:
        return _outcome("descriptive_nothing_shown", "nothing_shown")
    turn_of = {id(payload): turn for turn, payload in shown}
    matched = items_matching(reference.descriptor, [payload for _, payload in shown], definition)
    if not matched:
        return _outcome("descriptive_no_match", "no_match")
    source = {"source_domain": reference.reference_domain}
    newest = _newest(matched) if reference.selection == DESCRIPTIVE_SELECTION_LATEST else None
    if newest is not None:
        return _outcome(
            "descriptive_latest",
            "latest",
            items=[dict(newest)],
            source_turn_id=turn_of[id(newest)],
            **source,
        )
    if len(matched) == 1:
        return _outcome(
            "descriptive",
            "resolved",
            items=[dict(matched[0])],
            source_turn_id=turn_of[id(matched[0])],
            **source,
        )
    cap = settings.entity_resolution_max_candidates
    return _outcome(
        "descriptive_ambiguous",
        "ambiguous",
        candidates=[dict(item) for item in matched[:cap]],
        descriptor=reference.descriptor,
        **source,
    )
