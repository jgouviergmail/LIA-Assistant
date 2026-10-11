"""Cancellation must report durable withdrawal, including an unavailable store."""

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.services.draft_executor import execute_draft_if_confirmed

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("withdrawn", [True, False])
async def test_native_cancel_reports_only_a_successful_owned_withdrawal(withdrawn: bool) -> None:
    with patch(
        "src.domains.agents.application.cancellation.withdraw_application_draft",
        new=AsyncMock(return_value=withdrawn),
    ) as withdraw:
        result = await execute_draft_if_confirmed(
            {"action": "cancel", "draft_id": "owned", "draft_type": "application_action"},
            {},
            "cancel-turn",
            "fr",
        )
    withdraw.assert_awaited_once_with("owned")
    assert result is not None
    assert result.success is withdrawn
    agent_result = result.to_agent_result()
    assert (agent_result.get("status") == "cancelled") is withdrawn
    if not withdrawn:
        assert result.error == "CANCELLATION_UNAVAILABLE"


async def test_cancel_cannot_withdraw_a_command_without_an_authenticated_runtime() -> None:
    from src.domains.agents.application.cancellation import withdraw_application_draft

    with patch(
        "src.domains.agents.application.cancellation.cancel_command", new=AsyncMock()
    ) as cancel:
        assert not await withdraw_application_draft("unowned")
    cancel.assert_not_awaited()
