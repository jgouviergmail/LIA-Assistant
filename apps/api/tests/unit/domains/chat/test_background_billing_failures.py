"""Real background synthesis boundaries close paid usage before their fallback."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.domains.relations.debrief import llm as debrief
from src.domains.relations.debrief.schemas import DebriefDraft
from src.domains.telephony import return_synthesis as phone
from src.domains.telephony.schemas import ReturnProposal, StructuredCallData
from src.domains.telephony.spend import phone_call_run_id
from src.domains.telephony.synthesis_usage import track_synthesis_usage
from src.infrastructure.proactive import tracking

pytestmark = pytest.mark.unit


def _reply_capture(kwargs) -> None:
    capture = kwargs["config"]["callbacks"][0]
    run_id = uuid4()
    with patch("src.infrastructure.llm.token_capture.time", return_value=1000):
        capture.on_chat_model_start({}, [[]], run_id=run_id)
        capture.on_llm_end(
            LLMResult(
                generations=[
                    [
                        ChatGeneration(
                            message=AIMessage(
                                content="reply",
                                response_metadata={"model_name": "returned-model"},
                                usage_metadata={
                                    "input_tokens": 10,
                                    "output_tokens": 2,
                                    "total_tokens": 12,
                                },
                            )
                        )
                    ]
                ]
            ),
            run_id=run_id,
        )


@pytest.mark.parametrize("path", ["phone", "debrief"])
@pytest.mark.parametrize(
    "failure", [ValueError("invalid structured reply"), asyncio.CancelledError()]
)
async def test_synthesis_failure_records_paid_callback_with_same_run(
    path: str, failure: BaseException, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, call_id = uuid4(), uuid4()
    expected_run = phone_call_run_id(call_id) if path == "phone" else "debrief-run"
    module = phone if path == "phone" else debrief

    async def provider(*args, **kwargs):
        _reply_capture(kwargs)
        raise failure

    monkeypatch.setattr(module, "get_llm", lambda _: SimpleNamespace(model_name="requested-model"))
    monkeypatch.setattr(
        module,
        "get_llm_config_for_agent",
        lambda *_: SimpleNamespace(model="requested-model", provider="openai"),
    )
    monkeypatch.setattr(module, "get_structured_output_with_retry", provider)
    if path == "debrief":
        monkeypatch.setattr(debrief, "_personality_brief", AsyncMock(return_value=""))
    with patch.object(
        tracking, "track_proactive_tokens", new=AsyncMock(return_value=expected_run)
    ) as bill:
        with pytest.raises(type(failure)) as raised:
            if path == "phone":
                await phone.synthesize_return(
                    transcript="",
                    transcript_summary="",
                    structured_data=StructuredCallData(),
                    objective="",
                    callee_display="",
                    user_language="fr",
                    user_timezone="Europe/Paris",
                    user_id=user_id,
                    call_id=call_id,
                )
            else:
                await debrief.write_debrief(
                    author=debrief.DebriefAuthor(user_id, "reader", None, False),
                    person_name="person",
                    evidence={},
                    language="fr",
                    local_date=date(2026, 8, 17),
                    run_id=expected_run,
                    target_id="opaque-identity",
                )
        assert raised.value is failure
    bill.assert_awaited_once()
    values = bill.await_args.kwargs
    assert values["run_id"] == expected_run and values["user_id"] == user_id
    assert values["failed"] and values["source"] == "user"
    assert len(values["billing_records"]) == 1
    assert values["billing_records"][0].model_name == "returned-model"
    assert values["billing_records"][0].started_at == 1000


async def test_successful_phone_synthesis_is_not_billed_again_by_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, call_id = uuid4(), uuid4()

    async def provider(**kwargs):
        _reply_capture(kwargs)
        return ReturnProposal(summary="result", proposal_text="result")

    monkeypatch.setattr(phone, "get_llm", lambda _: SimpleNamespace(model_name="requested"))
    monkeypatch.setattr(
        phone,
        "get_llm_config_for_agent",
        lambda *_: SimpleNamespace(model="requested", provider="openai"),
    )
    monkeypatch.setattr(phone, "get_structured_output_with_retry", provider)
    with patch.object(
        tracking, "track_proactive_tokens", new=AsyncMock(return_value="run")
    ) as bill:
        _, usage = await phone.synthesize_return(
            transcript="",
            transcript_summary="",
            structured_data=StructuredCallData(),
            objective="",
            callee_display="",
            user_language="fr",
            user_timezone="UTC",
            user_id=user_id,
            call_id=call_id,
        )
        assert usage is not None and usage.accounting_handled
        assert usage.model_name == "returned-model"
        # Delivery happens later and retains the cost display, without replay.
        await track_synthesis_usage(usage, call_id=call_id, user_id=user_id)
    bill.assert_awaited_once()


async def test_successful_debrief_bill_is_internal_and_not_replayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def provider(*args, **kwargs):
        _reply_capture(kwargs)
        return DebriefDraft(headline="result", where_we_stand="result")

    monkeypatch.setattr(debrief, "get_llm", lambda _: SimpleNamespace(model_name="requested"))
    monkeypatch.setattr(
        debrief,
        "get_llm_config_for_agent",
        lambda *_: SimpleNamespace(model="requested", provider="openai"),
    )
    monkeypatch.setattr(debrief, "get_structured_output_with_retry", provider)
    monkeypatch.setattr(debrief, "_personality_brief", AsyncMock(return_value=""))
    with patch.object(
        tracking, "track_proactive_tokens", new=AsyncMock(return_value="run")
    ) as bill:
        _, usage = await debrief.write_debrief(
            author=debrief.DebriefAuthor(uuid4(), "reader", None, False),
            person_name="person",
            evidence={},
            language="fr",
            local_date=date(2026, 8, 17),
            run_id="run",
            target_id="opaque",
        )
    assert usage.accounting_handled
    assert usage.model_name == "returned-model"
    assert "accounting_handled" not in usage.model_dump(mode="json")
    assert "billing_records" not in usage.model_dump(mode="json")
    bill.assert_awaited_once()
