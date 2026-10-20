"""SMS evidence must fit every model that actually consumes the tool output."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.token_budget import count_external_tokens
from src.domains.agents.tools import sms_tools
from src.domains.sms.facade import SmsFacade
from src.domains.sms.read_schemas import SmsPage, SmsView

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "mode,small", [("pipeline", "sms_agent"), ("react", "react_agent"), ("react", "response")]
)
async def test_output_fits_a_smaller_actual_model_without_losing_the_source_page(
    monkeypatch, mode, small
):
    owner = uuid4()
    page = SmsPage(
        items=[
            SmsView(
                id=uuid4(),
                sender="Alice",
                display_name="Alice",
                body=" ".join(f"Café東京{index}" for index in range(800)),
                received_at=datetime.now(UTC),
                date_kind="received",
                origin="iphone",
            )
        ],
        total=1,
        as_of=datetime.now(UTC),
        revision=0,
    )
    monkeypatch.setattr(
        sms_tools, "validate_runtime_config", lambda *args: SimpleNamespace(user_id=str(owner))
    )
    monkeypatch.setattr(
        sms_tools, "tool_runtime_context", lambda runtime: SimpleNamespace(execution_mode=mode)
    )
    monkeypatch.setattr(
        sms_tools, "slot_tool_result_budget", lambda slot: 600 if slot == small else 4000
    )
    monkeypatch.setattr(SmsFacade, "list", AsyncMock(return_value=page))

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(sms_tools, "get_db_context", session)
    output = await sms_tools._read({}, object(), "list_sms_tool")
    assert output.success
    assert len(output.structured_data["sms_messages"]) == 1
    assert count_external_tokens(str(output)) <= 600
