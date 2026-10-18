"""Explicit preview/confirmation; short sessions surround bounded external work."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from src.core.config import settings
from src.core.exceptions import (
    BaseAPIException,
    ResourceConflictError,
    ResourceNotFoundError,
)
from src.domains.peers.capability_authority import (
    capability_authority,
    check_transfer_caps,
)
from src.domains.peers.capability_contracts import (
    CapabilityKind,
    CapabilityPreviewRequest,
    CapabilityTransferView,
    PackageSnapshot,
    TransferStatus,
)
from src.domains.peers.capability_install import TransferInstallation, snapshot_archive
from src.domains.peers.capability_models import PeerCapabilityTransfer
from src.domains.peers.capability_package import verify_snapshot
from src.domains.peers.capability_repository import (
    CapabilityTransferRepository,
    TransferClaimLost,
)
from src.domains.peers.capability_sources import (
    CapabilitySource,
    ensure_source_authorized,
    load_capability_source,
)
from src.domains.peers.capability_views import transfer_view
from src.domains.shared.action_sink import (
    PEER_CAPABILITY_SHARE_CAPABILITY,
    recorded_action,
)
from src.domains.skills.cache import SkillsCache
from src.domains.user_mcp.installation import (
    ValidatedMCPEndpoint,
    validate_install_endpoint,
)
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _same_request(row: PeerCapabilityTransfer, request: CapabilityPreviewRequest) -> None:
    if (row.connection_id, row.kind, row.source_id) != (
        request.connection_id,
        request.kind.value,
        request.source_id,
    ):
        raise ResourceConflictError("capability", detail="peers_capability_idempotency_conflict")


def _confirmed_package(row: PeerCapabilityTransfer, digest: str) -> PackageSnapshot:
    package = PackageSnapshot.model_validate(row.snapshot)
    if not verify_snapshot(package, digest):
        raise ResourceConflictError("capability", detail="peers_capability_changed")
    return package


async def get_capability_transfer(sender: UUID, transfer_id: UUID) -> CapabilityTransferView:
    async with get_db_context() as db:
        repo = CapabilityTransferRepository(db)
        row = await repo.owned(transfer_id, sender)
        if row is None:
            raise ResourceNotFoundError("capability")
        return transfer_view(row, await repo.components(row.id))


async def preview_capability(
    sender: UUID, request: CapabilityPreviewRequest
) -> CapabilityTransferView:
    async with get_db_context() as db:
        recipient = await capability_authority(db, sender, request.connection_id, request.kind)
        source = await load_capability_source(db, sender, request.kind, request.source_id)
        existing = await CapabilityTransferRepository(db).by_key(sender, request.idempotency_key)
        if existing is not None:
            _same_request(existing, request)
            return transfer_view(
                existing, await CapabilityTransferRepository(db).components(existing.id)
            )
        await check_transfer_caps(db, sender, recipient, 0)
    package = await source.snapshot()
    size = len(package.model_dump_json().encode())
    async with get_db_context() as db:
        recipient = await capability_authority(
            db,
            sender,
            request.connection_id,
            request.kind,
            lock=True,
            mcp_required=bool(package.servers),
        )
        await ensure_source_authorized(db, sender, request.kind, request.source_id)
        repo = CapabilityTransferRepository(db)
        existing = await repo.by_key(sender, request.idempotency_key)
        if existing is not None:
            _same_request(existing, request)
            return transfer_view(existing, await repo.components(existing.id))
        await check_transfer_caps(db, sender, recipient, size)
        row = PeerCapabilityTransfer(
            sender_id=sender,
            recipient_id=recipient,
            connection_id=request.connection_id,
            source_id=request.source_id,
            idempotency_key=request.idempotency_key,
            kind=request.kind.value,
            name=package.name,
            digest=package.digest,
            snapshot=package.model_dump(mode="json"),
            payload_bytes=size,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.peers_capability_preview_ttl_seconds),
        )
        db.add(row)
        await db.flush()
        return transfer_view(row, [])


async def send_capability(sender: UUID, transfer_id: UUID, digest: str) -> CapabilityTransferView:
    async with get_db_context() as db:
        repo = CapabilityTransferRepository(db)
        row = await repo.owned(transfer_id, sender)
        if row is None:
            raise ResourceNotFoundError("capability")
        if row.digest != digest:
            raise ResourceConflictError("capability", detail="peers_capability_changed")
        if row.status == TransferStatus.INSTALLED.value:
            return transfer_view(row, await repo.components(row.id))
        if row.snapshot is None or row.connection_id is None or row.expires_at <= datetime.now(UTC):
            raise ResourceConflictError("capability", detail="peers_capability_expired")
        kind = CapabilityKind(row.kind)
        recipient = await capability_authority(db, sender, row.connection_id, kind)
        await ensure_source_authorized(db, sender, kind, row.source_id)
        source = (
            await load_capability_source(db, sender, kind, row.source_id)
            if row.status == TransferStatus.PREPARING.value
            else None
        )
        package = _confirmed_package(row, digest)
        connection_id, source_id = row.connection_id, row.source_id
    archive, endpoints = await _preflight_snapshot(source, package)
    async with get_db_context() as db:
        await capability_authority(
            db,
            sender,
            connection_id,
            kind,
            lock=True,
            mcp_required=bool(package.servers),
        )
        lease = await CapabilityTransferRepository(db).claim(
            transfer_id,
            sender,
            digest,
            uuid4(),
            ttl_seconds=settings.peers_capability_lease_seconds,
            retry_seconds=settings.peers_capability_retry_ttl_seconds,
        )
        if lease is None:
            raise ResourceConflictError("capability", detail="peers_capability_busy")
    installation = TransferInstallation(lease, sender, recipient, connection_id, source_id, package)
    async with recorded_action(
        user_id=sender,
        capability=PEER_CAPABILITY_SHARE_CAPABILITY,
        arguments={"receipt_id": str(transfer_id), "attempt": str(lease.fence)},
    ) as action:
        result = await _run_installation(installation, archive, endpoints)
        action.succeeded = result.status is TransferStatus.INSTALLED
        return result


async def _preflight_snapshot(
    source: CapabilitySource | None, package: PackageSnapshot
) -> tuple[bytes, dict[str, ValidatedMCPEndpoint]]:
    """External preflight runs after the read transaction closes, before claiming."""
    if source is not None and (await source.snapshot()).digest != package.digest:
        raise ResourceConflictError("capability", detail="peers_capability_changed")
    endpoints = {
        server.key: await validate_install_endpoint(server.config.url) for server in package.servers
    }
    archive = await asyncio.to_thread(snapshot_archive, package) if package.files else b""
    return archive, endpoints


async def _run_installation(
    installation: TransferInstallation,
    archive: bytes,
    endpoints: dict[str, ValidatedMCPEndpoint],
) -> CapabilityTransferView:
    kind = installation.package.kind
    sender, transfer_id = installation.sender, installation.lease.transfer_id
    package = installation.package
    try:
        async with get_db_context() as db:
            if kind is CapabilityKind.SKILL:
                await installation.install_skill(db, archive)
            elif kind is CapabilityKind.MCP:
                server = package.servers[0]
                await installation.install_mcp(db, server.config, endpoints[server.key])
            else:
                await installation.install_plugin(db, archive, endpoints)
    except (Exception, asyncio.CancelledError) as exc:
        # A native importer may have committed a component before losing its ack.
        # Read durable outcomes on a NEW session; never infer rollback from an exception.
        logger.warning(
            "peer_capability_install_interrupted",
            transfer_id=str(transfer_id),
            error_type=type(exc).__name__,
        )
        if isinstance(exc, asyncio.CancelledError):
            raise
        await _finish_installation(installation, error_code="peers_capability_install_failed")
        if isinstance(exc, BaseAPIException):
            raise
        return await get_capability_transfer(sender, transfer_id)
    await _finish_installation(installation)
    return await get_capability_transfer(sender, transfer_id)


async def _finish_installation(
    installation: TransferInstallation, error_code: str | None = None
) -> None:
    async with get_db_context() as db:
        repo = CapabilityTransferRepository(db)
        components = await repo.components(installation.lease.transfer_id)
        published_skills = any(
            component.kind == CapabilityKind.SKILL.value and component.installed
            for component in components
        )
        complete = bool(components) and all(component.installed for component in components)
        status = (
            TransferStatus.INSTALLED
            if complete
            else (
                TransferStatus.PARTIAL
                if any(c.installed for c in components)
                else TransferStatus.FAILED
            )
        )
        try:
            await repo.finish(
                installation.lease,
                status,
                error_code=(None if complete else error_code or "peers_capability_incomplete"),
            )
        except TransferClaimLost:
            # A takeover/erasure owns the receipt now; this worker cannot settle it.
            await db.rollback()
            return
    if published_skills:
        # A committed component may have lost its acknowledgement before the
        # importer's cache callback. Reconcile from durable receipt identities.
        try:
            await SkillsCache.invalidate_and_reload()
        except Exception as exc:
            logger.warning(
                "peer_capability_catalogue_refresh_failed",
                transfer_id=str(installation.lease.transfer_id),
                error_type=type(exc).__name__,
            )
