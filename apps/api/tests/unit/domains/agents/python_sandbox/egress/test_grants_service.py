"""The grants service: what the tool reads, what a card answer writes (ADR-298)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.python_sandbox.egress.grants import (
    Decision,
    EgressGrantService,
    decision_from_answer,
)

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


class FakeRepository:
    def __init__(self, *, count: int = 0, scopes: dict[str, bool] | None = None) -> None:
        self.count = count
        self.scopes = dict(scopes or {})
        self.upserts: list[tuple[str, bool]] = []
        self.touched: list[str] = []

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        return self.count

    async def scopes_for_user(self, user_id: uuid.UUID) -> dict[str, bool]:
        return dict(self.scopes)

    async def upsert(self, user_id: uuid.UUID, host: str, *, share_turn_data: bool) -> Any:
        self.upserts.append((host, share_turn_data))
        self.scopes[host] = share_turn_data
        return SimpleNamespace(id=uuid.uuid4(), host=host, share_turn_data=share_turn_data)

    async def touch(self, user_id: uuid.UUID, hosts: Any, *, when: datetime) -> None:
        self.touched.extend(hosts)


def _service(repo: FakeRepository, *, cap: int = 3) -> EgressGrantService:
    with patch(
        "src.domains.agents.python_sandbox.egress.grants.get_settings",
        return_value=SimpleNamespace(python_sandbox_max_grants_per_user=cap),
    ):
        return EgressGrantService(repository=repo)


class TestDecisionVocabulary:
    def test_the_three_answers_and_nothing_else(self) -> None:
        assert decision_from_answer("confirm") is Decision.WITH_DATA
        assert decision_from_answer("confirm_without_data") is Decision.WITHOUT_DATA
        assert decision_from_answer("cancel") is Decision.REFUSED
        with pytest.raises(ValueError):
            decision_from_answer("edit")


class TestRecordingADecision:
    async def test_an_allowed_host_is_upserted_with_its_scope(self) -> None:
        repo = FakeRepository(count=0)
        service = _service(repo)
        with patch(
            "src.domains.agents.python_sandbox.egress.grants.get_settings",
            return_value=SimpleNamespace(python_sandbox_max_grants_per_user=3),
        ):
            outcome = await service.record(
                USER, ["a.example.org", "b.example.org"], Decision.WITHOUT_DATA
            )
        assert repo.upserts == [("a.example.org", False), ("b.example.org", False)]
        assert outcome.one_shot is False
        assert outcome.share_turn_data is False

    async def test_at_the_cap_the_answer_holds_for_this_run_only(self) -> None:
        """Nothing is written; the run still gets what the person allowed."""
        repo = FakeRepository(count=3)
        service = _service(repo)
        with patch(
            "src.domains.agents.python_sandbox.egress.grants.get_settings",
            return_value=SimpleNamespace(python_sandbox_max_grants_per_user=3),
        ):
            outcome = await service.record(USER, ["new.example.org"], Decision.WITH_DATA)
        assert repo.upserts == []
        assert outcome.one_shot is True
        assert outcome.share_turn_data is True

    async def test_an_already_granted_host_is_updated_even_at_the_cap(self) -> None:
        """The cap bounds NEW rows; changing one's mind on a known host is free."""
        repo = FakeRepository(count=3, scopes={"known.example.org": True})
        service = _service(repo)
        with patch(
            "src.domains.agents.python_sandbox.egress.grants.get_settings",
            return_value=SimpleNamespace(python_sandbox_max_grants_per_user=3),
        ):
            outcome = await service.record(USER, ["known.example.org"], Decision.WITHOUT_DATA)
        assert repo.upserts == [("known.example.org", False)]
        assert outcome.one_shot is False

    async def test_a_refusal_writes_nothing(self) -> None:
        repo = FakeRepository()
        service = _service(repo)
        outcome = await service.record(USER, ["x.example.org"], Decision.REFUSED)
        assert repo.upserts == [] and outcome.allowed is False


class TestWhatTheToolReads:
    async def test_scopes_are_the_hosts_and_their_data_flag(self) -> None:
        repo = FakeRepository(scopes={"a.example.org": True, "b.example.org": False})
        assert await _service(repo).scopes(USER) == {"a.example.org": True, "b.example.org": False}

    async def test_a_run_stamps_the_grants_it_relied_on(self) -> None:
        repo = FakeRepository(scopes={"a.example.org": True})
        await _service(repo).mark_used(USER, ["a.example.org"], when=datetime.now(UTC))
        assert repo.touched == ["a.example.org"]


class TestMarkReliedGrants:
    """The one reading of « which hosts did this run rely on »: stored grants
    only — a connector or operator host has nothing to stamp, and a run with
    none opens no session at all."""

    async def test_only_grant_hosts_are_stamped(self) -> None:
        import uuid
        from unittest.mock import AsyncMock, patch

        from src.domains.agents.python_sandbox.egress.grants import mark_relied_grants
        from src.domains.agents.python_sandbox.egress.hosts import HostStatus

        user = uuid.uuid4()
        with patch(
            "src.domains.agents.python_sandbox.egress.grants.mark_grants_used", new=AsyncMock()
        ) as stamp:
            await mark_relied_grants(
                user,
                {
                    "api.search.brave.com": HostStatus.CONNECTOR,
                    "status.example.org": HostStatus.OPERATOR,
                    "feeds.example.net": HostStatus.GRANT,
                    "b.example": HostStatus.GRANT,
                },
            )
            stamp.assert_awaited_once_with(user, ["feeds.example.net", "b.example"])
            stamp.reset_mock()
            await mark_relied_grants(user, {"api.search.brave.com": HostStatus.CONNECTOR})
            stamp.assert_not_awaited()
