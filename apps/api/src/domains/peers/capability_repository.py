"""Conditional receipt ownership and component outcomes share resource transactions."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.constants import PEERS_CAPABILITY_RETRY_TTL_SECONDS_DEFAULT
from src.domains.peers.capability_contracts import TransferStatus
from src.domains.peers.capability_models import (
    PeerCapabilityComponent,
    PeerCapabilityTransfer,
)


@dataclass(frozen=True)
class TransferLease:
    transfer_id: UUID
    owner: UUID
    fence: int


class TransferClaimLost(RuntimeError):
    """The operation must stop: it can no longer publish resource changes."""


class CapabilityTransferRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def owned(self, transfer_id: UUID, sender_id: UUID) -> PeerCapabilityTransfer | None:
        result = await self.db.execute(
            select(PeerCapabilityTransfer)
            .where(
                PeerCapabilityTransfer.id == transfer_id,
                PeerCapabilityTransfer.sender_id == sender_id,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def by_key(self, sender_id: UUID, key: UUID) -> PeerCapabilityTransfer | None:
        result = await self.db.execute(
            select(PeerCapabilityTransfer).where(
                PeerCapabilityTransfer.sender_id == sender_id,
                PeerCapabilityTransfer.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def claim(
        self,
        transfer_id: UUID,
        sender_id: UUID,
        digest: str,
        owner: UUID,
        *,
        ttl_seconds: int,
        retry_seconds: int = PEERS_CAPABILITY_RETRY_TTL_SECONDS_DEFAULT,
    ) -> TransferLease | None:
        row = await self.db.execute(
            update(PeerCapabilityTransfer)
            .where(
                PeerCapabilityTransfer.id == transfer_id,
                PeerCapabilityTransfer.sender_id == sender_id,
                PeerCapabilityTransfer.digest == digest,
                PeerCapabilityTransfer.expires_at > func.clock_timestamp(),
                (
                    PeerCapabilityTransfer.status.in_(
                        (
                            TransferStatus.PREPARING,
                            TransferStatus.PARTIAL,
                            TransferStatus.FAILED,
                        )
                    )
                )
                | (
                    (PeerCapabilityTransfer.status == TransferStatus.INSTALLING)
                    & (PeerCapabilityTransfer.lease_expires_at <= func.clock_timestamp())
                ),
            )
            .values(
                status=TransferStatus.INSTALLING.value,
                lease_owner=owner,
                lease_expires_at=func.clock_timestamp() + timedelta(seconds=ttl_seconds),
                expires_at=case(
                    (
                        PeerCapabilityTransfer.status == TransferStatus.PREPARING.value,
                        func.clock_timestamp() + timedelta(seconds=retry_seconds),
                    ),
                    else_=PeerCapabilityTransfer.expires_at,
                ),
                fence=PeerCapabilityTransfer.fence + 1,
                error_code=None,
            )
            .returning(PeerCapabilityTransfer.fence)
            .execution_options(synchronize_session=False)
        )
        fence = row.scalar_one_or_none()
        return TransferLease(transfer_id, owner, fence) if fence is not None else None

    def _owned_lease(self, lease: TransferLease) -> ColumnElement[bool]:
        return (
            (PeerCapabilityTransfer.id == lease.transfer_id)
            & PeerCapabilityTransfer.sender_id.is_not(None)
            & (PeerCapabilityTransfer.lease_owner == lease.owner)
            & (PeerCapabilityTransfer.fence == lease.fence)
            & (PeerCapabilityTransfer.lease_expires_at > func.clock_timestamp())
            & (PeerCapabilityTransfer.status == TransferStatus.INSTALLING.value)
        )

    async def fence_publication(self, lease: TransferLease, *, ttl_seconds: int) -> None:
        """Run immediately before commit; failure rolls back resource AND outcome."""
        published = exists(
            select(PeerCapabilityComponent.id).where(
                PeerCapabilityComponent.transfer_id == lease.transfer_id,
                PeerCapabilityComponent.installed.is_(True),
            )
        )
        updated = await self.db.execute(
            update(PeerCapabilityTransfer)
            .where(self._owned_lease(lease))
            .values(
                lease_expires_at=func.clock_timestamp() + timedelta(seconds=ttl_seconds),
                transferred_at=case(
                    (
                        published,
                        func.coalesce(
                            PeerCapabilityTransfer.transferred_at,
                            func.clock_timestamp(),
                        ),
                    ),
                    else_=PeerCapabilityTransfer.transferred_at,
                ),
            )
            .returning(PeerCapabilityTransfer.id)
            .execution_options(synchronize_session=False)
        )
        if updated.scalar_one_or_none() is None:
            raise TransferClaimLost("Transfer lease is no longer current")

    async def components(self, transfer_id: UUID) -> list[PeerCapabilityComponent]:
        result = await self.db.scalars(
            select(PeerCapabilityComponent)
            .where(PeerCapabilityComponent.transfer_id == transfer_id)
            .order_by(PeerCapabilityComponent.kind, PeerCapabilityComponent.key)
        )
        return list(result)

    async def reserve_component(
        self, transfer_id: UUID, *, kind: str, key: str, fingerprint: str
    ) -> PeerCapabilityComponent:
        await self.db.execute(
            insert(PeerCapabilityComponent)
            .values(
                transfer_id=transfer_id,
                kind=kind,
                key=key,
                fingerprint=fingerprint,
                installed=False,
            )
            .on_conflict_do_nothing(index_elements=["transfer_id", "kind", "key"])
        )
        component = await self.db.scalar(
            select(PeerCapabilityComponent).where(
                PeerCapabilityComponent.transfer_id == transfer_id,
                PeerCapabilityComponent.kind == kind,
                PeerCapabilityComponent.key == key,
            )
        )
        if component is None or component.fingerprint != fingerprint:
            raise ValueError("Transfer component identity changed")
        return component

    async def finish(
        self,
        lease: TransferLease,
        status: TransferStatus,
        *,
        error_code: str | None = None,
    ) -> None:
        if status not in {
            TransferStatus.INSTALLED,
            TransferStatus.PARTIAL,
            TransferStatus.FAILED,
            TransferStatus.CANCELLED,
        }:
            raise ValueError("A transfer must finish with a terminal outcome")
        statement = (
            update(PeerCapabilityTransfer)
            .where(self._owned_lease(lease))
            .values(
                status=status.value,
                error_code=error_code,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        if status is TransferStatus.INSTALLED:
            statement = statement.values(snapshot=None)
        result = await self.db.execute(
            statement.returning(PeerCapabilityTransfer.id).execution_options(
                synchronize_session=False
            )
        )
        if result.scalar_one_or_none() is None:
            raise TransferClaimLost("Transfer completion lost its lease")
