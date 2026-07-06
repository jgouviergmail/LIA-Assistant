"""Tests for the ``tool_confirmation`` branch of
``OrchestrationService._parse_approval_decision``.

A pre-execution tool confirmation is used by BOTH ``hitl_dispatch``
(``_handle_tool_confirmation``) and the ReAct mutation gate
(``react_execute_tools_node``). Both expect the resume value
``{"action": "confirm"|"cancel"}`` — NOT the generic ``{"decision": ...}``.

This locks that contract, including the safe default (any non-approval → cancel:
never execute a mutation without an explicit confirmation).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_INTERRUPT_DATA,
    FIELD_TYPE,
)
from src.domains.agents.services.orchestration.service import OrchestrationService


def _pending_tool_confirmation() -> dict:
    return {
        FIELD_INTERRUPT_DATA: {
            FIELD_ACTION_REQUESTS: [
                {FIELD_TYPE: "tool_confirmation", "tool_name": "delete_x_tool", "tool_args": {}}
            ]
        }
    }


async def _parse(message: str) -> dict:
    """Run _parse_approval_decision with a mocked tool_confirmation pending state."""
    svc = OrchestrationService()
    store = MagicMock()
    store.get_interrupt = AsyncMock(return_value=_pending_tool_confirmation())
    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.HITLStore", return_value=store),
    ):
        return await svc._parse_approval_decision(
            user_message=message, conversation_id=uuid4(), run_id="test"
        )


@pytest.mark.parametrize("message", ["oui", "ok", "yes", "confirme", "d'accord"])
async def test_tool_confirmation_approval_maps_to_confirm(message: str) -> None:
    """Explicit approval → {"action": "confirm"} (fast path, no LLM)."""
    result = await _parse(message)
    assert result == {"action": "confirm"}, result


@pytest.mark.parametrize("message", ["non", "no", "annule", "cancel", "refuse"])
async def test_tool_confirmation_rejection_maps_to_cancel(message: str) -> None:
    """Explicit rejection → {"action": "cancel"} (fast path, no LLM)."""
    result = await _parse(message)
    assert result.get("action") == "cancel", result
