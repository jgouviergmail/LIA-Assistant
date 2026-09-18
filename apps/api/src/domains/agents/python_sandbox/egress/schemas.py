"""Wire shapes of the egress grants (ADR-298)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.agents.python_sandbox.egress.hosts import HostStatus


class EgressGrantResponse(BaseModel):
    """One grant, as the settings page draws it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="The grant.")
    host: str = Field(description="The exact hostname the proxy matches.")
    share_turn_data: bool = Field(
        description="Whether the turn's collected data may reach a script that declares this host."
    )
    created_at: datetime = Field(description="When the person decided.")
    last_used_at: datetime | None = Field(
        default=None, description="When a run last relied on it; null when none did yet."
    )


class EgressGrantListResponse(BaseModel):
    """One page of grants, its exact total, and the bounds it obeys."""

    items: list[EgressGrantResponse]
    total: int = Field(description="EXACT count over the account's grants (ADR-185).")
    limit: int = Field(description="Page size applied.")
    offset: int = Field(description="Page start applied.")
    max_limit: int = Field(
        description="Largest page this API serves — published because it is enforced (ADR-184)."
    )
    max_per_user: int = Field(
        description=(
            "How many grants the account may keep — published because it is enforced: past "
            "it an approval holds for its run only."
        )
    )


class EgressGrantScopeUpdate(BaseModel):
    """The one thing a person changes on a grant from the settings page."""

    share_turn_data: bool = Field(description="The new scope.")


class ReachableHost(BaseModel):
    """A host a script may reach without asking, and why."""

    host: str
    status: HostStatus = Field(description="connector (a credential travels) or operator.")
    connector: str | None = Field(
        default=None, description="The connector whose key a script may use on this host."
    )


class ReachableHostsResponse(BaseModel):
    """What this account's scripts may reach without a question."""

    items: list[ReachableHost]
    ask_enabled: bool = Field(
        description="Whether an unknown host is asked of the person (else refused)."
    )


__all__ = [
    "EgressGrantListResponse",
    "EgressGrantResponse",
    "EgressGrantScopeUpdate",
    "ReachableHost",
    "ReachableHostsResponse",
]
