"""The call-back a vendor tool makes during an owner call (lot 7).

A public route with no session: it answers only for an ACTIVE OWNER call,
with the connector's derived token, for an allow-listed tool, within the
call's budget — and whatever it refuses reads as « not found », except a wrong
secret on a known call, which is a security event.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import Request

import src.domains.agents.telephony.live_tools as lmod
import src.domains.agents.telephony.live_tools_router as rmod
import src.domains.agents.telephony.voice_lookup as admission
from src.core.config import settings
from src.core.exceptions import ForbiddenError, ResourceNotFoundError
from src.domains.agents.telephony.live_tools import LiveToolSpec, result_lines
from src.domains.telephony.live_tools import LIVE_TOOL_HEADER, LiveToolAuth, LiveToolAuthOutcome

#: A derived list small enough to read: two catalogue tools and the native
#: memories lookup (lot 8).
SPECS: tuple[LiveToolSpec, ...] = (
    LiveToolSpec("get_events_tool", "event", "event", ("query",)),
    LiveToolSpec("get_tasks_tool", "task", "task", ()),
    LiveToolSpec("recall_memories", "context", "memories", (), True),
)


def _request(body: dict[str, Any] | str, *, token: str = "tok") -> Request:
    raw = body if isinstance(body, str) else json.dumps(body)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/telephony/tools/get_events_tool",
        "headers": [(LIVE_TOOL_HEADER.lower().encode(), token.encode())],
        "query_string": b"",
    }
    payload = raw.encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(scope, receive)


class _DB:
    def __init__(self, user: object | None) -> None:
        self.user = user

    async def get(self, _model, _pk):  # noqa: ANN001
        return self.user


def _call() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), user_id=uuid4())


@pytest.fixture
def _wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "auth": LiveToolAuth(LiveToolAuthOutcome.OK, call=_call()),
        "budget": True,
        "ran": [],
        "available": SPECS,
    }
    monkeypatch.setattr(settings, "telephony_live_tools_enabled", True)
    monkeypatch.setattr(lmod, "_SPECS", SPECS)

    async def _authorize(_db, *, call_id_raw, presented_token):  # noqa: ANN001
        state["seen"] = (call_id_raw, presented_token)
        return state["auth"]

    async def _budget(_redis, _call_id, *, limit, ttl_seconds):  # noqa: ANN001
        state["budget_args"] = (limit, ttl_seconds)
        return state["budget"]

    async def _redis() -> object:
        return object()

    async def _available(
        *, disabled_domains=frozenset()
    ) -> tuple[LiveToolSpec, ...]:  # noqa: ANN001
        state["disabled_domains"] = disabled_domains
        return tuple(s for s in state["available"] if s.domain not in disabled_domains)

    async def _run(spec, args, **kwargs):  # noqa: ANN001, ANN003
        state["ran"].append((spec.name, args, kwargs))
        return "2 events"

    monkeypatch.setattr(rmod, "authorize_live_tool_call", _authorize)
    monkeypatch.setattr(rmod, "consume_live_tool_budget", _budget)
    monkeypatch.setattr(rmod, "get_redis_cache", _redis)
    monkeypatch.setattr(rmod, "available_live_tools", _available)
    # The run is the shared admission's (ADR-301): the runner is bound there.
    monkeypatch.setattr(admission, "run_live_tool", _run)
    return state


def _user(disabled: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        full_name="Alex",
        email="a@example.com",
        language="fr",
        timezone="Europe/Paris",
        phone_disabled_domains=disabled or [],
    )


@pytest.mark.unit
async def test_a_valid_callback_runs_the_tool_and_answers_its_text(_wired: dict) -> None:
    call = _wired["auth"].call
    body = {"call_id": str(call.id), "query": "dentist", "max_results": 5}
    out = await rmod.live_tool_callback("get_events_tool", _request(body), db=_DB(_user()))
    assert out == {"result": "2 events"}
    assert _wired["seen"] == (str(call.id), "tok")
    name, args, kwargs = _wired["ran"][0]
    assert name == "get_events_tool"
    assert args == {"query": "dentist", "max_results": 5}  # the call id never reaches the tool
    assert kwargs["user_id"] == call.user_id and kwargs["language"] == "fr"
    # The lookup is filed on the phone's host: its surface, its run id, its call.
    assert kwargs["host"].surface == "phone_call"
    assert kwargs["host"].key == str(call.id)
    # The budget is the call's own: its counter dies with LIA's own notion of a
    # live call (the duration cap is the portal's, LIA does not know it).
    assert _wired["budget_args"] == (
        settings.telephony_live_tool_max_calls_per_call,
        settings.telephony_stale_call_timeout_minutes * 60,
    )


@pytest.mark.unit
async def test_the_route_hides_itself_while_the_flag_is_off(
    _wired: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telephony_live_tools_enabled", False)
    with pytest.raises(ResourceNotFoundError):
        await rmod.live_tool_callback("get_events_tool", _request({"call_id": "x"}), db=_DB(None))
    assert "seen" not in _wired  # nothing was even looked up


@pytest.mark.unit
@pytest.mark.parametrize(
    "outcome", [LiveToolAuthOutcome.UNKNOWN_CALL, LiveToolAuthOutcome.NOT_CONFIGURED]
)
async def test_an_unknown_or_unconfigured_call_reads_as_not_found(
    _wired: dict, outcome: LiveToolAuthOutcome
) -> None:
    _wired["auth"] = LiveToolAuth(outcome)
    with pytest.raises(ResourceNotFoundError):
        await rmod.live_tool_callback(
            "get_events_tool", _request({"call_id": str(uuid4())}), db=_DB(None)
        )
    assert _wired["ran"] == []


@pytest.mark.unit
async def test_a_wrong_secret_on_a_known_call_is_forbidden(_wired: dict) -> None:
    _wired["auth"] = LiveToolAuth(LiveToolAuthOutcome.BAD_SECRET)
    with pytest.raises(ForbiddenError):
        await rmod.live_tool_callback(
            "get_events_tool", _request({"call_id": str(uuid4())}, token="bad"), db=_DB(None)
        )


@pytest.mark.unit
async def test_a_tool_outside_the_allowlist_reads_as_not_found(_wired: dict) -> None:
    with pytest.raises(ResourceNotFoundError):
        await rmod.live_tool_callback(
            "send_email_tool", _request({"call_id": str(uuid4())}), db=_DB(_user())
        )
    assert _wired["ran"] == []


@pytest.mark.unit
async def test_a_tool_a_capability_switched_off_reads_as_not_found(_wired: dict) -> None:
    """The endpoint offers exactly what provisioning offers: a tool hidden by
    a capability switch is refused even if its vendor tool still exists."""
    _wired["available"] = tuple(s for s in SPECS if s.name != "get_events_tool")
    with pytest.raises(ResourceNotFoundError):
        await rmod.live_tool_callback(
            "get_events_tool", _request({"call_id": str(uuid4())}), db=_DB(_user())
        )


@pytest.mark.unit
async def test_a_domain_the_person_switched_off_reads_as_not_found(_wired: dict) -> None:
    """Lot 8: the person's own switches are read from THEIR row at every
    call-back — a tool still attached by a stale PATCH answers nothing on a
    domain switched off since."""
    with pytest.raises(ResourceNotFoundError):
        await rmod.live_tool_callback(
            "get_events_tool", _request({"call_id": str(uuid4())}), db=_DB(_user(["event"]))
        )
    assert _wired["disabled_domains"] == frozenset({"event"})
    assert _wired["ran"] == []
    # The memories lookup answers on its own route like any other tool.
    out = await rmod.live_tool_callback(
        "recall_memories", _request({"call_id": str(uuid4()), "query": "tea"}), db=_DB(_user())
    )
    assert out == {"result": "2 events"}
    assert _wired["ran"][-1][0] == "recall_memories"


@pytest.mark.unit
async def test_a_malformed_body_reads_as_not_found(_wired: dict) -> None:
    with pytest.raises(ResourceNotFoundError):
        await rmod.live_tool_callback("get_events_tool", _request("not json"), db=_DB(None))


@pytest.mark.unit
async def test_an_exhausted_budget_answers_a_sentence_the_agent_can_say(_wired: dict) -> None:
    _wired["budget"] = False
    out = await rmod.live_tool_callback(
        "get_events_tool", _request({"call_id": str(uuid4())}), db=_DB(_user())
    )
    assert out == {"result": result_lines()["budget_exhausted"]}
    assert _wired["ran"] == []


@pytest.mark.unit
async def test_a_call_whose_user_vanished_reads_as_not_found(_wired: dict) -> None:
    with pytest.raises(ResourceNotFoundError):
        await rmod.live_tool_callback(
            "get_events_tool", _request({"call_id": str(uuid4())}), db=_DB(None)
        )


# ---------------------------------------------------------------------------
# The Live mode's delegation call-back (ADR-301): the row's mode is the switch
# ---------------------------------------------------------------------------


def _delegation_request(body: dict[str, Any] | str, *, token: str = "tok") -> Request:
    request = _request(body, token=token)
    request.scope["path"] = "/telephony/tools/send_to_lia"
    return request


@pytest.fixture
def _delegation(_wired: dict, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from src.infrastructure.scheduler.out_of_turn_run import RunContext
    from src.infrastructure.scheduler.voice_delegation import DelegationOutcome, DelegationResult

    call = _wired["auth"].call
    call.call_mode = "delegated"
    state: dict[str, Any] = {
        "result": DelegationResult(DelegationOutcome.ANSWERED, "C'est noté.", note="warm note"),
        "context": RunContext(
            user=object(),
            language="fr",
            timezone="Europe/Paris",
            display_name="Alex",
            display_mode="cards",
        ),
    }

    async def _context(_db, _user_id):  # noqa: ANN001
        return state["context"]

    class _Conversations:
        async def get_or_create_conversation(self, _user_id, _db, *, language):  # noqa: ANN001
            return SimpleNamespace(id=uuid4())

    async def _delegate(request, *, context):  # noqa: ANN001
        state["delegated"] = (request, context)
        return state["result"]

    monkeypatch.setattr(rmod, "resolve_run_context", _context)
    monkeypatch.setattr(rmod, "ConversationService", _Conversations)
    monkeypatch.setattr(rmod, "delegate", _delegate)
    monkeypatch.setattr(settings, "telephony_delegation_timeout_seconds", 90, raising=False)
    return state


@pytest.mark.unit
async def test_a_delegation_reaches_the_bridge_and_answers_with_its_note(
    _wired: dict, _delegation: dict
) -> None:
    call = _wired["auth"].call
    body = {"call_id": str(call.id), "request": "Rappelle-moi la banque demain"}
    out = await rmod.delegation_callback(_delegation_request(body), db=_DB(_user()))
    assert out == {"result": "C'est noté.", "tone": "warm note"}
    request, context = _delegation["delegated"]
    assert request.request == "Rappelle-moi la banque demain"
    assert request.session.key == f"phone_call_{call.id.hex}"
    assert request.session.mode == "delegated"
    assert request.session.user_id == call.user_id
    # The bridge answers the inner margin BEFORE the vendor's own timeout.
    assert request.wait_seconds == 87.0
    assert request.request_id  # minted here: the vendor names none
    assert context is _delegation["context"]


@pytest.mark.unit
async def test_a_result_without_a_note_carries_no_tone_field(
    _wired: dict, _delegation: dict
) -> None:
    from src.infrastructure.scheduler.voice_delegation import DelegationOutcome, DelegationResult

    _delegation["result"] = DelegationResult(DelegationOutcome.TIMED_OUT, "still working")
    call = _wired["auth"].call
    out = await rmod.delegation_callback(
        _delegation_request({"call_id": str(call.id), "request": "x"}), db=_DB(_user())
    )
    assert out == {"result": "still working"}


@pytest.mark.unit
async def test_a_direct_call_reads_as_not_found_on_the_delegation_route(
    _wired: dict, _delegation: dict
) -> None:
    """A stale attach must not let a DIRECT call's agent delegate."""
    call = _wired["auth"].call
    call.call_mode = "direct"
    with pytest.raises(ResourceNotFoundError):
        await rmod.delegation_callback(
            _delegation_request({"call_id": str(call.id), "request": "x"}), db=_DB(_user())
        )
    assert "delegated" not in _delegation


@pytest.mark.unit
async def test_a_request_off_the_message_bound_reads_as_not_found(
    _wired: dict, _delegation: dict
) -> None:
    from src.core.constants import CHAT_MESSAGE_MAX_LENGTH

    call = _wired["auth"].call
    too_long = "x" * (CHAT_MESSAGE_MAX_LENGTH + 1)
    with pytest.raises(ResourceNotFoundError):
        await rmod.delegation_callback(
            _delegation_request({"call_id": str(call.id), "request": too_long}), db=_DB(_user())
        )
    with pytest.raises(ResourceNotFoundError):
        await rmod.delegation_callback(
            _delegation_request({"call_id": str(call.id), "request": 42}), db=_DB(_user())
        )
    assert "delegated" not in _delegation


@pytest.mark.unit
async def test_a_wrong_secret_on_the_delegation_route_is_forbidden(
    _wired: dict, _delegation: dict
) -> None:
    _wired["auth"] = LiveToolAuth(LiveToolAuthOutcome.BAD_SECRET)
    with pytest.raises(ForbiddenError):
        await rmod.delegation_callback(
            _delegation_request({"call_id": str(uuid4()), "request": "x"}), db=_DB(_user())
        )


@pytest.mark.unit
async def test_the_delegation_route_needs_no_live_tools_flag(
    _wired: dict, _delegation: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mode on the row is the switch, not the lookups' flag."""
    monkeypatch.setattr(settings, "telephony_live_tools_enabled", False)
    call = _wired["auth"].call
    out = await rmod.delegation_callback(
        _delegation_request({"call_id": str(call.id), "request": "x"}), db=_DB(_user())
    )
    assert out["result"] == "C'est noté."


@pytest.mark.unit
async def test_a_call_that_spent_its_budget_hears_a_sentence_on_the_delegation_route(
    _wired: dict, _delegation: dict
) -> None:
    from src.domains.voice_sessions.mandate import bridge_lines

    _wired["budget"] = False
    call = _wired["auth"].call
    out = await rmod.delegation_callback(
        _delegation_request({"call_id": str(call.id), "request": "x"}), db=_DB(_user())
    )
    assert out == {"result": bridge_lines()["budget_exhausted"]}
    assert "delegated" not in _delegation
