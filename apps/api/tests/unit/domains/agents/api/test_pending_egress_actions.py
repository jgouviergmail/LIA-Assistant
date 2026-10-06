"""Old pending questions remain answerable after the action-persistence fix."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Response

from src.core.exceptions import CacheError
from src.domains.agents.api.hitl_pending import check_pending_hitl_uncached
from src.domains.agents.api.router import get_pending_hitl_interrupt
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "available,expected",
    [
        (True, ["confirm", "confirm_without_data", "cancel"]),
        (False, ["confirm_without_data", "cancel"]),
    ],
)
async def test_legacy_pending_egress_has_the_scoped_actions(
    available: bool, expected: list[str]
) -> None:
    pending = {
        "message_id": "old-question",
        "action_requests": [
            {
                "type": "draft_critique",
                "draft_type": "sandbox_egress",
                "draft_id": "draft-old",
                "draft_content": {"data_summary": {"available": available}},
            }
        ],
    }
    response = Response()
    with (
        patch(
            "src.infrastructure.cache.get_conversation_id_cached",
            new=AsyncMock(return_value="conversation"),
        ),
        patch(
            "src.domains.agents.api.router.check_pending_hitl_uncached",
            new=AsyncMock(return_value=pending),
        ),
    ):
        result = await get_pending_hitl_interrupt(
            response, User(id=uuid.uuid4(), email="test@example.org")
        )
    assert result is not None
    assert [a["action"] for a in result.action_requests[0].get("available_actions", [])] == expected
    assert "available_actions" not in pending["action_requests"][0]
    assert response.headers["cache-control"] == "no-store"


async def test_pending_endpoint_does_not_claim_absence_during_a_redis_outage() -> None:
    with (
        patch(
            "src.infrastructure.cache.get_conversation_id_cached",
            new=AsyncMock(return_value="conversation"),
        ),
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(side_effect=ConnectionError("offline")),
        ),
    ):
        with pytest.raises(CacheError) as failed:
            await get_pending_hitl_interrupt(
                Response(), User(id=uuid.uuid4(), email="test@example.org")
            )
        assert failed.value.status_code == 503
        # The existing chat routing guard retains its fail-open contract.
        assert await check_pending_hitl_uncached("conversation") is None
