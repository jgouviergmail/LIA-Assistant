"""Reset actions preserve the source level semantics and complete exact owned scope."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.psyche_reset import execute_psyche_reset, prepare_psyche_reset
from src.domains.agents.application.psyche_reset_schemas import PsycheResetIntent
from src.domains.psyche.models import PsycheHistory, PsycheState
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["soft", "full", "purge", "absent", "stale", "new_history", "expired", "native_off"]
)
async def test_psyche_reset_uses_source_semantics_and_refuses_changed_scope(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = test_user.id
    row = PsycheState(
        user_id=owner,
        mood_pleasure=0.9,
        relationship_stage="STABLE",
        relationship_depth=0.8,
        trait_openness=0.7,
        drive_curiosity=0.9,
        narrative_identity="PRIVATE NARRATIVE",
        last_appraisal={"private": "PRIVATE APPRAISAL"},
    )
    if scenario != "absent":
        async_session.add(row)
    histories = [
        PsycheHistory(user_id=owner, snapshot_type="message")
        for _ in range(203 if scenario == "purge" else 2)
    ]
    async_session.add_all(histories)
    await async_session.commit()
    level = scenario if scenario in {"soft", "full", "purge"} else "soft"
    draft = await prepare_psyche_reset(async_session, owner, PsycheResetIntent(level=level))
    assert "PRIVATE NARRATIVE" not in str(draft.model_dump())
    assert "PRIVATE APPRAISAL" not in str(draft.model_dump())
    if scenario == "stale":
        await async_session.execute(
            update(PsycheState).where(PsycheState.user_id == owner).values(mood_pleasure=0.8)
        )
        await async_session.commit()
    elif scenario == "new_history":
        async_session.add(PsycheHistory(user_id=owner, snapshot_type="daily"))
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    receipt = PreferenceWriteReceipt()
    errors = {
        "stale": ResourceConflictError,
        "new_history": ResourceConflictError,
        "expired": CommandRejected,
        "native_off": AuthorizationError,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_psyche_reset(async_session, owner, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
        return
    await execute_psyche_reset(async_session, owner, draft, receipt)
    assert receipt.committed
    saved = await async_session.scalar(
        select(PsycheState)
        .where(PsycheState.user_id == owner)
        .execution_options(populate_existing=True)
    )
    count = await async_session.scalar(
        select(func.count()).select_from(PsycheHistory).where(PsycheHistory.user_id == owner)
    )
    if scenario == "purge":
        assert saved is None and count == 0
    elif scenario == "absent":
        assert saved is None and count == 2 and receipt.no_op
    else:
        assert saved is not None and saved.active_emotions == [] and saved.drive_curiosity == 0.5
        assert saved.trait_openness == 0.7 and count == 3
        assert saved.relationship_stage == ("ORIENTATION" if scenario == "full" else "STABLE")
        assert saved.narrative_identity == (None if scenario == "full" else "PRIVATE NARRATIVE")
