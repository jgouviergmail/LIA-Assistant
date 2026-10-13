"""Settings changes preserve a valid portrait unless its inputs or consent change."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.journals import management_projection, preference_commands, router
from src.domains.journals.schemas import JournalCostInfo, JournalSettingsUpdate, JournalSizeInfo
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def _fixture(monkeypatch: pytest.MonkeyPatch):
    user = User(
        id=uuid4(),
        email="journal-settings@example.test",
        journals_enabled=True,
        journal_consolidation_enabled=True,
        journal_consolidation_with_history=False,
        journal_max_total_chars=50000,
        journal_max_entry_chars=500,
        journal_context_max_chars=2000,
        journal_context_max_results=5,
        journal_portrait_full="A supported current synthesis.",
        extraction_revision=7,
        journal_revision=3,
        is_active=True,
    )
    service = MagicMock()
    service.repo.get_total_chars = AsyncMock(return_value=0)
    service.get_size_info = AsyncMock(
        return_value=JournalSizeInfo(total_chars=0, max_total_chars=50000, usage_pct=0)
    )
    constructor = MagicMock(return_value=service)
    constructor.build_cost_info_from_user.return_value = JournalCostInfo()
    monkeypatch.setattr(router, "JournalService", constructor)
    monkeypatch.setattr(preference_commands, "JournalService", constructor)
    monkeypatch.setattr(management_projection, "JournalService", constructor)
    repository = MagicMock()
    repository.get_by_id_for_preference_update = AsyncMock(return_value=user)
    monkeypatch.setattr(preference_commands, "UserRepository", MagicMock(return_value=repository))

    async def invalidate(_db, owner_id, *, invalidate_portrait=True):
        assert owner_id == user.id
        user.journal_revision_marked = True  # the words stay; the revision moves
        user.journal_revision += 1

    invalidator = AsyncMock(side_effect=invalidate)
    monkeypatch.setattr("src.domains.journals.lifecycle.mark_journal_changed", invalidator)
    monkeypatch.setattr(preference_commands, "mark_journal_changed", invalidator)
    return user, AsyncMock(), invalidator


@pytest.mark.parametrize(
    "changes",
    [
        {"journal_consolidation_enabled": False},
        {"journal_context_max_chars": 2500},
        {"journal_context_max_results": 6},
        {"journals_enabled": True},
        {"journal_consolidation_with_history": False},
        {"journal_max_entry_chars": 500},
        {"journals_enabled": None},
    ],
)
async def test_unrelated_settings_and_noops_preserve_the_current_portrait(monkeypatch, changes):
    user, db, invalidator = _fixture(monkeypatch)
    changed = any(
        value is not None and value != getattr(user, field) for field, value in changes.items()
    )
    result = await router.update_journal_settings(JournalSettingsUpdate(**changes), user, db)
    assert user.journal_portrait_full == "A supported current synthesis."
    assert user.journal_revision == 3
    assert user.extraction_revision == (8 if changed else 7)
    invalidator.assert_not_awaited()
    assert getattr(result, "portrait_invalidated", None) is False
    assert db.commit.await_count == int(changed)


@pytest.mark.parametrize(
    "changes",
    [
        {"journals_enabled": False},
        {"journal_consolidation_with_history": True},
        {"journal_max_entry_chars": 600},
        {"journal_max_total_chars": 60000},
    ],
)
async def test_changed_portrait_inputs_invalidate_and_acknowledge_the_cache(monkeypatch, changes):
    user, db, invalidator = _fixture(monkeypatch)
    result = await router.update_journal_settings(JournalSettingsUpdate(**changes), user, db)
    assert user.journal_portrait_full == "A supported current synthesis."
    assert user.journal_revision_marked is True
    assert user.journal_revision == 4
    assert user.extraction_revision == 8
    invalidator.assert_awaited_once_with(db, user.id)
    assert getattr(result, "portrait_invalidated", None) is True
    preference_commands.UserRepository.return_value.get_by_id_for_preference_update.assert_awaited_once_with(
        user.id
    )
    db.commit.assert_awaited_once()
