"""Confirmed deletion owns its source target and cannot race obsolete extraction state."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application import interest_removal
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.interest_removal_schemas import InterestDeleteRequest
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    ["active", "blocked", "dormant", "stale", "foreign", "late_disabled", "unknown_commit"],
)
async def test_exact_interest_deletion_uses_source_scope_and_revision(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    owner = test_user.id
    row = UserInterest(
        user_id=owner,
        topic="Owned target",
        category="science",
        status=scenario if scenario in {"blocked", "dormant"} else "active",
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    identity, revision = row.id, test_user.extraction_revision
    if scenario == "foreign":
        other = uuid4()
        async_session.add(
            User(
                id=other,
                email=f"foreign-removal-{other}@example.test",
                full_name="Other",
                is_active=True,
                is_verified=True,
            )
        )
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await interest_removal.prepare_interest_removal(
                async_session, other, InterestDeleteRequest(interest_id=identity)
            )
        return
    draft = await interest_removal.prepare_interest_removal(
        async_session, owner, InterestDeleteRequest(interest_id=identity)
    )
    assert await async_session.get(UserInterest, identity) is not None
    if scenario == "stale":
        await async_session.execute(
            update(UserInterest).where(UserInterest.id == identity).values(positive_signals=3)
        )
        await async_session.commit()
    original = interest_removal.delete_managed_interest

    async def delete(*args, **kwargs):
        result = await original(*args, **kwargs)
        if scenario == "late_disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return result

    receipt = PreferenceWriteReceipt()
    with patch(
        "src.domains.agents.application.interest_removal.delete_managed_interest",
        side_effect=delete,
    ):
        if scenario == "unknown_commit":
            with patch.object(async_session, "commit", side_effect=SQLAlchemyError("ack lost")):
                with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                    await interest_removal.execute_interest_removal(
                        async_session, owner, draft, receipt
                    )
            await async_session.rollback()
        elif scenario in {"stale", "late_disabled"}:
            with pytest.raises(
                ResourceConflictError if scenario == "stale" else AuthorizationError
            ):
                await interest_removal.execute_interest_removal(
                    async_session, owner, draft, receipt
                )
            await async_session.rollback()
        else:
            await interest_removal.execute_interest_removal(async_session, owner, draft, receipt)
    removed = scenario in {"active", "blocked", "dormant"}
    assert (await async_session.get(UserInterest, identity) is None) is removed
    assert receipt.committed is removed
    assert await async_session.scalar(
        select(User.extraction_revision).where(User.id == owner)
    ) == revision + int(removed)


async def test_source_ui_deletion_retains_delivered_history_and_invalidates_old_extractions(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.interests.models import InterestNotification
    from src.domains.interests.repository import InterestNotificationRepository
    from src.domains.interests.router import delete_interest

    monkeypatch.setattr(settings, "application_tools_enabled", False)
    owner = test_user.id
    row = UserInterest(
        user_id=owner,
        topic="Source target",
        category="science",
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.flush()
    note = InterestNotification(
        user_id=owner,
        interest_id=row.id,
        run_id=str(uuid4()),
        content="Previously delivered content",
        content_hash="a" * 64,
        source="llm",
    )
    async_session.add(note)
    foreign_owner = uuid4()
    async_session.add(
        User(
            id=foreign_owner,
            email=f"foreign-note-{foreign_owner}@example.test",
            full_name="Other",
            is_active=True,
            is_verified=True,
        )
    )
    await async_session.flush()
    foreign_note = InterestNotification(
        user_id=foreign_owner,
        interest_id=row.id,
        run_id=str(uuid4()),
        content="Foreign delivered content",
        content_hash="b" * 64,
        source="llm",
    )
    async_session.add(foreign_note)
    await async_session.commit()
    identity, note_id, revision = row.id, note.id, test_user.extraction_revision
    await delete_interest(identity, test_user, async_session)
    assert await async_session.get(UserInterest, identity) is None
    await async_session.refresh(note)
    assert note.interest_id is None and note.content == "Previously delivered content"
    await async_session.refresh(foreign_note)
    assert foreign_note.interest_id is None and foreign_note.content == "Foreign delivered content"
    history, total = await InterestNotificationRepository(async_session).get_history(
        owner, limit=10
    )
    assert total == 1
    assert [item.id for item in history] == [note_id]
    assert history[0].interest is None
    assert (
        await async_session.scalar(select(User.extraction_revision).where(User.id == owner))
        == revision + 1
    )
