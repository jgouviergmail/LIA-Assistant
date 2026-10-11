"""Reading a psyche is observational: no creation, model call, foreign state or capped total."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.psyche_queries import read_psyche
from src.domains.agents.application.psyche_read_schemas import PsycheRead
from src.domains.psyche.models import PsycheHistory, PsycheState
from src.domains.psyche.service import PsycheService
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    ["complete", "absent", "personal_off", "operator_off", "foreign_cursor", "late_operator"],
)
async def test_psyche_reader_never_materializes_state_and_pages_the_complete_owned_history(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    test_user.psyche_enabled = scenario != "personal_off"
    foreign_user = User(
        id=uuid4(), email=f"psyche-read-{uuid4()}@example.test", full_name="Other", is_active=True
    )
    async_session.add(foreign_user)
    await async_session.flush()
    if scenario != "absent":
        async_session.add(
            PsycheState(
                user_id=test_user.id,
                mood_pleasure=0.25,
                narrative_identity="PRIVATE NARRATIVE",
                last_appraisal={"private": "PRIVATE APPRAISAL"},
            )
        )
    when = datetime.now(UTC) - timedelta(hours=1)
    rows = [
        PsycheHistory(user_id=test_user.id, snapshot_type="message", created_at=when)
        for _ in range(53)
    ]
    foreign = PsycheHistory(
        user_id=foreign_user.id,
        snapshot_type="message",
        dominant_emotion="FOREIGN SECRET",
        created_at=when,
    )
    async_session.add_all([*rows, foreign])
    if scenario == "operator_off":
        async_session.add(
            SystemSetting(key=SystemSettingKey.CAPABILITY_PSYCHE_ENABLED, value="false")
        )
    await async_session.commit()
    create, summary = AsyncMock(), AsyncMock()
    monkeypatch.setattr(PsycheService, "get_or_create_state", create)
    monkeypatch.setattr(PsycheService, "generate_summary", summary)
    if scenario == "late_operator":
        from src.domains.agents.application import psyche_queries

        original = psyche_queries.read_psyche_history_page

        async def withdraw(*args, **kwargs):
            result = await original(*args, **kwargs)
            monkeypatch.setattr(settings, "psyche_enabled", False)
            return result

        monkeypatch.setattr(psyche_queries, "read_psyche_history_page", withdraw)
    request = PsycheRead(limit=5, after_id=foreign.id if scenario == "foreign_cursor" else None)
    if scenario in {"operator_off", "late_operator", "foreign_cursor"}:
        with pytest.raises(
            ResourceNotFoundError if scenario == "foreign_cursor" else AuthorizationError
        ):
            await read_psyche(async_session, test_user.id, request)
        create.assert_not_awaited()
        summary.assert_not_awaited()
        return
    seen = []
    while True:
        result = await read_psyche(async_session, test_user.id, request)
        assert result.total == 53 and len(result.history) <= 5
        assert result.settings.psyche_enabled is (scenario != "personal_off")
        assert (result.state is None) is (scenario == "absent")
        assert (result.expression is None) is (scenario == "absent")
        assert "PRIVATE NARRATIVE" not in result.model_dump_json()
        assert "PRIVATE APPRAISAL" not in result.model_dump_json()
        assert "FOREIGN SECRET" not in result.model_dump_json()
        seen.extend(entry.id for entry in result.history)
        if result.next_cursor is None:
            break
        request = PsycheRead(limit=5, after_id=result.next_cursor, as_of=result.as_of)
    assert len(seen) == len(set(seen)) == 53
    create.assert_not_awaited()
    summary.assert_not_awaited()
    assert await async_session.scalar(
        select(func.count()).select_from(PsycheState).where(PsycheState.user_id == test_user.id)
    ) == (0 if scenario == "absent" else 1)


async def test_psyche_history_filters_keep_empty_totals_and_stable_window(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    as_of = datetime.now(UTC)
    for hours, kind in [(1, "message"), (2, "reset_soft"), (25, "message"), (-1, "message")]:
        async_session.add(
            PsycheHistory(
                user_id=test_user.id, snapshot_type=kind, created_at=as_of - timedelta(hours=hours)
            )
        )
    await async_session.commit()
    result = await read_psyche(
        async_session, test_user.id, PsycheRead(hours=24, snapshot_type="message", as_of=as_of)
    )
    assert result.total == result.returned_count == 1
    assert not result.truncated and result.next_cursor is None
    empty = await read_psyche(async_session, test_user.id, PsycheRead(snapshot_type="not_present"))
    assert empty.total == empty.returned_count == 0 and empty.history == []
    with pytest.raises(ValueError, match="future"):
        await read_psyche(async_session, test_user.id, PsycheRead(as_of=as_of + timedelta(days=1)))
