"""A replaced skill keeps the version it replaced, and the person can restore it (lot 14).

Real PostgreSQL commits and a throwaway skills tree: the import pipeline, the
restoration and the removal run exactly as the routes run them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import SkillProvenance
from src.domains.skills.previous_version import previous_slot, previous_versions
from src.domains.skills.repository import SkillRepository
from src.domains.skills.restore import restore_previous
from tests.helpers.committed_account_session import async_session as async_session
from tests.integration.domains.skill_library.test_library_install import _user
from tests.integration.domains.skill_library.test_library_install import skill_dirs as skill_dirs
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration

NAME = "notes"


def _version(words: str) -> bytes:
    return manifest(NAME, words)


def _live(skill_dirs: Path, actor: UUID) -> str:
    return (skill_dirs / "users" / str(actor) / NAME / "SKILL.md").read_text(encoding="utf-8")


def _kept(skill_dirs: Path, actor: UUID) -> str | None:
    slot = previous_slot(str(skill_dirs / "users"), actor, NAME)
    return (slot / "SKILL.md").read_text(encoding="utf-8") if slot.is_dir() else None


async def _upload(
    db: AsyncSession,
    actor: UUID,
    words: str,
    provenance: SkillProvenance = SkillProvenance.AUTHORED,
) -> None:
    await SkillImportService(db).import_upload(
        _version(words), "SKILL.md", owner_id=actor, is_system=False, provenance=provenance
    )


async def test_an_upload_over_the_persons_skill_keeps_the_version_it_replaced(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    actor = await _user(async_session)

    await _upload(async_session, actor, "First words")
    assert _kept(skill_dirs, actor) is None  # a first import replaced nothing
    await _upload(async_session, actor, "Second words")

    assert _live(skill_dirs, actor) == _version("Second words").decode()
    assert _kept(skill_dirs, actor) == _version("First words").decode()
    assert set(previous_versions(str(skill_dirs / "users"), actor)) == {NAME}


async def test_an_edit_in_the_chat_keeps_the_version_it_replaced(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    actor = await _user(async_session)
    service = SkillImportService(async_session)

    await service.import_files({"SKILL.md": _version("First words").decode()}, owner_id=actor)
    await service.import_files({"SKILL.md": _version("Second words").decode()}, owner_id=actor)

    assert _kept(skill_dirs, actor) == _version("First words").decode()


async def test_restoring_puts_the_previous_version_back_and_can_itself_be_undone(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")
    await _upload(async_session, actor, "Second words")

    restored = await restore_previous(async_session, actor, NAME)

    assert restored["name"] == NAME
    assert _live(skill_dirs, actor) == _version("First words").decode()
    assert _kept(skill_dirs, actor) == _version("Second words").decode()
    row = await SkillRepository(async_session).get_owned(actor, NAME)
    assert row is not None and row.description == "First words"
    assert row.provenance == SkillProvenance.AUTHORED

    await restore_previous(async_session, actor, NAME)

    assert _live(skill_dirs, actor) == _version("Second words").decode()
    assert _kept(skill_dirs, actor) == _version("First words").decode()


async def test_a_third_party_version_is_never_kept_nor_restored_as_the_persons_own(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")
    await _upload(async_session, actor, "Second words")
    assert _kept(skill_dirs, actor) is not None

    # A fetched skill replaces the person's own: it keeps nothing, and the
    # older version of the person's skill goes with the incarnation it belonged to.
    await _upload(async_session, actor, "Fetched words", provenance=SkillProvenance.URL)
    assert _kept(skill_dirs, actor) is None
    # The person's own upload over a fetched skill: the fetched bytes are not kept.
    await _upload(async_session, actor, "Own words again")
    assert _kept(skill_dirs, actor) is None

    with pytest.raises(ResourceNotFoundError):
        await restore_previous(async_session, actor, NAME)


async def test_nothing_to_restore_is_said_as_such(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")

    with pytest.raises(ResourceNotFoundError):
        await restore_previous(async_session, actor, NAME)
    # A refusal keeps the owner lock until its request's transaction ends, as
    # every refused import does: the next request starts on a fresh one.
    await async_session.rollback()
    with pytest.raises(ResourceNotFoundError):
        await restore_previous(async_session, actor, "unknown-skill")
    await async_session.rollback()
    assert _live(skill_dirs, actor) == _version("First words").decode()


async def test_a_replacement_that_fails_to_commit_leaves_the_previous_version_as_it_was(
    async_session: AsyncSession, skill_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")
    await _upload(async_session, actor, "Second words")

    async def refused(_db: AsyncSession) -> None:
        raise RuntimeError("Controlled commit failure")

    monkeypatch.setattr("src.domains.skills.import_service.commit_skill_import", refused)
    with pytest.raises(RuntimeError, match="Controlled commit failure"):
        await _upload(async_session, actor, "Third words")

    assert _live(skill_dirs, actor) == _version("Second words").decode()
    assert _kept(skill_dirs, actor) == _version("First words").decode()


async def test_a_cancellation_while_the_slot_settles_keeps_the_commit_and_travels_on(
    async_session: AsyncSession, skill_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.skills import previous_version as module

    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")
    started, release = Event(), Event()
    real = module.settle_slot

    def slow_settle(backup: Path, slot: Path, *, keep: bool) -> None:
        started.set()
        assert release.wait(3)
        real(backup, slot, keep=keep)

    monkeypatch.setattr(module, "settle_slot", slow_settle)
    task = asyncio.create_task(_upload(async_session, actor, "Second words"))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done(), "the slot's disk step was abandoned mid-way"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    # Committed before the cancellation: the new version lives, the old one is kept.
    assert _live(skill_dirs, actor) == _version("Second words").decode()
    assert _kept(skill_dirs, actor) == _version("First words").decode()
    row = await SkillRepository(async_session).get_owned(actor, NAME)
    assert row is not None and row.description == "Second words"


async def test_deleting_the_skill_removes_its_previous_version(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    from src.domains.skills.removal import cleanup_removal, observe_removal, stage_removal

    actor = await _user(async_session)
    await _upload(async_session, actor, "First words")
    await _upload(async_session, actor, "Second words")
    row = await SkillRepository(async_session).get_owned(actor, NAME)
    assert row is not None

    observed = await observe_removal(async_session, actor, row.id)
    await stage_removal(async_session, actor, observed)
    await async_session.commit()
    assert await cleanup_removal(async_session, observed)
    await async_session.commit()

    assert _kept(skill_dirs, actor) is None
    assert previous_versions(str(skill_dirs / "users"), actor) == {}
