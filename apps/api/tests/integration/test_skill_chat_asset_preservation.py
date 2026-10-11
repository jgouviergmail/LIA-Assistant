"""A failed chat-package asset carryover cannot leave new files ahead of old SQL state."""

import asyncio
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill
from tests.integration.domains.skill_library.test_library_install import _user
from tests.integration.domains.skill_library.test_library_install import skill_dirs as skill_dirs
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("replacement", [False, True])
async def test_asset_copy_refusal_restores_the_whole_precommit_package(
    async_session: AsyncSession,
    skill_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bool,
) -> None:
    actor = await _user(async_session)
    service = SkillImportService(async_session)
    folder = skill_dirs / "users" / str(actor) / "chat-card"
    before = manifest("chat-card", "Original description").decode()
    if replacement:
        await service.import_files({"SKILL.md": before}, owner_id=actor)
        (folder / "thumbnail.png").write_bytes(b"complete original binary asset")

    def failing_copy(backup: Path, target: Path) -> None:
        (target / "thumbnail.png").write_bytes(b"partial new asset")
        raise OSError("Controlled asset copy failure")

    monkeypatch.setattr(
        "src.domains.skills.import_service._carry_over_untransportable", failing_copy
    )
    with pytest.raises(OSError, match="Controlled asset copy failure"):
        await service.import_files(
            {"SKILL.md": manifest("chat-card", "Changed description").decode()}, owner_id=actor
        )
    rows = list((await async_session.scalars(select(Skill).where(Skill.owner_id == actor))).all())
    if replacement:
        assert len(rows) == 1 and rows[0].description == "Original description"
        assert (folder / "SKILL.md").read_text(encoding="utf-8") == before
        assert (folder / "thumbnail.png").read_bytes() == b"complete original binary asset"
    else:
        assert rows == [] and not folder.exists()


@pytest.mark.parametrize("disk_step", ["copy", "swap"])
async def test_repeated_cancellation_waits_for_disk_work_before_restoring_old_files(
    async_session: AsyncSession,
    skill_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
    disk_step: str,
) -> None:
    actor = await _user(async_session)
    service = SkillImportService(async_session)
    before = manifest("chat-card", "Original description").decode()
    await service.import_files({"SKILL.md": before}, owner_id=actor)
    folder = skill_dirs / "users" / str(actor) / "chat-card"
    (folder / "thumbnail.png").write_bytes(b"original asset")
    started, release = Event(), Event()

    def slow_copy(backup: Path, target: Path) -> None:
        started.set()
        assert release.wait(3)
        (target / "thumbnail.png").write_bytes(b"copied asset")

    if disk_step == "copy":
        monkeypatch.setattr(
            "src.domains.skills.import_service._carry_over_untransportable", slow_copy
        )
    else:
        original_swap = SkillImportService._swap_in

        def slow_swap(staging: Path, target: Path, backup: Path) -> None:
            original_swap(staging, target, backup)
            started.set()
            assert release.wait(3)

        monkeypatch.setattr(SkillImportService, "_swap_in", staticmethod(slow_swap))
    task = asyncio.create_task(
        service.import_files(
            {"SKILL.md": manifest("chat-card", "Changed description").decode()}, owner_id=actor
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        for _ in range(10):
            await asyncio.sleep(0)
        task.cancel()
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done(), "Live-file rollback raced a worker which can still write"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (folder / "SKILL.md").read_text(encoding="utf-8") == before
    assert (folder / "thumbnail.png").read_bytes() == b"original asset"
