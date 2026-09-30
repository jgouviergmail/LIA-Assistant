"""A skill written in the chat, proposed then installed by the click, on PostgreSQL + Redis (ADR-327).

The unit tests record what the service ASKS for; this one lets the real import
pipeline answer: the ``skills`` row registered for the person with the
``authored`` provenance, the files on disk, the replacement that upserts the
same row, the refusal of a version the card never described — against the
real partial unique indexes, the real Redis script and the real disk.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.shared import action_sink
from src.domains.skills import proposal_service
from src.domains.skills.cache import SkillsCache
from src.domains.skills.models import Skill
from src.domains.skills.proposal_errors import STALE, ProposalRefusal
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


def _manifest(body: str) -> str:
    return (
        "---\nname: chat-made\ndescription: >\n  Does something useful for this test.\n"
        f"category: test\npriority: 50\n---\n\n# Chat made\n\n{body}\n"
    )


class _Recorder:
    """The action register's seam, recording in memory (the real one commits apart)."""

    def __init__(self) -> None:
        self.settled: list[bool] = []

    async def claim(self, *, user_id: Any, capability: str, arguments: dict[str, str]) -> object:
        return object()

    async def settle(self, ticket: Any, *, succeeded: bool) -> None:
        self.settled.append(succeeded)


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as exc:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {exc}")
    yield redis
    await redis.aclose()


@pytest.fixture()
def skill_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Skills written under a throwaway tree; the cache restored afterwards."""
    (tmp_path / "system").mkdir()
    (tmp_path / "users").mkdir()
    monkeypatch.setattr(settings, "skills_system_path", str(tmp_path / "system"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "users"))
    monkeypatch.setattr(settings, "skills_chat_import_enabled", True)
    saved = SkillsCache._skills, SkillsCache._loaded
    try:
        yield tmp_path
    finally:
        SkillsCache._skills, SkillsCache._loaded = saved


@pytest.fixture()
def one_session(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """The proposal's short validation session is the test's (rolled back at the end)."""

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(proposal_service, "get_db_context", context)
    return async_session


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    fake = _Recorder()
    monkeypatch.setattr(action_sink, "_recorder", fake)
    return fake


async def _user(db: AsyncSession) -> uuid.UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    return user.id


async def _rows(db: AsyncSession, owner: uuid.UUID) -> list[Skill]:
    result = await db.execute(select(Skill).where(Skill.owner_id == owner))
    return list(result.scalars())


@pytest.mark.asyncio
async def test_the_click_installs_exactly_the_proposal(
    one_session: AsyncSession,
    skill_dirs: Path,
    redis_client: Redis,
    recorder: _Recorder,
) -> None:
    me = await _user(one_session)
    files = {"SKILL.md": _manifest("Do the thing."), "references/notes.md": "# notes\n"}

    proposal, _ = await proposal_service.propose(
        files, owner_id=me, conversation_id=f"conv-{me}", redis=redis_client
    )
    assert await _rows(one_session, me) == [], "a proposal registered a skill"

    installed = await proposal_service.install(one_session, me, proposal.id, redis=redis_client)

    assert installed.status == "installed"
    rows = await _rows(one_session, me)
    assert [(r.name, r.provenance) for r in rows] == [("chat-made", "authored")]
    folder = skill_dirs / "users" / str(me) / "chat-made"
    assert (folder / "references" / "notes.md").read_text(encoding="utf-8") == "# notes\n"
    assert recorder.settled == [True]

    again = await proposal_service.install(one_session, me, proposal.id, redis=redis_client)
    assert again.status == "installed"
    count = await one_session.scalar(
        select(func.count()).select_from(Skill).where(Skill.owner_id == me)
    )
    assert count == 1
    assert recorder.settled == [True], "a second click acted again"


@pytest.mark.asyncio
async def test_a_replacement_installs_the_described_version_and_nothing_older(
    one_session: AsyncSession,
    skill_dirs: Path,
    redis_client: Redis,
    recorder: _Recorder,
) -> None:
    me = await _user(one_session)
    first, _ = await proposal_service.propose(
        {"SKILL.md": _manifest("v1")}, owner_id=me, conversation_id="c", redis=redis_client
    )
    await proposal_service.install(one_session, me, first.id, redis=redis_client)

    second, _ = await proposal_service.propose(
        {"SKILL.md": _manifest("v2"), "references/new.md": "new\n"},
        owner_id=me,
        conversation_id="c",
        redis=redis_client,
    )
    third, _ = await proposal_service.propose(
        {"SKILL.md": _manifest("v3")}, owner_id=me, conversation_id="c", redis=redis_client
    )
    assert second.changes is not None
    assert second.changes.added == ("references/new.md",)
    assert second.changes.modified == ("SKILL.md",)

    await proposal_service.install(one_session, me, second.id, redis=redis_client)

    # The third card described v1: v2 is installed now, so it must not overwrite it.
    with pytest.raises(ProposalRefusal) as refused:
        await proposal_service.install(one_session, me, third.id, redis=redis_client)
    assert refused.value.code == STALE
    folder = skill_dirs / "users" / str(me) / "chat-made"
    assert "v2" in (folder / "SKILL.md").read_text(encoding="utf-8")
    assert len(await _rows(one_session, me)) == 1
