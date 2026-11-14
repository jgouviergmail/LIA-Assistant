"""Account removal cannot forget a retired runtime or an unfinished file writer."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.conversation_execution import ExecutionKind, RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.exceptions import BaseAPIException
from src.domains.attachments.models import Attachment, AttachmentStatus
from src.domains.auth import service as auth_service
from src.domains.conversations import cleanup_port
from src.domains.conversations.cleanup_contracts import CleanupState
from src.domains.conversations.cleanup_models import ConversationOperation
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import Conversation
from src.domains.conversations.reservation_models import ConversationReservationWork
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.skills.lifecycle_lock import lock_skill_owner
from src.domains.users import account_cleanup_port
from src.domains.users.account_deletion_service import AccountDeletionService
from src.domains.users.models import User
from src.domains.users.repository import UserRepository
from src.domains.users.schemas import UserActivationUpdate
from src.domains.users.service import UserService
from src.infrastructure.account_cleanup_runtime import NativeAccountCleanup
from src.infrastructure.scheduler.unverified_account_cleanup import purge_unverified_account
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def test_repeated_verification_releases_owner_before_blacklisting_token(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.email = f"owner-{owner}@example.com"
        email = user.email
        await db.commit()

        async def token(_token: str, _kind: str) -> tuple[dict[str, str], str]:
            return {"sub": email}, "fictional-jti"

        async def blacklist(_jti: str, _kind: str) -> None:
            assert not db.in_transaction(), "Owner lock spans external token blacklisting"

        monkeypatch.setattr(auth_service, "verify_single_use_token", token)
        monkeypatch.setattr(auth_service, "mark_token_used", blacklist)
        response = await auth_service.AuthService(db).verify_email("fictional-token")
        assert response.id == owner


async def test_legacy_hard_delete_can_find_the_already_purged_inactive_account(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        await db.execute(
            update(User)
            .where(User.id == owner)
            .values(
                is_active=False, deleted_at=datetime.now(UTC), deletion_started_at=datetime.now(UTC)
            )
        )
        await db.commit()
        await UserService(db).delete_user(owner, hard_delete=True)
        assert await db.get(User, owner) is None


class ObservedCleanup:
    """Observe the real SQL orchestration at its separately tested native I/O seam."""

    def __init__(self, db: AsyncSession, *, succeeds: bool = True) -> None:
        self.db = db
        self.succeeds = succeeds
        self.runtimes: list[UUID] = []

    async def prepare_owner(self, owner: UUID) -> None:
        """No Live record exists in this cleanup fixture."""

    async def purge_checkpoint(self, target: ConversationRef) -> bool:
        assert not self.db.in_transaction(), "Account transaction spans native I/O"
        self.runtimes.append(target.runtime_id)
        return self.succeeds

    async def purge_tool_context(self, target: ConversationRef) -> bool:
        assert not self.db.in_transaction()
        return self.succeeds

    async def purge_pending(self, target: ConversationRef) -> bool:
        assert not self.db.in_transaction()
        return self.succeeds


@pytest.fixture
def external_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No vendor or existing account directory is touched by these SQL tests."""
    monkeypatch.setattr(account_cleanup_port, "_cleanup", NativeAccountCleanup())
    for name in (
        "attachments_storage_path",
        "rag_spaces_storage_path",
        "skills_users_path",
        "plugins_users_path",
        "meetings_storage_path",
    ):
        monkeypatch.setattr(settings, name, str(tmp_path / name))

    async def no_network(self: AccountDeletionService, owner: UUID) -> None:
        assert not self.db.in_transaction(), "Account transaction spans network I/O"

    async def empty_store(self: AccountDeletionService, owner: UUID) -> int:
        assert not self.db.in_transaction()
        return 0

    async def after_commit(self: AccountDeletionService, owner: UUID) -> None:
        assert not self.db.in_transaction()
        async with AsyncSession(self.db.bind) as independent:
            user = await independent.get(User, owner)
            assert user is not None and user.is_deleted, "Cache invalidated before final commit"

    for name in (
        "_revoke_all_oauth_tokens",
        "_disconnect_mcp_pool",
        "_invalidate_redis_sessions",
        "_cleanup_world_presence",
        "_cleanup_redis_caches",
        "_invalidate_usage_limit_cache",
    ):
        monkeypatch.setattr(AccountDeletionService, name, no_network)
    monkeypatch.setattr(AccountDeletionService, "_purge_langgraph_store", empty_store)
    monkeypatch.setattr(AccountDeletionService, "_invalidate_usage_limit_cache", after_commit)


async def _account(
    engine: AsyncEngine, identities: list[UUID], *, count: int = 3
) -> tuple[UUID, list[UUID], list[UUID]]:
    owner = await commit_owner(engine, identities)
    ids = [owner, *(uuid4() for _ in range(count - 1))]
    runtimes = [owner, *(uuid4() for _ in range(count - 1))]
    async with AsyncSession(engine) as db:
        for index, (identity, runtime) in enumerate(zip(ids, runtimes, strict=True)):
            db.add(
                Conversation(
                    id=identity,
                    user_id=owner,
                    runtime_id=runtime,
                    revision=0,
                    kind=ConversationKind.MAIN if index == 0 else ConversationKind.SECONDARY,
                    title=f"Owned topic {index}",
                )
            )
        await db.commit()
    return owner, ids, runtimes


async def test_account_removal_cleans_main_annexes_and_previous_retired_runtime(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    external_cleanup: None,
) -> None:
    owner, ids, runtimes = await _account(async_engine, committed_user_ids)
    other, _, other_runtimes = await _account(async_engine, committed_user_ids, count=1)
    audio = Path(settings.meetings_storage_path) / str(owner) / str(uuid4()) / "audio.webm"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"fictional audio")
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        await ConversationLifecycle(db).request_reset(
            owner, ids[1], operation_id=uuid4(), expected_revision=0
        )
        annex = await db.get(Conversation, ids[1])
        assert annex is not None
        runtimes.append(annex.runtime_id)
        admitted = await ConversationExecutionRepository(db).admit(
            ConversationRef(owner, ids[2], ConversationKind.SECONDARY, 0, runtimes[2]),
            run_id=uuid4().hex,
            stream_id=uuid4().hex,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admitted, RunAdmission)
        reservations = ConversationReservationRepository(db)
        closing = await reservations.begin_closing(admitted, worker_id=uuid4())
        assert await reservations.finish(closing)
        await db.commit()
        user = await db.get(User, owner)
        assert user is not None
        user.is_active = False
        await db.commit()
        native = ObservedCleanup(db)
        monkeypatch.setattr(cleanup_port, "_runtime_cleanup", native)
        removed, _ = await AccountDeletionService(db).delete_account(owner, None)
        assert removed.is_deleted
        assert await db.get(ConversationReservationWork, closing.id) is None
        assert not audio.exists()
        assert set(native.runtimes) == set(runtimes)
        assert not set(native.runtimes).intersection(other_runtimes)
        operations = list(
            await db.scalars(
                select(ConversationOperation).where(ConversationOperation.user_id == owner)
            )
        )
        assert len(operations) == len(runtimes)
        assert all(row.state == CleanupState.SUCCEEDED for row in operations)
        assert await db.get(Conversation, other) is not None


async def test_failed_cleanup_keeps_account_recoverable_and_runtime_intent(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    external_cleanup: None,
) -> None:
    owner, ids, runtimes = await _account(async_engine, committed_user_ids, count=1)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.is_active = False
        await db.commit()
        monkeypatch.setattr(cleanup_port, "_runtime_cleanup", ObservedCleanup(db, succeeds=False))
        with pytest.raises(BaseAPIException) as caught:
            await AccountDeletionService(db).delete_account(owner, None)
        assert caught.value.status_code == 409
        await db.refresh(user)
        assert not user.is_deleted and not user.is_active
        operations = list(
            await db.scalars(
                select(ConversationOperation).where(ConversationOperation.user_id == owner)
            )
        )
        assert len(operations) == 1 and operations[0].runtime_id == runtimes[0]
        assert operations[0].state != CleanupState.SUCCEEDED
        assert await db.get(Conversation, ids[0]) is not None
        await db.commit()
        with pytest.raises(BaseAPIException) as activation:
            await UserService(db).update_user_activation(
                owner, UserActivationUpdate(is_active=True), uuid4()
            )
        assert activation.value.status_code == 409
        await db.rollback()
        with pytest.raises(IntegrityError):
            await db.execute(update(User).where(User.id == owner).values(is_active=True))
        await db.rollback()


@pytest.mark.parametrize("kind", [ExecutionKind.GRAPH, ExecutionKind.LIVE])
@pytest.mark.parametrize("unknown", [False, True])
async def test_account_cannot_erase_a_running_or_unknown_producer(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    kind: ExecutionKind,
    unknown: bool,
    monkeypatch: pytest.MonkeyPatch,
    external_cleanup: None,
) -> None:
    owner, ids, runtimes = await _account(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        target = ConversationRef(owner, ids[2], ConversationKind.SECONDARY, 0, runtimes[2])
        admission = await ConversationExecutionRepository(db).admit(
            target,
            run_id=str(uuid4()),
            stream_id=str(uuid4()),
            worker_id=uuid4(),
            kind=kind,
        )
        assert isinstance(admission, RunAdmission)
        if kind == ExecutionKind.LIVE:
            repo = ConversationReservationRepository(db)
            work = await repo.begin(admission, worker_id=uuid4(), purpose="request")
            if unknown:
                await repo.mark_unknown(work)
        elif unknown:
            await ConversationExecutionRepository(db).mark_recovering(admission)
        await db.commit()
        user = await db.get(User, owner)
        assert user is not None
        user.is_active = False
        await db.commit()
        monkeypatch.setattr(cleanup_port, "_runtime_cleanup", ObservedCleanup(db))
        with pytest.raises(BaseAPIException) as result:
            await AccountDeletionService(db).delete_account(owner, None)
        assert result.value.status_code == 409
        await db.refresh(user)
        with pytest.raises(BaseAPIException):
            await UserRepository(db).hard_delete(user)
        await db.rollback()
        assert await db.get(Conversation, target.id) is not None
        assert (
            await db.scalar(
                select(ConversationOperation.id).where(ConversationOperation.user_id == owner)
            )
            is None
        )


async def test_account_file_failure_survives_retry_and_blocks_hard_erasure(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    external_cleanup: None,
) -> None:
    owner, _, _ = await _account(async_engine, committed_user_ids, count=1)
    path = Path(settings.attachments_storage_path) / str(owner) / "owned.txt"
    path.parent.mkdir(parents=True)
    path.write_text("Retain until removal succeeds", encoding="utf-8")
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        file = Attachment(
            user_id=owner,
            original_filename="owned.txt",
            stored_filename="owned.txt",
            mime_type="text/plain",
            file_size=28,
            content_type="document",
            file_path=f"{owner}/owned.txt",
            status=AttachmentStatus.READY,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(file)
        user = await db.get(User, owner)
        assert user is not None
        user.is_active = False
        await db.commit()
        file_id = file.id
        monkeypatch.setattr(cleanup_port, "_runtime_cleanup", ObservedCleanup(db))

        def refuse_unlink(self: Path, missing_ok: bool = False) -> None:
            raise PermissionError("Injected removal failure")

        with monkeypatch.context() as failure:
            failure.setattr(Path, "unlink", refuse_unlink)
            with pytest.raises(BaseAPIException):
                await AccountDeletionService(db).delete_account(owner, None)
        await db.refresh(file)
        assert file.status == AttachmentStatus.DELETING and path.exists()
        with pytest.raises(BaseAPIException):
            await UserRepository(db).hard_delete(user)
        await db.rollback()
        removed, counts = await AccountDeletionService(db).delete_account(owner, None)
        assert removed.is_deleted and counts["attachment_files"] == 1
        assert not path.exists()
        assert await db.get(Attachment, file_id) is None


async def test_unverified_sweep_uses_runtime_cleanup_instead_of_blind_cascade(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    external_cleanup: None,
) -> None:
    owner, _, runtimes = await _account(async_engine, committed_user_ids)
    cutoff = datetime.now(UTC) - timedelta(days=1)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.is_active, user.is_verified = False, False
        user.created_at = cutoff - timedelta(days=1)
        await db.commit()
        native = ObservedCleanup(db)
        monkeypatch.setattr(cleanup_port, "_runtime_cleanup", native)
        assert await purge_unverified_account(db, owner, cutoff)
        assert set(native.runtimes) == set(runtimes)
        assert await db.get(User, owner, populate_existing=True) is None


async def test_inactive_owner_cannot_publish_a_late_skill_directory(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        await db.execute(update(User).where(User.id == owner).values(is_active=False))
        await db.commit()
        with pytest.raises(BaseAPIException) as refused:
            await lock_skill_owner(db, owner)
        assert refused.value.status_code == 403
