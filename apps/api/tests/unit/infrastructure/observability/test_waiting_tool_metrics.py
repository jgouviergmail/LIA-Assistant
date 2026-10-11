"""An acknowledged handoff must not inflate tool success or failure metrics."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.observability.decorators import _record_returned_outcome

pytestmark = pytest.mark.unit


def test_waiting_tool_counts_one_finite_pending_outcome() -> None:
    framework, business = MagicMock(), MagicMock()
    result = {
        "success": False,
        "phase": "waiting",
        "committed": False,
        "interaction": {
            "interaction_id": str(uuid4()),
            "kind": "secure",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
    }
    _record_returned_outcome(
        result=result,
        tool_name="application_secure",
        agent_name="setting_agent",
        counter_metric=framework,
        usage_counter=business,
        started_at=0,
        log_execution=False,
        func_name="test_wait",
    )
    framework.labels.assert_called_once_with(
        tool_name="application_secure", agent_name="setting_agent", success="waiting"
    )
    business.labels.assert_called_once_with(
        agent_type="setting", tool_name="application_secure", outcome="waiting"
    )
