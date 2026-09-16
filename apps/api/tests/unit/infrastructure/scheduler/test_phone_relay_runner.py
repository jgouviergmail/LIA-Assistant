"""Unit tests for the relay runner — the call's words become the person's turn (lot 4).

Everything around the turn is faked at its seam (the engine, the pending-HITL
probe, the conversation lease, the push); what is exercised is the decision:
who was on the line, whether there is anything to relay, whether the thread
is free, and how each outcome settles.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

import src.infrastructure.scheduler.phone_relay_runner as runner
from src.core.config import settings
from src.domains.telephony.schemas import SelfCallRelay
from src.infrastructure.scheduler.out_of_turn_run import RunContext, RunOutcome, RunResult
from src.infrastructure.scheduler.phone_relay_runner import RelayOutcome, RelayRequest, run_relay


def _request(**overrides: Any) -> RelayRequest:
    base: dict[str, Any] = {
        "call_id": uuid4(),
        "user_id": uuid4(),
        "relay": SelfCallRelay(
            owner_confirmed=True, relay_message="Remind me to call the bank.", summary="S"
        ),
    }
    base.update(overrides)
    return RelayRequest(**base)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: RunContext | None = "default",  # type: ignore[assignment]
    pending: bool = False,
    conversation_id: object = "conv",
    lease_acquired: bool = True,
    result: RunResult | None = None,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    if context == "default":
        context = RunContext(
            user=SimpleNamespace(id=uuid4()),
            language="fr",
            timezone="Europe/Paris",
            display_name="Alex",
            display_mode="cards",
            execution_mode="react",
            memory_enabled=True,
            journals_enabled=False,
            psyche_enabled=True,
        )

    async def _context(_db, _user_id):  # noqa: ANN001
        return context

    async def _pending(_db, _user_id, _language):  # noqa: ANN001
        return pending, (uuid4() if conversation_id == "conv" else conversation_id)

    @contextlib.asynccontextmanager
    async def _lease(_redis, _conversation_id, *, run_id, stream_id):  # noqa: ANN001
        captured.setdefault("lease_attempts", 0)
        captured["lease_attempts"] += 1
        yield lease_acquired

    async def _stream(request):  # noqa: ANN001
        captured["request"] = request
        return result or RunResult(outcome=RunOutcome.SUCCESS, text="ok", attempts=1)

    async def _redis():
        return object()

    class _Dispatcher:
        def __init__(self, **kwargs: Any) -> None:
            captured["dispatcher_kwargs"] = kwargs

        async def dispatch(self, **kwargs: Any) -> None:
            captured["push"] = kwargs

    monkeypatch.setattr(runner, "resolve_run_context", _context)
    monkeypatch.setattr(runner, "conversation_has_pending_hitl", _pending)
    monkeypatch.setattr(runner, "active_run_lease", _lease)
    monkeypatch.setattr(runner, "stream_instruction", _stream)
    monkeypatch.setattr(runner, "get_redis_cache", _redis)
    monkeypatch.setattr(runner, "NotificationDispatcher", _Dispatcher)
    monkeypatch.setattr(settings, "telephony_relay_busy_retries", 2, raising=False)
    monkeypatch.setattr(settings, "telephony_relay_busy_delay_seconds", 0, raising=False)
    return captured


@pytest.mark.unit
async def test_the_relay_runs_as_the_persons_own_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch)
    request = _request()

    outcome = await run_relay(request, db=object())

    assert outcome is RelayOutcome.ANSWERED
    stream = captured["request"]
    assert stream.prompt == "Remind me to call the bank."
    assert stream.spoken_by_person is True
    assert stream.execution_mode == "react"
    assert stream.memory_enabled is True
    assert stream.psyche_enabled is True
    assert stream.origin is not None
    assert stream.origin.kind == "phone_call"
    assert stream.origin.hidden is False
    assert stream.origin.ticket_id == str(request.call_id)
    assert stream.run_id == stream.origin.run_id
    # Lot 8: the SAME run id as the call's live lookups and its synthesis, so
    # the per-run summary the chat meter reads is the whole call's bill.
    from src.domains.telephony.spend import phone_call_run_id

    assert stream.run_id == phone_call_run_id(request.call_id)
    assert stream.session_id.startswith("phone_call_")
    assert stream.timeout_seconds == settings.telephony_relay_timeout_seconds
    # The answer lives in the chat; the push only says so (archive/SSE off).
    assert captured["dispatcher_kwargs"] == {"archive_enabled": False, "sse_enabled": False}


@pytest.mark.unit
async def test_someone_else_on_the_line_relays_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch)
    outcome = await run_relay(
        _request(relay=SelfCallRelay(owner_confirmed=False, relay_message="x", summary="S")),
        db=object(),
    )
    assert outcome is RelayOutcome.NOT_OWNER
    assert "request" not in captured


@pytest.mark.unit
async def test_nothing_to_relay_is_honest(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch)
    outcome = await run_relay(
        _request(relay=SelfCallRelay(owner_confirmed=True, relay_message="  ", summary="S")),
        db=object(),
    )
    assert outcome is RelayOutcome.EMPTY
    assert "request" not in captured


@pytest.mark.unit
async def test_a_pending_question_on_the_thread_stops_the_relay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(monkeypatch, pending=True)
    outcome = await run_relay(_request(), db=object())
    assert outcome is RelayOutcome.PENDING_QUESTION
    assert "request" not in captured


@pytest.mark.unit
async def test_a_busy_thread_is_retried_then_given_up(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch, lease_acquired=False)
    outcome = await run_relay(_request(), db=object())
    assert outcome is RelayOutcome.BUSY
    assert captured["lease_attempts"] == settings.telephony_relay_busy_retries
    assert "request" not in captured


@pytest.mark.unit
async def test_an_unresolved_conversation_runs_without_a_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(monkeypatch, conversation_id=None)
    outcome = await run_relay(_request(), db=object())
    assert outcome is RelayOutcome.ANSWERED
    assert "lease_attempts" not in captured


@pytest.mark.unit
async def test_drafts_waiting_send_a_push_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(
        monkeypatch, result=RunResult(outcome=RunOutcome.WAITING, text="?", attempts=1)
    )
    outcome = await run_relay(_request(), db=object())
    assert outcome is RelayOutcome.WAITING
    assert captured["dispatcher_kwargs"] == {"archive_enabled": False, "sse_enabled": False}
    assert captured["push"]["task_type"] == "phone_call"
    assert captured["push"]["push_enabled"] is True


@pytest.mark.unit
async def test_an_answered_relay_sends_a_push_saying_the_chat_holds_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The phone is a channel for someone AWAY from the app: once the turn ran,
    a push says LIA acted and the answer is in the chat (push only — the
    answer itself is already archived as the turn's own row)."""
    captured = _install(monkeypatch)
    from src.core.i18n_telephony import get_return_phrases

    outcome = await run_relay(_request(), db=object())
    assert outcome is RelayOutcome.ANSWERED
    assert captured["dispatcher_kwargs"] == {"archive_enabled": False, "sse_enabled": False}
    assert captured["push"]["content"] == get_return_phrases("fr")["relay_answered"]
    assert captured["push"]["push_enabled"] is True
    assert captured["push"]["metadata"] == {"relay": "answered"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("run_outcome", "expected"),
    [
        (RunOutcome.QUOTA_BLOCKED, RelayOutcome.QUOTA_BLOCKED),
        (RunOutcome.FAILED, RelayOutcome.FAILED),
    ],
)
async def test_refusals_and_failures_are_named(
    monkeypatch: pytest.MonkeyPatch, run_outcome: RunOutcome, expected: RelayOutcome
) -> None:
    _install(monkeypatch, result=RunResult(outcome=run_outcome, text="", attempts=1, error="e"))
    assert await run_relay(_request(), db=object()) is expected


@pytest.mark.unit
async def test_an_inactive_account_fails_the_relay(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, context=None)
    assert await run_relay(_request(), db=object()) is RelayOutcome.FAILED


@pytest.mark.unit
def test_every_fallback_outcome_has_a_sentence_in_every_language() -> None:
    from src.core.i18n_telephony import RETURN_PHRASES
    from src.infrastructure.scheduler.phone_relay_runner import FALLBACK_PHRASE_KEYS

    fallbacks = {o for o in RelayOutcome if o not in (RelayOutcome.ANSWERED, RelayOutcome.WAITING)}
    assert set(FALLBACK_PHRASE_KEYS) == fallbacks
    for language, phrases in RETURN_PHRASES.items():
        for outcome, key in FALLBACK_PHRASE_KEYS.items():
            assert phrases.get(key), (language, outcome)
        assert phrases.get("relay_drafts_waiting"), language
        assert phrases.get("relay_answered"), language
        assert phrases.get("relay_unanswered"), language
        assert phrases.get("relay_call_failed"), language
        assert phrases.get("self_call_title"), language
