"""The feedback route composes what the module tests prove one helper at a time.

``test_response_feedback.py`` replays the route's flow by hand (``_submit``), so
nothing held the route itself: measured 2026-10-23, no suite executed it, nor the
efficacy seam it calls last (ADR-348, AC-030b). Through HTTP, against PostgreSQL:

- a message the person does not own is a 404 that hides it, and stays untouched;
- only the FIRST verdict reaches the journals (a change never re-feeds counters
  that have no decrement path);
- a thumbs-down comment becomes a correction, a thumbs-up one does not;
- the efficacy hook runs in a savepoint of its own: when it fails, its writes are
  taken back and the person's verdict stands.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.field_names import FIELD_RESPONSE_FEEDBACK
from src.core.session_dependencies import get_current_active_session
from src.domains.conversations import efficacy_feedback, response_feedback
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User
from src.main import app

pytestmark = pytest.mark.integration

TITLE = "Before any hook"


def _path(message_id: UUID) -> str:
    return f"/api/v1/conversations/me/messages/{message_id}/feedback"


async def _answer(db: AsyncSession, owner: UUID) -> UUID:
    """An ordinary assistant answer in the owner's one conversation, by its id.

    Ids, never instances: the assertions expire the session, and an expired
    instance would load itself synchronously outside the event loop.
    """
    db.add(Conversation(id=owner, user_id=owner, title=TITLE, message_count=0, total_tokens=0))
    await db.commit()
    message = ConversationMessage(
        conversation_id=owner, role="assistant", content="Here it is.", message_metadata={}
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message.id


async def _feedback(db: AsyncSession, message_id: UUID) -> object:
    db.expire_all()
    row = await db.get(ConversationMessage, message_id)
    assert row is not None
    return (row.message_metadata or {}).get(FIELD_RESPONSE_FEEDBACK)


async def _title(db: AsyncSession, owner: UUID) -> str | None:
    db.expire_all()
    return (
        await db.execute(select(Conversation.title).where(Conversation.id == owner))
    ).scalar_one()


@pytest.fixture
async def signed_in(test_user: User) -> AsyncIterator[UUID]:
    """The signed-in account, by its id."""

    def current() -> User:
        return test_user

    app.dependency_overrides[get_current_active_session] = current
    yield test_user.id
    app.dependency_overrides.pop(get_current_active_session, None)


class _Recorder:
    """The efficacy seam's implementation, writing nothing and remembering each call."""

    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID, str]] = []

    async def apply(self, db: AsyncSession, user_id: UUID, message_id: UUID, verdict: str) -> None:
        self.calls.append((user_id, message_id, verdict))


class _FailsAfterWriting:
    """An implementation that writes, then fails before its own work is done."""

    async def apply(self, db: AsyncSession, user_id: UUID, message_id: UUID, verdict: str) -> None:
        await db.execute(
            update(Conversation).where(Conversation.id == user_id).values(title="written")
        )
        raise RuntimeError("efficacy store unavailable")


def _record(monkeypatch: pytest.MonkeyPatch, name: str, returns: object) -> list[tuple[Any, ...]]:
    """Record the route's calls of a journals helper; its effects are the module tests'."""
    calls: list[tuple[Any, ...]] = []

    async def recorded(*args: Any, **_: Any) -> object:
        calls.append(args)
        return returns

    monkeypatch.setattr(response_feedback, name, recorded)
    return calls


async def test_a_message_the_person_does_not_own_is_not_found_and_untouched(
    async_client: AsyncClient, async_session: AsyncSession, signed_in: UUID
) -> None:
    stranger = User(
        email="stranger@test.local", hashed_password="x", is_active=True, is_superuser=False
    )
    async_session.add(stranger)
    await async_session.commit()
    theirs = await _answer(async_session, stranger.id)

    response = await async_client.post(_path(theirs), json={"verdict": "thumbs_up"})

    assert response.status_code == 404
    assert await _feedback(async_session, theirs) is None


async def test_only_the_first_verdict_reaches_the_journals(
    async_client: AsyncClient,
    async_session: AsyncSession,
    signed_in: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(efficacy_feedback, "_hooks", None)
    journals = _record(monkeypatch, "apply_verdict_to_journals", 0)
    answer = await _answer(async_session, signed_in)

    first = await async_client.post(_path(answer), json={"verdict": "thumbs_up"})
    changed = await async_client.post(_path(answer), json={"verdict": "thumbs_down"})

    assert (first.status_code, changed.status_code) == (200, 200)
    assert len(journals) == 1, "a verdict change re-fed counters that cannot decrement"
    assert await _feedback(async_session, answer) == {"verdict": "thumbs_down"}


@pytest.mark.parametrize(
    ("verdict", "comment", "corrections"),
    [
        ("thumbs_down", "  Too long  ", ["Too long"]),
        ("thumbs_up", "Nice", []),
        ("thumbs_down", "   ", []),
    ],
)
async def test_only_a_thumbs_down_comment_becomes_a_correction(
    async_client: AsyncClient,
    async_session: AsyncSession,
    signed_in: UUID,
    monkeypatch: pytest.MonkeyPatch,
    verdict: str,
    comment: str,
    corrections: list[str],
) -> None:
    monkeypatch.setattr(efficacy_feedback, "_hooks", None)
    recorded = _record(monkeypatch, "record_comment_as_correction", None)
    answer = await _answer(async_session, signed_in)

    response = await async_client.post(_path(answer), json={"verdict": verdict, "comment": comment})

    assert response.status_code == 200
    assert [args[2] for args in recorded] == corrections
    stored = await _feedback(async_session, answer)
    assert stored == (
        {"verdict": verdict, "comment": comment.strip()}
        if comment.strip()
        else {"verdict": verdict}
    )


async def test_the_efficacy_seam_receives_the_verdict(
    async_client: AsyncClient,
    async_session: AsyncSession,
    signed_in: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hooks = _Recorder()
    monkeypatch.setattr(efficacy_feedback, "_hooks", hooks)
    answer = await _answer(async_session, signed_in)

    response = await async_client.post(_path(answer), json={"verdict": "thumbs_up"})

    assert response.status_code == 200
    assert hooks.calls == [(signed_in, answer, "thumbs_up")]


async def test_a_failing_efficacy_hook_takes_its_writes_back_and_the_verdict_stands(
    async_client: AsyncClient,
    async_session: AsyncSession,
    signed_in: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(efficacy_feedback, "_hooks", _FailsAfterWriting())
    answer = await _answer(async_session, signed_in)

    response = await async_client.post(_path(answer), json={"verdict": "thumbs_down"})

    assert response.status_code == 200
    assert await _feedback(async_session, answer) == {"verdict": "thumbs_down"}
    assert await _title(async_session, signed_in) == TITLE
