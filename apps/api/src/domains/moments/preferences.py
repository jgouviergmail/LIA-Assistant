"""Which kinds of moment a person accepts being interrupted by.

The preference stores a REFUSAL set, never an allow-list — ADR-197's doctrine
applied to a second vocabulary. ``NULL`` means « never expressed », so an
account that predates the feature behaves exactly as before, and a kind shipped
in a later lot is ON until someone refuses it rather than invisible until
everyone re-opts in.

The two directions are deliberately asymmetric:

- **reading is forgiving.** The column is JSONB and could have been hand-edited;
  the safe reading of anything unexpected is « nothing refused ». Silencing a
  kind by accident is the failure to avoid, not the other way round.
- **writing is strict.** A value the registry does not know is dropped rather
  than stored, so a renamed kind cannot silence itself for ever, and a stale
  client cannot save a refusal nobody can ever lift.
"""

from __future__ import annotations

from typing import Any

from src.domains.moments.kinds import MOMENT_KIND_SPECS
from src.domains.moments.models import MomentKind

#: Every kind key a person may refuse. Derived from the enum, never retyped.
MOMENT_KIND_KEYS: frozenset[str] = frozenset(kind.value for kind in MomentKind)

#: Display order the API publishes, so the panel never re-declares a vocabulary
#: it does not enforce. Declaration order of the registry.
MOMENT_KIND_ORDER: tuple[str, ...] = tuple(kind.value for kind in MOMENT_KIND_SPECS)


def disabled_kinds_for(user: Any) -> frozenset[str]:
    """Kinds this person refused, read tolerantly.

    Args:
        user: User model, or anything carrying the attribute.

    Returns:
        The refused kind keys; empty when nothing valid is stored.
    """
    raw = getattr(user, "moment_kinds_disabled", None)
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(item for item in raw if isinstance(item, str) and item in MOMENT_KIND_KEYS)


def is_kind_enabled(user: Any, kind: str) -> bool:
    """Whether LIA may come back to this person for this kind of instant.

    Args:
        user: User model.
        kind: A ``MomentKind`` value.

    Returns:
        True unless they explicitly refused it.
    """
    return kind not in disabled_kinds_for(user)


def sanitize_disabled_kinds(values: list[str]) -> list[str]:
    """Validate and normalise a refusal list before it is stored.

    Args:
        values: What the client sent.

    Returns:
        The known kinds among them, deduplicated, in the published order — so
        two saves of the same choice produce the same column and a write is
        only ever a real change.
    """
    asked = {value for value in values if isinstance(value, str)}
    return [kind for kind in MOMENT_KIND_ORDER if kind in asked]


def unmet_kind_dependencies(*, available: frozenset[str]) -> dict[str, tuple[str, ...]]:
    """Kinds that would yield nothing, and what they are waiting for.

    Published so the panel can say « requires Calendar » rather than offer a
    live control that produces nothing (ADR-184).

    Args:
        available: Connector categories this account actually has.

    Returns:
        Mapping of kind to the requirements it is missing; empty when every
        kind can work.
    """
    return {
        kind.value: missing
        for kind, spec in MOMENT_KIND_SPECS.items()
        if (missing := tuple(need for need in spec.requires if need not in available))
    }
