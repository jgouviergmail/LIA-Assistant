"""A waiting message joins the answer being written, through its route (ADR-385).

Real PostgreSQL and Redis; the harness occupies the account with its own admission,
whose notes a test opens or closes as the loop would.
"""

import asyncio

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE
from src.core.conversation_execution import RunAdmission, RunEnd
from src.domains.agents.api.background_runner import drain_chat_producers
from src.domains.agents.utils.hitl_store import HITLStore
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.streaming.run_admission import owned_execution
from tests.fixtures.chat_http import HttpHarness
from tests.fixtures.chat_http import http as http

pytestmark = pytest.mark.integration

ROUTE = "/agents/chat/waiting"


def selection(admission: RunAdmission) -> dict[str, object]:
    return {
        "conversation_id": str(admission.target.id),
        "conversation_revision": admission.target.revision,
    }


async def notes(engine: AsyncEngine, admission: RunAdmission, *, open_: bool) -> None:
    async with AsyncSession(engine) as db:
        repository = ConversationExecutionRepository(db)
        if open_:
            assert await repository.open_notes(admission)
        else:
            assert await repository.close_notes(admission)
        await db.commit()


async def stored(engine: AsyncEngine, admission: RunAdmission) -> WaitingMessage | None:
    async with AsyncSession(engine) as db:
        return await db.scalar(
            select(WaitingMessage).where(WaitingMessage.user_id == admission.target.owner_id)
        )


async def test_the_offer_follows_whether_the_answer_takes_notes(
    http: HttpHarness, async_engine: AsyncEngine
) -> None:
    params = selection(http.admission)
    kept = await http.client.post(ROUTE, params=params, json={"message": "only Sunday"})
    assert kept.json()["waiting"]["can_join"] is False
    await notes(async_engine, http.admission, open_=True)
    assert (await http.client.get(ROUTE, params=params)).json()["can_join"] is True
    added = await http.client.post(ROUTE, params=params, json={"message": "and cheap"})
    assert added.json()["waiting"]["can_join"] is True
    edited = await http.client.put(
        ROUTE, params=params, json={"message": "only Sunday, cheap", "version": 2}
    )
    assert edited.json()["can_join"] is True
    await notes(async_engine, http.admission, open_=False)
    assert (await http.client.get(ROUTE, params=params)).json()["can_join"] is False


async def test_a_message_joins_the_answer_that_takes_notes(
    http: HttpHarness, async_engine: AsyncEngine
) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "only Sunday"})
    await notes(async_engine, http.admission, open_=True)

    joined = await http.client.post(f"{ROUTE}/join", params=params, json={"version": 1})

    assert joined.status_code == 200
    body = joined.json()
    assert body["status"] == "joining" and body["can_join"] is False
    assert body["stream_id"] == http.admission.stream_id
    row = await stored(async_engine, http.admission)
    assert row is not None and row.status == WaitingStatus.JOINING
    # Read back, it says it joins and offers nothing more.
    read = (await http.client.get(ROUTE, params=params)).json()
    assert read["status"] == "joining" and read["can_join"] is False


async def test_an_answer_that_takes_no_note_refuses_and_the_words_keep_waiting(
    http: HttpHarness, async_engine: AsyncEngine
) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "only Sunday"})

    refused = await http.client.post(f"{ROUTE}/join", params=params, json={"version": 1})

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "waiting_note_closed"
    assert refused.json()["detail"]["message"]
    row = await stored(async_engine, http.admission)
    assert row is not None and row.status == WaitingStatus.WAITING


async def test_a_join_names_the_version_it_read(
    http: HttpHarness, async_engine: AsyncEngine
) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "one"})
    await http.client.post(ROUTE, params=params, json={"message": "two"})
    await notes(async_engine, http.admission, open_=True)

    stale = await http.client.post(f"{ROUTE}/join", params=params, json={"version": 1})

    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "waiting_message_changed"


async def test_send_now_on_a_joining_note_says_it_changed(
    http: HttpHarness, async_engine: AsyncEngine
) -> None:
    """A stale tab offering « Send now » learns the message joined the answer meanwhile."""
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "only Sunday"})
    await notes(async_engine, http.admission, open_=True)
    assert (await http.client.post(f"{ROUTE}/join", params=params, json={"version": 1})).is_success

    refused = await http.client.post(f"{ROUTE}/send", params=params)

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "waiting_message_changed"


async def test_send_now_decides_under_the_owner_lock_every_close_takes(
    http: HttpHarness, async_engine: AsyncEngine
) -> None:
    """« Send now » reads whether the account is busy under the owner lock (ADR-384).

    Decided beside a close that has not committed, it would mark the message for
    « the next release » — the very one settling what waited — and answer that it
    is waiting: after an interrupted run, the words would stay behind a release
    that already passed.
    """
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "now"})
    async with AsyncSession(async_engine) as closing:
        # What a close holds while it writes the run's end and settles what waited.
        await hold_owner_lock(
            closing, CONVERSATION_OWNER_LOCK_SCOPE, http.admission.target.owner_id
        )
        sending = asyncio.create_task(http.client.post(f"{ROUTE}/send", params=params))
        await asyncio.sleep(0.3)
        assert not sending.done(), "send-now decided without the owner lock"
        await closing.rollback()
    answer = await asyncio.wait_for(sending, timeout=5)
    assert answer.status_code == 200, answer.text


async def test_nothing_to_join_is_not_found(http: HttpHarness, async_engine: AsyncEngine) -> None:
    await notes(async_engine, http.admission, open_=True)
    params = selection(http.admission)
    missing = await http.client.post(f"{ROUTE}/join", params=params, json={"version": 1})
    assert missing.status_code == 404


async def test_a_closed_answer_refuses_a_note(http: HttpHarness, async_engine: AsyncEngine) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "too late"})
    await notes(async_engine, http.admission, open_=True)
    async with owned_execution(http.admission) as authority:
        authority.end = RunEnd.NORMAL
    refused = await http.client.post(f"{ROUTE}/join", params=params, json={"version": 1})
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "waiting_note_closed"
    # The release sent the waiting message as the next turn (ADR-384): let it settle.
    _, pending = await drain_chat_producers(timeout=5)
    assert pending == 0


async def test_no_note_joins_while_a_question_waits_for_its_answer(
    http: HttpHarness, async_engine: AsyncEngine, redis_client: Redis
) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "Not an answer"})
    await notes(async_engine, http.admission, open_=True)
    async with owned_execution(http.admission) as authority:
        await HITLStore(redis_client, settings.hitl_pending_data_ttl_seconds).save_interrupt(
            str(http.admission.target.runtime_id),
            {"run_id": http.admission.run_id, "action_requests": [{"type": "clarification"}]},
        )
        refused = await http.client.post(f"{ROUTE}/join", params=params, json={"version": 1})
        authority.end = RunEnd.NORMAL
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "waiting_question_pending"
