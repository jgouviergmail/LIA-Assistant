"""Source summary bills provider-reported tokens once, retaining the caller session."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from src.domains.psyche.service import PsycheService
from tests.unit.domains.psyche.test_service_summary import _make_state

pytestmark = pytest.mark.unit


async def test_source_summary_retains_accounted_attempt_and_approved_boundary():
    owner = uuid4()
    db = AsyncMock()
    service = PsycheService(db)
    service.get_or_create_state = AsyncMock(return_value=_make_state(user_id=owner))
    service._load_personality_name = AsyncMock(return_value="Default")
    boundary = AsyncMock()
    message = AIMessage(
        content="LIA is curious.",
        usage_metadata={"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
    )
    with (
        patch("src.infrastructure.llm.get_llm", return_value=MagicMock(model_name="test-model")),
        patch(
            "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
            new_callable=AsyncMock,
            return_value=message,
        ) as invoke,
        patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens", new_callable=AsyncMock
        ) as settle,
    ):
        assert (
            await service.generate_summary(owner, "fr", before_model=boundary) == "LIA is curious."
        )
        boundary.assert_awaited_once()
        invoke.assert_awaited_once()
        settle.assert_awaited_once()
        arguments = settle.call_args.kwargs
        assert arguments["user_id"] == owner and arguments["db"] is db
        assert arguments["task_type"] == "psyche_summary"
        assert arguments["tokens_in"] == 12 and arguments["tokens_out"] == 7
        assert len(arguments["billing_records"]) == 1
