"""Live read-only tools on an owner call — the telephony half (lot 7).

What this leaf owes the rest: a token derived from the connector's secret and
never equal to it, the public URL a vendor tool calls back on, the vendor
tool body built from ONE declaration of a tool's parameters, a fingerprint
that notices any drift of that body, the authorization of a call-back (an
active OWNER call, the right secret, nothing revealed otherwise), and a
per-call budget of lookups.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.live_tools as mod
from src.core.config import settings
from src.domains.telephony.live_tools import (
    LIVE_TOOL_HEADER,
    LiveToolAuthOutcome,
    LiveToolParameter,
    authorize_live_tool_call,
    consume_live_tool_budget,
    live_tool_token,
    live_tool_url,
    live_tools_fingerprint,
    webhook_tool_body,
)
from src.domains.telephony.models import CallKind, PhoneCallStatus

# ---------------------------------------------------------------------------
# The token and the URL
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_live_tool_token_is_derived_and_never_the_secret_itself() -> None:
    token = live_tool_token("whsec_abc")
    assert token == live_tool_token("whsec_abc")
    assert token != "whsec_abc"
    assert "whsec_abc" not in token
    assert len(token) == 64 and all(c in "0123456789abcdef" for c in token)
    assert token != live_tool_token("whsec_abd")


@pytest.mark.unit
def test_live_tool_url_points_at_this_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_url", "https://lia-back.example.test")
    assert live_tool_url("get_events_tool") == (
        f"https://lia-back.example.test{settings.api_prefix}/telephony/tools/get_events_tool"
    )


# ---------------------------------------------------------------------------
# The vendor tool body, from one declaration
# ---------------------------------------------------------------------------


def _params() -> tuple[LiveToolParameter, ...]:
    return (
        LiveToolParameter(name="query", type="string", description="Free text", required=False),
        LiveToolParameter(
            name="max_results",
            type="integer",
            description="Max (1-25)",
            required=False,
            enum=None,
        ),
        LiveToolParameter(
            name="scope",
            type="string",
            description="Which",
            required=True,
            enum=("mine", "all"),
        ),
    )


@pytest.mark.unit
def test_webhook_tool_body_carries_call_id_secret_and_parameters() -> None:
    body = webhook_tool_body(
        name="get_events_tool",
        description="Read the agenda.",
        url="https://x.test/api/v1/telephony/tools/get_events_tool",
        token="tok",
        parameters=_params(),
        timeout_seconds=20,
    )
    cfg = body["tool_config"]
    assert cfg["type"] == "webhook"
    assert cfg["name"] == "get_events_tool"
    assert cfg["description"] == "Read the agenda."
    assert cfg["response_timeout_secs"] == 20
    schema = cfg["api_schema"]
    assert schema["url"] == "https://x.test/api/v1/telephony/tools/get_events_tool"
    assert schema["method"] == "POST"
    assert schema["request_headers"] == {LIVE_TOOL_HEADER: "tok"}
    props = schema["request_body_schema"]["properties"]
    # The call id is bound to the dynamic variable the dial path injects, so the
    # vendor fills it and the model never types it.
    assert props["call_id"] == {"type": "string", "dynamic_variable": "call_id"}
    assert props["query"] == {"type": "string", "description": "Free text"}
    assert props["scope"] == {"type": "string", "description": "Which", "enum": ["mine", "all"]}
    assert schema["request_body_schema"]["required"] == ["call_id", "scope"]


@pytest.mark.unit
def test_webhook_tool_body_types_the_items_of_an_array() -> None:
    """Measured 2026-09-16 on the vendor: an array parameter is refused (422)
    unless its ``items`` carry a description of their own."""
    body = webhook_tool_body(
        name="get_route_tool",
        description="Route.",
        url="u",
        token="t",
        parameters=(
            LiveToolParameter(
                name="waypoints",
                type="array",
                description="Places to pass by",
                required=False,
                items_type="string",
            ),
        ),
        timeout_seconds=20,
    )
    props = body["tool_config"]["api_schema"]["request_body_schema"]["properties"]
    assert props["waypoints"]["type"] == "array"
    assert props["waypoints"]["description"] == "Places to pass by"
    assert props["waypoints"]["items"]["type"] == "string"
    assert props["waypoints"]["items"]["description"]


@pytest.mark.unit
def test_live_tools_fingerprint_notices_drift_and_ignores_order() -> None:
    a = webhook_tool_body(
        name="a", description="d", url="u", token="t", parameters=(), timeout_seconds=20
    )
    b = webhook_tool_body(
        name="b", description="d", url="u", token="t", parameters=(), timeout_seconds=20
    )
    assert live_tools_fingerprint([a, b]) == live_tools_fingerprint([b, a])
    drifted = webhook_tool_body(
        name="a", description="d2", url="u", token="t", parameters=(), timeout_seconds=20
    )
    assert live_tools_fingerprint([a, b]) != live_tools_fingerprint([drifted, b])
    rotated = webhook_tool_body(
        name="a", description="d", url="u", token="t2", parameters=(), timeout_seconds=20
    )
    assert live_tools_fingerprint([a]) != live_tools_fingerprint([rotated])


# ---------------------------------------------------------------------------
# Authorizing a call-back
# ---------------------------------------------------------------------------


def _call(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "call_kind": CallKind.SELF,
        "status": PhoneCallStatus.IN_PROGRESS,
        "initiated_at": datetime.now(UTC) - timedelta(minutes=2),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _Repo:
    def __init__(self, call: SimpleNamespace | None) -> None:
        self.call = call

    async def get_by_call_id(self, call_id):  # noqa: ANN001
        return self.call if self.call is not None and self.call.id == call_id else None


class _Connectors:
    def __init__(self, secret: str | None) -> None:
        self.secret = secret

    async def get_api_key_credentials(self, user_id, connector_type):  # noqa: ANN001
        if self.secret is None:
            return None
        return SimpleNamespace(api_key="k", api_secret=self.secret)


def _wire(
    monkeypatch: pytest.MonkeyPatch, call: SimpleNamespace | None, secret: str | None = "whsec"
) -> None:
    monkeypatch.setattr(mod, "TelephonyRepository", lambda _db: _Repo(call))
    monkeypatch.setattr(mod, "ConnectorService", lambda _db: _Connectors(secret))


@pytest.mark.unit
async def test_authorize_accepts_an_active_owner_call_with_the_right_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = _call()
    _wire(monkeypatch, call)
    auth = await authorize_live_tool_call(
        object(), call_id_raw=str(call.id), presented_token=live_tool_token("whsec")
    )
    assert auth.outcome is LiveToolAuthOutcome.OK
    assert auth.call is call


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    ["", "not-a-uuid", str(uuid4())],
    ids=["empty", "malformed", "unknown"],
)
async def test_authorize_refuses_an_unknown_call_without_revealing_why(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    _wire(monkeypatch, _call())
    auth = await authorize_live_tool_call(object(), call_id_raw=raw, presented_token="x")
    assert auth.outcome is LiveToolAuthOutcome.UNKNOWN_CALL
    assert auth.call is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"call_kind": CallKind.THIRD_PARTY},
        {"call_kind": CallKind.VERIFICATION},
        {"status": PhoneCallStatus.COMPLETED},
        {"status": PhoneCallStatus.FAILED},
        {
            "initiated_at": datetime.now(UTC)
            - timedelta(minutes=settings.telephony_stale_call_timeout_minutes, seconds=61)
        },
        {"initiated_at": None},
    ],
    ids=["third_party", "verification", "completed", "failed", "too_old", "no_start"],
)
async def test_authorize_refuses_anything_but_a_live_owner_call(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, object]
) -> None:
    """A stranger's call, a finished call or a stale row read exactly like an
    unknown id: the secret is never even compared."""
    call = _call(**overrides)
    _wire(monkeypatch, call)
    auth = await authorize_live_tool_call(
        object(), call_id_raw=str(call.id), presented_token=live_tool_token("whsec")
    )
    assert auth.outcome is LiveToolAuthOutcome.UNKNOWN_CALL


@pytest.mark.unit
async def test_authorize_refuses_a_wrong_token_on_a_known_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = _call()
    _wire(monkeypatch, call)
    auth = await authorize_live_tool_call(
        object(), call_id_raw=str(call.id), presented_token=live_tool_token("other")
    )
    assert auth.outcome is LiveToolAuthOutcome.BAD_SECRET
    assert auth.call is None


@pytest.mark.unit
async def test_authorize_refuses_the_raw_secret_presented_as_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The webhook secret itself never opens the door: only its derivation does."""
    call = _call()
    _wire(monkeypatch, call)
    auth = await authorize_live_tool_call(
        object(), call_id_raw=str(call.id), presented_token="whsec"
    )
    assert auth.outcome is LiveToolAuthOutcome.BAD_SECRET


@pytest.mark.unit
async def test_authorize_reads_not_configured_when_the_connector_has_no_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = _call()
    _wire(monkeypatch, call, secret=None)
    auth = await authorize_live_tool_call(
        object(), call_id_raw=str(call.id), presented_token="anything"
    )
    assert auth.outcome is LiveToolAuthOutcome.NOT_CONFIGURED


# ---------------------------------------------------------------------------
# The per-call budget
# ---------------------------------------------------------------------------


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl


@pytest.mark.unit
async def test_budget_admits_up_to_the_limit_then_refuses() -> None:
    redis = _Redis()
    call_id = uuid4()
    verdicts = [
        await consume_live_tool_budget(redis, call_id, limit=3, ttl_seconds=900) for _ in range(5)
    ]
    assert verdicts == [True, True, True, False, False]
    key = next(iter(redis.values))
    assert key.startswith("telephony_live_tool:") and str(call_id) in key
    # The counter dies with the call: the TTL is set on the first lookup.
    assert redis.ttls[key] == 900


# ---------------------------------------------------------------------------
# Attaching the tools to the AGENT for the owner call (measured 2026-09-16:
# the vendor refuses tool ids inside a per-call override)
# ---------------------------------------------------------------------------


class _Client:
    def __init__(self, *, fail: bool = False) -> None:
        self.patches: list[tuple[str, list[str]]] = []
        self.fail = fail

    async def set_agent_tool_ids(self, agent_id: str, tool_ids) -> None:  # noqa: ANN001
        if self.fail:
            from src.domains.telephony.client import ElevenLabsAgentsError

            raise ElevenLabsAgentsError(500, "boom")
        self.patches.append((agent_id, list(tool_ids)))


@pytest.mark.unit
async def test_attach_patches_the_agent_and_remembers_it_on_the_connector() -> None:
    from src.domains.telephony.live_tools import attach_live_tools

    client = _Client()
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag_1", "x": 1})
    before = connector.connector_metadata

    assert await attach_live_tools(client, connector, ["tool_a", "tool_b"]) is True
    assert client.patches == [("ag_1", ["tool_a", "tool_b"])]
    assert connector.connector_metadata["live_tools_attached"] is True
    assert connector.connector_metadata["x"] == 1
    assert connector.connector_metadata is not before  # a NEW dict (the JSONB rule)

    assert await attach_live_tools(client, connector, []) is True
    assert client.patches[-1] == ("ag_1", [])
    assert connector.connector_metadata["live_tools_attached"] is False


@pytest.mark.unit
async def test_attach_reports_a_vendor_refusal_and_keeps_the_record_honest() -> None:
    from src.domains.telephony.live_tools import attach_live_tools

    connector = SimpleNamespace(connector_metadata={"agent_id": "ag_1"})
    assert await attach_live_tools(_Client(fail=True), connector, ["tool_a"]) is False
    assert "live_tools_attached" not in connector.connector_metadata

    connector = SimpleNamespace(
        connector_metadata={"agent_id": "ag_1", "live_tools_attached": True}
    )
    assert await attach_live_tools(_Client(fail=True), connector, []) is False
    assert (
        connector.connector_metadata["live_tools_attached"] is True
    )  # still attached, retried later


class _Db:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.unit
async def test_detach_resolves_the_connector_and_only_patches_when_attached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.telephony.live_tools import detach_live_tools

    connector = SimpleNamespace(
        connector_metadata={"agent_id": "ag_1", "live_tools_attached": True}, status="active"
    )
    client = _Client()

    class _Telephony:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_active(self, _user_id):  # noqa: ANN001
            return connector

    monkeypatch.setattr(mod, "TelephonyConnectorService", _Telephony)
    monkeypatch.setattr(mod, "ConnectorService", lambda _db: _Connectors("whsec"))
    db = _Db()

    assert await detach_live_tools(db, user_id=uuid4(), client_factory=lambda _k: client) is True
    assert client.patches == [("ag_1", [])]
    assert connector.connector_metadata["live_tools_attached"] is False
    # ADR-304: the reads end BEFORE the vendor PATCH, the new state is
    # committed after it — two commits, none spanning the vendor call.
    assert db.commits == 2

    # Already detached: nothing to PATCH, nothing to commit.
    assert await detach_live_tools(db, user_id=uuid4(), client_factory=lambda _k: client) is True
    assert len(client.patches) == 1 and db.commits == 2


@pytest.mark.unit
async def test_detach_without_a_connector_is_a_quiet_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.domains.telephony.live_tools import detach_live_tools

    class _None:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_active(self, _user_id):  # noqa: ANN001
            return None

    monkeypatch.setattr(mod, "TelephonyConnectorService", _None)
    assert await detach_live_tools(_Db(), user_id=uuid4()) is False
