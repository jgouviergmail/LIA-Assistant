"""Real imports stop before live writes and report known commits before cache refresh."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skill_library import service
from src.domains.skill_library.errors import LibraryRefusal
from src.domains.skill_library.schemas import LibraryInstallRequest
from src.domains.skills.cache import SkillsCache
from tests.integration.domains.skill_library.test_library_install import (
    REPO,
    _user,
)
from tests.integration.domains.skill_library.test_library_install import (
    hub as hub,
)
from tests.integration.domains.skill_library.test_library_install import (
    one_session as one_session,
)
from tests.integration.domains.skill_library.test_library_install import (
    skill_dirs as skill_dirs,
)
from tests.unit.domains.skill_library.fakes import FakeHub, manifest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_preview_reads_the_requested_commit_after_head_moves(
    one_session: AsyncSession, skill_dirs: Path, hub: FakeHub
) -> None:
    actor = await _user(one_session)
    approved = hub.publish(REPO, "approved", {"skills/pdf/SKILL.md": manifest("pdf", "approved")})
    hub.publish(REPO, "later", {"skills/pdf/SKILL.md": manifest("pdf", "later")})
    request = LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=approved)
    preview = await service.preview_install(actor, request)
    assert preview.commit_sha == approved and preview.description == "approved"
    assert not (skill_dirs / "users" / str(actor) / "pdf").exists()


@pytest.mark.asyncio
async def test_pre_swap_refusal_preserves_previous_files(
    one_session: AsyncSession, skill_dirs: Path, hub: FakeHub
) -> None:
    actor = await _user(one_session)
    first = hub.publish(REPO, "first", {"skills/pdf/SKILL.md": manifest("pdf", "first")})
    installed = await service.install(
        actor, LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=first)
    )
    second = hub.publish(REPO, "second", {"skills/pdf/SKILL.md": manifest("pdf", "second")})
    live = skill_dirs / "users" / str(actor) / "pdf" / "SKILL.md"
    previous = live.read_bytes()

    async def refuse(db: AsyncSession) -> None:
        assert db is one_session and live.read_bytes() == previous
        raise PermissionError("Authority revoked")

    with pytest.raises(PermissionError):
        await service.update(actor, installed.skill_id, second, before_swap=refuse)
    assert live.read_bytes() == previous


@pytest.mark.asyncio
async def test_commit_receipt_precedes_failed_cache_refresh(
    one_session: AsyncSession, skill_dirs: Path, hub: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await _user(one_session)
    commit = hub.publish(REPO, "receipt", {"skills/pdf/SKILL.md": manifest("pdf")})
    request = LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=commit)
    acknowledged = []
    monkeypatch.setattr(
        SkillsCache, "invalidate_and_reload", AsyncMock(side_effect=OSError("cache"))
    )
    with pytest.raises(OSError):
        await service.install(
            actor, request, after_commit=lambda skill: acknowledged.append(skill.id)
        )
    assert len(acknowledged) == 1
    assert (skill_dirs / "users" / str(actor) / "pdf" / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_changed_preview_refuses_before_any_live_install(
    one_session: AsyncSession, skill_dirs: Path, hub: FakeHub
) -> None:
    actor = await _user(one_session)
    commit = hub.publish(REPO, "sealed", {"skills/pdf/SKILL.md": manifest("pdf")})
    request = LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=commit)
    preview = await service.preview_install(actor, request)
    forged = preview.model_copy(update={"tree_sha": "a" * 40})
    with pytest.raises(LibraryRefusal):
        await service.install(actor, request, expected_preview=forged)
    assert not (skill_dirs / "users" / str(actor) / "pdf").exists()


@pytest.mark.asyncio
async def test_lost_commit_ack_never_invokes_success_hook(
    one_session: AsyncSession, skill_dirs: Path, hub: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.skills.import_commit import SkillImportCompletionUnknown

    actor = await _user(one_session)
    commit = hub.publish(REPO, "lost", {"skills/pdf/SKILL.md": manifest("pdf")})
    request = LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=commit)
    original = one_session.commit

    async def lost() -> None:
        await original()
        raise OSError("lost ack")

    acknowledged = []
    monkeypatch.setattr(one_session, "commit", lost)
    with pytest.raises(SkillImportCompletionUnknown):
        await service.install(
            actor, request, after_commit=lambda skill: acknowledged.append(skill.id)
        )
    assert not acknowledged
    assert (skill_dirs / "users" / str(actor) / "pdf" / "SKILL.md").is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_final_authority_refusal_restores_previous_package(
    one_session: AsyncSession, skill_dirs: Path, hub: FakeHub, cancelled: bool
) -> None:
    actor = await _user(one_session)
    first = hub.publish(REPO, "before", {"skills/pdf/SKILL.md": manifest("pdf", "before")})
    installed = await service.install(
        actor, LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=first)
    )
    after = hub.publish(REPO, "after", {"skills/pdf/SKILL.md": manifest("pdf", "after")})
    live = skill_dirs / "users" / str(actor) / "pdf" / "SKILL.md"
    previous = live.read_bytes()

    async def refuse(db: AsyncSession) -> None:
        assert "after" in live.read_text()
        if cancelled:
            import asyncio

            raise asyncio.CancelledError()
        from src.domains.agents.application.command_service import CommandRejected

        raise CommandRejected("EXPIRED")

    import asyncio

    from src.domains.agents.application.command_service import CommandRejected

    with pytest.raises(
        asyncio.CancelledError if cancelled else CommandRejected,
        match=None if cancelled else "EXPIRED",
    ):
        await service.update(actor, installed.skill_id, after, before_commit=refuse)
    assert live.read_bytes() == previous
