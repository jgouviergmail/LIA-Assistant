"""Deciding who asked for a turn — once, for all three registers.

The registers each carry a ``source`` column, and the rule that fills it was
written four times: in :mod:`decisions`, :mod:`runtime`, :mod:`scope` and
:mod:`treatments`, each spelling ``"scheduled" if automated else "user"``. Four
copies are four chances for one to stop agreeing, and adding a third origin
would have had to find every one of them — ADR-248's rule about the ReAct stop
condition, applied to the register's own vocabulary.

The three origins are not degrees of the same thing:

- ``user`` — they typed it;
- ``scheduled`` — they wrote a routine and the scheduler chose the minute, so
  its actions belong beside the ones they typed;
- ``proactive`` — LIA decided: a morning briefing that reads their mail, a
  heartbeat that reaches out. Measured 2026-09-07, 228 such runs over fourteen
  days had produced no register row at all.

``subagent`` is not decided here: a sub-agent runs inside a turn that already
has an authority, and its scope carries it.
"""

from __future__ import annotations

from src.domains.agents.effects.models import EffectSource
from src.domains.agents.effects.schemas import EffectSourceName


def resolve_source(
    context: object | None,
    *,
    scope: object | None = None,
    proactive: bool = False,
    automated: bool | None = None,
) -> EffectSourceName:
    """Name the authority a register row belongs to.

    Args:
        context: The running :class:`RuntimeContext`, or None outside a turn.
        scope: A published effect scope. When it names a source, that source is
            returned verbatim — it was decided closer to the call than this
            function can see (a sub-agent, a HITL resumption).
        proactive: True when LIA started this on its own initiative. Wins over
            the automation flag: a proactive run is automated too, and the more
            specific answer must survive, or every briefing would be filed as a
            routine its owner configured.
        automated: The automation flag, for callers that hold it without a
            context — the turn factory receives it as an argument. Overrides
            what the context would have said.

    Returns:
        The source name, always a declared :class:`EffectSource` value.
    """
    scoped = getattr(scope, "source", None) if scope is not None else None
    if scoped:
        return scoped  # type: ignore[no-any-return]
    if proactive:
        return EffectSource.PROACTIVE.value
    is_automated = (
        automated
        if automated is not None
        else bool(context is not None and getattr(context, "is_automated_source", False))
    )
    if is_automated:
        return EffectSource.SCHEDULED.value
    # The pre-existing default of all four copies. Rows written under it exist,
    # so changing this answer would reclassify history rather than describe it.
    return EffectSource.USER.value


__all__ = ["resolve_source"]
