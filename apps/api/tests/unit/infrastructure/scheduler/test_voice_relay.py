"""Unit tests for the relay synthesis — the session becomes a message (ADR-290 lot 4, ADR-301).

The transcript is projected under a token budget with the cut stated, the
model is reached through the ONE structured-output chokepoint with the
session's owner named, and the result is a first-person message plus the
owner flag the runner reads before anything is relayed. The entry is a
carrier-neutral transcript: the phone reads it from the vendor's payload,
a browser session from its record.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import src.infrastructure.scheduler.voice_relay as relay
from src.core.config import settings
from src.domains.telephony.budget import token_count
from src.domains.telephony.schemas import SelfCallData, SelfCallRelay
from src.domains.voice_sessions.session import VoiceCarrier
from src.domains.voice_sessions.transcript import VoiceTranscript


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
        relay.transcript_of_payload(
            _payload([("agent", "hello"), ("user", "hi, remind me to call the bank")])
        ),
        budget_tokens=1000,
    )
    assert text.splitlines() == ["agent: hello", "user: hi, remind me to call the bank"]
    assert cut is False


@pytest.mark.unit
def test_project_transcript_cuts_at_turn_boundaries_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turns = [("user", f"turn {i} " + " ".join(["word"] * 30)) for i in range(40)]
    text, cut = relay.project_transcript(
        relay.transcript_of_payload(_payload(turns)), budget_tokens=200
    )
    assert cut is True
    kept = text.splitlines()
    assert kept[0].startswith("user: turn 0 ")
    assert all(line.startswith("user: turn ") for line in kept)
    assert token_count(text) <= 200 + 40


@pytest.mark.unit
def test_extract_self_data_reads_the_owner_flag_and_requests() -> None:
    data = relay.collected_of_payload(
        _payload([], collected={"owner_confirmed": True, "requests": "call the bank"})
    )
    assert data == SelfCallData(owner_confirmed=True, requests="call the bank")


@pytest.mark.unit
def test_extract_self_data_degrades_on_a_mistyped_value() -> None:
    data = relay.collected_of_payload(_payload([], collected={"owner_confirmed": "maybe"}))
    assert data == SelfCallData()


def _install(monkeypatch: pytest.MonkeyPatch, *, result: SelfCallRelay) -> dict:
    captured: dict = {}

    async def _fake_chokepoint(**kwargs: Any) -> SelfCallRelay:
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
        carrier=VoiceCarrier.PHONE,
        transcript=relay.transcript_of_payload(
            _payload([("agent", "hello"), ("user", "remind me to call the bank tomorrow")])
        ),
        collected=relay.collected_of_payload(
            _payload([("agent", "hello"), ("user", "remind me to call the bank tomorrow")])
        ),
        vendor_summary=relay.vendor_summary_of_payload(
            _payload([("agent", "hello"), ("user", "remind me to call the bank tomorrow")])
        ),
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
        carrier=VoiceCarrier.PHONE,
        transcript=relay.transcript_of_payload(_payload(turns)),
        collected=relay.collected_of_payload(_payload(turns)),
        vendor_summary=relay.vendor_summary_of_payload(_payload(turns)),
        objective="",
        user_language="en",
        user_timezone="UTC",
        user_id=None,
    )

    human = captured["messages"][1].content
    assert "TRANSCRIPT (cut" in human


@pytest.mark.unit
async def test_the_relay_holds_no_session_across_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """The workboard runner's rule (review 2026-09-20): the probes run on a
    session of the relay's own, closed BEFORE the turn — measured 8.9 s of
    ``idle in transaction`` when the caller's session was held across it."""
    import contextlib
    from uuid import uuid4

    from src.domains.voice_sessions.session import VoiceSession
    from src.infrastructure.scheduler.out_of_turn_run import RunContext, RunOutcome, RunResult

    seen: dict[str, Any] = {"open": 0, "probed_open": None, "turn_open": None, "sessions": 0}

    @contextlib.asynccontextmanager
    async def _db_context():  # noqa: ANN202
        seen["open"] += 1
        seen["sessions"] += 1
        try:
            yield object()
        finally:
            seen["open"] -= 1

    async def _context(_db, _user_id):  # noqa: ANN001
        return RunContext(
            user=SimpleNamespace(id=uuid4()),
            language="fr",
            timezone="Europe/Paris",
            display_name="Alex",
            display_mode="cards",
            execution_mode="pipeline",
            memory_enabled=False,
            journals_enabled=False,
            psyche_enabled=False,
        )

    async def _pending(_db, _user_id, _language):  # noqa: ANN001
        seen["probed_open"] = seen["open"]
        return False, uuid4()

    @contextlib.asynccontextmanager
    async def _lease(_redis, _conversation_id, *, run_id, stream_id):  # noqa: ANN001
        yield True

    async def _stream(_request):  # noqa: ANN001
        seen["turn_open"] = seen["open"]
        return RunResult(outcome=RunOutcome.SUCCESS, text="ok", attempts=1)

    async def _redis() -> object:
        return object()

    monkeypatch.setattr(relay, "get_db_context", _db_context)
    monkeypatch.setattr(relay, "resolve_run_context", _context)
    monkeypatch.setattr(relay, "conversation_has_pending_hitl", _pending)
    monkeypatch.setattr(relay, "active_run_lease", _lease)
    monkeypatch.setattr(relay, "stream_instruction", _stream)
    monkeypatch.setattr(relay, "get_redis_cache", _redis)
    session = VoiceSession.browser(
        session_id="s" * 32,
        run_id="live_session_" + "s" * 32,
        mode="direct",
        user_id=uuid4(),
        conversation_id=uuid4(),
        language="fr",
        timezone="Europe/Paris",
    )
    outcome = await relay.run_voice_relay(
        relay.VoiceRelayRequest(
            session=session,
            relay=SelfCallRelay(owner_confirmed=True, relay_message="Remind me.", summary="s"),
        )
    )
    assert outcome is relay.RelayOutcome.ANSWERED
    assert seen["sessions"] == 1  # one session for the two probes
    assert seen["probed_open"] == 1  # the probes ran on it
    assert seen["turn_open"] == 0  # and it was closed before the turn
    assert seen["open"] == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("carrier", "named", "not_named"),
    [
        (VoiceCarrier.PHONE, "a phone call LIA placed", "authenticated"),
        (VoiceCarrier.BROWSER, "the line is authenticated", "a phone call LIA placed"),
    ],
)
async def test_the_context_names_the_line_that_carried_the_session(
    monkeypatch: pytest.MonkeyPatch, carrier: VoiceCarrier, named: str, not_named: str
) -> None:
    """The prompt's rule on who was speaking reads the SESSION line (review 2026-09-20).

    A browser session is the account holder's by construction; the prompt
    used to be written for a phone call alone, so its rule asked the model to
    find an identity check a browser transcript never holds.
    """
    captured = _install(
        monkeypatch, result=SelfCallRelay(owner_confirmed=True, relay_message="x", summary="s")
    )
    await relay.synthesize_relay(
        carrier=carrier,
        transcript=VoiceTranscript.from_rows([("user", "book the dentist for Thursday")]),
        collected=SelfCallData(owner_confirmed=True),
        vendor_summary="",
        objective="",
        user_language="en",
        user_timezone="UTC",
        user_id=None,
    )
    human = captured["messages"][1].content
    session_line = next(line for line in human.splitlines() if line.startswith("SESSION: "))
    assert named in session_line and not_named not in session_line
    # The lines file stands in for what the session did not carry — never a
    # phone-only word on a browser session.
    assert "OBJECTIVE: (a catch-up session)" in human
    assert "VENDOR SUMMARY: (none provided)" in human
