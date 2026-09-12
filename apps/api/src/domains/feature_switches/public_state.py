"""The capability states an anonymous reader may learn about this instance.

``GET /config`` is public and cookie-less. Publishing every capability's
EFFECTIVE state there — the deployment ceiling AND the operator switch — lets
a page that merely links to an instance say what a visitor will find and what
they will not: the demonstrator invitation of another LIA reads it live
(``LiveDemoInvitation``), so the list never drifts from the instance's own
``.env`` the way a hand-kept copy would.

Nothing here is secret: each flag already governs a visible surface (a
settings section, a bubble action, a composer button), so a reader learns from
this payload only what the screens would have told them one by one.
"""

from __future__ import annotations

from typing import TypedDict

from src.domains.feature_switches.registry import (
    CAPABILITY_SPECS,
    deployment_allows,
    disabled_capabilities,
)


class PublicCapabilityState(TypedDict):
    """One capability as the public configuration describes it."""

    enabled: bool
    family: str


async def public_capability_states() -> dict[str, PublicCapabilityState]:
    """Every registry capability with its effective availability.

    The operator switches are read in ONE pass (``disabled_capabilities``),
    which also gives this read the store's own degradation: a failing store
    reports nothing switched off, and the payload then says exactly what the
    deployment ceiling says — the behaviour the routes enforce in that case.

    Returns:
        ``{capability value: {"enabled": bool, "family": str}}`` for every
        member of the registry, keyed by the frontend's vocabulary
        (``capabilities.items.<value>``).
    """
    switched_off = await disabled_capabilities()
    return {
        capability.value: PublicCapabilityState(
            enabled=deployment_allows(capability) and capability not in switched_off,
            family=spec.family,
        )
        for capability, spec in CAPABILITY_SPECS.items()
    }
