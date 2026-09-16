"""Unit tests for the owner call's return path — synthesize, claim, relay, settle (lot 4)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

import src.domains.telephony.owner_call as oc
from src.domains.telephony.models import (
    CallKind,
    NotificationStatus,
    PhoneCallOutcome,
    PhoneCallStatus,
)
from src.domains.telephony.schemas import SelfCallRelay
from src.domains.telephony.synthesis_usage import SynthUsage
from src.infrastructure.scheduler.phone_relay_runner import RelayOutcome


def _call() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=PhoneCallStatus.DIALING,
        objective="catch-up",
        callee_display="Alex",
        call_kind=CallKind.SELF,
    )


def _payload() -> dict:
    return {
        "data": {
            "metadata": {"call_duration_secs": 90},
            "status": "done",
            "analysis": {
                "transcript_summary": "vendor summary",
                "data_collection_results": {"owner_confirmed": {"value": True}},
            },
            "transcript": [{"role": "user", "message": "remind me"}],
        }
    }


class _Repo:
    def __init__(self, claimed: bool = True) -> None:
        self.claimed = claimed
        self.calls: list[tuple[str, Any]] = []

    async def mark_completed(self, cid, **kwargs):  # noqa: ANN001
        self.calls.append(("mark_completed", kwargs))
        return self.claimed

    async def mark_relay_delivered(self, cid, *, outcome="answered"):  # noqa: ANN001
        self.calls.append(("mark_relay_delivered", cid, outcome))
        return True


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    relay: SelfCallRelay | Exception | None = None,
    outcome: RelayOutcome = RelayOutcome.ANSWERED,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    result = relay or SelfCallRelay(owner_confirmed=True, relay_message="remind me", summary="S")

    async def _synth(**kwargs):  # noqa: ANN003
        captured["synth"] = kwargs
        if isinstance(result, Exception):
            raise result
        return result, SynthUsage(tokens_in=10, tokens_out=5, tokens_cache=0, model_name="m")

    async def _run(request, *, db):  # noqa: ANN001
        captured["relay_request"] = request
        return outcome

    async def _settle(**kwargs):  # noqa: ANN003
        captured["settle"] = kwargs

    async def _track(usage, *, call_id, user_id):  # noqa: ANN001
        captured["tracked"] = usage

    async def _detach(db, *, user_id):  # noqa: ANN001
        captured["detached"] = user_id
        return True

    monkeypatch.setattr(oc, "detach_live_tools", _detach)
    monkeypatch.setattr(oc, "synthesize_relay", _synth)
    monkeypatch.setattr(oc, "run_relay", _run)
    monkeypatch.setattr(oc, "settle_owner_call", _settle)
    monkeypatch.setattr(oc, "track_synthesis_usage", _track)
    return captured


@pytest.mark.unit
async def test_the_row_is_claimed_as_relaying_then_the_relay_runs_and_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(monkeypatch)
    repo = _Repo()
    call = _call()
    user = SimpleNamespace(id=call.user_id)

    await oc.process_owner_call(
        db=object(),
        repo=repo,  # type: ignore[arg-type]
        call=call,  # type: ignore[arg-type]
        payload=_payload(),
        user=user,
        language="fr",
        user_timezone="Europe/Paris",
        status=PhoneCallStatus.COMPLETED,
        call_seconds=Decimal("90"),
    )

    kind, kwargs = repo.calls[0]
    assert kind == "mark_completed"
    assert kwargs["notification_status"] is NotificationStatus.RELAYING
    assert kwargs["summary"] == "S"
    assert kwargs["structured_data"] == {"owner_confirmed": True}
    assert kwargs["outcome"] is PhoneCallOutcome.OBJECTIVE_MET
    assert kwargs["debrief"] is None
    assert "relay_failed" in kwargs["notification_content"] or kwargs["notification_content"]
    assert captured["synth"]["user_id"] == call.user_id
    assert captured["relay_request"].relay.relay_message == "remind me"
    assert captured["settle"]["outcome"] is RelayOutcome.ANSWERED
    assert captured["tracked"].tokens_in == 10


@pytest.mark.unit
async def test_a_lost_claim_relays_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch)
    repo = _Repo(claimed=False)
    call = _call()

    await oc.process_owner_call(
        db=object(),
        repo=repo,  # type: ignore[arg-type]
        call=call,  # type: ignore[arg-type]
        payload=_payload(),
        user=SimpleNamespace(id=call.user_id),
        language="fr",
        user_timezone="Europe/Paris",
        status=PhoneCallStatus.COMPLETED,
        call_seconds=None,
    )
    assert "relay_request" not in captured
    assert "settle" not in captured


@pytest.mark.unit
async def test_a_failed_synthesis_settles_as_failed_with_the_vendor_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(monkeypatch, relay=RuntimeError("provider down"))
    repo = _Repo()
    call = _call()

    await oc.process_owner_call(
        db=object(),
        repo=repo,  # type: ignore[arg-type]
        call=call,  # type: ignore[arg-type]
        payload=_payload(),
        user=SimpleNamespace(id=call.user_id),
        language="fr",
        user_timezone="Europe/Paris",
        status=PhoneCallStatus.COMPLETED,
        call_seconds=None,
    )
    _, kwargs = repo.calls[0]
    assert kwargs["summary"] == "vendor summary"
    assert kwargs["outcome"] is PhoneCallOutcome.PARTIAL
    assert "relay_request" not in captured  # no words to relay
    assert captured["settle"]["outcome"] is RelayOutcome.FAILED


@pytest.mark.unit
async def test_an_unanswered_call_is_unreachable_and_never_relayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install(monkeypatch)
    repo = _Repo()
    call = _call()

    await oc.process_owner_call(
        db=object(),
        repo=repo,  # type: ignore[arg-type]
        call=call,  # type: ignore[arg-type]
        payload=_payload(),
        user=SimpleNamespace(id=call.user_id),
        language="fr",
        user_timezone="Europe/Paris",
        status=PhoneCallStatus.NO_ANSWER,
        call_seconds=None,
    )
    _, kwargs = repo.calls[0]
    assert kwargs["outcome"] is PhoneCallOutcome.UNREACHABLE
    assert "synth" not in captured  # no model spent on a call nobody answered
    # « Nobody answered » is not « someone else answered »: the person reads
    # the difference (production 2026-09-16, a call that died at pickup was
    # reported as answered by a stranger).
    assert captured["settle"]["outcome"] is RelayOutcome.UNANSWERED


@pytest.mark.unit
async def test_a_call_that_failed_technically_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch)
    repo = _Repo()
    call = _call()

    await oc.process_owner_call(
        db=object(),
        repo=repo,  # type: ignore[arg-type]
        call=call,  # type: ignore[arg-type]
        payload=_payload(),
        user=SimpleNamespace(id=call.user_id),
        language="fr",
        user_timezone="Europe/Paris",
        status=PhoneCallStatus.FAILED,
        call_seconds=None,
    )
    assert "synth" not in captured
    assert captured["settle"]["outcome"] is RelayOutcome.CALL_FAILED


@pytest.mark.unit
async def test_the_live_tools_are_detached_from_the_agent_once_the_call_ended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tools were attached to the AGENT for this call (the vendor refuses
    per-call ids): they come off when the call ends, best-effort, before the
    next stranger is dialled — and the dial path detaches again if this fails."""
    captured = _install(monkeypatch)
    detached: list = []

    async def _detach(db, *, user_id):  # noqa: ANN001
        detached.append(user_id)
        return True

    monkeypatch.setattr(oc, "detach_live_tools", _detach)
    repo = _Repo()
    call = _call()
    await oc.process_owner_call(
        db=object(),
        repo=repo,  # type: ignore[arg-type]
        call=call,  # type: ignore[arg-type]
        payload=_payload(),
        user=SimpleNamespace(id=call.user_id),
        language="fr",
        user_timezone="Europe/Paris",
        status=PhoneCallStatus.COMPLETED,
        call_seconds=None,
    )
    assert detached == [call.user_id]
    assert captured["settle"]["outcome"] is RelayOutcome.ANSWERED


@pytest.mark.unit
async def test_no_recipient_closes_the_outbox(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch)
    repo = _Repo()
    call = _call()

    await oc.process_owner_call(
        db=object(),
        repo=repo,  # type: ignore[arg-type]
        call=call,  # type: ignore[arg-type]
        payload=_payload(),
        user=None,
        language="fr",
        user_timezone="Europe/Paris",
        status=PhoneCallStatus.COMPLETED,
        call_seconds=None,
    )
    # Closed as FAILED, never as « answered »: nobody was there to relay to.
    assert ("mark_relay_delivered", call.id, "failed") in repo.calls
    assert "relay_request" not in captured
