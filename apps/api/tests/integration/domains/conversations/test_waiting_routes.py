"""The waiting message's routes on real PostgreSQL and Redis (ADR-384).

The harness occupies the account with its own admission: every keep is
written behind a busy account unless a test closes it first.
"""

from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.constants import CHAT_MESSAGE_MAX_LENGTH
from src.core.conversation_execution import RunAdmission, RunEnd
from src.domains.agents.api.background_runner import drain_chat_producers
from src.domains.agents.utils.hitl_store import HITLStore
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.waiting_models import WaitingMessage
from src.infrastructure.streaming.run_admission import owned_execution
from src.infrastructure.streaming.run_stream_broker import is_cancel_requested
from tests.fixtures.chat_http import HttpHarness
from tests.fixtures.chat_http import http as http

pytestmark = pytest.mark.integration

ROUTE = "/agents/chat/waiting"


def selection(admission: RunAdmission) -> dict[str, object]:
    return {
        "conversation_id": str(admission.target.id),
        "conversation_revision": admission.target.revision,
    }


async def close(admission: RunAdmission, end: RunEnd) -> None:
    async with owned_execution(admission) as authority:
        authority.end = end


async def test_words_written_while_lia_works_wait_and_later_ones_are_added(
    http: HttpHarness,
) -> None:
    params = selection(http.admission)
    first = await http.client.post(ROUTE, params=params, json={"message": "Add the dentist"})
    assert first.status_code == 200
    assert first.json()["departed"] is False
    assert first.json()["waiting"]["status"] == "waiting"
    second = await http.client.post(ROUTE, params=params, json={"message": "and the bakery"})
    assert second.json()["waiting"]["content"] == "Add the dentist\n\nand the bakery"
    read = await http.client.get(ROUTE, params=params)
    assert read.status_code == 200 and read.json()["version"] == 2
    assert read.headers["cache-control"] == "no-store"
    assert http.calls == []


async def test_words_too_long_once_added_are_refused(http: HttpHarness) -> None:
    params = selection(http.admission)
    filled = "x" * (CHAT_MESSAGE_MAX_LENGTH - 1)
    assert (await http.client.post(ROUTE, params=params, json={"message": filled})).is_success
    refused = await http.client.post(ROUTE, params=params, json={"message": "y"})
    assert refused.status_code == 422
    assert str(CHAT_MESSAGE_MAX_LENGTH) in refused.json()["detail"]


async def test_an_edit_names_the_version_it_read(http: HttpHarness) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "one"})
    stale = await http.client.put(ROUTE, params=params, json={"message": "uno", "version": 2})
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "waiting_message_changed"
    edited = await http.client.put(ROUTE, params=params, json={"message": "uno", "version": 1})
    assert edited.status_code == 200 and edited.json()["content"] == "uno"


async def test_a_withdrawn_message_is_gone(http: HttpHarness) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "one"})
    assert (await http.client.delete(ROUTE, params=params)).status_code == 204
    assert (await http.client.delete(ROUTE, params=params)).status_code == 404
    assert (await http.client.get(ROUTE, params=params)).json() is None


async def test_a_strangers_discussion_is_not_found(http: HttpHarness) -> None:
    params = {"conversation_id": str(uuid4()), "conversation_revision": 0}
    response = await http.client.post(ROUTE, params=params, json={"message": "one"})
    assert response.status_code == 404


async def test_send_now_stops_the_running_answer_of_the_same_discussion(
    http: HttpHarness, async_engine: AsyncEngine, redis_client: Redis
) -> None:
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(ConversationExecution)
            .where(ConversationExecution.id == http.admission.activity_id)
            .values(cancellable=True)
        )
        await db.commit()
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "Send it now"})
    sent = await http.client.post(f"{ROUTE}/send", params=params)
    assert sent.status_code == 200
    assert sent.json() == {"departed": False, "stopping": True, "stream_id": None}
    assert await is_cancel_requested(redis_client, http.admission.stream_id)
    assert (await http.client.get(ROUTE, params=params)).json()["send_requested"] is True


async def test_send_now_is_refused_while_a_question_waits_for_its_answer(
    http: HttpHarness, redis_client: Redis
) -> None:
    params = selection(http.admission)
    await http.client.post(ROUTE, params=params, json={"message": "Not an answer"})
    async with owned_execution(http.admission) as authority:
        await HITLStore(redis_client, settings.hitl_pending_data_ttl_seconds).save_interrupt(
            str(http.admission.target.runtime_id),
            {"run_id": http.admission.run_id, "action_requests": [{"type": "clarification"}]},
        )
        authority.end = RunEnd.NORMAL
    refused = await http.client.post(f"{ROUTE}/send", params=params)
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "waiting_question_pending"


async def test_on_a_free_account_a_plain_send_leaves_at_once(
    http: HttpHarness, async_engine: AsyncEngine
) -> None:
    await close(http.admission, RunEnd.NORMAL)
    params = selection(http.admission)
    response = await http.client.post(ROUTE, params=params, json={"message": "Right away"})
    assert response.status_code == 200
    body = response.json()
    assert body["departed"] is True and body["waiting"] is None and body["stream_id"]
    _, pending = await drain_chat_producers(timeout=5)
    assert pending == 0
    assert [call.stream_id for call in http.calls] == [body["stream_id"]]


@pytest.mark.parametrize(("end", "departed"), [(RunEnd.NORMAL, True), (RunEnd.INTERRUPTED, False)])
async def test_written_behind_a_run_that_just_ended_its_end_decides(
    http: HttpHarness, async_engine: AsyncEngine, end: RunEnd, departed: bool
) -> None:
    await close(http.admission, end)
    params = selection(http.admission)
    response = await http.client.post(
        ROUTE,
        params=params,
        json={"message": "Written behind it", "behind_stream_id": http.admission.stream_id},
    )
    assert response.status_code == 200 and response.json()["departed"] is departed
    await drain_chat_producers(timeout=5)
    if not departed:
        assert response.json()["waiting"]["status"] == "held"
        async with AsyncSession(async_engine) as db:
            stored = await db.scalar(
                select(WaitingMessage.status).where(
                    WaitingMessage.user_id == http.admission.target.owner_id
                )
            )
            assert stored == "held"
