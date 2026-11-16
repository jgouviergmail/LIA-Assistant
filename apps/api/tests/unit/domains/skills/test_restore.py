"""Untrusted restoration names are refused before account or filesystem access."""

import asyncio
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.domains.skills import restore as restore_module
from src.domains.skills.models import SkillProvenance
from src.domains.skills.previous_version import previous_slot
from src.domains.skills.restore import restore_previous
from src.domains.users import file_writers
from tests.helpers.account_file_writes import account_writer_sql_stub as account_writer_sql_stub

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name",
    [
        "../notes",
        "../../another-owner/.lia-previous/notes",
        "nested/notes",
        "/outside/notes",
        "..\\notes",
        "C:\\outside\\notes",
        "notes:stream",
        ".",
        "..",
    ],
)
async def test_restore_rejects_path_names_before_account_or_disk_access(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_writer_sql_stub: None,
) -> None:
    """Even an owned row cannot make a malformed name a filesystem authority."""
    monkeypatch.setattr("src.domains.skills.restore.settings.skills_users_path", str(tmp_path))
    db = MagicMock(bind=None)
    db.scalar = AsyncMock(return_value=SkillProvenance.AUTHORED.value)

    with pytest.raises(ValidationError):
        await restore_previous(db, uuid4(), name)

    db.scalar.assert_not_awaited()
    assert list(tmp_path.iterdir()) == []


def _package(folder: Path) -> None:
    """Create real, valid manifest bytes for filesystem admission tests."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\nname: notes\ndescription: Previous notes.\n---\n# Notes\n", encoding="utf-8"
    )


def _linked_package(root: Path, slot: Path, scenario: str) -> None:
    """Place a link on one independently meaningful boundary of the kept tree."""
    outside = root.parent / "outside"
    if scenario in {"owner", "scope", "sibling_scope", "slot", "local_slot"}:
        link = {
            "owner": slot.parent.parent,
            "scope": slot.parent,
            "sibling_scope": slot.parent,
            "slot": slot,
            "local_slot": slot,
        }[scenario]
        target = (
            slot.parent.with_name(slot.parent.name + "-other")
            if scenario == "sibling_scope"
            else outside
        )
        if scenario == "local_slot":
            target = slot.with_name("another-slot")
        package = target / slot.relative_to(link)
        _package(package)
    else:
        _package(slot)
        _package(outside)
        relative = {
            "manifest": "SKILL.md",
            "resource": "notes.md",
            "resource_directory": "references",
        }[scenario]
        link = slot / relative
        target = outside if scenario == "resource_directory" else outside / "SKILL.md"
        if scenario == "manifest":
            link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege unavailable; run the Linux proof")
        raise


@pytest.mark.parametrize(
    "scenario",
    [
        "owner",
        "scope",
        "sibling_scope",
        "slot",
        "local_slot",
        "manifest",
        "resource",
        "resource_directory",
    ],
)
async def test_restore_refuses_linked_scope_and_package_before_import(
    scenario: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_writer_sql_stub: None,
) -> None:
    """A valid skill name never authorizes reading another directory or linked resource."""
    root = tmp_path / "users"
    owner = uuid4()
    slot = previous_slot(str(root), owner, "notes")
    _linked_package(root, slot, scenario)
    monkeypatch.setattr("src.domains.skills.restore.settings.skills_users_path", str(root))
    db = MagicMock(bind=None)
    db.scalar = AsyncMock(side_effect=[owner, SkillProvenance.AUTHORED.value])
    importer = AsyncMock(return_value={"name": "notes"})
    monkeypatch.setattr("src.domains.skills.restore.SkillImportService.import_directory", importer)

    with pytest.raises(ResourceNotFoundError):
        await restore_previous(db, owner, "notes")

    importer.assert_not_awaited()


async def test_restore_hands_the_importer_the_checked_canonical_account_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_writer_sql_stub: None,
) -> None:
    """An ordinary kept package remains restorable through the existing import door."""
    root = tmp_path / "users"
    owner = uuid4()
    slot = previous_slot(str(root), owner, "notes")
    _package(slot)
    (slot / "references").mkdir()
    (slot / "references" / "notes.md").write_text("Kept content", encoding="utf-8")
    configured = root / ".." / root.name
    monkeypatch.setattr("src.domains.skills.restore.settings.skills_users_path", str(configured))
    db = MagicMock(bind=None)
    db.scalar = AsyncMock(side_effect=[owner, SkillProvenance.AUTHORED.value])
    importer = AsyncMock(return_value={"name": "notes"})
    monkeypatch.setattr("src.domains.skills.restore.SkillImportService.import_directory", importer)

    assert await restore_previous(db, owner, "notes") == {"name": "notes"}

    importer.assert_awaited_once_with(
        slot.resolve(), owner_id=owner, provenance=SkillProvenance.AUTHORED
    )


async def test_restore_cancellation_waits_for_admission_before_releasing_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_writer_sql_stub: None,
) -> None:
    """The durable writer cannot close while its cancelled filesystem reader still runs."""
    root = tmp_path / "users"
    owner = uuid4()
    _package(previous_slot(str(root), owner, "notes"))
    monkeypatch.setattr(restore_module.settings, "skills_users_path", str(root))
    db = MagicMock(bind=None)
    db.scalar = AsyncMock(side_effect=[owner, SkillProvenance.AUTHORED.value])
    importer = AsyncMock(return_value={"name": "notes"})
    monkeypatch.setattr(restore_module.SkillImportService, "import_directory", importer)
    started, release, settled = Event(), Event(), Event()
    real_admission = restore_module._restorable_source
    closed_after_settlement: list[bool] = []

    def paused_admission(users_root: str, owner_id: UUID, name: str) -> Path | None:
        started.set()
        try:
            assert release.wait(3)
            return real_admission(users_root, owner_id, name)
        finally:
            settled.set()

    async def finish_record(
        sessions: async_sessionmaker[AsyncSession], account: UUID, identity: UUID
    ) -> None:
        closed_after_settlement.append(settled.is_set())

    monkeypatch.setattr(restore_module, "_restorable_source", paused_admission)
    monkeypatch.setattr(file_writers, "_finish", finish_record)
    task = asyncio.create_task(restore_previous(db, owner, "notes"))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        for _ in range(10):
            await asyncio.sleep(0)
        assert closed_after_settlement == [], "the account writer closed before its disk read"
        assert not task.done(), "the filesystem admission was abandoned"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(settled.wait, 3)

    assert closed_after_settlement == [True]
    importer.assert_not_awaited()
