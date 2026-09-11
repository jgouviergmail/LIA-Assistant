"""The two shapes a moment travels in, once it leaves its table.

Deliberately free of every heavy import: the heartbeat reads these to render its
FRESH section, and a domain that pulled the detectors in with them would drag
the connectors, the workboard and the relations into a module whose only job is
to say « a meeting just ended, here is what it was ».
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MomentFacts:
    """What a revalidation found, at the instant the moment is served.

    A moment is detected minutes or hours before it is served, and the world
    moves in between: an event is cancelled, moved, or declined. The claim
    therefore re-reads the fact rather than trusting what was filed — which is
    also why the stored payload carries no names: they would be a stale copy of
    something re-read anyway.

    Attributes:
        still_valid: False when the fact no longer holds — the moment settles as
            ``cancelled`` and nothing is said.
        lines: Rendered facts for the prompt, in English like the rest of the
            heartbeat's dynamic context. Bounded and factual: what happened,
            when, and with how many people — never an opinion about it.
    """

    still_valid: bool
    lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ServedMoment:
    """One moment, ready to be put in front of the decision.

    Attributes:
        kind: A ``MomentKind`` value, carried for the audit and the metrics.
        headline: The one-line English statement of what just became true.
        lines: The revalidated facts.

    Deliberately carries no row id: the sweep settles the row from the id it
    claimed with, and a second copy travelling through the heartbeat would be a
    field nobody reads — the kind of thing that quietly starts being trusted.
    """

    kind: str
    headline: str
    lines: tuple[str, ...]
