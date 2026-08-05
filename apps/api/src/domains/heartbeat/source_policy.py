"""Which sources the heartbeat may interrupt the user from.

Being connected to a service and being interrupted from it were the same
switch: to stop receiving mail-driven nudges, the documented answer was to
disconnect the mail connector — which also removes the tool the user asks
with. This module separates the two.

It gates ``ContextAggregator.aggregate`` and nothing else. That aggregator has
exactly ONE caller (``HeartbeatProactiveTask.select_target``), so refusing a
source here removes it from the proactive decision **without touching the
agent's tools**: "LIA may use my mail when I ask" and "LIA may interrupt me
about my mail" become independent, which is the whole point.

Gating happens BEFORE the fetch, so a refused source also stops costing an API
call — a side benefit, not the reason.

The preference is stored as the DISABLED set, not the enabled one. Two
consequences, both deliberate:

- ``NULL`` (never expressed) means everything is on, so existing accounts keep
  their exact behaviour with no migration of preferences;
- a source added to the registry later is ON until the user refuses it, rather
  than silently missing from everyone's stored allowlist.

The module holds no I/O and imports no sibling: ``context_aggregator`` is
frozen at its audited size and must only shrink, so the policy lives here.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Every source a heartbeat notification can be *about*.
#:
#: These are the eleven the aggregator fetches on the user's behalf. The other
#: names it handles (``activity`` and the three anti-redundancy windows) are
#: NOT sources: they tell the decision what was already sent. Gating them would
#: make the assistant repeat itself, not interrupt less — so they are absent
#: here and, by construction, never gated.
HEARTBEAT_SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "calendar",
        "tasks",
        "emails",
        "weather",
        "interests",
        "memories",
        "journals",
        "health_signals",
        "birthdays",
        "open_loops",
        "departure",
        "habits",
    }
)

#: Display order for the settings UI — the API publishes it so the frontend
#: never re-declares the vocabulary (ADR-184: what a validator enforces, its
#: producer must be able to read).
HEARTBEAT_SOURCE_ORDER: tuple[str, ...] = (
    "calendar",
    "emails",
    "tasks",
    "weather",
    "interests",
    "memories",
    "journals",
    "health_signals",
    "birthdays",
    "open_loops",
    "departure",
    "habits",
)


#: Sources whose fetcher is a no-op without another source's result.
#:
#: ``fetch_departure_advice`` opens with ``if not calendar_events: return
#: None`` — it is a second-pass consumer of the calendar the first pass already
#: fetched. Refuse ``calendar`` and the ``departure`` switch stays ON and
#: produces nothing, forever, with no way for the reader to find out why.
#:
#: Declared here rather than discovered, and PUBLISHED to the settings panel
#: (ADR-184: whatever a system enforces, whoever produces the value must be
#: able to read). ``journals`` and ``memories`` are deliberately absent: they
#: also consume the first pass, but through a query that falls back to a
#: generic one, so they degrade instead of going silent.
HEARTBEAT_SOURCE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "departure": ("calendar",),
}


def assert_source_registry_complete() -> None:
    """Fail loudly when the registry and its declarations drift apart.

    Called at boot (ADR-085 doctrine) and from a unit test. Checked in BOTH
    directions: a key present in one and absent from the other would either
    hide a switch the backend honours, or publish a switch that silences
    nothing. Dependencies are checked on both sides too — one naming a source
    that does not exist would publish a requirement nobody can satisfy.

    Raises:
        RuntimeError: On any divergence between the declarations.
    """
    ordered = frozenset(HEARTBEAT_SOURCE_ORDER)
    if len(HEARTBEAT_SOURCE_ORDER) != len(ordered):
        raise RuntimeError("HEARTBEAT_SOURCE_ORDER contains duplicates")
    missing = HEARTBEAT_SOURCE_KEYS - ordered
    extra = ordered - HEARTBEAT_SOURCE_KEYS
    if missing or extra:
        raise RuntimeError(
            "Heartbeat source registry drift — "
            f"absent from the display order: {sorted(missing)}; "
            f"declared there but not a source: {sorted(extra)}."
        )
    for source, requires in HEARTBEAT_SOURCE_DEPENDENCIES.items():
        unknown = sorted({source, *requires} - HEARTBEAT_SOURCE_KEYS)
        if unknown:
            raise RuntimeError(f"Heartbeat dependency on unknown source(s): {', '.join(unknown)}.")
        if source in requires:
            raise RuntimeError(f"Heartbeat source {source!r} depends on itself.")


assert_source_registry_complete()


# ---------------------------------------------------------------------------
# Reading the preference
# ---------------------------------------------------------------------------


def disabled_sources_for(user: Any) -> frozenset[str]:
    """Sources this user refused, read tolerantly.

    Reading is deliberately forgiving while writing is strict
    (:func:`sanitize_disabled_sources`): the column is JSONB and could have
    been hand-edited, and the safe reading of anything unexpected is the
    historical behaviour — every source enabled. Silencing a source by
    accident is the failure to avoid, not the other way round.

    Args:
        user: User model (or anything carrying the attribute).

    Returns:
        The refused source keys; empty when nothing valid is stored.
    """
    raw = getattr(user, "heartbeat_disabled_sources", None)
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(
        item for item in raw if isinstance(item, str) and item in HEARTBEAT_SOURCE_KEYS
    )


def unmet_dependencies(disabled: list[str]) -> dict[str, tuple[str, ...]]:
    """Sources left ON whose dependency the reader refused.

    Reported so the panel can say "this needs the calendar" instead of leaving
    a live switch that yields nothing. A source refused ALONGSIDE its
    dependency is absent: the reader already turned it off, so there is no
    surprise left to explain and saying it anyway would be noise.

    Args:
        disabled: The refusal set, as stored.

    Returns:
        Mapping of still-enabled source to the dependencies it is missing.
    """
    refused = set(disabled)
    return {
        source: missing
        for source, requires in HEARTBEAT_SOURCE_DEPENDENCIES.items()
        if source not in refused and (missing := tuple(r for r in requires if r in refused))
    }


def is_source_enabled(user: Any, source: str) -> bool:
    """Whether the heartbeat may read this source for this user.

    Args:
        user: User model.
        source: A source key — or any internal context name, which is never
            gated (it is not a source; see :data:`HEARTBEAT_SOURCE_KEYS`).

    Returns:
        True unless the user explicitly refused this source.
    """
    return source not in disabled_sources_for(user)


# ---------------------------------------------------------------------------
# Writing the preference
# ---------------------------------------------------------------------------


def sanitize_disabled_sources(values: list[str]) -> list[str]:
    """Validate and normalise a refusal list before it is stored.

    Strict where reading is tolerant: an unknown key is refused rather than
    dropped, because a typo that silently silences nothing is a preference the
    user believes they set. Sorted and de-duplicated so the stored value is
    canonical and two equivalent requests produce one row state.

    Args:
        values: Source keys the user refuses.

    Returns:
        The canonical list to store.

    Raises:
        ValueError: If any value is not a known source key.
    """
    unknown = sorted({value for value in values if value not in HEARTBEAT_SOURCE_KEYS})
    if unknown:
        raise ValueError(f"unknown heartbeat source(s): {', '.join(unknown)}")
    return sorted(set(values))
