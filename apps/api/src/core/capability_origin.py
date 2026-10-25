"""Read-only provenance of a capability, independent of the other side's lifetime.

Two directions of one act: where a recipient's copy came from
(``CapabilityOrigin``), and who a sender shared theirs with
(``CapabilityShare``). Each side sees its own act only, never the state of
the other side's copy.
"""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

CapabilityOriginKind = Literal["skill", "mcp", "plugin"]


class CapabilityOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sender_display_name: str | None
    shared_at: AwareDatetime
    transfer_id: UUID


class CapabilityShare(BaseModel):
    """One recipient a sender's capability was published to — its latest share.

    ``recipient_display_name`` is None once that account is deactivated or
    erased (the origin's own rule); ``complete`` is False while or when only
    part of it was installed; ``can_share_again`` is the server's sharing
    policy for that recipient, so no client decides it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    recipient_id: UUID
    recipient_display_name: str | None
    shared_at: AwareDatetime
    transfer_id: UUID
    complete: bool
    can_share_again: bool
