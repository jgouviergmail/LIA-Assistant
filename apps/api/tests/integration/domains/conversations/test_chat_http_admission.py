"""HTTP target/admission boundaries against real PostgreSQL and disposable Redis."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.constants import HITL_RATE_LIMIT_REQUESTS, HITL_RATE_LIMIT_WINDOW_SECONDS
from src.core.conversation_execution import RunEnd
from src.domains.agents.api.background_runner import drain_chat_producers
from src.domains.agents.utils.hitl_store import HITLStore
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.infrastructure.streaming.run_admission import owned_execution
from src.infrastructure.streaming.run_stream_broker import listeners_key
from tests.fixtures.chat_http import HttpHarness
from tests.fixtures.chat_http import http as http

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("relayed", [False, True])
async def test_busy_is_refused_before_sse_in_both_transport_modes(
    http: HttpHarness,
    monkeypatch: pytest.MonkeyPatch,
    relayed: bool,
) -> None:
    monkeypatch.setattr(settings, "background_runs_enabled", relayed)
    response = await http.client.post("/agents/chat/stream", json=http.payload())
    assert response.status_code == 409
    assert "text/event-stream" not in response.headers.get("content-type", "")
    assert response.json()["detail"]["active_run"]["conversation_id"] == str(
        http.admission.target.id
    )
    assert http.calls == []


@pytest.mark.parametrize("invalid", ["foreign", "stale", "partial"])
async def test_bad_target_never_starts_a_stream(http: HttpHarness, invalid: str) -> None:
    payload = http.payload()
    if invalid == "foreign":
        payload["conversation_id"] = str(uuid4())
    elif invalid == "stale":
        payload["conversation_revision"] = http.admission.target.revision + 1
    else:
        del payload["conversation_revision"]
    response = await http.client.post("/agents/chat/stream", json=payload)
    assert response.status_code == {"foreign": 404, "stale": 409, "partial": 422}[invalid]
    assert http.calls == []


async def test_inline_post_runs_on_selected_annex_and_releases_after_join(
    http: HttpHarness,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(http.admission, end=RunEnd.NORMAL)
        await db.commit()
    response = await http.client.post("/agents/chat/stream", json=http.payload())
    assert response.status_code == 200
    assert '"type":"done"' in response.text
    assert len(http.calls) == 1
    assert http.calls[0].target == http.admission.target
    assert http.calls[0].stream_id != http.admission.stream_id
    async with AsyncSession(async_engine) as db:
        assert (
            await ConversationExecutionRepository(db).active_for_owner(
                http.admission.target.owner_id
            )
            is None
        )


async def test_unreadable_question_fails_before_sse_without_leaving_admission(
    http: HttpHarness,
    async_engine: AsyncEngine,
    redis_client: Redis,
) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(http.admission, end=RunEnd.NORMAL)
        await db.commit()
    key = f"hitl_pending:{http.admission.target.runtime_id}"
    await redis_client.set(key, "not-json", ex=30)
    try:
        response = await http.client.post("/agents/chat/stream", json=http.payload())
        assert response.status_code == 503
        assert http.calls == []
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(
                    http.admission.target.owner_id
                )
                is None
            )
    finally:
        await redis_client.delete(key)


async def test_activity_is_account_wide_even_without_a_main_or_relay(http: HttpHarness) -> None:
    response = await http.client.get("/agents/runs/active")
    assert response.status_code == 200
    body = response.json()
    assert body["active"] is True
    assert body["conversation_id"] == str(http.admission.target.id)
    assert body["stream_id"] is None and body["can_resume"] is False
    assert not {"runtime_id", "activity_id", "worker_id", "owner_token", "fence"} & body.keys()


@pytest.mark.parametrize(
    "path", ["/agents/runs/active", "/agents/hitl/pending", "/agents/runs/active/cancel"]
)
async def test_control_endpoints_validate_the_selected_generation(
    http: HttpHarness, path: str
) -> None:
    method = http.client.post if path.endswith("cancel") else http.client.get
    params: dict[str, str | int] = {
        "conversation_id": str(http.admission.target.id),
        "conversation_revision": http.admission.target.revision + 1,
    }
    assert (await method(path, params=params)).status_code == 409
    params["conversation_id"] = str(uuid4())
    assert (await method(path, params=params)).status_code == 404
    del params["conversation_revision"]
    assert (await method(path, params=params)).status_code == 422


async def release_seed(http: HttpHarness, engine: AsyncEngine) -> None:
    """The fixture owns an unused claim; close it explicitly before admitting the request."""
    async with AsyncSession(engine) as db:
        await ConversationExecutionRepository(db).close_owned(http.admission, end=RunEnd.NORMAL)
        await db.commit()


@pytest.mark.parametrize("relayed", [False, True])
async def test_exhausted_hitl_limit_is_an_http_429_before_any_stream_or_model(
    http: HttpHarness,
    async_engine: AsyncEngine,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
    relayed: bool,
) -> None:
    monkeypatch.setattr(settings, "background_runs_enabled", relayed)
    store = HITLStore(redis_client, HITL_RATE_LIMIT_WINDOW_SECONDS * 2)
    async with owned_execution(http.admission):
        await store.save_interrupt(
            str(http.admission.target.runtime_id),
            {
                "run_id": http.admission.run_id,
                "action_requests": [{"type": "tool_confirmation"}],
            },
        )
    for _ in range(HITL_RATE_LIMIT_REQUESTS):
        assert (
            await http.client.post("/agents/chat/stream", json=http.payload())
        ).status_code == 200
        _, pending = await drain_chat_producers(timeout=5)
        assert pending == 0
    response = await http.client.post("/agents/chat/stream", json=http.payload())
    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["retry-after"] == str(HITL_RATE_LIMIT_WINDOW_SECONDS)
    assert response.json()["detail"]["error"] == "rate_limit_exceeded"
    assert len(http.calls) == HITL_RATE_LIMIT_REQUESTS
    async with AsyncSession(async_engine) as db:
        assert (
            await ConversationExecutionRepository(db).active_for_owner(
                http.admission.target.owner_id
            )
            is None
        )


async def test_an_unreadable_question_is_an_http_refusal_and_closes_only_its_unused_claim(
    http: HttpHarness,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await release_seed(http, async_engine)

    async def failed_read(self: HITLStore, thread_id: str) -> None:
        raise ConnectionError("Test pending question unavailable")

    monkeypatch.setattr(HITLStore, "get_pending", failed_read)
    response = await http.client.post("/agents/chat/stream", json=http.payload())
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert http.calls == []
    async with AsyncSession(async_engine) as db:
        assert (
            await ConversationExecutionRepository(db).active_for_owner(
                http.admission.target.owner_id
            )
            is None
        )


async def test_two_first_http_messages_cannot_start_two_graphs(
    http: HttpHarness,
    async_engine: AsyncEngine,
) -> None:
    await release_seed(http, async_engine)
    payload = http.payload()
    del payload["conversation_id"], payload["conversation_revision"]
    http.hold = True
    first = asyncio.create_task(http.client.post("/agents/chat/stream", json=payload))
    try:
        await asyncio.wait_for(http.entered.wait(), 5)
        second = await http.client.post("/agents/chat/stream", json=payload)
        assert second.status_code == 409
        assert len(http.calls) == 1
        assert http.calls[0].target.kind.value == "main"
        async with AsyncSession(async_engine) as db:
            row = await db.get(Conversation, http.calls[0].target.id)
            assert row is not None and row.user_id == http.admission.target.owner_id
    finally:
        http.release.set()
        result = await asyncio.wait_for(first, 5)
    assert result.status_code == 200


async def test_hitl_resume_keeps_billing_but_gets_a_new_transport_on_the_exact_runtime(
    http: HttpHarness,
    async_engine: AsyncEngine,
    redis_client: Redis,
) -> None:
    await release_seed(http, async_engine)
    key = f"hitl_pending:{http.admission.target.runtime_id}"
    await redis_client.set(
        key,
        json.dumps(
            {
                "schema_version": 1,
                "interrupt_ts": datetime.now(UTC).isoformat(),
                "interrupt_data": {
                    "run_id": "original-billing",
                    "action_requests": [{"type": "tool_confirmation"}],
                },
            }
        ),
        ex=30,
    )
    try:
        response = await http.client.post("/agents/chat/stream", json=http.payload())
        assert response.status_code == 200
        assert http.calls[0].run_id == "original-billing"
        assert http.calls[0].stream_id != "original-billing"
        assert http.calls[0].target == http.admission.target
    finally:
        await redis_client.delete(key)


async def test_stale_button_never_starts_a_model_and_releases_its_unused_claim(
    http: HttpHarness,
    async_engine: AsyncEngine,
) -> None:
    await release_seed(http, async_engine)
    payload = {
        **http.payload(),
        "hitl_decision": {"message_id": "question-id", "action": "confirm"},
    }
    response = await http.client.post("/agents/chat/stream", json=payload)
    assert response.status_code == 200
    chunks = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert [chunk["type"] for chunk in chunks] == ["error", "done"]
    assert chunks[0]["metadata"]["error_code"] == "hitl_decision_stale"
    assert all(
        chunk["metadata"]["conversation_id"] == str(http.admission.target.id) for chunk in chunks
    )
    assert http.calls == []
    async with AsyncSession(async_engine) as db:
        assert (
            await ConversationExecutionRepository(db).active_for_owner(
                http.admission.target.owner_id
            )
            is None
        )


async def test_inline_stop_is_scoped_and_waits_for_its_producer(
    http: HttpHarness,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await release_seed(http, async_engine)
    monkeypatch.setattr(settings, "background_runs_cancel_poll_seconds", 0.01)
    http.hold = True
    request = asyncio.create_task(http.client.post("/agents/chat/stream", json=http.payload()))
    params = {
        "conversation_id": str(http.admission.target.id),
        "conversation_revision": str(http.admission.target.revision),
    }
    try:
        await asyncio.wait_for(http.entered.wait(), 5)
        status = (await http.client.get("/agents/runs/active", params=params)).json()
        assert status["can_cancel"] is True and status["can_resume"] is False
        wrong = await http.client.post("/agents/runs/active/cancel")
        assert wrong.json()["cancelled"] is False  # omission means Main, never the active annex
        stopped = await http.client.post("/agents/runs/active/cancel", params=params)
        assert stopped.json()["cancelled"] is True
        result = await asyncio.wait_for(request, 5)
        assert '"cancelled":true' in result.text
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(
                    http.admission.target.owner_id
                )
                is None
            )
    finally:
        http.release.set()
        await asyncio.wait_for(request, 5)


async def test_reattach_proves_exact_target_and_keeps_the_admitted_transport_snapshot(
    http: HttpHarness,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    redis_client: Redis,
) -> None:
    await release_seed(http, async_engine)
    monkeypatch.setattr(settings, "background_runs_enabled", True)
    monkeypatch.setattr(settings, "background_runs_xread_block_ms", 100)
    http.hold = True
    request = asyncio.create_task(http.client.post("/agents/chat/stream", json=http.payload()))
    reattached: asyncio.Task[Response] | None = None
    try:
        await asyncio.wait_for(http.entered.wait(), 5)
        path = f"/agents/runs/{http.calls[0].stream_id}/stream"
        assert (await http.client.get(path)).status_code == 404
        # A settings change affects subsequent runs, not an already-admitted relay.
        monkeypatch.setattr(settings, "background_runs_enabled", False)
        params = {
            "conversation_id": str(http.admission.target.id),
            "conversation_revision": str(http.admission.target.revision),
        }
        reattached = asyncio.create_task(http.client.get(path, params=params))
        assert (await http.client.get("/agents/runs/active", params=params)).json()["can_resume"]
        # Observe both real subscribers before releasing the producer.
        async with asyncio.timeout(5):
            while int(await redis_client.get(listeners_key(http.calls[0].stream_id)) or 0) < 2:
                await asyncio.sleep(0.01)
        http.release.set()
        result = await asyncio.wait_for(reattached, 5)
        assert result.status_code == 200 and '"type":"done"' in result.text
    finally:
        http.release.set()
        await asyncio.wait_for(request, 5)
        if reattached is not None:
            await asyncio.wait_for(reattached, 5)
