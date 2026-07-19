"""Integration tests: GET /agents/hitl/pending (Lot 1 T1.4).

The approval card cannot be rebuilt after a page reload from history alone —
this endpoint exposes the Redis-backed pending interrupt. Contract under
test: authoritative read (no detection cache), scoped to the session user's
own conversation, ``null`` body when nothing is pending, ``Cache-Control:
no-store`` always set.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.agents.utils.hitl_store import HITLStore
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client():
    """Real Redis client matching get_redis_cache decode mode. Skips if down."""
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as e:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {e}")
    yield redis
    await redis.aclose()


# Conversation resolution (``get_conversation_id_cached``) reads through
# ``get_db_context()`` — the real database context — while the fixture user
# only exists inside the sandboxed test transaction. That helper has its own
# coverage; here it is patched so THIS endpoint's real contract stays under
# test: authoritative Redis read, payload mapping, no-store header.


def _interrupt_data(message_id: str) -> dict:
    return {
        "action_requests": [
            {
                "type": "tool_confirmation",
                "tool_name": "send_email_tool",
                "tool_args": {"to": "test@example.com"},
                "available_actions": [
                    {"action": "confirm", "label": "confirm", "style": "primary"},
                    {"action": "cancel", "label": "cancel", "style": "destructive"},
                ],
            }
        ],
        "run_id": "run_t14",
        "message_id": message_id,
        "generated_question": "Confirmer l'envoi ?",
    }


class TestPendingHitlEndpoint:
    async def test_no_conversation_returns_null(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        client, _user = authenticated_client
        resp = await client.get("/api/v1/agents/hitl/pending")
        assert resp.status_code == 200
        assert resp.json() is None
        assert resp.headers["cache-control"] == "no-store"

    async def test_pending_interrupt_is_exposed_then_cleared(
        self,
        authenticated_client: tuple[AsyncClient, User],
        redis_client: Redis,
        monkeypatch: pytest.MonkeyPatch,
    ):
        client, _user = authenticated_client
        conversation_id = uuid.uuid4()

        async def _get_test_redis() -> Redis:
            return redis_client

        async def _resolve_conversation(_user_id: uuid.UUID) -> str:
            return str(conversation_id)

        # The endpoint resolves Redis through the cache module — point it at
        # the test client so the store below and the app read the same db.
        monkeypatch.setattr("src.infrastructure.cache.redis.get_redis_cache", _get_test_redis)
        monkeypatch.setattr(
            "src.infrastructure.cache.get_conversation_id_cached", _resolve_conversation
        )

        store = HITLStore(
            redis_client=redis_client, ttl_seconds=settings.hitl_pending_data_ttl_seconds
        )
        message_id = f"hitl_{uuid.uuid4().hex[:12]}"
        try:
            await store.save_interrupt(str(conversation_id), _interrupt_data(message_id))

            resp = await client.get("/api/v1/agents/hitl/pending")
            assert resp.status_code == 200
            body = resp.json()
            assert body is not None
            assert body["message_id"] == message_id
            assert body["generated_question"] == "Confirmer l'envoi ?"
            assert body["interrupt_ts"]
            actions = body["action_requests"][0]["available_actions"]
            assert [a["action"] for a in actions] == ["confirm", "cancel"]

            # Cleared pending -> null again (authoritative read, no stale cache)
            await store.clear_interrupt(str(conversation_id))
            resp2 = await client.get("/api/v1/agents/hitl/pending")
            assert resp2.status_code == 200
            assert resp2.json() is None
        finally:
            await store.delete_interrupt(str(conversation_id))

    async def test_requires_authentication(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/agents/hitl/pending")
        assert resp.status_code == 401
