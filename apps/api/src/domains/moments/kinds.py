"""A kind is a detector, a revalidator, a headline and a label — declared once.

This is the registry the next three kinds grow through, so it carries ADR-085's
doctrine from the first member rather than after the drift: a table keyed by an
enum gets a boot-time completeness assert, checked BOTH ways.

The two failure modes it closes are different, and both are silent:

- a member with no spec — the sweep loops over the kinds and quietly skips one,
  so a feature ships and never fires;
- a spec with no member — a kind is removed and its detector keeps filing rows
  nothing will ever serve.

The label is part of the contract, not decoration: the settings panel renders
``t(spec.label_key)`` for whatever the backend publishes, and i18next falls back
to the key itself. A kind added backend-side alone puts a raw
``moments.kind_deadline_eve`` in front of a reader in all six languages at once,
with every gate green — which is why a test holds the six locales to this table.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.domains.moments.detectors import event_followup
from src.domains.moments.models import MomentKind
from src.domains.moments.repository import MomentCandidate
from src.domains.moments.schemas import MomentFacts

#: Find what should be anticipated for this account, now.
DetectorFn = Callable[[Any, datetime], Awaitable[list[MomentCandidate]]]

#: Re-read the fact at the instant it is served, and say whether it still holds.
RevalidatorFn = Callable[[Any, str, Mapping[str, Any]], Awaitable[MomentFacts]]


@dataclass(frozen=True, slots=True)
class MomentKindSpec:
    """Everything one kind of moment needs to exist.

    Attributes:
        kind: The member this spec describes.
        detector: What finds candidates for an account.
        revalidator: What re-reads the fact before anything is said.
        headline: The English line that opens the FRESH prompt section — what
            just became true. English like the rest of the heartbeat's dynamic
            context; the person's own language is applied when the message is
            written, not when the decision is taken.
        label_key: i18n key the settings panel resolves for this kind's switch.
        requires: Capabilities or connector categories without which this kind
            yields nothing. Published so the panel can say « requires Calendar »
            rather than offer a live control that produces nothing (ADR-184).
    """

    kind: MomentKind
    detector: DetectorFn
    revalidator: RevalidatorFn
    headline: str
    label_key: str
    requires: tuple[str, ...]


MOMENT_KIND_SPECS: dict[MomentKind, MomentKindSpec] = {
    MomentKind.EVENT_FOLLOWUP: MomentKindSpec(
        kind=MomentKind.EVENT_FOLLOWUP,
        detector=event_followup.detect,
        revalidator=event_followup.revalidate,
        headline="A meeting on their calendar has just ended.",
        label_key="moments.kind_event_followup",
        requires=("calendar",),
    ),
}


def assert_moment_kind_registry_complete(
    specs: Mapping[Any, MomentKindSpec] | None = None,
) -> None:
    """Refuse to boot on a kind with no spec, or a spec with no kind.

    Args:
        specs: The table to check. Defaults to the shipped one; a caller passes
            its own only to prove this guard fires.

    Raises:
        RuntimeError: On either half of the partition, naming what is missing.
    """
    table = MOMENT_KIND_SPECS if specs is None else specs
    declared = set(table)
    known = set(MomentKind)

    missing = sorted(kind.value for kind in known - declared)
    unknown = sorted(str(getattr(kind, "value", kind)) for kind in declared - known)
    if missing or unknown:
        raise RuntimeError(
            "Moment kind registry incomplete: "
            f"kinds with no spec={missing}, specs with no kind={unknown}"
        )

    for kind, spec in table.items():
        if spec.kind is not kind:
            raise RuntimeError(
                f"Moment kind spec filed under {kind} declares {spec.kind}: "
                "a detector routed to the wrong rows fails silently."
            )
        if not spec.headline.strip():
            raise RuntimeError(
                f"Moment kind {kind} has no headline: the FRESH section "
                "would tell the model it was woken for nothing."
            )


# The boot carries this: every process that imports the registry checks it.
assert_moment_kind_registry_complete()
