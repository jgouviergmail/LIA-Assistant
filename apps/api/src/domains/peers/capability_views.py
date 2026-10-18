"""Bounded receipt projections never expose retained bytes or lease authority."""

from src.domains.peers.capability_contracts import (
    CapabilityComponentView,
    CapabilityFileView,
    CapabilityKind,
    CapabilityTransferView,
    PackageSnapshot,
    TransferStatus,
)
from src.domains.peers.capability_models import (
    PeerCapabilityComponent,
    PeerCapabilityTransfer,
)
from src.domains.user_mcp.models import UserMCPAuthType


def transfer_view(
    row: PeerCapabilityTransfer, components: list[PeerCapabilityComponent]
) -> CapabilityTransferView:
    package = PackageSnapshot.model_validate(row.snapshot) if row.snapshot else None
    return CapabilityTransferView(
        id=row.id,
        kind=CapabilityKind(row.kind),
        name=row.name,
        status=TransferStatus(row.status),
        digest=row.digest,
        created_at=row.created_at,
        transferred_at=row.transferred_at,
        error_code=row.error_code,
        files=(
            tuple(CapabilityFileView(path=f.path, size=len(f.content)) for f in package.files)
            if package
            else ()
        ),
        omitted=package.omitted if package else (),
        requires_credentials=(
            any(s.config.auth_type is not UserMCPAuthType.NONE for s in package.servers)
            if package
            else False
        ),
        components=tuple(
            CapabilityComponentView(
                kind=CapabilityKind(c.kind),
                key=c.key,
                resource_id=c.resource_id,
                installed=c.installed,
                error_code=c.error_code,
            )
            for c in components
        ),
    )
