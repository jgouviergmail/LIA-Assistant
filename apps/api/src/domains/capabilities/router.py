"""The capability map — one read, one payload, no score.

Read-only and cheap: probes run in parallel, each on its own session, each
failing soft. The client draws a map from this; it never tunes anything here.

The payload carries STATE and FACTS, never a level, a percentage of
completion, or any comparison with another account. A capability is
`unavailable` (the instance disabled it — absent from the map entirely),
`dormant` (available, nothing set up) or `live`. What makes it live is a count
the reader can verify.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.core.session_dependencies import get_current_active_session
from src.domains.capabilities.service import resolve_capabilities
from src.domains.users.models import User

router = APIRouter(prefix="/capabilities", tags=["Capabilities"])


class CapabilityNode(BaseModel):
    """One capability of the map."""

    key: str = Field(
        description=(
            "Stable identifier. The client resolves the label from it, so a "
            "capability added later never surfaces as a raw i18n key."
        )
    )
    active: bool = Field(description="Whether the account can use it right now.")
    detail: int | None = Field(
        default=None,
        description=(
            "A count the reader can verify (connectors linked, memories kept). "
            "Never a score — a fact about this account, not a ranking."
        ),
    )


class CapabilityMap(BaseModel):
    """Everything the map draws.

    ``nodes`` holds ONLY what this instance offers: a subsystem the deployment
    disabled is absent, not greyed out (gate-keeper, ADR-061). ``live`` and
    ``total`` are counts of those same nodes, so the two never disagree — and
    they are counts, not a percentage of completion.
    """

    nodes: list[CapabilityNode]
    live: int = Field(ge=0, description="How many are usable right now.")
    total: int = Field(ge=0, description="How many this instance offers at all.")


@router.get(
    "",
    response_model=CapabilityMap,
    summary="What LIA can do for this account",
    description=(
        "Every capability this instance offers, and whether the account can "
        "use it right now. Read-only; nothing here is a level or a score."
    ),
)
async def get_capability_map(
    user: User = Depends(get_current_active_session),
) -> CapabilityMap:
    """The capability map for the authenticated account.

    Args:
        user: Authenticated session owner.

    Returns:
        The offered capabilities, in a stable order, and how many are live.
    """
    probes = await resolve_capabilities(user)
    offered = [probe for probe in probes if probe.available]
    return CapabilityMap(
        nodes=[
            CapabilityNode(key=probe.key, active=probe.active, detail=probe.detail)
            for probe in offered
        ],
        live=sum(1 for probe in offered if probe.active),
        total=len(offered),
    )
