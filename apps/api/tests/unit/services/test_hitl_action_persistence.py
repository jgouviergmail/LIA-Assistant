"""The restored card must offer the same decisions as the live interrupt."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.nodes.react_egress_question import build_interrupt_payload
from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator
from src.domains.agents.services.streaming.service import StreamingService
from src.domains.agents.utils.hitl_store import HITLStore
from tests.helpers.hitl_interactions import StaticDraftInteraction
from tests.helpers.redis_databases import RedisServer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "available,expected",
    [
        (True, ["confirm", "confirm_without_data", "cancel"]),
        (False, ["confirm_without_data", "cancel"]),
    ],
)
async def test_saved_egress_offers_the_live_actions_and_preserves_resume_context(
    available: bool, expected: list[str]
) -> None:
    conversation_id = uuid.uuid4()
    store = HITLStore(RedisServer().client(2), ttl_seconds=60)
    payload = build_interrupt_payload(
        {
            "draft_id": "draft-egress",
            "draft_type": "sandbox_egress",
            "step_id": "step-1",
            "draft_content": {
                "hosts_unknown": ["example.org"],
                "data_summary": {"available": available},
            },
        },
        user_language="fr",
    )
    service = StreamingService(hitl_store=store)
    interaction = StaticDraftInteraction(MagicMock(spec=HitlQuestionGenerator))
    with (
        patch("src.domains.agents.services.streaming.service._get_hitl_registry") as registry,
        patch("src.domains.agents.services.streaming.service._get_hitl_question_generator"),
    ):
        registry.return_value.from_action_type.return_value = interaction
        chunks = [
            chunk
            async for chunk in service._handle_hitl_interrupt(
                {"__interrupt__": [SimpleNamespace(value=payload, id="egress")]},
                conversation_id,
                "scheduled-run",
            )
        ]
    live = next(chunk.metadata for chunk in chunks if chunk.type == "hitl_interrupt_metadata")
    restored = await store.get_pending(str(conversation_id))
    assert restored is not None and live is not None
    request = restored["action_requests"][0]
    assert [action["action"] for action in request.get("available_actions", [])] == expected
    assert request["available_actions"] == live["action_requests"][0]["available_actions"]
    assert request["step_id"] == "step-1"
    assert restored["run_id"] == "scheduled-run"
    assert restored["message_id"] == live["message_id"]
