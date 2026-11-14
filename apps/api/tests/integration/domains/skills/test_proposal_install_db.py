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
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.conversation_target import ConversationRef
from src.domains.shared import action_sink
from src.domains.skills import proposal_service
from src.domains.skills.cache import SkillsCache
from src.domains.skills.import_commit import SkillImportCompletionUnknown, commit_skill_import
from src.domains.skills.models import Skill
from src.domains.skills.proposal_errors import STALE, ProposalRefusal
from src.domains.skills.proposals import SkillProposal
from src.infrastructure.streaming import run_admission, runtime_redis
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


async def test_lost_import_acknowledgement_never_replays_the_original_proposal(
    one_session,
    skill_dirs,
    redis_client,
    recorder,
    monkeypatch,
    target: ConversationRef,
) -> None:
    actor = target.owner_id
    proposal, _ = await _propose(
        target,
        {"SKILL.md": _manifest("Controlled instructions.")},
        redis=redis_client,
    )
    commits = 0

    async def lost_ack(db):
        nonlocal commits
        commits += 1
        await commit_skill_import(db)
        raise SkillImportCompletionUnknown()

    monkeypatch.setattr("src.domains.skills.import_service.commit_skill_import", lost_ack)
    for _ in range(2):
        with pytest.raises(ProposalRefusal) as error:
            await proposal_service.install(one_session, actor, proposal.id, redis=redis_client)
        assert error.value.code == "skill_proposal_completion_unknown"
    saved = await proposal_service.read(actor, proposal.id, redis=redis_client)
    assert saved.status == "unknown" and commits == 1
    assert (skill_dirs / "users" / str(actor) / "chat-made" / "SKILL.md").is_file()
    assert recorder.settled == [False]


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
async def target(
    async_engine: AsyncEngine, committed_user_ids: list[uuid.UUID], redis_client: Redis
) -> AsyncIterator[ConversationRef]:
    """Use an independently committed owner, then clean only its temporary proposal keys."""
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    yield target
    keys = [key async for key in redis_client.scan_iter(f"skill_proposal*{target.owner_id}*")]
    if keys:
        await redis_client.delete(*keys)


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
async def one_session(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, committed_user_ids: list[uuid.UUID]
) -> AsyncIterator[AsyncSession]:
    """Own the click's session; validation and authority use independent short transactions."""

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(proposal_service, "get_db_context", context)
    monkeypatch.setattr(run_admission, "get_db_context", context)
    monkeypatch.setattr(runtime_redis, "get_db_context", context)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        yield db


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    fake = _Recorder()
    monkeypatch.setattr(action_sink, "_recorder", fake)
    return fake


async def _propose(
    target: ConversationRef, files: dict[str, str], *, redis: Redis
) -> tuple[SkillProposal, int]:
    """Run preparation under real admission, then close it before the independent click."""
    async with run_admission.execution_for_turn(
        target.owner_id, target=target, admission=None, run_id=None, language=None
    ):
        return await proposal_service.propose(
            files, owner_id=target.owner_id, runtime_id=target.runtime_id, redis=redis
        )


async def _rows(db: AsyncSession, owner: uuid.UUID) -> list[Skill]:
    result = await db.execute(select(Skill).where(Skill.owner_id == owner))
    return list(result.scalars())


@pytest.mark.asyncio
async def test_the_click_installs_exactly_the_proposal(
    one_session: AsyncSession,
    skill_dirs: Path,
    redis_client: Redis,
    recorder: _Recorder,
    target: ConversationRef,
) -> None:
    me = target.owner_id
    files = {"SKILL.md": _manifest("Do the thing."), "references/notes.md": "# notes\n"}

    proposal, _ = await _propose(target, files, redis=redis_client)
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
    target: ConversationRef,
) -> None:
    me = target.owner_id
    first, _ = await _propose(target, {"SKILL.md": _manifest("v1")}, redis=redis_client)
    await proposal_service.install(one_session, me, first.id, redis=redis_client)

    second, _ = await _propose(
        target,
        {"SKILL.md": _manifest("v2"), "references/new.md": "new\n"},
        redis=redis_client,
    )
    third, _ = await _propose(target, {"SKILL.md": _manifest("v3")}, redis=redis_client)
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
