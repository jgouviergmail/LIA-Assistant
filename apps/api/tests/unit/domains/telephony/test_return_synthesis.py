"""Unit tests for the telephony return synthesis + delivery (P4.2)."""

from __future__ import annotations

import contextlib
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.return_synthesis as rs
from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus
from src.domains.telephony.schemas import ReturnProposal, StructuredCallData

# --------------------------------------------------------------------------- #
# Payload extraction
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_extract_structured_maps_data_collection() -> None:
    payload = {
        "data": {
            "analysis": {
                "data_collection_results": {
                    "agreed": {"value": True, "rationale": "she said yes"},
                    "proposed_datetime": {"value": "2026-07-14T19:00"},
                    "location": {"value": "Chez Paul"},
                    "unknown_field": {"value": "ignored"},
                }
            }
        }
    }
    sd = rs._extract_structured(payload)
    assert sd.agreed is True
    assert sd.proposed_datetime == "2026-07-14T19:00"
    assert sd.location == "Chez Paul"
    # extra="ignore" keeps StructuredCallData minimal
    assert not hasattr(sd, "unknown_field")


@pytest.mark.unit
def test_extract_structured_empty() -> None:
    assert rs._extract_structured({}) == StructuredCallData()


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"data": {"status": "done"}}, PhoneCallStatus.COMPLETED),
        ({"data": {"status": "failed"}}, PhoneCallStatus.FAILED),
        (
            {"data": {"metadata": {"termination_reason": "voicemail detected"}}},
            PhoneCallStatus.VOICEMAIL,
        ),
        ({"data": {"metadata": {"termination_reason": "no_answer"}}}, PhoneCallStatus.NO_ANSWER),
        ({}, PhoneCallStatus.COMPLETED),
    ],
)
def test_map_status(payload: dict, expected: PhoneCallStatus) -> None:
    assert rs._map_status(payload) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "agreed,status,expected",
    [
        (True, PhoneCallStatus.COMPLETED, PhoneCallOutcome.OBJECTIVE_MET),
        (False, PhoneCallStatus.COMPLETED, PhoneCallOutcome.DECLINED),
        (None, PhoneCallStatus.COMPLETED, PhoneCallOutcome.PARTIAL),
        (True, PhoneCallStatus.VOICEMAIL, PhoneCallOutcome.UNREACHABLE),
    ],
)
def test_derive_outcome(agreed, status, expected) -> None:
    assert rs._derive_outcome(StructuredCallData(agreed=agreed), status) == expected


@pytest.mark.unit
def test_extract_call_seconds() -> None:
    assert rs._extract_call_seconds({"data": {"metadata": {"call_duration_secs": 42}}}) == Decimal(
        "42"
    )
    assert rs._extract_call_seconds({}) is None
    assert rs._extract_call_seconds({"data": {"metadata": {"call_duration_secs": "bad"}}}) is None


# --------------------------------------------------------------------------- #
# synthesize_return
# --------------------------------------------------------------------------- #


@pytest.mark.unit
async def test_synthesize_return_uses_typed_output_and_context(monkeypatch) -> None:
    captured: dict = {}

    class _FakeStructured:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return ReturnProposal(summary="S", proposal_text="P")

    class _FakeLLM:
        def with_structured_output(self, model, **kwargs):
            captured["model"] = model
            captured["include_raw"] = kwargs.get("include_raw")
            return _FakeStructured()

    monkeypatch.setattr(rs, "get_llm", lambda _t: _FakeLLM())
    monkeypatch.setattr(rs, "load_prompt", lambda _n, _v: "SYSTEM")

    proposal, usage = await rs.synthesize_return(
        transcript="raw transcript",
        transcript_summary="she agreed",
        structured_data=StructuredCallData(agreed=True, proposed_datetime="mardi 19h"),
        objective="ask availability",
        callee_display="Marie",
        user_language="fr",
    )

    assert proposal == ReturnProposal(summary="S", proposal_text="P")
    assert usage is None  # the fake returns a plain proposal (no include_raw envelope)
    assert captured["model"] is ReturnProposal
    assert captured["include_raw"] is True  # needed to surface token usage (G-1)
    assert len(captured["messages"]) == 2  # system + human
    human = captured["messages"][1].content
    assert "OBJECTIVE: ask availability" in human
    assert "CALLEE: Marie" in human
    assert "LANGUAGE: fr" in human
    assert "mardi 19h" in human


# --------------------------------------------------------------------------- #
# process_completed_call
# --------------------------------------------------------------------------- #


def _install_pipeline(monkeypatch, *, call, mark_result: bool = True) -> dict:
    captured: dict = {}

    class _FakeRepo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def get_by_call_id(self, _cid):
            return call

        async def mark_completed(self, cid, **kwargs):
            captured["mark"] = {"call_id": cid, **kwargs}
            return mark_result

    async def _get_user(_model, _pk):
        return SimpleNamespace(language="fr")

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace(get=_get_user)

    class _FakeDispatcher:
        async def dispatch(self, **kwargs):
            captured["dispatch"] = kwargs
            return None

    async def _fake_synth(**kwargs):
        captured["synth_in"] = kwargs
        return (
            ReturnProposal(summary="Recap", proposal_text="J'ai appelé Marie"),
            rs._SynthUsage(tokens_in=40, tokens_out=20, tokens_cache=0, model_name="gpt-4.1-nano"),
        )

    async def _fake_track(**kwargs):
        captured["track"] = kwargs
        return "tok_1"

    monkeypatch.setattr(rs, "TelephonyRepository", _FakeRepo)
    monkeypatch.setattr(rs, "get_db_context", _ctx)
    monkeypatch.setattr(rs, "NotificationDispatcher", lambda: _FakeDispatcher())
    monkeypatch.setattr(rs, "synthesize_return", _fake_synth)
    monkeypatch.setattr(rs, "track_proactive_tokens", _fake_track)
    return captured


def _payload() -> dict:
    return {
        "data": {
            "metadata": {"call_duration_secs": 30},
            "status": "done",
            "analysis": {
                "transcript_summary": "she agreed",
                "data_collection_results": {"agreed": {"value": True}},
            },
            "transcript": [{"role": "agent", "message": "hi"}, {"role": "user", "message": "sure"}],
        }
    }


@pytest.mark.unit
async def test_process_persists_minimized_and_delivers_once(monkeypatch) -> None:
    call = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=PhoneCallStatus.DIALING,
        objective="ask availability",
        callee_display="Marie",
    )
    captured = _install_pipeline(monkeypatch, call=call)

    await rs.process_completed_call(call.id, _payload())

    mark = captured["mark"]
    # Only the minimized outcome is persisted — NEVER the transcript.
    assert mark["summary"] == "Recap"
    assert mark["structured_data"] == {"agreed": True}
    assert mark["status"] == PhoneCallStatus.COMPLETED
    assert mark["outcome"] == PhoneCallOutcome.OBJECTIVE_MET
    assert "transcript" not in mark
    assert "hi" not in str(mark)  # transcript text does not leak into persistence
    # The transcript WAS available to synthesis (then discarded).
    assert "hi" in captured["synth_in"]["transcript"]
    # Delivered exactly once, with the localized title.
    assert captured["dispatch"]["content"] == "J'ai appelé Marie"
    assert captured["dispatch"]["task_type"] == "phone_call"
    assert captured["dispatch"]["title"] == "Retour d'appel"
    # G-1: the synthesis LLM token usage is tracked (like briefing/heartbeat).
    assert captured["track"]["tokens_in"] == 40
    assert captured["track"]["task_type"] == "phone_call"
    assert captured["track"]["model_name"] == "gpt-4.1-nano"


@pytest.mark.unit
async def test_process_skips_when_already_terminal(monkeypatch) -> None:
    call = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=PhoneCallStatus.COMPLETED,  # already processed
        objective="x",
        callee_display="Marie",
    )
    captured = _install_pipeline(monkeypatch, call=call)
    await rs.process_completed_call(call.id, _payload())
    assert "mark" not in captured
    assert "dispatch" not in captured


@pytest.mark.unit
async def test_process_no_delivery_when_lost_race(monkeypatch) -> None:
    call = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=PhoneCallStatus.DIALING,
        objective="x",
        callee_display="Marie",
    )
    captured = _install_pipeline(monkeypatch, call=call, mark_result=False)
    await rs.process_completed_call(call.id, _payload())
    assert "mark" in captured  # attempted
    assert "dispatch" not in captured  # but lost the race → no double delivery


@pytest.mark.unit
async def test_process_falls_back_on_synthesis_failure(monkeypatch) -> None:
    call = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=PhoneCallStatus.DIALING,
        objective="x",
        callee_display="Marie",
    )
    captured = _install_pipeline(monkeypatch, call=call)

    async def _boom(**kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(rs, "synthesize_return", _boom)
    await rs.process_completed_call(call.id, _payload())
    # Still delivers something (the raw ElevenLabs summary as fallback).
    assert captured["dispatch"]["content"] == "she agreed"
    # No usage on the failure path → nothing tracked.
    assert "track" not in captured
