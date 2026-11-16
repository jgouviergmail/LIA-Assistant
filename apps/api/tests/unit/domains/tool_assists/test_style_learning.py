"""Learning the person's writing style at their click (ADR-383 amendment 2026-11-16).

The route reaches the assists' door with the person's language, runs the learning on the
door's own run (its config bills the call, its reading files the sent mail), through the
account's one learning at a time, in place of the record the person sees when the click
arrives, tells a mailbox's own failure in the page's words, and answers how it ended with
what it cost.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.runnables import RunnableConfig

from src.core.exceptions import ConnectorAPIError
from src.core.llm_usage import LLMUsage
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.agents.emails.writing_style import (
    Learning,
    LearningOutcome,
    SentMailUnreadable,
)
from src.domains.tool_assists import style_learning
from src.domains.tool_assists.catalogue import ToolAssist
from src.domains.tool_assists.door import Assisted, AssistRun

pytestmark = pytest.mark.unit


@dataclass
class _Person:
    id: UUID
    language: str = "fr-FR"


PERSON = _Person(id=uuid4())
COST = LLMUsage(tokens_in=900, tokens_out=60, cost_eur=0.02, model_name="m")
#: The run config the door hands its work: what bills the model call.
DOOR_CONFIG = RunnableConfig(metadata={"run": "the door's own"})
#: The record the person sees when the click arrives: the one the learning replaces.
SEEN = datetime(2026, 11, 13, 9, 30, 15, 123456, tzinfo=UTC)


@dataclass
class _Seen:
    """What reached the door, the account's one learning and the learning."""

    door: list[dict[str, Any]]
    flights: list[UUID]
    learned: list[dict[str, Any]]
    events: list[str]


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> _Seen:
    record = _Seen(door=[], flights=[], learned=[], events=[])

    async def door(
        assist: ToolAssist,
        user_id: UUID,
        language: str,
        work: Callable[[AssistRun], Awaitable[Learning]],
    ) -> Assisted[Learning]:
        record.events.append("door")
        record.door.append({"assist": assist, "user_id": user_id, "language": language})
        run = AssistRun(user_id, language, DOOR_CONFIG)
        return Assisted(await work(run), COST)

    async def one_at_a_time(user_id: UUID, learn: Callable[[], Awaitable[Learning]]) -> Learning:
        record.flights.append(user_id)
        return await learn()

    async def record_seen(user_id: UUID) -> datetime | None:
        record.events.append("record read")
        assert user_id == PERSON.id
        return SEEN

    monkeypatch.setattr(style_learning, "run_assist", door)
    monkeypatch.setattr(style_learning, "learn_one_at_a_time", one_at_a_time)
    monkeypatch.setattr(style_learning, "learned_record_at", record_seen)
    return record


def _learning(monkeypatch: pytest.MonkeyPatch, seen: _Seen, answer: Learning | Exception) -> None:
    async def learn(
        user_id: UUID, *, replaces: datetime | None, config: Any, reading: Any
    ) -> Learning:
        seen.learned.append(
            {"user_id": user_id, "replaces": replaces, "config": config, "reading": reading}
        )
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(style_learning, "learn_writing_style", learn)


@pytest.fixture
def app() -> Iterator[FastAPI]:
    application = FastAPI()
    application.include_router(style_learning.router)
    application.dependency_overrides[get_current_active_session_for_stream] = lambda: PERSON
    application.dependency_overrides[style_learning.rate_limit_style_learning] = lambda: None
    yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def test_a_click_learns_through_the_door_and_answers_what_it_cost(
    client: AsyncClient, seen: _Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    _learning(monkeypatch, seen, Learning("learned", 12))

    response = await client.post("/writing-style/learn")

    assert response.status_code == 200
    assert response.json() == {
        "outcome": "learned",
        "mails_read": 12,
        "usage": COST.model_dump(mode="json"),
    }
    assert seen.door == [
        {"assist": ToolAssist.WRITING_STYLE_LEARN, "user_id": PERSON.id, "language": "fr"}
    ]


async def test_the_learning_runs_on_the_doors_own_run(
    client: AsyncClient, seen: _Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its config bills the model call; its reading files the read of the sent mail."""
    _learning(monkeypatch, seen, Learning("learned", 12))

    await client.post("/writing-style/learn")

    (learned,) = seen.learned
    assert learned["user_id"] == PERSON.id
    assert learned["config"] is DOOR_CONFIG
    assert getattr(learned["reading"], "__func__", None) is AssistRun.reading


async def test_a_click_is_the_accounts_one_learning_at_a_time(
    client: AsyncClient, seen: _Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same claim the assistant's card takes: a second request waits, paying nothing."""
    _learning(monkeypatch, seen, Learning("learned", 12))

    await client.post("/writing-style/learn")

    assert seen.flights == [PERSON.id]


async def test_a_click_replaces_the_record_seen_when_it_arrived_and_nothing_since(
    client: AsyncClient, seen: _Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read before anything waits: a forget confirmed meanwhile is the person's later act."""
    _learning(monkeypatch, seen, Learning("learned", 12))

    await client.post("/writing-style/learn")

    (learned,) = seen.learned
    assert learned["replaces"] == SEEN
    assert seen.events == ["record read", "door"]


@pytest.mark.parametrize(
    "outcome", ["too_few", "no_mailbox", "reconnect", "switched_off", "superseded"]
)
async def test_a_learning_that_kept_nothing_says_why(
    client: AsyncClient, seen: _Seen, monkeypatch: pytest.MonkeyPatch, outcome: LearningOutcome
) -> None:
    _learning(monkeypatch, seen, Learning(outcome, 0))

    response = await client.post("/writing-style/learn")

    assert response.status_code == 200 and response.json()["outcome"] == outcome


async def test_a_mailbox_that_failed_is_told_in_the_pages_words(
    client: AsyncClient, seen: _Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = SentMailUnreadable("the sent folder could not be read")
    failed.__cause__ = ConnectorAPIError("google_gmail", 401, "unauthorized")
    _learning(monkeypatch, seen, failed)

    response = await client.post("/writing-style/learn")

    assert response.json()["detail"]["code"] == "reconnect_required"


async def test_a_mailbox_that_does_not_answer_is_said_unavailable_never_the_model(
    client: AsyncClient, seen: _Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = SentMailUnreadable("the sent folder could not be read")
    failed.__cause__ = ConnectionError("down")
    _learning(monkeypatch, seen, failed)

    response = await client.post("/writing-style/learn")

    assert response.json()["detail"]["code"] == "provider_unavailable"
