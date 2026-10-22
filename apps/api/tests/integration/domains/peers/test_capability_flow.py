"""Real commits and recipient state, rather than optimistic wrapper outcomes."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.constants import (
    AGENT_PLUGINS_MCP_SCHEMA_ID,
    AGENT_PLUGINS_PLUGIN_SCHEMA_ID,
)
from src.core.exceptions import ValidationError
from src.core.security.utils import encrypt_data
from src.domains.peers import capability_flow, capability_sources
from src.domains.peers.capability_contracts import (
    CapabilityKind,
    CapabilityPreviewRequest,
    PortableMCPConfig,
    TransferStatus,
)
from src.domains.peers.capability_models import PeerCapabilityTransfer
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.plugins.models import UserPlugin
from src.domains.skills import import_service as skill_import
from src.domains.skills.cache import SkillsCache
from src.domains.skills.import_commit import SkillImportCompletionUnknown
from src.domains.skills.models import Skill, UserSkillState
from src.domains.user_mcp.installation import ValidatedMCPEndpoint
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.service import UserMCPServerService
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def test_skill_is_disabled_at_first_commit_and_retry_preserves_recipient_edits(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, autoflush=False)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            yield db
            await db.commit()

    monkeypatch.setattr(capability_flow, "get_db_context", sessions)
    monkeypatch.setattr(settings, "peers_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "users"))
    monkeypatch.setattr(settings, "skills_system_path", str(tmp_path / "system"))
    async with sessions() as db:
        sender, recipient = UserFactory.create(), UserFactory.create()
        db.add_all([sender, recipient])
        await db.flush()
        committed_user_ids.extend([sender.id, recipient.id])
        first, second = canonical_pair(sender.id, recipient.id)
        pair = PeerConnection(
            user_a_id=first,
            user_b_id=second,
            requested_by_id=sender.id,
            status="accepted",
        )
        skill = Skill(
            name="shared-example",
            description="Useful instructions",
            owner_id=sender.id,
            is_system=False,
            provenance="authored",
        )
        db.add_all([pair, skill])
        await db.flush()
        request = CapabilityPreviewRequest(
            connection_id=pair.id,
            kind=CapabilityKind.SKILL,
            source_id=skill.id,
            idempotency_key=uuid4(),
        )
    root = tmp_path / "users" / str(sender.id) / skill.name
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: shared-example\ndescription: Useful instructions\n---\nInstructions",
        encoding="utf-8",
    )
    preview = await capability_flow.preview_capability(sender.id, request)
    assert preview.status is TransferStatus.PREPARING
    original_commit = skill_import.commit_skill_import
    first_commits: list[UUID] = []

    async def observe_first_commit(session: AsyncSession) -> None:
        await original_commit(session)
        async with sessions() as observer:
            copied = (
                await observer.execute(select(Skill).where(Skill.owner_id == recipient.id))
            ).scalar_one()
            state = (
                await observer.execute(
                    select(UserSkillState).where(UserSkillState.skill_id == copied.id)
                )
            ).scalar_one()
            assert not state.is_active
            first_commits.append(copied.id)

    monkeypatch.setattr(skill_import, "commit_skill_import", observe_first_commit)
    receipt = await capability_flow.send_capability(sender.id, preview.id, preview.digest)
    assert receipt.status is TransferStatus.INSTALLED
    assert len(first_commits) == 1
    async with sessions() as db:
        copy = (await db.execute(select(Skill).where(Skill.owner_id == recipient.id))).scalar_one()
        state = (
            await db.execute(select(UserSkillState).where(UserSkillState.skill_id == copy.id))
        ).scalar_one()
        assert not state.is_active
        assert copy.provenance == "peer"
        copy_id = copy.id
        state.is_active = True
    retained = tmp_path / "users" / str(recipient.id) / skill.name / "SKILL.md"
    retained.write_text("recipient edited", encoding="utf-8")
    again = await capability_flow.send_capability(sender.id, preview.id, preview.digest)
    assert again.status is TransferStatus.INSTALLED
    assert retained.read_text(encoding="utf-8") == "recipient edited"
    async with sessions() as db:
        assert (
            await db.execute(select(Skill.id).where(Skill.owner_id == recipient.id))
        ).scalar_one() == copy_id
        assert (
            await db.execute(
                select(UserSkillState.is_active).where(UserSkillState.skill_id == copy_id)
            )
        ).scalar_one()


@pytest.mark.parametrize(
    "interruption",
    [
        "none",
        "lost_ack",
        "lost_ack_root_edit",
        "server_failure",
        "recipient_delete",
        "source_edit",
    ],
)
async def test_plugin_retains_sanitized_files_and_first_components_are_disabled(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption: str,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, autoflush=False)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            yield db
            await db.commit()

    async def validated(url: str) -> ValidatedMCPEndpoint:
        return ValidatedMCPEndpoint(url)

    monkeypatch.setattr(capability_flow, "get_db_context", sessions)
    monkeypatch.setattr(capability_flow, "validate_install_endpoint", validated)
    for flag in ("peers_enabled", "skills_enabled", "plugins_enabled", "mcp_enabled"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    monkeypatch.setattr(settings, "skills_system_path", str(tmp_path / "system"))
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    manifest = {
        "$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID,
        "name": "shared-plugin",
        "description": "Useful package",
    }
    async with sessions() as db:
        sender, recipient = UserFactory.create(), UserFactory.create()
        db.add_all([sender, recipient])
        await db.flush()
        committed_user_ids.extend([sender.id, recipient.id])
        first, second = canonical_pair(sender.id, recipient.id)
        pair = PeerConnection(
            user_a_id=first,
            user_b_id=second,
            requested_by_id=sender.id,
            status="accepted",
        )
        plugin = UserPlugin(
            user_id=sender.id,
            name="shared-plugin",
            manifest=manifest,
            spec_version="1.0.0",
        )
        db.add_all([pair, plugin])
        await db.flush()
        db.add(
            Skill(
                name="example-skill",
                description="Current source",
                owner_id=sender.id,
                is_system=False,
                provenance="plugin",
                plugin_id=plugin.id,
            )
        )
        db.add(
            UserMCPServer(
                user_id=sender.id,
                name="shared-plugin:remote",
                plugin_id=plugin.id,
                url="https://live.example.test/api",
                auth_type="bearer",
                credentials_encrypted=encrypt_data(json.dumps({"token": "sender-secret-token"})),
                hitl_required=False,
                domain_description="Current endpoint",
            )
        )
        request = CapabilityPreviewRequest(
            connection_id=pair.id,
            kind=CapabilityKind.PLUGIN,
            source_id=plugin.id,
            idempotency_key=uuid4(),
        )
    root = tmp_path / "plugins" / str(sender.id) / plugin.name
    (root / "skills" / "example").mkdir(parents=True)
    (root / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "skills" / "example" / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: Useful instructions\n---\nInstructions",
        encoding="utf-8",
    )
    live_skill = tmp_path / "skills" / str(sender.id) / "example-skill"
    live_skill.mkdir(parents=True)
    (live_skill / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: Current source\n---\nCurrent instructions",
        encoding="utf-8",
    )
    (root / "mcp.json").write_text(
        json.dumps(
            {
                "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
                "mcpServers": {
                    "remote": {
                        "type": "streamable-http",
                        "url": "https://mcp.example.test/api",
                        "headers": {"Authorization": "Bearer sender-secret-token"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    config_reads: list[UUID] = []
    original_config = capability_sources._mcp_config

    def observe_config(db: AsyncSession, server: UserMCPServer) -> PortableMCPConfig:
        config_reads.append(server.id)
        return original_config(db, server)

    monkeypatch.setattr(capability_sources, "_mcp_config", observe_config)
    preview = await capability_flow.preview_capability(sender.id, request)
    async with sessions() as db:
        initial = await db.get(PeerCapabilityTransfer, preview.id)
        assert initial is not None
        preview_expires_at = initial.expires_at
    original_commit = skill_import.commit_skill_import
    commits: list[UUID] = []

    async def observe_first_commit(session: AsyncSession) -> None:
        await original_commit(session)
        async with sessions() as observer:
            copied = (
                await observer.execute(select(Skill).where(Skill.owner_id == recipient.id))
            ).scalar_one()
            assert not (
                await observer.execute(
                    select(UserSkillState.is_active).where(UserSkillState.skill_id == copied.id)
                )
            ).scalar_one()
            commits.append(copied.id)
            receipt = await observer.get(PeerCapabilityTransfer, preview.id)
            assert receipt is not None and receipt.transferred_at is not None
        if interruption in {"lost_ack", "lost_ack_root_edit"}:
            raise SkillImportCompletionUnknown("Simulated lost acknowledgement")

    monkeypatch.setattr(skill_import, "commit_skill_import", observe_first_commit)
    original_create = UserMCPServerService.create_server

    async def fail_server(*args: object, **kwargs: object) -> None:
        raise ValidationError("Simulated admission failure")

    if interruption in {"server_failure", "recipient_delete", "source_edit"}:
        monkeypatch.setattr(UserMCPServerService, "create_server", fail_server)
    result = await capability_flow.send_capability(sender.id, preview.id, preview.digest)
    assert len(commits) == 1
    assert len(config_reads) == 2  # One preview observation and one confirmation observation.
    assert SkillsCache.get_exact("example-skill", str(recipient.id)) is not None
    if interruption != "none":
        assert result.status is TransferStatus.PARTIAL
        if interruption == "source_edit":
            # Publication confirms immutable bytes. A later sender edit must
            # neither replace that snapshot nor prevent its missing components.
            (root / "plugin.json").write_text("changed after publication", encoding="utf-8")
            async with sessions() as db:
                receipt = await db.get(PeerCapabilityTransfer, preview.id)
                assert receipt is not None
                assert receipt.expires_at > preview_expires_at
        monkeypatch.setattr(skill_import, "commit_skill_import", original_commit)
        monkeypatch.setattr(UserMCPServerService, "create_server", original_create)
        copied_path = tmp_path / "skills" / str(recipient.id) / "example-skill" / "SKILL.md"
        copied_path.write_text("recipient edited", encoding="utf-8")
        async with sessions() as db:
            copied = await db.get(Skill, commits[0])
            assert copied is not None
            if interruption == "recipient_delete":
                await db.delete(copied)
            else:
                state = (
                    await db.execute(
                        select(UserSkillState).where(UserSkillState.skill_id == copied.id)
                    )
                ).scalar_one()
                state.is_active = True
        plugin_file = tmp_path / "plugins" / str(recipient.id) / plugin.name / "plugin.json"
        if plugin_file.exists():
            plugin_file.write_text("recipient plugin metadata edit", encoding="utf-8")
        if interruption == "lost_ack_root_edit":
            async with sessions() as db:
                edited = (
                    await db.execute(select(UserPlugin).where(UserPlugin.user_id == recipient.id))
                ).scalar_one()
                edited.manifest = {
                    **edited.manifest,
                    "description": "Recipient changed plugin",
                }
            from src.core.exceptions import BaseAPIException

            with pytest.raises(BaseAPIException):
                await capability_flow.send_capability(sender.id, preview.id, preview.digest)
            async with sessions() as db:
                edited = (
                    await db.execute(select(UserPlugin).where(UserPlugin.user_id == recipient.id))
                ).scalar_one()
                assert edited.manifest["description"] == "Recipient changed plugin"
                assert not list(
                    await db.scalars(
                        select(UserMCPServer.id).where(UserMCPServer.user_id == recipient.id)
                    )
                )
            return
        result = await capability_flow.send_capability(sender.id, preview.id, preview.digest)
        assert copied_path.read_text(encoding="utf-8") == "recipient edited"
        if interruption != "lost_ack":
            assert plugin_file.read_text(encoding="utf-8") == "recipient plugin metadata edit"
    assert result.status is TransferStatus.INSTALLED
    async with sessions() as db:
        skill = (
            await db.execute(select(Skill).where(Skill.owner_id == recipient.id))
        ).scalar_one_or_none()
        if interruption == "recipient_delete":
            assert skill is None
        else:
            assert skill is not None and skill.peer_authored and skill.provenance == "plugin"
            active = (
                await db.execute(
                    select(UserSkillState.is_active).where(UserSkillState.skill_id == skill.id)
                )
            ).scalar_one()
            assert active == (interruption != "none")
        server = (
            await db.execute(select(UserMCPServer).where(UserMCPServer.user_id == recipient.id))
        ).scalar_one()
        assert not server.is_enabled and server.credentials_encrypted is None
        assert server.auth_type == "bearer" and server.status == "auth_required"
        assert server.url == "https://live.example.test/api"
    retained = tmp_path / "plugins" / str(recipient.id) / plugin.name / "mcp.json"
    assert retained.is_file()
    assert "sender-secret-token" not in retained.read_text(encoding="utf-8")
    assert "Authorization" not in retained.read_text(encoding="utf-8")
