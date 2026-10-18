"""Native installers bind disabled resources and receipt outcomes in one commit."""

from dataclasses import dataclass
from io import BytesIO
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.peers.capability_authority import capability_authority
from src.domains.peers.capability_contracts import (
    CapabilityKind,
    PackageSnapshot,
    PortableMCPConfig,
)
from src.domains.peers.capability_models import PeerCapabilityComponent
from src.domains.peers.capability_plugin import install_plugin
from src.domains.peers.capability_repository import (
    CapabilityTransferRepository,
    TransferLease,
)
from src.domains.peers.capability_sources import ensure_source_authorized
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill, SkillProvenance
from src.domains.skills.personal_state import set_personal_state
from src.domains.user_mcp.installation import (
    OfflineMCPInstallation,
    ValidatedMCPEndpoint,
)
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.schemas import UserMCPServerCreate
from src.domains.user_mcp.service import UserMCPServerService


def snapshot_archive(package: PackageSnapshot) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for resource in package.files:
            archive.writestr(resource.path, resource.content)
    return buffer.getvalue()


@dataclass(frozen=True)
class TransferInstallation:
    lease: TransferLease
    sender: UUID
    recipient: UUID
    connection_id: UUID
    source_id: UUID
    package: PackageSnapshot

    async def check(self, db: AsyncSession) -> None:
        recipient = await capability_authority(
            db,
            self.sender,
            self.connection_id,
            self.package.kind,
            lock=True,
            mcp_required=bool(self.package.servers),
        )
        if recipient != self.recipient:
            raise AuthorizationError()
        await ensure_source_authorized(db, self.sender, self.package.kind, self.source_id)
        await CapabilityTransferRepository(db).fence_publication(
            self.lease, ttl_seconds=settings.peers_capability_lease_seconds
        )

    async def reserve(
        self, db: AsyncSession, kind: CapabilityKind, key: str
    ) -> PeerCapabilityComponent:
        return await CapabilityTransferRepository(db).reserve_component(
            self.lease.transfer_id,
            kind=kind.value,
            key=key,
            fingerprint=self.package.digest,
        )

    async def skill_before_swap(self, db: AsyncSession) -> None:
        await self.check(db)
        existing = await db.scalar(
            select(Skill.id).where(
                Skill.name == self.package.name,
                or_(Skill.owner_id == self.recipient, Skill.is_system.is_(True)),
            )
        )
        if existing is not None:
            raise ResourceConflictError("capability", self.package.name)

    async def skill_registered(self, db: AsyncSession, skill: Skill) -> None:
        await set_personal_state(db, self.recipient, skill.id, enabled=False)
        component = await self.reserve(db, CapabilityKind.SKILL, skill.name)
        component.resource_id = skill.id
        component.installed = True
        component.error_code = None
        skill.peer_authored = self.package.kind is CapabilityKind.PLUGIN
        await db.flush()

    async def install_skill(self, db: AsyncSession, archive: bytes) -> None:
        component = await self.reserve(db, CapabilityKind.SKILL, self.package.name)
        if component.installed:
            return
        await SkillImportService(db).import_upload(
            archive,
            "shared.zip",
            owner_id=self.recipient,
            is_system=False,
            provenance=SkillProvenance.PEER,
            after_register=self.skill_registered,
            before_swap=self.skill_before_swap,
            before_commit=self.check,
        )

    async def install_mcp(
        self,
        db: AsyncSession,
        config: PortableMCPConfig,
        endpoint: ValidatedMCPEndpoint,
    ) -> None:
        component = await self.reserve(db, CapabilityKind.MCP, config.name)
        if component.installed:
            return

        async def before_write(session: AsyncSession) -> None:
            await self.check(session)
            existing = await session.scalar(
                select(UserMCPServer.id).where(
                    UserMCPServer.user_id == self.recipient,
                    UserMCPServer.name == config.name,
                )
            )
            if existing is not None:
                raise ResourceConflictError("capability", config.name)

        server = await UserMCPServerService(db).create_server(
            self.recipient,
            UserMCPServerCreate(
                name=config.name,
                url=config.url,
                domain_description=config.domain_description,
                timeout_seconds=config.timeout_seconds,
                iterative_mode=config.iterative_mode,
            ),
            extra_headers=config.extra_headers or None,
            before_write=before_write,
            offline_install=OfflineMCPInstallation(
                config.auth_type, config.header_name, endpoint, config.oauth_scopes
            ),
        )
        component.resource_id = server.id
        component.installed = True
        await self.check(db)
        await db.commit()

    async def install_plugin(
        self,
        db: AsyncSession,
        archive: bytes,
        endpoints: dict[str, ValidatedMCPEndpoint],
    ) -> None:
        await install_plugin(self, db, archive, endpoints)
