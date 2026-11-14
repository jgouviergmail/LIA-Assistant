"""Live questions round-trip through real SQL authority, Redis and the HTTP endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from langgraph.types import Interrupt
from redis.asyncio import Redis

from src.domains.agents.nodes.react_egress_question import build_interrupt_payload
from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator
from src.domains.agents.services.streaming.service import StreamingService
from src.domains.agents.utils.hitl_store import HITLStore
from src.infrastructure.streaming.run_admission import owned_execution
from tests.fixtures.chat_http import HttpHarness
from tests.fixtures.chat_http import http as http
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.conversation_executions import reserved as reserved
from tests.helpers.hitl_interactions import StaticDraftInteraction

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "available,expected",
    [
        (True, ["confirm", "confirm_without_data", "cancel"]),
        (False, ["confirm_without_data", "cancel"]),
    ],
)
async def test_scheduled_egress_offers_the_same_live_persisted_and_reloaded_actions(
    http: HttpHarness,
    redis_client: Redis,
    available: bool,
    expected: list[str],
) -> None:
    """Production action preservation; only question wording generation is substituted."""
    admission = http.admission
    store = HITLStore(redis_client, ttl_seconds=60)
    payload = build_interrupt_payload(
        {
            "draft_id": "draft-egress",
            "draft_type": "sandbox_egress",
            "step_id": "step-egress",
            "draft_content": {
                "hosts_unknown": ["example.org"],
                "data_summary": {"available": available},
            },
        },
        user_language="fr",
    )
    interaction = StaticDraftInteraction(MagicMock(spec=HitlQuestionGenerator))
    service = StreamingService(hitl_store=store)
    async with owned_execution(admission):
        with (
            patch("src.domains.agents.services.streaming.service._get_hitl_registry") as registry,
            patch("src.domains.agents.services.streaming.service._get_hitl_question_generator"),
        ):
            registry.return_value.from_action_type.return_value = interaction
            chunks = [
                chunk
                async for chunk in service._handle_hitl_interrupt(
                    {"__interrupt__": [Interrupt(value=payload, id="scheduled-egress")]},
                    admission.target,
                    admission.run_id,
                )
            ]
        live = next(chunk.metadata for chunk in chunks if chunk.type == "hitl_interrupt_metadata")
        restored = await store.get_pending(str(admission.target.runtime_id))
        assert restored is not None and live is not None
        response = await http.client.get(
            "/agents/hitl/pending",
            params={
                "conversation_id": str(admission.target.id),
                "conversation_revision": admission.target.revision,
            },
        )
        assert response.status_code == 200
        body = response.json()
        request = body["action_requests"][0]
        assert [action["action"] for action in request["available_actions"]] == expected
        assert request["available_actions"] == restored["action_requests"][0]["available_actions"]
        assert request["available_actions"] == live["action_requests"][0]["available_actions"]
        assert request["step_id"] == "step-egress"
        assert body["message_id"] == restored["message_id"] == live["message_id"]
        assert restored["run_id"] == admission.run_id
        assert response.headers["cache-control"] == "no-store"
        assert (await http.client.get("/agents/hitl/pending")).json() is None
        await store.clear_interrupt(str(admission.target.runtime_id))
        cleared = await http.client.get(
            "/agents/hitl/pending",
            params={
                "conversation_id": str(admission.target.id),
                "conversation_revision": admission.target.revision,
            },
        )
        assert cleared.status_code == 200 and cleared.json() is None
        assert cleared.headers["cache-control"] == "no-store"


async def test_no_primary_returns_null_without_creating_it(http: HttpHarness) -> None:
    response = await http.client.get("/agents/hitl/pending")
    assert response.status_code == 200 and response.json() is None
    assert response.headers["cache-control"] == "no-store"


async def test_requires_authentication(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/agents/hitl/pending")
    assert response.status_code == 401
