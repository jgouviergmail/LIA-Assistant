"""Putting a skill's previous version back from the chat, on real PostgreSQL and real files (R5).

The proposal seals the skill and the version it would bring back; the confirmation restores
exactly that version through the same door as the settings (``skills.restore.restore_previous``),
and the version it puts aside becomes restorable in turn. A version changed after the proposal,
an expired proposal or a switched-off capability restores nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.skill_restore import (
    execute_skill_restore,
    prepare_skill_restore,
)
from src.domains.agents.application.skill_restore_schemas import SkillRestoreInput
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill
from src.domains.skills.previous_version import previous_slot
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.committed_account_session import async_session as async_session
from tests.integration.domains.skill_library.test_library_install import _user
from tests.integration.domains.skill_library.test_library_install import skill_dirs as skill_dirs
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration

NAME = "notes"


async def _upload(db: AsyncSession, actor: UUID, words: str) -> None:
    await SkillImportService(db).import_upload(
        manifest(NAME, words), "SKILL.md", owner_id=actor, is_system=False
    )


def _live(skill_dirs: Path, actor: UUID) -> str:
    return (skill_dirs / "users" / str(actor) / NAME / "SKILL.md").read_text(encoding="utf-8")


def _kept(skill_dirs: Path, actor: UUID) -> str | None:
    slot = previous_slot(str(skill_dirs / "users"), actor, NAME)
    return (slot / "SKILL.md").read_text(encoding="utf-8") if slot.is_dir() else None


async def _skill_id(db: AsyncSession, actor: UUID) -> UUID:
    found = await db.scalar(select(Skill.id).where(Skill.owner_id == actor, Skill.name == NAME))
    assert found is not None
    return found


@pytest.fixture
def tools_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)


async def test_the_confirmed_proposal_puts_the_previous_version_back_and_keeps_the_other(
    async_session: AsyncSession, skill_dirs: Path, tools_on: None
) -> None:
    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")
    await _upload(async_session, actor, "Second words")
    request = SkillRestoreInput(skill_id=await _skill_id(async_session, actor))

    draft = await prepare_skill_restore(async_session, actor, request)
    assert "First words" not in draft.model_dump_json(), "no version's words enter the proposal"
    receipt = PreferenceWriteReceipt()
    await execute_skill_restore(async_session, actor, draft, receipt)

    assert receipt.committed
    assert "First words" in _live(skill_dirs, actor)
    assert "Second words" in (_kept(skill_dirs, actor) or ""), "the restoration can be undone"


async def test_a_skill_with_no_previous_version_is_never_proposed(
    async_session: AsyncSession, skill_dirs: Path, tools_on: None
) -> None:
    actor = await _user(async_session)
    await _upload(async_session, actor, "Only words")

    with pytest.raises(CommandRejected) as refused:
        await prepare_skill_restore(
            async_session, actor, SkillRestoreInput(skill_id=await _skill_id(async_session, actor))
        )

    assert refused.value.code == "NOT_FOUND_OR_UNAUTHORIZED"


@pytest.mark.parametrize("scenario", ["replaced_meanwhile", "expired", "operator_off"])
async def test_a_proposal_that_no_longer_holds_restores_nothing(
    async_session: AsyncSession,
    skill_dirs: Path,
    tools_on: None,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")
    await _upload(async_session, actor, "Second words")
    draft = await prepare_skill_restore(
        async_session, actor, SkillRestoreInput(skill_id=await _skill_id(async_session, actor))
    )
    if scenario == "replaced_meanwhile":
        # The version the proposal named is no longer the one that would come back.
        await _upload(async_session, actor, "Third words")
    elif scenario == "expired":
        draft.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    else:
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    live_before = _live(skill_dirs, actor)
    receipt = PreferenceWriteReceipt()

    with pytest.raises((CommandRejected, BaseAPIException)):
        await execute_skill_restore(async_session, actor, draft, receipt)

    assert not receipt.committed
    assert _live(skill_dirs, actor) == live_before
