"""Normal UI updates keep their source wire shape and cannot write an inactive cached owner."""

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.psyche.models import PsycheState
from src.domains.psyche.router import get_psyche_state, update_psyche_settings
from src.domains.psyche.schemas import PsycheSettingsResponse, PsycheSettingsUpdate
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["source", "native_off", "inactive_owner"])
async def test_source_psyche_preferences_use_current_owner_without_native_dependency(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", scenario != "native_off")
    test_user.psyche_stability = 50
    await async_session.commit()
    if scenario == "inactive_owner":
        await async_session.execute(
            update(User).where(User.id == test_user.id).values(is_active=False)
        )
        await async_session.commit()
        with pytest.raises(ResourceNotFoundError):
            await update_psyche_settings(
                PsycheSettingsUpdate(psyche_stability=100), test_user, async_session
            )
        await async_session.refresh(test_user)
        assert test_user.psyche_stability == 50
        return
    saved = await update_psyche_settings(
        PsycheSettingsUpdate(psyche_stability=100), test_user, async_session
    )
    assert isinstance(saved, PsycheSettingsResponse) and saved.psyche_stability == 100
    await async_session.refresh(test_user)
    assert test_user.psyche_stability == 100


async def test_passive_frontend_state_read_does_not_initialize_or_commit(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    commit = AsyncMock()
    monkeypatch.setattr(async_session, "commit", commit)
    assert await get_psyche_state(test_user, async_session, initialize=False) is None
    commit.assert_not_awaited()
    assert (
        await async_session.scalar(
            select(func.count()).select_from(PsycheState).where(PsycheState.user_id == test_user.id)
        )
        == 0
    )
