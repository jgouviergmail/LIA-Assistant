"""The habit proposals routes over HTTP, on a real PostgreSQL (ADR-375).

The account is read on the request's own session, as production does, so the
routes run inside the transaction they really run in. What is pinned here is
the HTTP contract the cards read: the page and its exact total, « learning is
off » said rather than an empty page, a stranger's proposal answered as
absent, a refused act answered 409 with a stable reason, and a decision
refused while the person's own switch is off.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.habits.models import ProposalKind
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.proposals_router import router
from src.domains.users.models import User

pytestmark = pytest.mark.integration

AUTOMATE = {
    "domain": "weather",
    "cadence": "weekdays",
    "weekday": None,
    "hour": 7,
    "minute": 30,
    "distinct_days": 14,
    "active_days": 22,
    "part_of_day": "morning",
    "existing_routine": None,
}


@pytest.fixture(autouse=True)
def _heartbeat_handlers_installed() -> None:
    """The boot installs heartbeat's two handlers; a test process has no boot."""
    from src.domains.heartbeat import proposal_handlers

    proposal_handlers.install()


async def _user(db: AsyncSession, *, habits_enabled: bool = True) -> uuid.UUID:
    user = User(
        email=f"routes-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        is_active=True,
        is_verified=True,
        timezone="Europe/Paris",
        language="fr",
        habits_enabled=habits_enabled,
    )
    db.add(user)
    await db.flush()
    return user.id


async def _open(db: AsyncSession, user_id: uuid.UUID, key: str, facts: dict[str, Any]) -> str:
    repo = HabitProposalRepository(db)
    assert await repo.open(user_id, ProposalKind.AUTOMATE_NEED.value, key, facts)
    [row] = [row for row in await repo.list_for_user(user_id) if row.key == key]
    proposal_id = str(row.id)
    await db.commit()
    return proposal_id


@pytest.fixture
async def as_person(async_session: AsyncSession) -> AsyncIterator[Any]:
    """An HTTP client signed in as the account the test names."""
    signed_in: dict[str, uuid.UUID] = {}

    async def authenticated(db: AsyncSession = Depends(get_db)) -> User:
        # Production reads the account on the request's own session.
        account = await db.scalar(select(User).where(User.id == signed_in["id"]))
        assert account is not None
        return account

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: async_session
    app.dependency_overrides[get_current_active_session] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:

        def client(user_id: uuid.UUID) -> httpx.AsyncClient:
            signed_in["id"] = user_id
            return http

        yield client


async def test_the_page_states_the_exact_total_beyond_itself(
    async_session: AsyncSession, as_person: Any
) -> None:
    user_id = await _user(async_session)
    for domain in ("weather", "email", "task"):
        await _open(async_session, user_id, domain, {**AUTOMATE, "domain": domain})

    response = await as_person(user_id).get("/habits/proposals", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["learning_enabled"], len(body["proposals"])) == (3, True, 2)
    first = body["proposals"][0]
    assert first["kind"] == "automate_need"
    assert first["facts"]["hour"] == 7 and first["facts"]["cadence"] == "weekdays"


async def test_learning_switched_off_is_said_not_read_as_empty(
    async_session: AsyncSession, as_person: Any
) -> None:
    user_id = await _user(async_session, habits_enabled=False)
    await _open(async_session, user_id, "weather", AUTOMATE)

    page = (await as_person(user_id).get("/habits/proposals")).json()
    assert page == {"proposals": [], "total": 0, "learning_enabled": False}

    refused = await as_person(user_id).post(f"/habits/proposals/{uuid.uuid4()}/accept")
    assert refused.status_code == 403
    assert refused.json()["detail"] == {"error_code": "FEATURE_DISABLED"}


async def test_a_strangers_proposal_is_answered_as_absent(
    async_session: AsyncSession, as_person: Any
) -> None:
    owner = await _user(async_session)
    stranger = await _user(async_session)
    proposal_id = await _open(async_session, owner, "weather", AUTOMATE)

    response = await as_person(stranger).post(f"/habits/proposals/{proposal_id}/refuse")

    assert response.status_code == 404


async def test_a_decision_answers_its_status_and_a_second_one_is_a_stable_conflict(
    async_session: AsyncSession, as_person: Any
) -> None:
    user_id = await _user(async_session)
    proposal_id = await _open(async_session, user_id, "weather", AUTOMATE)
    client = as_person(user_id)

    first = await client.post(f"/habits/proposals/{proposal_id}/dismiss")
    second = await client.post(f"/habits/proposals/{proposal_id}/accept")

    assert first.status_code == 200
    assert first.json() == {
        "id": proposal_id,
        "kind": "automate_need",
        "status": "dismissed",
        "routine_id": None,
    }
    assert second.status_code == 409
    assert second.json()["detail"] == {"error_code": "PROPOSAL_NOT_OPEN"}


async def test_an_unknown_verdict_is_refused_by_the_route(
    async_session: AsyncSession, as_person: Any
) -> None:
    user_id = await _user(async_session)
    proposal_id = await _open(async_session, user_id, "weather", AUTOMATE)

    response = await as_person(user_id).post(f"/habits/proposals/{proposal_id}/approve")

    assert response.status_code == 422
