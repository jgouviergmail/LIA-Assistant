"""A library skill installed and updated through the REAL import pipeline, on PostgreSQL (ADR-327).

The network is the fake hub; everything the account keeps is real: the
``skills`` row the import registers with the ``library`` provenance, the
``skill_library_sources`` row written in the SAME transaction, the upsert an
update makes, the files on disk, the conflicts read from the database and the
cascade when the skill is removed. Only a real database executes the partial
unique indexes, the provenance CHECK and ``ON CONFLICT`` — a mocked repository
would accept anything.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.web_fetch import url_validator
from src.domains.skill_library import cache, service
from src.domains.skill_library.errors import NAME_TAKEN, LibraryRefusal
from src.domains.skill_library.models import SkillLibrarySource
from src.domains.skill_library.repository import SkillLibraryRepository, SourceRecord
from src.domains.skill_library.schemas import LibraryInstallRequest
from src.domains.skills.cache import SkillsCache
from src.domains.skills.models import Skill
from src.domains.skills.preference_service import SkillPreferenceService
from tests.fixtures.factories import UserFactory
from tests.unit.domains.skill_library.fakes import FakeHub, manifest

pytestmark = pytest.mark.integration

REPO = "acme/skills"


async def _user(db: AsyncSession) -> uuid.UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    return user.id


def _record(**overrides: str) -> SourceRecord:
    base = {
        "portal": "skills_sh",
        "origin": "github",
        "repository": REPO,
        "ref": "HEAD",
        "path": "skills/pdf",
        "registry_id": f"{REPO}/pdf",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
    }
    return SourceRecord(**{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture()
def skill_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Skills written under a throwaway tree; the cache restored afterwards."""
    from src.core.config import settings

    (tmp_path / "system").mkdir()
    (tmp_path / "users").mkdir()
    monkeypatch.setattr(settings, "skills_system_path", str(tmp_path / "system"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "users"))
    saved = SkillsCache._skills, SkillsCache._loaded
    try:
        yield tmp_path
    finally:
        SkillsCache._skills, SkillsCache._loaded = saved


@pytest.fixture()
def one_session(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """Every short session the service opens is the test's (rolled back at the end)."""

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(service, "get_db_context", context)
    return async_session


@pytest.fixture()
def hub(monkeypatch: pytest.MonkeyPatch) -> FakeHub:
    fake = FakeHub()
    monkeypatch.setattr(service, "_client", fake.client)
    monkeypatch.setattr(url_validator, "_resolve_dns_sync", lambda _h: ["93.184.216.34"])

    async def nothing(_key: str) -> None:
        return None

    async def keep_nothing(_key: str, _value: object, _ttl: int) -> None:
        return None

    monkeypatch.setattr(cache, "cached", nothing)
    monkeypatch.setattr(cache, "store", keep_nothing)
    return fake


class TestTheProvenanceRecord:
    @pytest.mark.asyncio
    async def test_an_update_replaces_the_row_it_does_not_add_one(
        self, async_session: AsyncSession
    ) -> None:
        me = await _user(async_session)
        skill = await SkillPreferenceService(async_session).create_skill_for_import(
            name="pdf", description="d", is_system=False, owner_id=me, provenance=None
        )
        skill.provenance = "library"
        await async_session.flush()
        repo = SkillLibraryRepository(async_session)
        await repo.record(skill.id, _record())
        await repo.record(skill.id, _record(commit_sha="c" * 40))

        rows = (
            (
                await async_session.execute(
                    select(SkillLibrarySource).where(SkillLibrarySource.skill_id == skill.id)
                )
            )
            .scalars()
            .all()
        )
        assert [r.commit_sha for r in rows] == ["c" * 40]

    @pytest.mark.asyncio
    async def test_another_account_s_installation_reads_as_absent(
        self, async_session: AsyncSession
    ) -> None:
        me, them = await _user(async_session), await _user(async_session)
        skill = await SkillPreferenceService(async_session).create_skill_for_import(
            name="pdf", description="d", is_system=False, owner_id=them, provenance=None
        )
        skill.provenance = "library"
        await async_session.flush()
        await SkillLibraryRepository(async_session).record(skill.id, _record())

        repo = SkillLibraryRepository(async_session)
        assert await repo.installed(me) == []
        assert await repo.installed_skill(me, skill.id) is None
        assert [s.name for s in await repo.installed(them)] == ["pdf"]


class TestInstallingThroughThePipeline:
    @pytest.mark.asyncio
    async def test_install_then_update_then_remove(
        self, one_session: AsyncSession, skill_dirs: Path, hub: FakeHub
    ) -> None:
        me = await _user(one_session)
        files = {"skills/pdf/SKILL.md": manifest("pdf"), "skills/pdf/references/r.md": b"v1"}
        first = hub.publish(REPO, "v1", files)

        installed = await service.install(
            me,
            LibraryInstallRequest(
                repository=REPO, path="skills/pdf", commit_sha=first, portal="skills_sh"
            ),
        )
        skill = await one_session.get(Skill, installed.skill_id)
        assert skill is not None and (skill.owner_id, skill.provenance) == (me, "library")
        on_disk = skill_dirs / "users" / str(me) / "pdf" / "references" / "r.md"
        assert on_disk.read_bytes() == b"v1"

        second = hub.publish(REPO, "v2", {**files, "skills/pdf/references/r.md": b"v2"})
        (row,) = await SkillLibraryRepository(one_session).installed(me)
        assert row.commit_sha == first

        updated = await service.update(me, installed.skill_id, second)
        assert updated.skill_id == installed.skill_id
        (row,) = await SkillLibraryRepository(one_session).installed(me)
        assert (row.commit_sha, row.tree_sha) == (second, hub.tree_sha(REPO, second, "skills/pdf"))
        assert on_disk.read_bytes() == b"v2"

        await one_session.execute(delete(Skill).where(Skill.id == installed.skill_id))
        await one_session.flush()
        left = await one_session.execute(
            select(SkillLibrarySource).where(SkillLibrarySource.skill_id == installed.skill_id)
        )
        assert left.first() is None

    @pytest.mark.asyncio
    async def test_a_name_the_person_already_wrote_is_not_taken_over(
        self, one_session: AsyncSession, skill_dirs: Path, hub: FakeHub
    ) -> None:
        me = await _user(one_session)
        await SkillPreferenceService(one_session).create_skill_for_import(
            name="pdf", description="mine", is_system=False, owner_id=me, provenance=None
        )
        commit = hub.publish(REPO, "v1", {"skills/pdf/SKILL.md": manifest("pdf")})

        with pytest.raises(LibraryRefusal) as refused:
            await service.install(
                me, LibraryInstallRequest(repository=REPO, path="skills/pdf", commit_sha=commit)
            )
        assert refused.value.code == NAME_TAKEN

    @pytest.mark.asyncio
    async def test_a_system_name_is_never_shadowed_by_a_library_skill(
        self, one_session: AsyncSession, skill_dirs: Path, hub: FakeHub
    ) -> None:
        me = await _user(one_session)
        await SkillPreferenceService(one_session).create_skill_for_import(
            name="briefing", description="system", is_system=True, owner_id=None
        )
        commit = hub.publish(REPO, "v1", {"SKILL.md": manifest("briefing")})

        with pytest.raises(LibraryRefusal) as refused:
            await service.install(me, LibraryInstallRequest(repository=REPO, commit_sha=commit))
        assert refused.value.code == NAME_TAKEN
