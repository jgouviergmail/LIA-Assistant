"""Cancellation must report durable withdrawal, including an unavailable store."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.i18n_draft_refusals import get_draft_refusal_message
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
        # The code stays for diagnostics; the card reads a sentence that never
        # says « cancelled », since the command may already be running.
        assert result.result_data["error_code"] == "CANCELLATION_UNAVAILABLE"
        assert result.error == get_draft_refusal_message("CANCELLATION_UNAVAILABLE", "fr")
        assert agent_result["status"] == "error"


async def test_cancel_cannot_withdraw_a_command_without_an_authenticated_runtime() -> None:
    from src.domains.agents.application.cancellation import withdraw_application_draft

    with patch(
        "src.domains.agents.application.cancellation.cancel_command", new=AsyncMock()
    ) as cancel:
        assert not await withdraw_application_draft("unowned")
    cancel.assert_not_awaited()
