"""Source settings must preserve revision invalidation and exact approved comparisons."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ValidationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.journal_settings import (
    execute_journal_settings,
    prepare_journal_settings,
)
from src.domains.agents.application.journal_settings_schemas import JournalSettingsPatch
from src.domains.journals.models import JournalEntry
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "disable",
        "context",
        "noop",
        "stale",
        "usage",
        "expired",
        "late_off",
        "lost_ack",
        "committed_lost_ack",
    ],
)
async def test_journal_settings_compare_source_and_preserve_observed_commit_truth(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner_id = test_user.id
    test_user.journals_enabled = True
    test_user.journal_context_max_results = 5
    test_user.journal_max_total_chars = 10000
    test_user.journal_portrait_full = "Stored portrait"
    await async_session.commit()
    journal_revision = test_user.journal_revision
    extraction_revision = test_user.extraction_revision
    patch = (
        {"journal_max_total_chars": 5000}
        if scenario == "usage"
        else (
            {"journal_context_max_results": 1}
            if scenario == "context"
            else {"journals_enabled": scenario == "noop"}
        )
    )
    draft = await prepare_journal_settings(
        async_session, owner_id, JournalSettingsPatch.model_validate(patch)
    )
    receipt = PreferenceWriteReceipt()
    if scenario == "stale":
        await async_session.execute(
            update(User).where(User.id == owner_id).values(journals_enabled=False)
        )
        await async_session.commit()
    elif scenario == "usage":
        async_session.add(
            JournalEntry(
                user_id=owner_id,
                theme="learnings",
                title="Usage",
                content="a" * 6000,
                char_count=6000,
            )
        )
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "late_off":
        original_flush = async_session.flush

        async def revoke(*args, **kwargs):
            await original_flush(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "flush", revoke)
    elif scenario.endswith("lost_ack"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await original_commit()
            raise OperationalError("commit", {}, RuntimeError("ack unavailable"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    errors = {
        "stale": ResourceConflictError,
        "usage": ValidationError,
        "expired": CommandRejected,
        "late_off": AuthorizationError,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_journal_settings(async_session, owner_id, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    else:
        await execute_journal_settings(async_session, owner_id, draft, receipt)
        assert receipt.committed and receipt.no_op is (scenario == "noop")
    saved = await async_session.scalar(
        select(User).where(User.id == owner_id).execution_options(populate_existing=True)
    )
    assert saved is not None
    changed = scenario in {"disable", "context", "committed_lost_ack"}
    assert saved.extraction_revision == extraction_revision + int(changed)
    invalidated = scenario in {"disable", "committed_lost_ack"}
    assert saved.journal_revision == journal_revision + int(invalidated)
    # ADR-343: the portrait is kept whatever the scenario; an invalidating one
    # moves the revision above, which is what reads the words as STALE.
    assert saved.journal_portrait_full == "Stored portrait"
    assert saved.journals_enabled is (scenario not in {"disable", "stale", "committed_lost_ack"})
    assert saved.journal_context_max_results == (1 if scenario == "context" else 5)
