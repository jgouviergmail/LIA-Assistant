"""Proposing a skill from the chat, and installing it at the person's click (ADR-327).

The model proposes; only the card's button installs. These tests pin what the
click may and may not do: install what was validated, refuse a version the
card never described, never install twice, and record the act in the register
only once every refusal has had its say. The Redis script itself (the cap and
the eviction) is proven on a real server in the integration suite.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.exceptions import BaseAPIException, ValidationError
from src.domains.shared import action_sink
from src.domains.skills import proposal_service
from src.domains.skills.proposal_errors import (
    BUSY,
    DISABLED,
    NAME_TAKEN,
    NOT_FOUND,
    QUOTA_REACHED,
    STALE,
    UNAVAILABLE,
    ProposalRefusal,
)
from src.domains.skills.proposals import (
    _SAVE_SCRIPT,
    ProposalChanges,
    ProposalStore,
    SkillProposal,
    _pending_proposals,
    package_fingerprint,
)
from src.infrastructure.locks.redis_claim import RELEASE_SCRIPT

pytestmark = pytest.mark.unit

OWNER = uuid4()
NOW = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
FILES = {"SKILL.md": "---\nname: ma-skill\n---\nbody\n", "references/r.md": "ref\n"}


class FakeRedis:
    """The commands the proposal store and the claim send — no Lua semantics."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.fail = False

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise ConnectionError("down")
        return self.keys.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
        xx: bool = False,
        keepttl: bool = False,
    ) -> bool | None:
        if self.fail:
            raise ConnectionError("down")
        if (nx and key in self.keys) or (xx and key not in self.keys):
            return None
        self.keys[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *args: Any) -> int:
        if script == _SAVE_SCRIPT:
            self.keys[str(args[1])] = str(args[3])
            return 0
        if script == RELEASE_SCRIPT:
            key, token = str(args[0]), str(args[1])
            if self.keys.get(key) == token:
                del self.keys[key]
                return 1
            return 0
        raise NotImplementedError(script[:30])


class FakeRecorder:
    """The register's side of the action seam, recording what it was told."""

    def __init__(self) -> None:
        self.claims: list[dict[str, Any]] = []
        self.settled: list[bool] = []

    async def claim(self, *, user_id: Any, capability: str, arguments: dict[str, str]) -> object:
        self.claims.append({"user_id": user_id, "capability": capability, **arguments})
        return object()

    async def settle(self, ticket: Any, *, succeeded: bool) -> None:
        self.settled.append(succeeded)


class _Db:
    async def __aenter__(self) -> MagicMock:
        return MagicMock()

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def recorder() -> FakeRecorder:
    fake = FakeRecorder()
    action_sink.install_action_recorder(fake)
    return fake


@pytest.fixture
def service_settings() -> Iterator[SimpleNamespace]:
    values = SimpleNamespace(
        skills_chat_import_enabled=True,
        skill_proposal_ttl_seconds=3600,
        skill_proposals_max_per_user=5,
    )
    with patch.object(proposal_service, "settings", values):
        yield values


@pytest.fixture
def importer() -> Iterator[MagicMock]:
    service = MagicMock()
    service.validate_files = AsyncMock(return_value={"name": "ma-skill", "description": "Useful."})
    service.import_files = AsyncMock(return_value={"name": "ma-skill"})
    with (
        patch.object(proposal_service, "SkillImportService", return_value=service),
        patch.object(proposal_service, "get_db_context", return_value=_Db()),
    ):
        yield service


def _installed_skill(tmp_path: Path, files: dict[str, str]) -> dict[str, str]:
    """A skill of the person's own on disk, as the cache names it."""
    folder = tmp_path / "ma-skill"
    for relative, text in files.items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_text(text, encoding="utf-8")
    return {"name": "ma-skill", "source_path": str(folder / "SKILL.md")}


def _cache(entry: dict[str, str] | None) -> Any:
    return patch("src.domains.skills.cache.SkillsCache.get_exact", return_value=entry)


def _proposal(**overrides: Any) -> SkillProposal:
    values: dict[str, Any] = {
        "id": "p" * 32,
        "owner_id": str(OWNER),
        "name": "ma-skill",
        "description": "Useful.",
        "files": dict(FILES),
        "sizes": {path: len(text) for path, text in FILES.items()},
        "created_at": NOW.isoformat(),
        "expires_at": NOW.isoformat(),
        "replaces": None,
        "changes": None,
    }
    values.update(overrides)
    return SkillProposal(**values)


async def _stored(redis: FakeRedis, proposal: SkillProposal) -> None:
    await ProposalStore(redis).save(proposal, ttl_seconds=60, max_per_owner=5, now=0)


class TestPropose:
    async def test_a_new_skill_is_kept_and_its_card_queued(
        self, redis: FakeRedis, importer: MagicMock, service_settings: SimpleNamespace
    ) -> None:
        with _cache(None):
            proposal, _ = await proposal_service.propose(
                FILES, owner_id=OWNER, conversation_id="conv", now=NOW, redis=redis
            )

        assert proposal.replaces is None and proposal.changes is None
        assert proposal.expires_at == "2026-09-30T11:00:00+00:00"
        assert await ProposalStore(redis).load(str(OWNER), proposal.id) == proposal
        assert [p.id for p in _pending_proposals.peek("conv")] == [proposal.id]
        importer.validate_files.assert_awaited_once_with(FILES, owner_id=OWNER)
        importer.import_files.assert_not_awaited()

    async def test_a_replacement_names_the_version_it_replaces(
        self,
        tmp_path: Path,
        redis: FakeRedis,
        importer: MagicMock,
        service_settings: SimpleNamespace,
    ) -> None:
        installed = {"SKILL.md": "old\n", "references/gone.md": "g\n"}
        with _cache(_installed_skill(tmp_path, installed)):
            proposal, _ = await proposal_service.propose(
                FILES, owner_id=OWNER, conversation_id="conv", now=NOW, redis=redis
            )

        assert proposal.replaces == package_fingerprint(installed)
        assert proposal.changes == ProposalChanges(
            added=("references/r.md",), modified=("SKILL.md",), removed=("references/gone.md",)
        )

    async def test_a_refused_package_is_neither_kept_nor_shown(
        self, redis: FakeRedis, importer: MagicMock, service_settings: SimpleNamespace
    ) -> None:
        importer.validate_files.side_effect = ValidationError(detail="declares a missing file")

        with _cache(None), pytest.raises(ValidationError):
            await proposal_service.propose(
                FILES, owner_id=OWNER, conversation_id="conv", now=NOW, redis=redis
            )

        assert redis.keys == {}
        assert _pending_proposals.peek("conv") == []

    async def test_a_cache_that_fails_offers_nothing(
        self, redis: FakeRedis, importer: MagicMock, service_settings: SimpleNamespace
    ) -> None:
        redis.eval = AsyncMock(side_effect=ConnectionError("down"))  # type: ignore[method-assign]

        with _cache(None), pytest.raises(ConnectionError):
            await proposal_service.propose(
                FILES, owner_id=OWNER, conversation_id="conv", now=NOW, redis=redis
            )

        assert _pending_proposals.peek("conv") == []


class TestInstall:
    async def test_installs_what_was_proposed_and_records_the_act(
        self,
        redis: FakeRedis,
        importer: MagicMock,
        recorder: FakeRecorder,
        service_settings: SimpleNamespace,
    ) -> None:
        proposal = _proposal()
        await _stored(redis, proposal)

        with _cache(None):
            installed = await proposal_service.install(MagicMock(), OWNER, proposal.id, redis=redis)

        assert installed.status == "installed"
        importer.import_files.assert_awaited_once_with(FILES, owner_id=OWNER)
        assert recorder.claims == [
            {"user_id": OWNER, "capability": "skill_proposal_install", "target": "ma-skill"}
        ]
        assert recorder.settled == [True]
        stored = await ProposalStore(redis).load(str(OWNER), proposal.id)
        assert stored is not None and stored.status == "installed" and stored.files == {}
        assert not [k for k in redis.keys if k.startswith("skill_proposal_claim")]

    async def test_a_second_click_installs_nothing(
        self,
        redis: FakeRedis,
        importer: MagicMock,
        recorder: FakeRecorder,
        service_settings: SimpleNamespace,
    ) -> None:
        await _stored(redis, _proposal().installed())

        installed = await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert installed.status == "installed"
        importer.import_files.assert_not_awaited()
        assert recorder.claims == []

    async def test_another_accounts_proposal_is_not_found(
        self, redis: FakeRedis, importer: MagicMock, service_settings: SimpleNamespace
    ) -> None:
        await _stored(redis, _proposal())

        with pytest.raises(ProposalRefusal) as refused:
            await proposal_service.install(MagicMock(), UUID(int=7), "p" * 32, redis=redis)

        assert refused.value.code == NOT_FOUND

    async def test_switched_off_chat_skills_install_nothing(
        self, redis: FakeRedis, importer: MagicMock, service_settings: SimpleNamespace
    ) -> None:
        service_settings.skills_chat_import_enabled = False
        await _stored(redis, _proposal())

        with pytest.raises(ProposalRefusal) as refused:
            await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert refused.value.code == DISABLED
        importer.import_files.assert_not_awaited()

    async def test_an_install_in_flight_refuses_the_other_click(
        self, redis: FakeRedis, importer: MagicMock, service_settings: SimpleNamespace
    ) -> None:
        await _stored(redis, _proposal())
        redis.keys[f"skill_proposal_claim:{OWNER}:{'p' * 32}"] = "someone-else"

        with pytest.raises(ProposalRefusal) as refused:
            await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert refused.value.code == BUSY
        importer.import_files.assert_not_awaited()
        # The other holder's claim is never released by the loser.
        assert redis.keys[f"skill_proposal_claim:{OWNER}:{'p' * 32}"] == "someone-else"

    async def test_a_skill_that_appeared_since_is_stale(
        self,
        tmp_path: Path,
        redis: FakeRedis,
        importer: MagicMock,
        recorder: FakeRecorder,
        service_settings: SimpleNamespace,
    ) -> None:
        await _stored(redis, _proposal())

        with _cache(_installed_skill(tmp_path, {"SKILL.md": "another\n"})):
            with pytest.raises(ProposalRefusal) as refused:
                await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert refused.value.code == STALE
        importer.import_files.assert_not_awaited()
        assert recorder.claims == []
        assert not [k for k in redis.keys if k.startswith("skill_proposal_claim")]

    async def test_a_replaced_skill_that_changed_since_is_stale(
        self,
        tmp_path: Path,
        redis: FakeRedis,
        importer: MagicMock,
        service_settings: SimpleNamespace,
    ) -> None:
        described = {"SKILL.md": "v1\n"}
        await _stored(redis, _proposal(replaces=package_fingerprint(described)))

        with _cache(_installed_skill(tmp_path, {"SKILL.md": "v2\n"})):
            with pytest.raises(ProposalRefusal) as refused:
                await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert refused.value.code == STALE

    async def test_the_described_version_is_replaced(
        self,
        tmp_path: Path,
        redis: FakeRedis,
        importer: MagicMock,
        recorder: FakeRecorder,
        service_settings: SimpleNamespace,
    ) -> None:
        described = {"SKILL.md": "v1\n"}
        await _stored(redis, _proposal(replaces=package_fingerprint(described)))

        with _cache(_installed_skill(tmp_path, described)):
            await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        importer.import_files.assert_awaited_once()
        assert recorder.settled == [True]

    async def test_an_install_whose_record_was_lost_is_done_not_stale(
        self,
        tmp_path: Path,
        redis: FakeRedis,
        importer: MagicMock,
        recorder: FakeRecorder,
        service_settings: SimpleNamespace,
    ) -> None:
        """The skill on disk IS the proposal: an earlier click installed it."""
        await _stored(redis, _proposal())

        with _cache(_installed_skill(tmp_path, FILES)):
            installed = await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert installed.status == "installed"
        importer.import_files.assert_not_awaited()
        assert recorder.claims == []

    async def test_a_refusal_before_the_act_is_never_recorded(
        self,
        redis: FakeRedis,
        importer: MagicMock,
        recorder: FakeRecorder,
        service_settings: SimpleNamespace,
    ) -> None:
        importer.validate_files.side_effect = BaseAPIException(status_code=429, detail="quota")
        await _stored(redis, _proposal())

        with _cache(None), pytest.raises(ProposalRefusal) as refused:
            await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert refused.value.code == QUOTA_REACHED
        assert recorder.claims == []

    async def test_a_write_lost_to_a_concurrent_change_settles_as_a_failure(
        self,
        redis: FakeRedis,
        importer: MagicMock,
        recorder: FakeRecorder,
        service_settings: SimpleNamespace,
    ) -> None:
        importer.import_files.side_effect = BaseAPIException(status_code=409, detail="taken")
        await _stored(redis, _proposal())

        with _cache(None), pytest.raises(ProposalRefusal) as refused:
            await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert refused.value.code == NAME_TAKEN
        assert recorder.settled == [False]
        stored = await ProposalStore(redis).load(str(OWNER), "p" * 32)
        assert stored is not None and stored.status == "pending"

    async def test_an_unreachable_cache_is_named(
        self, redis: FakeRedis, importer: MagicMock, service_settings: SimpleNamespace
    ) -> None:
        redis.fail = True

        with pytest.raises(ProposalRefusal) as refused:
            await proposal_service.install(MagicMock(), OWNER, "p" * 32, redis=redis)

        assert refused.value.code == UNAVAILABLE
