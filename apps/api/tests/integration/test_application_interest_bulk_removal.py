"""Global removal confirms the complete source scope, including rows beyond UI pages."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application import interest_bulk_removal
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.interest_bulk_removal import (
    execute_interest_bulk_removal,
    prepare_interest_bulk_removal,
)
from src.domains.agents.application.interest_bulk_schemas import InterestBulkDeleteRequest
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["whole_scope", "new_row", "renamed", "notification", "empty", "unknown_commit"]
)
async def test_bulk_interest_removal_confirms_whole_source_scope_and_rejects_new_facts(
    async_session: AsyncSession, test_user: User, scenario: str
) -> None:
    owner = test_user.id
    other = uuid4()
    async_session.add(
        User(
            id=other,
            email=f"other-bulk-interest-{other}@example.test",
            full_name="Other",
            is_active=True,
            is_verified=True,
        )
    )
    await async_session.flush()
    rows = [
        UserInterest(
            user_id=owner,
            topic=f"Owned topic {index}",
            category="science",
            status=("active", "blocked", "dormant")[index % 3],
            last_mentioned_at=datetime.now(UTC),
        )
        for index in range(603 if scenario == "whole_scope" else 0 if scenario == "empty" else 1)
    ]
    async_session.add_all(
        [
            *rows,
            UserInterest(
                user_id=other,
                topic="Foreign topic",
                category="science",
                last_mentioned_at=datetime.now(UTC),
            ),
        ]
    )
    await async_session.commit()
    revision = test_user.extraction_revision
    identity = rows[0].id if rows else None
    draft = await prepare_interest_bulk_removal(
        async_session, owner, InterestBulkDeleteRequest(scope="all_owned")
    )
    assert draft.before["interests_to_delete"]["selected_count"] == len(rows)
    assert "Owned topic" not in str(draft.before) and "Foreign topic" not in str(draft.before)
    if scenario == "new_row":
        async_session.add(
            UserInterest(
                user_id=owner,
                topic="New topic",
                category="culture",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        await async_session.commit()
    elif scenario in {"renamed", "notification"}:
        await async_session.execute(
            update(UserInterest)
            .where(UserInterest.id == identity)
            .values(
                **(
                    {"topic": "Renamed topic"}
                    if scenario == "renamed"
                    else {"last_notified_at": datetime.now(UTC)}
                )
            )
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario in {"new_row", "renamed"}:
        with pytest.raises(ResourceConflictError):
            await execute_interest_bulk_removal(async_session, owner, draft, receipt)
        await async_session.rollback()
    elif scenario == "unknown_commit":
        with patch.object(async_session, "commit", side_effect=SQLAlchemyError("ack lost")):
            with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
                await execute_interest_bulk_removal(async_session, owner, draft, receipt)
        await async_session.rollback()
    else:
        await execute_interest_bulk_removal(async_session, owner, draft, receipt)
        assert receipt.committed and receipt.no_op is (scenario == "empty")
    total = await async_session.scalar(
        select(func.count()).select_from(UserInterest).where(UserInterest.user_id == owner)
    )
    assert total == (
        2 if scenario == "new_row" else 1 if scenario in {"renamed", "unknown_commit"} else 0
    )
    assert (
        await async_session.scalar(
            select(func.count()).select_from(UserInterest).where(UserInterest.user_id == other)
        )
        == 1
    )
    assert await async_session.scalar(
        select(User.extraction_revision).where(User.id == owner)
    ) == revision + int(scenario in {"whole_scope", "notification"})


@pytest.mark.parametrize("scenario", ["legacy_metadata", "late_disabled", "source_ui"])
async def test_global_removal_handles_legacy_rows_and_late_withdrawal_through_shared_owner(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    owner = test_user.id
    row = UserInterest(
        user_id=owner,
        topic="X",
        category="legacy_category",
        status="legacy_status",
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    if scenario == "source_ui":
        from src.domains.interests.router import delete_all_interests

        monkeypatch.setattr(settings, "application_tools_enabled", False)
        await delete_all_interests(test_user, async_session)
    else:
        draft = await prepare_interest_bulk_removal(
            async_session, owner, InterestBulkDeleteRequest(scope="all_owned")
        )
        selection = draft.before["interests_to_delete"]
        assert selection["unknown_category_count"] == selection["unknown_status_count"] == 1
        assert "legacy_category" not in str(selection) and "legacy_status" not in str(selection)
        receipt = PreferenceWriteReceipt()
        original = interest_bulk_removal.delete_all_managed_interests

        async def withdraw(*args, **kwargs):
            count = await original(*args, **kwargs)
            if scenario == "late_disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            return count

        with patch(
            "src.domains.agents.application.interest_bulk_removal.delete_all_managed_interests",
            side_effect=withdraw,
        ):
            if scenario == "late_disabled":
                with pytest.raises(AuthorizationError):
                    await execute_interest_bulk_removal(async_session, owner, draft, receipt)
                await async_session.rollback()
                assert not receipt.committed
            else:
                await execute_interest_bulk_removal(async_session, owner, draft, receipt)
    total = await async_session.scalar(
        select(func.count()).select_from(UserInterest).where(UserInterest.user_id == owner)
    )
    assert total == int(scenario == "late_disabled")
