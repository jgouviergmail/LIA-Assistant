"""A stored payload fragment never becomes a reported completed tool result."""

from uuid import uuid4

import pytest

from src.domains.agents.effects.runtime import ClaimTicket, _serve_lost_claim

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("status", ["failed", "succeeded", "claimed", "abandoned"])
def test_tool_replay_refuses_a_truncated_record_without_reinterpreting_its_content(
    status: str,
) -> None:
    ticket = ClaimTicket(uuid4(), None, {"truncated": True, "text": '{"success":true'}, status)
    answer = _serve_lost_claim("application_action_executor", ticket)
    assert answer["success"] is False
    assert "truncated" not in str(answer.get("data"))
