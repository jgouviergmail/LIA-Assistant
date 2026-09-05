"""The parameters travel from the callback to the record (ADR-263, lot 7).

The pure normalisation has its own suite. What this one asserts is the SEAM —
that the tracking callback actually reads what LangChain hands it, and that
both of its exits carry it. A module that normalises perfectly and is never
called produces a register full of NULLs and nobody notices.

The failure path matters at least as much as the success one: a call that
failed is exactly the call whose settings someone will want to read.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

pytestmark = [pytest.mark.unit]


def _handler(tracker: Any) -> Any:
    from src.infrastructure.observability.callbacks import TokenTrackingCallback

    return TokenTrackingCallback(tracker=tracker, run_id="run-1")


_PARAMS = {
    "_type": "openai-chat",
    "model": "gpt-4.1-mini",
    "temperature": 0.35,
    "top_p": 0.9,
    "max_completion_tokens": 1500,
    "reasoning_effort": "medium",
    # Never stored, never digested: the whole reason for an allowlist.
    "api_key": "sk-live-must-not-be-stored",
}


class TestTheCallbackReadsWhatLangChainGivesIt:
    async def test_the_chat_model_path_captures_the_parameters(self) -> None:
        handler = _handler(AsyncMock())
        run_id = uuid.uuid4()

        await handler.on_chat_model_start(
            {},
            [[]],
            run_id=run_id,
            metadata={"llm_type": "response"},
            invocation_params=dict(_PARAMS),
        )

        captured = handler._call_context[str(run_id)]["params"]
        assert captured.provider == "openai"
        assert captured.temperature == 0.35
        assert captured.max_output_tokens == 1500
        assert captured.reasoning_level == "medium"

    async def test_the_legacy_completion_path_captures_them_too(self) -> None:
        handler = _handler(AsyncMock())
        run_id = uuid.uuid4()

        await handler.on_llm_start(
            {},
            ["hi"],
            run_id=run_id,
            metadata={"llm_type": "response"},
            invocation_params=dict(_PARAMS),
        )

        assert handler._call_context[str(run_id)]["params"].provider == "openai"

    async def test_a_credential_never_reaches_the_record(self) -> None:
        handler = _handler(AsyncMock())
        run_id = uuid.uuid4()

        await handler.on_chat_model_start(
            {}, [[]], run_id=run_id, metadata={}, invocation_params=dict(_PARAMS)
        )

        captured = handler._call_context[str(run_id)]["params"]
        assert "sk-live-must-not-be-stored" not in str(captured)

    async def test_a_path_with_no_parameters_still_stores_a_context(self) -> None:
        """Raising here would turn an observability concern into a broken turn."""
        handler = _handler(AsyncMock())
        run_id = uuid.uuid4()

        await handler.on_chat_model_start({}, [[]], run_id=run_id, metadata={})

        assert handler._call_context[str(run_id)]["params"] is not None


class TestBothExitsCarryThem:
    async def test_a_SUCCESSFUL_call_records_the_parameters(self) -> None:
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, LLMResult

        tracker = AsyncMock()
        handler = _handler(tracker)
        run_id = uuid.uuid4()
        await handler.on_chat_model_start(
            {},
            [[]],
            run_id=run_id,
            metadata={"llm_type": "response"},
            invocation_params=dict(_PARAMS),
        )

        message = AIMessage(
            content="ok",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            response_metadata={"model_name": "gpt-4.1-mini"},
        )
        await handler.on_llm_end(
            LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id
        )

        params = tracker.record_node_tokens.await_args.kwargs["params"]
        assert params.provider == "openai"
        assert params.temperature == 0.35

    async def test_a_FAILED_call_records_them_too(self) -> None:
        """The call whose settings someone will actually want to read."""
        tracker = AsyncMock()
        handler = _handler(tracker)
        run_id = uuid.uuid4()
        await handler.on_chat_model_start(
            {},
            [[]],
            run_id=run_id,
            metadata={"llm_type": "response"},
            invocation_params=dict(_PARAMS),
        )

        await handler.on_llm_error(RuntimeError("provider said no"), run_id=run_id)

        kwargs = tracker.record_node_tokens.await_args.kwargs
        assert kwargs["status"] == "error"
        assert kwargs["params"].provider == "openai"


class TestTheRecordAndTheLogAgree:
    def test_every_captured_field_has_a_column(self) -> None:
        """A field the record carries and the table cannot hold is a field that
        is silently dropped between the callback and the register."""
        from src.domains.chat.models import TokenUsageLog
        from src.domains.chat.tracking_records import TokenUsageRecord
        from src.infrastructure.llm.inference_params import InferenceParams

        columns = set(TokenUsageLog.__table__.columns.keys())
        for field in InferenceParams._fields:
            assert field in TokenUsageRecord._fields, f"{field} stops at the record"
            assert field in columns, f"{field} has no column"

    def test_the_record_stays_backward_compatible(self) -> None:
        """Every new field has a default: a NamedTuple without them would break
        every existing construction, and there are several."""
        from src.domains.chat.tracking_records import TokenUsageRecord

        record = TokenUsageRecord(
            node_name="n",
            model_name="m",
            prompt_tokens=1,
            completion_tokens=1,
            cached_tokens=0,
            cost_usd=0.0,
            cost_eur=0.0,
            usd_to_eur_rate=__import__("decimal").Decimal("1"),
        )

        assert record.provider is None
        assert record.params_digest is None
