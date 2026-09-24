"""Unit tests for the ElevenLabs Agents client (P2.1) — mocked, no network."""

import json

import httpx
import pytest

from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError


def _client(handler) -> ElevenLabsAgentsClient:
    return ElevenLabsAgentsClient("sk-test", transport=httpx.MockTransport(handler))


@pytest.mark.unit
async def test_webrtc_token_uses_the_private_key_and_requires_a_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/convai/conversation/token"
        assert request.url.params["agent_id"] == "agent_1"
        assert request.headers["xi-api-key"] == "sk-test"
        return httpx.Response(200, json={"token": "livekit-token", "conversation_id": "conv_1"})

    assert await _client(handler).webrtc_token("agent_1") == "livekit-token"
    with pytest.raises(ElevenLabsAgentsError, match="no token"):
        await _client(lambda _request: httpx.Response(200, json={})).webrtc_token("agent_1")


@pytest.mark.unit
async def test_initiate_outbound_call_disables_recording_and_passes_call_id():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"success": True, "conversation_id": "conv_1", "callSid": "CA1"}
        )

    res = await _client(handler).initiate_outbound_call(
        agent_id="ag_1",
        agent_phone_number_id="pn_1",
        to_number="+33600000000",
        dynamic_variables={"call_id": "c1", "objective": "resto"},
        ringing_timeout_secs=30,
    )

    assert res.success is True
    assert res.conversation_id == "conv_1"
    assert res.call_sid == "CA1"
    assert captured["path"].endswith("/twilio/outbound-call")
    assert captured["body"]["call_recording_enabled"] is False
    dyn = captured["body"]["conversation_initiation_client_data"]["dynamic_variables"]
    assert dyn["call_id"] == "c1"
    assert captured["body"]["telephony_call_config"]["ringing_timeout_secs"] == 30


@pytest.mark.unit
async def test_validate_key_true_on_200_false_on_401():
    ok = await _client(lambda r: httpx.Response(200, json=[])).validate_key()
    bad = await _client(lambda r: httpx.Response(401, json={"detail": "invalid"})).validate_key()
    assert ok is True
    assert bad is False


@pytest.mark.unit
async def test_list_phone_numbers_parses_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "phone_number_id": "pn_1",
                    "phone_number": "+33600000000",
                    "provider": "twilio",
                    "assigned_agent": None,
                }
            ],
        )

    nums = await _client(handler).list_phone_numbers()
    assert len(nums) == 1
    assert nums[0].phone_number_id == "pn_1"
    assert nums[0].provider == "twilio"


@pytest.mark.unit
async def test_api_error_raises_typed_exception():
    with pytest.raises(ElevenLabsAgentsError) as exc:
        await _client(lambda r: httpx.Response(500, text="boom")).list_phone_numbers()
    assert exc.value.status_code == 500


@pytest.mark.unit
async def test_vendor_auth_error_is_classified_structurally():
    """Prod 2026-08-15: ElevenLabs started rejecting legacy key-ID-shaped
    credentials with 400 {"detail": {"type": "authentication_error", ...}}.
    Classification reads the vendor's structured taxonomy field — never a
    message substring (ToolErrorCode doctrine)."""
    body = {
        "detail": {
            "type": "authentication_error",
            "code": "invalid_api_key",
            "message": "API key ID used as API key - only valid API keys can be used.",
        }
    }
    with pytest.raises(ElevenLabsAgentsError) as exc:
        await _client(lambda r: httpx.Response(400, json=body)).list_phone_numbers()
    assert exc.value.is_auth_error is True


@pytest.mark.unit
async def test_http_401_is_an_auth_error_whatever_the_body():
    with pytest.raises(ElevenLabsAgentsError) as exc:
        await _client(lambda r: httpx.Response(401, text="nope")).list_phone_numbers()
    assert exc.value.is_auth_error is True


@pytest.mark.unit
async def test_configuration_400_is_not_an_auth_error():
    body = {"detail": "built_in_tools.end_call.name: Field required"}
    with pytest.raises(ElevenLabsAgentsError) as exc:
        await _client(lambda r: httpx.Response(400, json=body)).list_phone_numbers()
    assert exc.value.is_auth_error is False


@pytest.mark.unit
async def test_server_error_is_not_an_auth_error():
    with pytest.raises(ElevenLabsAgentsError) as exc:
        await _client(lambda r: httpx.Response(500, text="boom")).list_phone_numbers()
    assert exc.value.is_auth_error is False


# ---------------------------------------------------------------------------
# One agent, two mandates (lot 2): the override permission and the per-call override
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_initiate_outbound_call_sends_the_override_when_given() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "conversation_id": "conv_x"})

    client = ElevenLabsAgentsClient("sk", transport=httpx.MockTransport(handler))
    await client.initiate_outbound_call(
        agent_id="ag",
        agent_phone_number_id="pn",
        to_number="+33612345678",
        dynamic_variables={"call_id": "c1"},
        ringing_timeout_secs=30,
        conversation_config_override={"agent": {"prompt": {"prompt": "owner"}}},
    )
    init = seen["body"]["conversation_initiation_client_data"]
    assert init["conversation_config_override"] == {"agent": {"prompt": {"prompt": "owner"}}}
    assert init["dynamic_variables"] == {"call_id": "c1"}


@pytest.mark.unit
async def test_initiate_outbound_call_omits_the_override_by_default() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True, "conversation_id": "conv_x"})

    client = ElevenLabsAgentsClient("sk", transport=httpx.MockTransport(handler))
    await client.initiate_outbound_call(
        agent_id="ag",
        agent_phone_number_id="pn",
        to_number="+33612345678",
        dynamic_variables={"call_id": "c1"},
        ringing_timeout_secs=30,
    )
    assert "conversation_config_override" not in seen["body"]["conversation_initiation_client_data"]


# ---------------------------------------------------------------------------
# Live tools (lot 7): the permission opens only under the flag; tools are
# created and deleted through the client
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_create_tool_posts_the_body_and_returns_the_vendor_id() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "tool_abc", "tool_config": {}})

    client = ElevenLabsAgentsClient("sk", transport=httpx.MockTransport(handler))
    tool_id = await client.create_tool({"tool_config": {"type": "webhook", "name": "x"}})
    assert tool_id == "tool_abc"
    assert seen["method"] == "POST"
    assert seen["path"].endswith("/convai/tools")
    assert seen["body"]["tool_config"]["name"] == "x"


@pytest.mark.unit
async def test_delete_tool_forces_and_tolerates_a_vendor_refusal() -> None:
    """Measured 2026-09-16: a tool still referenced answers 409 unless
    ``?force=true``; cleanup is best-effort like the agent's own delete."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "tool_gone" in str(request.url):
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(204)

    client = ElevenLabsAgentsClient("sk", transport=httpx.MockTransport(handler))
    await client.delete_tool("tool_ok")
    await client.delete_tool("tool_gone")  # does not raise
    assert seen[0].endswith("/convai/tools/tool_ok?force=true")
    assert seen[1].endswith("/convai/tools/tool_gone?force=true")


# ---------------------------------------------------------------------------
# The LLM is the portal's, never LIA's (owner decision, 2026-09-16)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# The agent body carries what is LIA's, and nothing the portal administers
# (owner decision, 2026-09-16)
# ---------------------------------------------------------------------------


def _body(**overrides):  # noqa: ANN003, ANN202
    from src.domains.telephony.client import _agent_config_body

    base = {
        "name": "LIA telephony — X",
        "system_prompt": "guardrails",
        "first_message": "Bonjour",
        "data_collection": [{"identifier": "agreed", "type": "boolean", "description": "agreed?"}],
    }
    return _agent_config_body(**{**base, **overrides})


@pytest.mark.unit
def test_the_agent_body_carries_only_what_is_lias() -> None:
    """The model, the language, the voice, the audio format and the duration
    cap are administered on the ElevenLabs portal and never leave LIA's
    keyboard: sent once, they would overwrite the portal on every sync and
    require a restart to change (owner decision). What LIA sends is its own:
    the name, the prompt, the greeting, the system tools the prompt relies
    on, the data-collection contract and the override permission."""
    body = _body()
    assert set(body) == {"name", "conversation_config", "platform_settings"}
    agent = body["conversation_config"]["agent"]
    assert set(body["conversation_config"]) == {"agent"}  # no tts, asr, conversation
    assert set(agent) == {"prompt", "first_message"}  # no language
    assert set(agent["prompt"]) == {"prompt", "built_in_tools"}  # no llm, no tool_ids
    assert "end_call" in agent["prompt"]["built_in_tools"]
    assert "voicemail_detection" in agent["prompt"]["built_in_tools"]
    assert body["platform_settings"]["data_collection"]["agreed"] == {
        "type": "boolean",
        "description": "agreed?",
    }


@pytest.mark.unit
def test_the_override_permission_opens_the_prompt_and_the_greeting_only() -> None:
    """The per-call override replaces the two things LIA renders per mandate;
    the language, the duration cap and the tools are the portal's or the
    agent's, never a per-call field (the vendor refuses ``tool_ids`` in an
    override anyway — measured on a real call, 2026-09-16)."""
    from src.domains.telephony.client import override_permissions

    allowed = override_permissions()["conversation_config_override"]
    assert allowed == {"agent": {"prompt": {"prompt": True}, "first_message": True}}
    assert _body()["platform_settings"]["overrides"] == override_permissions()


@pytest.mark.unit
async def test_create_and_update_send_the_same_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.setdefault("bodies", []).append(
            (request.method, request.url.path, json.loads(request.content))
        )
        return httpx.Response(200, json={"agent_id": "ag_new"})

    client = _client(handler)
    agent_id = await client.create_agent(name="n", system_prompt="s", first_message="f")
    await client.update_agent("ag_new", name="n", system_prompt="s", first_message="f")
    assert agent_id == "ag_new"
    (m1, p1, b1), (m2, p2, b2) = captured["bodies"]
    assert (
        (m1, m2) == ("POST", "PATCH")
        and p1.endswith("/agents/create")
        and p2.endswith("/agents/ag_new")
    )
    assert b1 == b2


@pytest.mark.unit
async def test_set_agent_tool_ids_patches_the_agent_prompt_only() -> None:
    """Live tools are attached to the AGENT for the owner call and detached
    after (the vendor refuses per-call ``tool_ids``): one small PATCH, the
    rest of the config untouched."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    await _client(handler).set_agent_tool_ids("ag_1", ["tool_a", "tool_b"])
    assert captured["method"] == "PATCH" and captured["path"].endswith("/agents/ag_1")
    assert captured["body"] == {
        "conversation_config": {"agent": {"prompt": {"tool_ids": ["tool_a", "tool_b"]}}}
    }
