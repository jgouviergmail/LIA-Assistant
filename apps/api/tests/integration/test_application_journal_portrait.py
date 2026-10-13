"""Native portrait reads preserve the source's revision and consent boundaries."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.journal_portrait_queries import read_journal_portrait
from src.domains.journals.source_state import portrait_source_state
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["current", "stale_revision", "source_moved", "personal_off", "missing"]
)
async def test_portrait_matches_source_visibility_without_recompilation(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    test_user.journals_enabled = True
    test_user.journal_portrait_full = "Observed owned portrait"
    test_user.journal_portrait_brief = "Owned brief"
    test_user.journal_portrait_compiled_at = datetime.now(UTC)
    await async_session.flush()
    test_user.journal_portrait_sources = {
        "version": 1,
        "journal_entries": 0,
        "sources": {},
        "journal_revision": test_user.journal_revision,
        "source_state": await portrait_source_state(async_session, test_user),
    }
    await async_session.commit()
    owner_id = test_user.id
    if scenario == "stale_revision":
        values = {"journal_revision": test_user.journal_revision + 1}
    elif scenario == "source_moved":
        values = {
            "journal_consolidation_with_history": not test_user.journal_consolidation_with_history
        }
    elif scenario == "personal_off":
        values = {"journals_enabled": False}
    elif scenario == "missing":
        values = {"journal_portrait_sources": None}
    else:
        values = {}
    if values:
        await async_session.execute(
            update(User)
            .where(User.id == owner_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    result = await read_journal_portrait(async_session, owner_id)
    # The words are served whenever the account may read them; moved evidence is
    # a FLAG, never a reason to hide them (2026-10-12).
    served = scenario != "personal_off"
    assert result.full == ("Observed owned portrait" if served else None)
    assert result.brief == ("Owned brief" if served else None)
    assert result.stale is (scenario in ("stale_revision", "source_moved", "missing"))
    await async_session.refresh(test_user)
    assert test_user.journal_portrait_full == "Observed owned portrait"


async def test_portrait_refuses_late_operator_revocation(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.agents.application import journal_portrait_queries as queries

    monkeypatch.setattr(settings, "journals_enabled", True)
    owner_id = test_user.id
    original = queries.read_managed_portrait

    async def revoked(db: AsyncSession, actor: User):
        result = await original(db, actor)
        db.add(
            SystemSetting(key=SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED, value="false")
        )
        await db.flush()
        return result

    monkeypatch.setattr(queries, "read_managed_portrait", revoked)
    with pytest.raises(AuthorizationError):
        await queries.read_journal_portrait(async_session, owner_id)
