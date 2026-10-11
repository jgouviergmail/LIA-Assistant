"""Native exact library consent uses the original PostgreSQL/filesystem import path."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.skills.cache import SkillsCache
from src.domains.users.preference_cas import PreferenceWriteReceipt
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


@pytest.mark.parametrize("scenario", ["valid", "revoked", "expired", "cache_failed", "lost_ack"])
async def test_exact_native_library_install(
    one_session: AsyncSession,
    skill_dirs: Path,
    hub: FakeHub,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    from src.domains.agents.application import skill_library_import as native
    from src.domains.agents.application.skill_library_import_schemas import LibraryInstallInput

    for setting in ("application_tools_enabled", "skills_enabled", "skill_library_enabled"):
        monkeypatch.setattr(settings, setting, True)
    monkeypatch.setattr(native, "rate_limit_library", AsyncMock())
    actor = await _user(one_session)
    approved = hub.publish(REPO, "native", {"skills/pdf/SKILL.md": manifest("pdf", "approved")})
    request = LibraryInstallInput(repository=REPO, path="skills/pdf", commit_sha=approved)
    draft = await native.prepare_library_install(one_session, actor, request)
    live = skill_dirs / "users" / str(actor) / "pdf" / "SKILL.md"
    assert not live.exists() and "Body." not in draft.model_dump_json()
    hub.publish(REPO, "moved", {"skills/pdf/SKILL.md": manifest("pdf", "later")})
    receipt = PreferenceWriteReceipt()
    if scenario == "revoked":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "expired":
        from datetime import UTC, datetime, timedelta

        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "cache_failed":
        monkeypatch.setattr(
            SkillsCache, "invalidate_and_reload", AsyncMock(side_effect=OSError("cache"))
        )
    elif scenario == "lost_ack":
        original = one_session.commit
        from src.domains.skill_library import service

        register = service._register

        async def lose(*args, **kwargs):
            async def commit():
                await original()
                raise OSError("lost ACK")

            monkeypatch.setattr(one_session, "commit", commit)
            return await register(*args, **kwargs)

        monkeypatch.setattr(service, "_register", lose)
    if scenario in {"valid", "cache_failed"}:
        await native.execute_library_import(one_session, actor, draft, receipt)
        assert receipt.committed and "approved" in live.read_text()
        assert receipt.values["cache_refresh_pending"] == (scenario == "cache_failed")
    elif scenario == "lost_ack":
        with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
            await native.execute_library_import(one_session, actor, draft, receipt)
        assert not receipt.committed and live.exists()
    else:
        with pytest.raises(Exception):
            await native.execute_library_import(one_session, actor, draft, receipt)
        assert not receipt.committed and not live.exists()


@pytest.mark.parametrize("scenario", ["valid", "changed_files", "changed_source", "foreign"])
async def test_library_update_seals_owned_source_and_old_files(
    one_session: AsyncSession,
    skill_dirs: Path,
    hub: FakeHub,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    from src.domains.agents.application import skill_library_import as native
    from src.domains.agents.application.skill_library_import_schemas import LibraryUpdateInput
    from src.domains.skill_library import service
    from src.domains.skill_library.models import SkillLibrarySource
    from src.domains.skill_library.schemas import LibraryInstallRequest

    for setting in ("application_tools_enabled", "skills_enabled", "skill_library_enabled"):
        monkeypatch.setattr(settings, setting, True)
    monkeypatch.setattr(native, "rate_limit_library", AsyncMock())
    actor = await _user(one_session)
    files = {"skills/pdf/SKILL.md": manifest("pdf"), "skills/pdf/references/r.md": b"old"}
    first = hub.publish(REPO, "native-old", files)
    installed = await service.install(
        actor, LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=first)
    )
    second = hub.publish(REPO, "native-new", {**files, "skills/pdf/references/r.md": b"new"})
    request = LibraryUpdateInput(skill_id=installed.skill_id, commit_sha=second)
    if scenario == "foreign":
        other = await _user(one_session)
        with pytest.raises(CommandRejected, match="NOT_FOUND_OR_UNAUTHORIZED"):
            await native.prepare_library_update(one_session, other, request)
        return
    draft = await native.prepare_library_update(one_session, actor, request)
    assert draft.after["skill_library_import"]["preview"]["changes"]["modified"] == [
        "references/r.md"
    ]
    file = skill_dirs / "users" / str(actor) / "pdf" / "references" / "r.md"
    assert file.read_bytes() == b"old"
    if scenario == "changed_files":
        file.write_bytes(b"changed locally")
    elif scenario == "changed_source":
        source = await one_session.scalar(
            select(SkillLibrarySource).where(SkillLibrarySource.skill_id == installed.skill_id)
        )
        assert source is not None
        source.registry_id = "changed"
        await one_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario == "valid":
        await native.execute_library_import(one_session, actor, draft, receipt)
        assert receipt.committed and file.read_bytes() == b"new"
    else:
        with pytest.raises((CommandRejected, service.LibraryRefusal)):
            await native.execute_library_import(one_session, actor, draft, receipt)
        assert not receipt.committed and file.read_bytes() != b"new"


@pytest.mark.parametrize("timing", ["download", "registration"])
async def test_revocation_during_import_refuses_live_commit(
    one_session: AsyncSession,
    skill_dirs: Path,
    hub: FakeHub,
    monkeypatch: pytest.MonkeyPatch,
    timing: str,
) -> None:
    from src.core.exceptions import BaseAPIException
    from src.domains.agents.application import skill_library_import as native
    from src.domains.agents.application.skill_library_import_schemas import LibraryInstallInput
    from src.domains.skill_library import service

    for setting in ("application_tools_enabled", "skills_enabled", "skill_library_enabled"):
        monkeypatch.setattr(settings, setting, True)
    monkeypatch.setattr(native, "rate_limit_library", AsyncMock())
    actor = await _user(one_session)
    approved = hub.publish(REPO, "revocation", {"skills/pdf/SKILL.md": manifest("pdf")})
    draft = await native.prepare_library_install(
        one_session,
        actor,
        LibraryInstallInput(repository=REPO, path="skills/pdf", commit_sha=approved),
    )
    if timing == "download":
        original = service.download

        async def download(*args):
            result = await original(*args)
            monkeypatch.setattr(settings, "skills_enabled", False)
            return result

        monkeypatch.setattr(service, "download", download)
    else:
        original = service.SkillLibraryRepository.record

        async def record(*args):
            await original(*args)
            monkeypatch.setattr(settings, "skills_enabled", False)

        monkeypatch.setattr(service.SkillLibraryRepository, "record", record)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(BaseAPIException):
        await native.execute_library_import(one_session, actor, draft, receipt)
    assert not receipt.committed
    assert not (skill_dirs / "users" / str(actor) / "pdf" / "SKILL.md").exists()
