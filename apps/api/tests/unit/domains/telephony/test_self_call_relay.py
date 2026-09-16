"""Unit tests for the relay synthesis — the call becomes a message (lot 4).

The transcript is projected under a token budget with the cut stated, the
model is reached through the ONE structured-output chokepoint with the call's
owner named, and the result is a first-person message plus the owner flag the
runner reads before anything is relayed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.domains.telephony.self_call_relay as relay
from src.core.config import settings
from src.domains.telephony.budget import token_count
from src.domains.telephony.schemas import SelfCallData, SelfCallRelay


def _payload(turns: list[tuple[str, str]], *, collected: dict | None = None) -> dict:
    return {
        "data": {
            "metadata": {"call_duration_secs": 300},
            "status": "done",
            "analysis": {
                "transcript_summary": "vendor summary",
                "data_collection_results": {
                    key: {"value": value} for key, value in (collected or {}).items()
                },
            },
            "transcript": [{"role": role, "message": text} for role, text in turns],
        }
    }


@pytest.mark.unit
def test_project_transcript_keeps_every_turn_under_budget() -> None:
    text, cut = relay.project_transcript(
        _payload([("agent", "hello"), ("user", "hi, remind me to call the bank")]),
        budget_tokens=1000,
    )
    assert text.splitlines() == ["agent: hello", "user: hi, remind me to call the bank"]
    assert cut is False


@pytest.mark.unit
def test_project_transcript_cuts_at_turn_boundaries_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turns = [("user", f"turn {i} " + " ".join(["word"] * 30)) for i in range(40)]
    text, cut = relay.project_transcript(_payload(turns), budget_tokens=200)
    assert cut is True
    kept = text.splitlines()
    assert kept[0].startswith("user: turn 0 ")
    assert all(line.startswith("user: turn ") for line in kept)
    assert token_count(text) <= 200 + 40


@pytest.mark.unit
def test_extract_self_data_reads_the_owner_flag_and_requests() -> None:
    data = relay.extract_self_data(
        _payload([], collected={"owner_confirmed": True, "requests": "call the bank"})
    )
    assert data == SelfCallData(owner_confirmed=True, requests="call the bank")


@pytest.mark.unit
def test_extract_self_data_degrades_on_a_mistyped_value() -> None:
    data = relay.extract_self_data(_payload([], collected={"owner_confirmed": "maybe"}))
    assert data == SelfCallData()


def _install(monkeypatch: pytest.MonkeyPatch, *, result: SelfCallRelay) -> dict:
    captured: dict = {}

    async def _fake_chokepoint(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        for handler in kwargs["config"]["callbacks"]:
            if isinstance(handler, relay.TokenCaptureHandler):
                handler.tokens_in += 300
                handler.tokens_out += 60
        return result

    monkeypatch.setattr(relay, "get_llm", lambda _t: object())
    monkeypatch.setattr(relay, "load_telephony_prompt", lambda _n, _v: "SYSTEM")
    monkeypatch.setattr(
        relay,
        "get_llm_config_for_agent",
        lambda _s, _t: SimpleNamespace(provider="openai", model="gpt-4.1-mini"),
    )
    monkeypatch.setattr(relay, "get_structured_output_with_retry", _fake_chokepoint)
    return captured


@pytest.mark.unit
async def test_synthesize_relay_goes_through_the_chokepoint_with_the_owner_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import uuid4

    user_id = uuid4()
    captured = _install(
        monkeypatch,
        result=SelfCallRelay(owner_confirmed=True, relay_message="Remind me…", summary="S"),
    )
    monkeypatch.setattr(settings, "telephony_relay_transcript_max_tokens", 5000, raising=False)

    outcome, usage = await relay.synthesize_relay(
        payload=_payload([("agent", "hello"), ("user", "remind me to call the bank tomorrow")]),
        objective="catch-up",
        user_language="fr",
        user_timezone="Europe/Paris",
        user_id=user_id,
    )

    assert outcome.relay_message == "Remind me…"
    assert captured["user_id"] == user_id
    assert captured["node_name"] == "telephony_synthesis"
    assert captured["schema"] is SelfCallRelay
    human = captured["messages"][1].content
    assert "remind me to call the bank tomorrow" in human
    assert "LANGUAGE: French (fr)" in human or "LANGUAGE: fran" in human
    assert "OBJECTIVE: catch-up" in human
    assert usage is not None and usage.tokens_in == 300 and usage.tokens_out == 60


@pytest.mark.unit
async def test_synthesize_relay_states_the_transcript_cut_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(
        monkeypatch, result=SelfCallRelay(owner_confirmed=True, relay_message="x", summary="s")
    )
    monkeypatch.setattr(settings, "telephony_relay_transcript_max_tokens", 500, raising=False)
    turns = [("user", f"turn {i} " + " ".join(["word"] * 30)) for i in range(40)]

    await relay.synthesize_relay(
        payload=_payload(turns),
        objective="",
        user_language="en",
        user_timezone="UTC",
        user_id=None,
    )

    human = captured["messages"][1].content
    assert "TRANSCRIPT (cut" in human
