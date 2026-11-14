"""Accepted discussion file usage and orphan decisions on real PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionRevoked
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.exceptions import BaseAPIException
from src.domains.agents.api import attachments_injection
from src.domains.agents.api.archive_first import archive_user_message_first, turn_attachment_meta
from src.domains.agents.models import create_initial_state
from src.domains.attachments.attachable_queries import build_attachable_statement
from src.domains.attachments.card_lifetimes import current_lifetimes
from src.domains.attachments.conversation_usage import ConversationAttachmentUsageRepository
from src.domains.attachments.file_repository import AttachmentFileRepository
from src.domains.attachments.keep import keep_generated, keep_usage
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
    ConversationAttachmentUsage,
)
from src.domains.attachments.repository import AttachmentRepository
from src.domains.attachments.service import AttachmentService
from src.domains.conversations.models import Conversation
from src.domains.conversations.service import ConversationService
from tests.fixtures.factories import UserFactory
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def test_retired_kept_files_release_the_visible_keep_allowance(
    async_session: AsyncSession,
) -> None:
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    kept = await _attachment(
        async_session, owner.id, origin=AttachmentOrigin.GENERATED_IMAGE, expires_at=None
    )
    before = await AttachmentRepository(async_session).kept_totals()
    await AttachmentFileRepository(async_session).retire_owned(
        owner.id, reason="user_deleted", ids=[kept.id]
    )
    usage = await keep_usage(async_session, owner.id)
    assert (usage.kept_files, usage.kept_bytes) == (0, 0)
    after = await AttachmentRepository(async_session).kept_totals()
    assert after == (before[0] - 1, before[1] - kept.file_size)
    assert await async_session.get(Attachment, kept.id) is not None


async def _targets(db: AsyncSession, owner_id: UUID) -> tuple[ConversationRef, ConversationRef]:
    """Two discussions of one owner, with distinct rotated working identities."""
    targets = (
        ConversationRef(owner_id, owner_id, ConversationKind.MAIN, 2, uuid4()),
        ConversationRef(owner_id, uuid4(), ConversationKind.SECONDARY, 2, uuid4()),
    )
    db.add_all(
        [
            Conversation(
                id=target.id,
                user_id=owner_id,
                kind=target.kind,
                revision=target.revision,
                runtime_id=target.runtime_id,
                title="Fixture discussion",
            )
            for target in targets
        ]
    )
    await db.flush()
    return targets


async def _attachment(
    db: AsyncSession,
    owner_id: UUID,
    *,
    origin: AttachmentOrigin = AttachmentOrigin.UPLOAD,
    expires_at: datetime | None,
    status: str = AttachmentStatus.READY,
) -> Attachment:
    """Persist a file with an explicit lifecycle, never inferred from its name."""
    file_id = uuid4()
    row = Attachment(
        id=file_id,
        user_id=owner_id,
        original_filename="Fixture.png",
        stored_filename=f"{file_id}.png",
        file_path=f"{owner_id}/{file_id}.png",
        mime_type="image/png",
        file_size=12,
        content_type=AttachmentContentType.IMAGE,
        origin=origin.value,
        status=status,
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()
    return row


async def test_expired_upload_is_not_accepted_before_the_periodic_sweep(
    async_session: AsyncSession,
) -> None:
    """READY alone is not evidence that a file remains available for a new turn."""
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    expired = await _attachment(
        async_session, owner.id, expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )

    with pytest.raises(BaseAPIException) as refused:
        await AttachmentService(async_session).get_batch([expired.id], owner.id)

    assert refused.value.status_code == 404


async def test_kept_generated_file_and_unexpired_upload_remain_available(
    async_session: AsyncSession,
) -> None:
    """No upload extension and no accidental expiry of an explicitly kept asset."""
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    deadline = datetime.now(UTC) + timedelta(hours=1)
    upload = await _attachment(async_session, owner.id, expires_at=deadline)
    kept = await _attachment(
        async_session, owner.id, origin=AttachmentOrigin.GENERATED_IMAGE, expires_at=None
    )

    rows = await AttachmentService(async_session).get_batch([upload.id, kept.id], owner.id)

    assert {row.id for row in rows} == {upload.id, kept.id}
    assert upload.expires_at == deadline
    assert kept.expires_at is None


async def test_accepted_files_keep_the_persons_order_not_the_lock_order(
    async_session: AsyncSession,
) -> None:
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    main, _ = await _targets(async_session, owner.id)
    deadline = datetime.now(UTC) + timedelta(hours=1)
    files = [await _attachment(async_session, owner.id, expires_at=deadline) for _ in range(3)]
    wanted = sorted((row.id for row in files), reverse=True)
    rows = await ConversationAttachmentUsageRepository(async_session).accept_batch(
        owner.id, [*wanted, wanted[0]], main
    )
    assert [row.id for row in rows] == wanted


async def test_idempotent_keep_holds_its_file_until_the_answer_commits(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Already-kept is still an assertion: a competing delete cannot pass that read."""
    owner = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as setup:
        row = await _attachment(
            setup, owner, origin=AttachmentOrigin.GENERATED_IMAGE, expires_at=None
        )
        identity = row.id
        await setup.commit()
    async with AsyncSession(async_engine) as keeper, AsyncSession(async_engine) as deleting:
        ready, release = asyncio.Event(), asyncio.Event()
        real_commit = keeper.commit
        blocker_pid = await keeper.scalar(text("SELECT pg_backend_pid()"))

        async def pause_commit() -> None:
            ready.set()
            await release.wait()
            await real_commit()

        monkeypatch.setattr(keeper, "commit", pause_commit)
        keeping = asyncio.create_task(keep_generated(keeper, owner, [identity], language="fr"))
        await asyncio.wait_for(ready.wait(), timeout=5)

        async def remove() -> None:
            await AttachmentFileRepository(deleting).retire_owned(
                owner, ids=[identity], reason="user_deleted"
            )
            await deleting.commit()

        removal = asyncio.create_task(remove())
        try:
            async with asyncio.timeout(5):
                while True:
                    async with async_engine.connect() as observer:
                        blocked = await observer.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid))"
                            ),
                            {"pid": blocker_pid},
                        )
                    if blocked:
                        break
                    assert (
                        not removal.done()
                    ), "Deletion passed the idempotent keep before its answer committed"
                    await asyncio.sleep(0.01)
            release.set()
            assert await keeping == ([identity], [])
            await removal
        finally:
            release.set()
            await asyncio.gather(keeping, removal, return_exceptions=True)


@pytest.mark.parametrize("surface", ["card", "mail"])
async def test_retired_and_unpublished_files_are_absent_from_every_readable_surface(
    async_session: AsyncSession,
    surface: str,
) -> None:
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    ready, pending, retired = [
        await _attachment(
            async_session, owner.id, origin=AttachmentOrigin.GENERATED_IMAGE, expires_at=None
        )
        for _ in range(3)
    ]
    pending.status = AttachmentStatus.UPLOADED
    retired.status, retired.deletion_reason = AttachmentStatus.DELETING, "user_deleted"
    await async_session.flush()
    ids = {ready.id, pending.id, retired.id}
    if surface == "card":
        visible = set(await current_lifetimes(async_session, owner.id, ids))
    else:
        visible = {
            row.id
            for row in await async_session.scalars(
                build_attachable_statement(owner.id, now=datetime.now(UTC), ids=list(ids))
            )
        }
    assert visible == {ready.id}


async def test_releasing_one_discussion_keeps_shared_generated_and_unattributed_files(
    async_session: AsyncSession,
) -> None:
    """Usage, origin and deadline are independent facts; a source FK proves no usage."""
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    main, annex = await _targets(async_session, owner.id)
    deadline = datetime.now(UTC) + timedelta(hours=1)
    exclusive, shared, draft, unknown = [
        await _attachment(async_session, owner.id, expires_at=deadline) for _ in range(4)
    ]
    generated = await _attachment(
        async_session, owner.id, origin=AttachmentOrigin.GENERATED_DOCUMENT, expires_at=None
    )
    # Generation provenance is deliberately NOT the attachment-usage relation.
    unknown.conversation_id = main.id
    repo = ConversationAttachmentUsageRepository(async_session)
    main_ids = [exclusive.id, shared.id, generated.id, shared.id]
    accepted = await repo.accept_batch(owner.id, main_ids, main)
    await repo.accept_batch(owner.id, [shared.id], annex)
    await repo.accept_batch(owner.id, [shared.id], annex)

    assert {row.id for row in accepted} == set(main_ids)
    assert await async_session.scalar(select(func.count(ConversationAttachmentUsage.id))) == 4
    assert shared.expires_at == deadline
    removed = await repo.release_conversation_usages(main)
    assert removed == (exclusive.id,)
    await async_session.refresh(exclusive)
    assert exclusive.status == AttachmentStatus.DELETING
    for row in (shared, draft, unknown, generated):
        await async_session.refresh(row)
        assert row.status == AttachmentStatus.READY
    assert generated.expires_at is None

    assert await repo.release_conversation_usages(main) == ()
    assert await repo.release_conversation_usages(annex) == (shared.id,)


async def test_partial_acceptance_and_wrong_owner_are_atomic_refusals(
    async_session: AsyncSession,
) -> None:
    """A missing/foreign file leaves no partial usage behind."""
    owner, stranger = UserFactory.create(), UserFactory.create()
    async_session.add_all([owner, stranger])
    await async_session.flush()
    main, _ = await _targets(async_session, owner.id)
    deadline = datetime.now(UTC) + timedelta(hours=1)
    mine = await _attachment(async_session, owner.id, expires_at=deadline)
    theirs = await _attachment(async_session, stranger.id, expires_at=deadline)
    repo = ConversationAttachmentUsageRepository(async_session)

    for refused_id in (theirs.id, uuid4()):
        with pytest.raises(BaseAPIException) as refused:
            await repo.accept_batch(owner.id, [mine.id, refused_id], main)
        assert refused.value.status_code == 404
        assert await async_session.scalar(select(func.count(ConversationAttachmentUsage.id))) == 0
    with pytest.raises(ExecutionRevoked):
        await repo.accept_batch(stranger.id, [theirs.id], main)


async def test_a_retiring_generated_file_cannot_be_promised_as_kept(
    async_session: AsyncSession,
) -> None:
    """A file reserved for physical removal is no longer rescuable by the gallery."""
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    generated = await _attachment(
        async_session,
        owner.id,
        origin=AttachmentOrigin.GENERATED_IMAGE,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    generated.status = AttachmentStatus.DELETING
    generated.deletion_reason = "expired"
    await async_session.flush()

    kept, skipped = await keep_generated(async_session, owner.id, [generated.id], language="en")

    assert kept == []
    assert skipped == [generated.id]


async def test_retired_generation_cannot_attach_or_release_a_new_generations_files(
    async_session: AsyncSession,
) -> None:
    """The same business UUID after a reset is not the same file authority."""
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    main, _ = await _targets(async_session, owner.id)
    upload = await _attachment(
        async_session, owner.id, expires_at=datetime.now(UTC) + timedelta(hours=1)
    )
    repo = ConversationAttachmentUsageRepository(async_session)
    current = replace(main, revision=main.revision + 1, runtime_id=uuid4())
    await async_session.execute(
        update(Conversation)
        .where(Conversation.id == main.id)
        .values(revision=current.revision, runtime_id=current.runtime_id)
    )
    await repo.accept_batch(owner.id, [upload.id], current)

    with pytest.raises(ExecutionRevoked):
        await repo.accept_batch(owner.id, [upload.id], main)
    with pytest.raises(ExecutionRevoked):
        await repo.release_conversation_usages(main)
    assert await async_session.scalar(select(func.count(ConversationAttachmentUsage.id))) == 1
    assert upload.status == AttachmentStatus.READY


async def test_release_rolls_back_with_its_callers_transaction(async_session: AsyncSession) -> None:
    """A lifecycle failure cannot commit the file transition ahead of its messages."""
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    main, _ = await _targets(async_session, owner.id)
    upload = await _attachment(
        async_session, owner.id, expires_at=datetime.now(UTC) + timedelta(hours=1)
    )
    upload_id = upload.id
    repo = ConversationAttachmentUsageRepository(async_session)
    await repo.accept_batch(owner.id, [upload_id], main)

    with pytest.raises(RuntimeError, match="Injected lifecycle failure"):
        async with async_session.begin_nested():
            assert await repo.release_conversation_usages(main) == (upload_id,)
            raise RuntimeError("Injected lifecycle failure")

    await async_session.refresh(upload)
    assert upload.status == AttachmentStatus.READY
    assert await async_session.scalar(select(func.count(ConversationAttachmentUsage.id))) == 1


@pytest.mark.parametrize("accept_first", [True, False])
async def test_attach_and_last_release_serialize_on_the_file_in_both_orders(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], accept_first: bool
) -> None:
    """The blocked connection is observed in PostgreSQL, not inferred from a sleep."""
    owner_id = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as setup:
        main, annex = await _targets(setup, owner_id)
        upload = await _attachment(
            setup, owner_id, expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        file_id = upload.id
        await ConversationAttachmentUsageRepository(setup).accept_batch(owner_id, [file_id], main)
        await setup.commit()

    async def second_act() -> tuple[UUID, ...]:
        async with AsyncSession(async_engine, expire_on_commit=False) as second:
            repo = ConversationAttachmentUsageRepository(second)
            if accept_first:
                result = await repo.release_conversation_usages(main)
            else:
                result = tuple(
                    row.id for row in await repo.accept_batch(owner_id, [file_id], annex)
                )
            await second.commit()
            return result

    async with AsyncSession(async_engine, expire_on_commit=False) as first:
        repo = ConversationAttachmentUsageRepository(first)
        if accept_first:
            await repo.accept_batch(owner_id, [file_id], annex)
        else:
            assert await repo.release_conversation_usages(main) == (file_id,)
        blocker_pid = await first.scalar(text("SELECT pg_backend_pid()"))
        task = asyncio.create_task(second_act())
        try:
            async with asyncio.timeout(5):
                while True:
                    async with async_engine.connect() as observer:
                        waiting = await observer.scalar(
                            text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE :pid = ANY(pg_blocking_pids(pid))"
                            ),
                            {"pid": blocker_pid},
                        )
                    if waiting:
                        break
                    assert not task.done(), "The second act bypassed the file's retirement lock"
                    await asyncio.sleep(0.01)
            await first.commit()
            if accept_first:
                assert await task == ()
            else:
                with pytest.raises(BaseAPIException) as refused:
                    await task
                assert refused.value.status_code == 404
        finally:
            await first.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async with AsyncSession(async_engine) as observer_db:
        row = await observer_db.get(Attachment, file_id)
        assert row is not None
        assert row.status == (AttachmentStatus.READY if accept_first else AttachmentStatus.DELETING)
        remaining = list(
            await observer_db.scalars(
                select(ConversationAttachmentUsage.conversation_id).where(
                    ConversationAttachmentUsage.attachment_id == file_id
                )
            )
        )
        assert remaining == ([annex.id] if accept_first else [])


async def test_the_chat_records_usage_before_a_failed_early_archive(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A best-effort archive must never lose the accepted file's retirement authority."""
    owner_id = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine, expire_on_commit=False) as setup:
        _, target = await _targets(setup, owner_id)
        upload = await _attachment(
            setup, owner_id, expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        file_id = upload.id
        await setup.commit()

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def refused_archive(*args: object, **kwargs: object) -> None:
        raise OSError("Injected archive failure")

    monkeypatch.setattr(ConversationService, "archive_message", refused_archive)
    monkeypatch.setattr("src.infrastructure.database.get_db_context", database)
    monkeypatch.setattr(attachments_injection, "get_db_context", database)
    state = create_initial_state(owner_id, "session", "usage-run", user_language="en")
    state["messages"] = [HumanMessage(content="Use this file")]
    await attachments_injection.inject_attachments_into_state(
        state=state,
        attachment_ids=[file_id],
        user_id=owner_id,
        user_language="en",
        run_id="usage-run",
        target=target,
    )
    archived = await archive_user_message_first(
        conv_service=ConversationService(),
        conversation_id=target.id,
        user_message="Use this file",
        run_id="usage-run",
        is_hitl_resumption=False,
        attachment_meta=turn_attachment_meta(state, [file_id]),
        stt_kwargs={},
    )
    assert archived is None
    async with AsyncSession(async_engine) as observer:
        usage = (
            await observer.scalars(
                select(ConversationAttachmentUsage).where(
                    ConversationAttachmentUsage.attachment_id == file_id
                )
            )
        ).one_or_none()
        assert usage is not None
        assert (usage.conversation_id, usage.conversation_revision) == (target.id, target.revision)
