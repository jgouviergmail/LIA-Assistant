"""Reading a register by WHO set the work in motion.

Both journals carry four authorships, and one of them behaves nothing like the
others: a heartbeat sweep runs on its own schedule and can outnumber by far the
handful of actions a person actually asked for. Mixed into one list, the four
lines that matter drown under four hundred that do not — the argument that
already made Actions and Consultations two tabs rather than one merged view.

The vocabulary is shared by both journals on purpose. Two copies of « what
counts as mine » is how the Actions tab and the Consultations tab come to
disagree about the same row.

``MINE`` is defined by EXCLUSION rather than as a list. A fifth authorship added
tomorrow lands in the person's own reading by default — visible and possibly
misfiled, never invisible, which is the only safe direction for a register.
"""

from __future__ import annotations

from enum import Enum

from src.domains.agents.effects.models import EffectSource


class RegisterOrigin(str, Enum):
    """Which authorships a journal reading holds."""

    #: Everything the person set in motion: what they typed, the routines they
    #: wrote, and the sub-agents those turns delegated to.
    MINE = "mine"
    #: What LIA decided on its own — the heartbeat sweep, the interest sweeps,
    #: the weekly self-reflection.
    INITIATIVE = "initiative"
    #: No filter at all.
    ALL = "all"


#: The one authorship that is LIA's own decision rather than a person's.
_INITIATIVE_SOURCES: tuple[str, ...] = (EffectSource.PROACTIVE.value,)


def origin_sources(origin: RegisterOrigin) -> tuple[str, ...] | None:
    """The ``source`` values one reading holds.

    Args:
        origin: The reading asked for.

    Returns:
        The authorships to keep, or ``None`` when the reading filters nothing —
        ``None`` rather than the full tuple, so a caller adds no WHERE clause
        at all for the unfiltered case.
    """
    if origin is RegisterOrigin.ALL:
        return None
    if origin is RegisterOrigin.INITIATIVE:
        return _INITIATIVE_SOURCES
    return tuple(member.value for member in EffectSource if member.value not in _INITIATIVE_SOURCES)


__all__ = ["RegisterOrigin", "origin_sources"]
