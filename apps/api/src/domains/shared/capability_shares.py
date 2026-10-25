"""Who a sender shared a capability with — and whether they may share it again.

The sender's side of ``capability_origins``, through the same registered SQL
metadata and for the same reason: skills, plugins and MCP list their own
cards, and the peers domain installs them, so a reader here keeps the
dependency one-way.

A share is PUBLISHED once its receipt carries ``transferred_at`` — the
instant its first component reached the recipient, the very predicate that
gives the recipient's copy its origin. One query serves a whole page of
cards, the newest share of each recipient first.

Whether a sender may share again is ONE function, ``reshare_allowed``: the
owner's rule (2026-10-24) makes a published share final FOR NOW, and the day
a newer version may be sent again only that function changes — no index,
no constraint stands in its way. The preview and the send ask it under the
pair's lock, the settings lists publish its verdict per recipient.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, Table, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.capability_origin import CapabilityOriginKind, CapabilityShare
from src.infrastructure.database.session import Base

#: ``TransferStatus.INSTALLED`` — every component of the share reached the recipient.
_COMPLETE: Final = "installed"
#: ``TransferStatus.INSTALLING`` — a confirmed share whose installation is running.
_INSTALLING: Final = "installing"


@dataclass(frozen=True, slots=True)
class _Published:
    source_id: UUID
    recipient_id: UUID
    recipient_display_name: str | None
    shared_at: datetime
    transfer_id: UUID
    digest: str
    complete: bool


def reshare_allowed(previous_digests: Sequence[str], current_digest: str | None) -> bool:
    """Whether a capability may be shared with a recipient it was published to before.

    Args:
        previous_digests: The digests of every share of it already given to
            that recipient — published, or (at the preview and the send)
            still installing.
        current_digest: The version about to be shared, when known (the
            preview and the send know it, a settings list does not). Today's
            rule does not read it: it is where a « newer version » rule would.

    Returns:
        True when nothing was published to that recipient yet.
    """
    return not previous_digests


def _transfers() -> Table:
    transfers: Table = Base.metadata.tables["peer_capability_transfers"]
    return transfers


def _is_published(transfers: Table) -> ColumnElement[bool]:
    """The receipt reached the recipient — the predicate of the recipient's origin too."""
    return transfers.c.transferred_at.is_not(None)


async def _published(
    db: AsyncSession, owner_id: UUID, kind: CapabilityOriginKind, source_ids: Sequence[UUID]
) -> list[_Published]:
    transfers = _transfers()
    users = Base.metadata.tables["users"]
    recipient_name = case(
        (users.c.deleted_at.is_(None) & users.c.is_active.is_(True), users.c.full_name),
        else_=None,
    )
    query = (
        select(
            transfers.c.source_id,
            transfers.c.recipient_id,
            recipient_name.label("recipient_display_name"),
            transfers.c.transferred_at,
            transfers.c.id,
            transfers.c.digest,
            transfers.c.status,
        )
        .select_from(transfers.outerjoin(users, users.c.id == transfers.c.recipient_id))
        .where(
            transfers.c.sender_id == owner_id,
            transfers.c.kind == kind,
            transfers.c.source_id.in_(source_ids),
            _is_published(transfers),
        )
        .order_by(transfers.c.transferred_at.desc(), transfers.c.id.desc())
    )
    return [
        _Published(
            source_id=row.source_id,
            recipient_id=row.recipient_id,
            recipient_display_name=row.recipient_display_name,
            shared_at=row.transferred_at,
            transfer_id=row.id,
            digest=row.digest,
            complete=row.status == _COMPLETE,
        )
        for row in (await db.execute(query)).all()
    ]


async def capability_shares(
    db: AsyncSession,
    owner_id: UUID,
    kind: CapabilityOriginKind,
    source_ids: Iterable[UUID],
) -> dict[UUID, list[CapabilityShare]]:
    """The recipients each of ``source_ids`` was published to, newest share first.

    Args:
        db: Session.
        owner_id: The sender — only their own shares are read.
        kind: The kind of the capabilities.
        source_ids: The sender's capabilities on the page.

    Returns:
        ``{source id: one entry per recipient}``; a never-shared capability is absent.
    """
    ids = tuple(source_ids)
    if not ids:
        return {}
    digests: dict[tuple[UUID, UUID], list[str]] = defaultdict(list)
    latest: dict[tuple[UUID, UUID], _Published] = {}
    for share in await _published(db, owner_id, kind, ids):
        pair = (share.source_id, share.recipient_id)
        digests[pair].append(share.digest)
        latest.setdefault(pair, share)
    shares: dict[UUID, list[CapabilityShare]] = defaultdict(list)
    for pair, share in latest.items():
        shares[share.source_id].append(
            CapabilityShare(
                recipient_id=share.recipient_id,
                recipient_display_name=share.recipient_display_name,
                shared_at=share.shared_at,
                transfer_id=share.transfer_id,
                complete=share.complete,
                can_share_again=reshare_allowed(digests[pair], None),
            )
        )
    return dict(shares)


async def share_again_allowed(
    db: AsyncSession,
    *,
    sender_id: UUID,
    recipient_id: UUID,
    kind: str,
    source_id: UUID,
    current_digest: str | None,
    excluding: UUID | None = None,
) -> bool:
    """The policy's verdict for one recipient, read on the caller's (locked) session.

    A share being INSTALLED counts as given: the pair's lock is released before
    the installation runs, so a second receipt confirmed meanwhile would
    otherwise reach the recipient too.

    Args:
        db: The session holding the pair's lock.
        sender_id: Who shares.
        recipient_id: Who would receive.
        kind: The capability's kind.
        source_id: The sender's capability.
        current_digest: The version about to be shared.
        excluding: A receipt that is not a PREVIOUS share — the one being
            resumed, so a partial share can still complete.

    Returns:
        Whether this share may go ahead.
    """
    transfers = _transfers()
    query = select(transfers.c.digest).where(
        transfers.c.sender_id == sender_id,
        transfers.c.recipient_id == recipient_id,
        transfers.c.kind == kind,
        transfers.c.source_id == source_id,
        _is_published(transfers) | (transfers.c.status == _INSTALLING),
    )
    if excluding is not None:
        query = query.where(transfers.c.id != excluding)
    return reshare_allowed(list((await db.execute(query)).scalars()), current_digest)


__all__ = ["capability_shares", "reshare_allowed", "share_again_allowed"]
