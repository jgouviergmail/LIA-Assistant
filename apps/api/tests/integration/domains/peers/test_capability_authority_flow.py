"""Adversarial admission tests exercise actual SQL and filesystem effects."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.account_export import builder as account_export
from src.domains.conversations.models import ConversationMessage
from src.domains.peers import capability_flow, capability_notifications
from src.domains.peers.capability_authority import capability_authority
from src.domains.peers.capability_contracts import (
    CapabilityKind,
    CapabilityPreviewRequest,
    PackageSnapshot,
    PortableFile,
    TransferStatus,
)
from src.domains.peers.capability_install import TransferInstallation
from src.domains.peers.capability_models import PeerCapabilityTransfer
from src.domains.peers.models import PeerBlock, PeerConnection, canonical_pair
from src.domains.skills.models import Skill
from src.domains.user_mcp.installation import ValidatedMCPEndpoint
from src.domains.user_mcp.models import UserMCPServer
from src.infrastructure.proactive.notification import NotificationDispatcher
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def test_recipient_export_does_not_disclose_an_unconfirmed_preview(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account_export, "get_db_context", world.sessions)
    preview = await capability_flow.preview_capability(world.sender, world.request)
    sender_rows = await account_export._fetch_table_rows("peer_capability_transfers", world.sender)
    assert len(sender_rows) == 1 and "snapshot" not in sender_rows[0]
    assert (
        await account_export._fetch_table_rows("peer_capability_transfers", world.recipient) == []
    )
    await capability_flow.send_capability(world.sender, preview.id, preview.digest)
    assert (
        len(await account_export._fetch_table_rows("peer_capability_transfers", world.recipient))
        == 1
    )


@dataclass(frozen=True)
class World:
    sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]]
    sender: UUID
    recipient: UUID
    request: CapabilityPreviewRequest
    manifest: Path


@pytest_asyncio.fixture
async def world(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> World:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            yield db
            await db.commit()

    monkeypatch.setattr(capability_flow, "get_db_context", sessions)
    for flag in ("peers_enabled", "skills_enabled", "plugins_enabled", "mcp_enabled"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
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
            name="authority-example",
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
    root = tmp_path / "skills" / str(sender.id) / skill.name
    root.mkdir(parents=True)
    manifest = root / "SKILL.md"
    manifest.write_text(
        "---\nname: authority-example\ndescription: Useful instructions\n---\nInstructions",
        encoding="utf-8",
    )
    return World(sessions, sender.id, recipient.id, request, manifest)


@pytest.mark.parametrize(
    "revocation",
    [
        "removed",
        "block",
        "source_deleted",
        "disabled_feature",
        "foreign_actor",
        "changed_digest",
        "changed_source",
    ],
)
async def test_revoked_or_stale_confirmation_creates_no_copy(
    world: World, revocation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    preview = await capability_flow.preview_capability(world.sender, world.request)
    actor, digest = world.sender, preview.digest
    async with world.sessions() as db:
        if revocation == "removed":
            pair = await db.get(PeerConnection, world.request.connection_id)
            assert pair is not None
            pair.status = "removed"
        elif revocation == "block":
            db.add(PeerBlock(blocker_id=world.recipient, blocked_id=world.sender))
        elif revocation == "source_deleted":
            skill = await db.get(Skill, world.request.source_id)
            assert skill is not None
            await db.delete(skill)
    if revocation == "disabled_feature":
        monkeypatch.setattr(settings, "skills_enabled", False)
    elif revocation == "foreign_actor":
        actor = world.recipient
    elif revocation == "changed_digest":
        digest = "0" * 64
    elif revocation == "changed_source":
        world.manifest.write_text(
            world.manifest.read_text(encoding="utf-8") + " changed", encoding="utf-8"
        )
    with pytest.raises(BaseAPIException):
        await capability_flow.send_capability(actor, preview.id, digest)
    async with world.sessions() as db:
        assert not list(await db.scalars(select(Skill.id).where(Skill.owner_id == world.recipient)))


async def test_pair_quota_serializes_concurrent_previews(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "peers_capability_pair_daily_limit", 1)
    second = world.request.model_copy(update={"idempotency_key": uuid4()})
    results = await asyncio.gather(
        capability_flow.preview_capability(world.sender, world.request),
        capability_flow.preview_capability(world.sender, second),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert any(
        isinstance(result, BaseAPIException) and result.status_code == 429 for result in results
    )


async def test_stored_snapshot_bytes_must_still_match_the_confirmed_digest(
    world: World,
) -> None:
    preview = await capability_flow.preview_capability(world.sender, world.request)
    async with world.sessions() as db:
        receipt = await db.get(PeerCapabilityTransfer, preview.id)
        assert receipt is not None
        package = PackageSnapshot.model_validate(receipt.snapshot)
        changed = package.model_copy(
            update={
                "files": (
                    PortableFile(
                        path="SKILL.md",
                        content=package.files[0].content + b"\nChanged bytes",
                    ),
                )
            }
        )
        receipt.snapshot = changed.model_dump(mode="json")
    with pytest.raises(BaseAPIException):
        await capability_flow.send_capability(world.sender, preview.id, preview.digest)


async def test_plugin_only_requires_mcp_feature_when_its_snapshot_contains_mcp(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mcp_enabled", False)
    async with world.sessions() as db:
        assert (
            await capability_authority(
                db, world.sender, world.request.connection_id, CapabilityKind.PLUGIN
            )
            == world.recipient
        )
        with pytest.raises(BaseAPIException):
            await capability_authority(
                db,
                world.sender,
                world.request.connection_id,
                CapabilityKind.PLUGIN,
                mcp_required=True,
            )


async def test_existing_recipient_skill_is_never_overwritten(world: World) -> None:
    async with world.sessions() as db:
        db.add(
            Skill(
                name="authority-example",
                description="Recipient version",
                owner_id=world.recipient,
                is_system=False,
                provenance="authored",
            )
        )
    preview = await capability_flow.preview_capability(world.sender, world.request)
    with pytest.raises(BaseAPIException):
        await capability_flow.send_capability(world.sender, preview.id, preview.digest)
    async with world.sessions() as db:
        existing = (
            await db.execute(select(Skill).where(Skill.owner_id == world.recipient))
        ).scalar_one()
        assert existing.description == "Recipient version"


@pytest_asyncio.fixture
async def system_skill(world: World) -> AsyncIterator[Skill]:
    """A committed system row has no owner whose erasure could clean it up."""
    async with world.sessions() as db:
        system = Skill(
            name="system-example",
            description="System source",
            owner_id=None,
            is_system=True,
            provenance="system",
            admin_enabled=True,
        )
        db.add(system)
        await db.flush()
    try:
        yield system
    finally:
        async with world.sessions() as db:
            await db.execute(delete(Skill).where(Skill.id == system.id))


async def test_system_skill_export_cannot_shadow_the_recipients_system_skill(
    world: World, system_skill: Skill
) -> None:
    request = world.request.model_copy(update={"source_id": system_skill.id})
    manifest = Path(settings.skills_system_path) / "system-example" / "SKILL.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "---\nname: system-example\ndescription: System source\n---\nInstructions",
        encoding="utf-8",
    )
    preview = await capability_flow.preview_capability(world.sender, request)
    with pytest.raises(BaseAPIException):
        await capability_flow.send_capability(world.sender, preview.id, preview.digest)
    async with world.sessions() as db:
        assert not list(await db.scalars(select(Skill.id).where(Skill.owner_id == world.recipient)))
        existing = await db.get(Skill, system_skill.id)
        assert existing is not None and existing.admin_enabled
    assert manifest.read_text(encoding="utf-8").endswith("Instructions")


@pytest.mark.parametrize("auth_type", ["api_key", "bearer", "oauth2", "none"])
async def test_mcp_dns_occurs_without_a_database_checkout_and_no_credentials_are_copied(
    world: World,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    auth_type: str,
) -> None:
    async def validated(url: str) -> ValidatedMCPEndpoint:
        async with world.sessions() as observer:
            assert (
                await observer.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction'"
                    )
                )
                == 0
            )
        return ValidatedMCPEndpoint(url)

    monkeypatch.setattr(capability_flow, "validate_install_endpoint", validated)
    async with world.sessions() as db:
        source = UserMCPServer(
            user_id=world.sender,
            name="Personal MCP",
            url="https://mcp.example.test/api",
            auth_type=auth_type,
            required_header_name="X-Custom-Key" if auth_type == "api_key" else None,
            oauth_metadata=(
                {
                    "requested_scopes": "read:items",
                    "authorization_endpoint": "https://sender.example.test/authorize",
                }
                if auth_type == "oauth2"
                else None
            ),
            domain_description="Useful endpoint",
        )
        db.add(source)
        await db.flush()
        request = world.request.model_copy(
            update={"kind": CapabilityKind.MCP, "source_id": source.id}
        )
    preview = await capability_flow.preview_capability(world.sender, request)
    receipt = await capability_flow.send_capability(world.sender, preview.id, preview.digest)
    assert receipt.status is TransferStatus.INSTALLED
    async with world.sessions() as db:
        copy = (
            await db.execute(select(UserMCPServer).where(UserMCPServer.user_id == world.recipient))
        ).scalar_one()
        assert not copy.is_enabled and copy.status == (
            "inactive" if auth_type == "none" else "auth_required"
        )
        assert copy.credentials_encrypted is None and copy.discovered_tools_cache is None
        assert copy.required_header_name == ("X-Custom-Key" if auth_type == "api_key" else None)
        assert copy.hitl_required is None
        assert copy.oauth_metadata == (
            {"requested_scopes": "read:items"} if auth_type == "oauth2" else None
        )


@pytest.mark.parametrize("fail_first", [False, True])
async def test_notification_archive_and_outbox_ack_are_one_commit(
    world: World, monkeypatch: pytest.MonkeyPatch, fail_first: bool
) -> None:
    monkeypatch.setattr(capability_notifications, "get_db_context", world.sessions)
    publish = AsyncMock()
    monkeypatch.setattr(NotificationDispatcher, "_publish_sse", publish)
    preview = await capability_flow.preview_capability(world.sender, world.request)
    await capability_flow.send_capability(world.sender, preview.id, preview.digest)
    original_archive = NotificationDispatcher._archive_message
    if fail_first:

        async def fail_archive(*args: object, **kwargs: object) -> None:
            await original_archive(*args, **kwargs)
            raise RuntimeError("Simulated precommit failure")

        monkeypatch.setattr(NotificationDispatcher, "_archive_message", fail_archive)
        await capability_notifications.deliver_capability_receipt(preview.id)
        async with world.sessions() as db:
            receipt = await db.get(PeerCapabilityTransfer, preview.id)
            assert receipt is not None and not receipt.notification_sent
            assert not list(
                await db.scalars(
                    select(ConversationMessage).where(
                        ConversationMessage.message_metadata["target_id"].astext == str(preview.id)
                    )
                )
            )
        monkeypatch.setattr(NotificationDispatcher, "_archive_message", original_archive)
    await capability_notifications.deliver_capability_receipt(preview.id)
    async with world.sessions() as db:
        receipt = await db.get(PeerCapabilityTransfer, preview.id)
        assert receipt is not None and receipt.notification_sent
        messages = list(
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.message_metadata["target_id"].astext == str(preview.id)
                )
            )
        )
        assert len(messages) == 1
    await capability_notifications.deliver_capability_receipt(preview.id)
    publish.assert_awaited_once()


async def test_cancel_before_skill_commit_rolls_back_disk_and_can_resume(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    preview = await capability_flow.preview_capability(world.sender, world.request)
    original = TransferInstallation.check
    calls = 0

    async def cancel_at_commit(self: TransferInstallation, db: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        await original(self, db)
        if calls == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(TransferInstallation, "check", cancel_at_commit)
    with pytest.raises(asyncio.CancelledError):
        await capability_flow.send_capability(world.sender, preview.id, preview.digest)
    async with world.sessions() as db:
        assert not list(await db.scalars(select(Skill.id).where(Skill.owner_id == world.recipient)))
        receipt = await db.get(PeerCapabilityTransfer, preview.id)
        assert receipt is not None
        receipt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    copied = (
        Path(settings.skills_users_path) / str(world.recipient) / "authority-example" / "SKILL.md"
    )
    assert not copied.exists()
    monkeypatch.setattr(TransferInstallation, "check", original)
    result = await capability_flow.send_capability(world.sender, preview.id, preview.digest)
    assert result.status is TransferStatus.INSTALLED and copied.is_file()


@pytest.mark.parametrize("peers_enabled", [True, False])
async def test_expired_preview_loses_bytes_and_cannot_be_published(
    world: World, monkeypatch: pytest.MonkeyPatch, peers_enabled: bool
) -> None:
    monkeypatch.setattr(capability_notifications, "get_db_context", world.sessions)
    preview = await capability_flow.preview_capability(world.sender, world.request)
    async with world.sessions() as db:
        receipt = await db.get(PeerCapabilityTransfer, preview.id)
        assert receipt is not None
        receipt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(settings, "peers_enabled", peers_enabled)
    await capability_notifications.maintain_capability_transfers()
    async with world.sessions() as db:
        receipt = await db.get(PeerCapabilityTransfer, preview.id)
        assert receipt is not None and receipt.snapshot is None and receipt.status == "cancelled"
        assert receipt.payload_bytes > 0
    with pytest.raises(BaseAPIException):
        await capability_flow.send_capability(world.sender, preview.id, preview.digest)
