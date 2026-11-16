"""The one door a model surface reads the opted-in health context through."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from structlog.testing import capture_logs

from src.domains.health_metrics import prompt_context

pytestmark = pytest.mark.unit

_SECRET = "row 42 holds the person's words"


@dataclass
class _User:
    """The two attributes the door reads of an account."""

    health_metrics_agents_enabled: bool
    timezone: str = "Asia/Tokyo"


class _Session:
    """A session nobody queries directly: the repository and service are fakes."""


class _World:
    """What the door met: the session opened, the account, the service's answer."""

    def __init__(self, user: _User | None, *, answer: str = "", fail: bool = False) -> None:
        self.user = user
        self.answer = answer
        self.fail = fail
        self.sessions = 0
        self.asked: list[tuple[UUID, ZoneInfo]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        world = self

        @asynccontextmanager
        async def db_context() -> AsyncIterator[_Session]:
            world.sessions += 1
            yield _Session()

        class _Users:
            def __init__(self, db: _Session) -> None:
                del db

            async def get_by_id(self, user_id: UUID) -> _User | None:
                del user_id
                return world.user

        class _Service:
            def __init__(self, db: _Session) -> None:
                del db

            async def build_health_context_for_prompt(
                self, user_id: UUID, *, zone: ZoneInfo
            ) -> str:
                if world.fail:
                    raise RuntimeError(_SECRET)
                world.asked.append((user_id, zone))
                return world.answer

        monkeypatch.setattr(prompt_context, "get_db_context", db_context)
        monkeypatch.setattr(prompt_context, "UserRepository", _Users)
        monkeypatch.setattr(prompt_context, "HealthMetricsService", _Service)


@pytest.fixture
def switched_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt_context.settings, "health_metrics_enabled", True)


async def test_the_instance_switch_off_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(_User(True), answer="steps: 9000")
    world.install(monkeypatch)
    monkeypatch.setattr(prompt_context.settings, "health_metrics_enabled", False)

    assert await prompt_context.opted_in_health_context(uuid4(), surface="test") == ""
    assert world.sessions == 0


@pytest.mark.usefixtures("switched_on")
async def test_an_unknown_account_has_no_context(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(None, answer="steps: 9000")
    world.install(monkeypatch)

    assert await prompt_context.opted_in_health_context(uuid4(), surface="test") == ""
    assert world.asked == []


@pytest.mark.usefixtures("switched_on")
async def test_a_person_who_did_not_opt_in_has_no_context(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(_User(False), answer="steps: 9000")
    world.install(monkeypatch)

    assert await prompt_context.opted_in_health_context(uuid4(), surface="test") == ""
    assert world.asked == []


@pytest.mark.usefixtures("switched_on")
async def test_an_opted_in_person_gets_the_block_read_in_their_zone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(_User(True), answer="steps: 9000")
    world.install(monkeypatch)
    owner = uuid4()

    assert await prompt_context.opted_in_health_context(owner, surface="test") == "steps: 9000"
    assert world.asked == [(owner, ZoneInfo("Asia/Tokyo"))]
    assert world.sessions == 1


@pytest.mark.usefixtures("switched_on")
async def test_a_failure_leaves_the_context_out_and_logs_its_type_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(_User(True), fail=True)
    world.install(monkeypatch)

    with capture_logs() as logs:
        answer = await prompt_context.opted_in_health_context(uuid4(), surface="journal")

    assert answer == ""
    failures = [line for line in logs if line["event"] == "health_prompt_context_failed"]
    assert len(failures) == 1
    assert failures[0]["surface"] == "journal"
    assert failures[0]["error_type"] == "RuntimeError"
    assert _SECRET not in repr(failures[0])
