"""Disposable PostgreSQL verifies ownership, expiry and fenced command recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_repository import (
    claim_command,
    close_command,
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.users.models import User

pytestmark = pytest.mark.integration


def proposal(actor: User, *, expired: bool = False) -> ApplicationActionDraftContent:
    return ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=actor.id,
        operation_id="preferences.update",
        schema_fingerprint="a" * 64,
        expected_digest="b" * 64,
        intent={"font_size": 17},
        before={"font_size": 16},
        after={"font_size": 17},
        title="Application preferences",
        expires_at=datetime.now(UTC) + timedelta(minutes=-1 if expired else 15),
    )


async def test_encrypted_command_is_bound_to_owner_target_and_presented_content(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    content = proposal(test_user)
    await save_command(async_session, content, "draft-" + str(content.command_id))
    await async_session.commit()
    row = await get_command(async_session, content.command_id, test_user.id)
    assert row is not None
    assert "font_size" not in row.content_encrypted
    assert matches_command(row, content, row.draft_id)
    assert not matches_command(row, content, "a-different-approval")
    tampered = content.model_copy(update={"after": {"font_size": 19}})
    assert not matches_command(row, tampered, row.draft_id)
    assert await get_command(async_session, content.command_id, uuid4()) is None


async def test_one_approval_claims_once_and_stale_worker_cannot_close_it(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    content = proposal(test_user)
    await save_command(async_session, content, "draft-" + str(content.command_id))
    await async_session.commit()
    token = await claim_command(async_session, content.command_id, test_user.id)
    assert token is not None
    assert await claim_command(async_session, content.command_id, test_user.id) is None
    result = ApplicationExecutionOutcome(
        success=True, phase=ApplicationPhase.COMMITTED, committed=True, values={"font_size": 17}
    )
    assert not await close_command(async_session, content.command_id, test_user.id, uuid4(), result)
    assert await close_command(async_session, content.command_id, test_user.id, token, result)
    assert not await close_command(async_session, content.command_id, test_user.id, token, result)
    row = await get_command(async_session, content.command_id, test_user.id)
    assert row is not None and row.phase == ApplicationPhase.COMMITTED
    assert row.result_encrypted is not None and "font_size" not in row.result_encrypted


async def test_expired_or_unowned_approval_never_claims(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    content = proposal(test_user, expired=True)
    await save_command(async_session, content, "draft-" + str(content.command_id))
    await async_session.commit()
    assert await claim_command(async_session, content.command_id, test_user.id) is None
    assert await claim_command(async_session, content.command_id, uuid4()) is None
    row = await get_command(async_session, content.command_id, test_user.id)
    assert row is not None and row.phase == ApplicationPhase.PENDING


async def test_cancelled_approval_stays_cancelled_and_cannot_be_claimed(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    from src.domains.agents.application.command_repository import cancel_command

    content = proposal(test_user)
    draft_id = "draft-" + str(content.command_id)
    await save_command(async_session, content, draft_id)
    await async_session.commit()
    assert not await cancel_command(async_session, draft_id, uuid4())
    assert await cancel_command(async_session, draft_id, test_user.id)
    assert await cancel_command(async_session, draft_id, test_user.id)
    assert await claim_command(async_session, content.command_id, test_user.id) is None


async def test_edit_replaces_the_presented_digest_and_refuses_an_already_claimed_command(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    from src.domains.agents.application.command_repository import replace_pending_command

    content = proposal(test_user)
    draft_id = "draft-" + str(content.command_id)
    await save_command(async_session, content, draft_id)
    await async_session.commit()
    revised = content.model_copy(update={"intent": {"font_size": 18}, "after": {"font_size": 18}})
    assert await replace_pending_command(async_session, content, revised)
    row = await get_command(async_session, content.command_id, test_user.id)
    assert row is not None
    assert not matches_command(row, content, draft_id)
    assert matches_command(row, revised, draft_id)
    assert not await replace_pending_command(async_session, content, revised)
    assert await claim_command(async_session, revised.command_id, test_user.id) is not None
    assert not await replace_pending_command(async_session, revised, content)


async def test_two_independent_workers_can_claim_only_once(async_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(
        id=uuid4(),
        email=f"command-race-{uuid4()}@example.test",
        hashed_password="test-only",
        is_active=True,
        is_verified=True,
    )
    content = proposal(actor)
    try:
        async with sessions() as db:
            db.add(actor)
            await db.flush()
            await save_command(db, content, "draft-" + str(content.command_id))
            await db.commit()

        async def worker():
            async with sessions() as db:
                return await claim_command(db, content.command_id, actor.id)

        claims = await asyncio.gather(worker(), worker())
        assert sum(token is not None for token in claims) == 1
    finally:
        async with sessions() as db:
            await db.execute(delete(User).where(User.id == actor.id))
            await db.commit()


async def test_expiry_during_revision_cannot_revive_the_approval(
    async_session: AsyncSession, test_user: User
) -> None:
    from src.domains.agents.application.command_repository import replace_pending_command

    content = proposal(test_user)
    draft_id = "draft-" + str(content.command_id)
    await save_command(async_session, content, draft_id)
    await async_session.commit()
    # The revision began while valid, but its resolver/model finishes after expiry.
    await async_session.execute(
        update(ApplicationCommand)
        .where(ApplicationCommand.id == content.command_id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await async_session.commit()
    revised = content.model_copy(update={"intent": {"font_size": 18}, "after": {"font_size": 18}})
    assert not await replace_pending_command(async_session, content, revised)
    row = await get_command(async_session, content.command_id, test_user.id)
    assert row is not None and matches_command(row, content, draft_id)
    assert await claim_command(async_session, content.command_id, test_user.id) is None
