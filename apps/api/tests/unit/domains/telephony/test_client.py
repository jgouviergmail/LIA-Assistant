"""Unit tests for the ElevenLabs Agents client (P2.1) — mocked, no network."""

import json

import httpx
import pytest

from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError


def _client(handler) -> ElevenLabsAgentsClient:
    return ElevenLabsAgentsClient("sk-test", transport=httpx.MockTransport(handler))


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
async def test_create_agent_returns_agent_id_with_language():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"agent_id": "ag_new"})

    agent_id = await _client(handler).create_agent(
        name="LIA telephony", system_prompt="guardrails", first_message="Bonjour", language="fr"
    )
    assert agent_id == "ag_new"
    assert captured["body"]["conversation_config"]["agent"]["language"] == "fr"


@pytest.mark.unit
async def test_create_agent_includes_data_collection():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"agent_id": "ag_dc"})

    dc = [{"identifier": "agreed", "type": "boolean", "description": "agreed?"}]
    await _client(handler).create_agent(
        name="n", system_prompt="s", first_message="f", language="fr", data_collection=dc
    )
    collected = captured["body"]["platform_settings"]["data_collection"]
    assert collected["agreed"] == {"type": "boolean", "description": "agreed?"}


@pytest.mark.unit
async def test_api_error_raises_typed_exception():
    with pytest.raises(ElevenLabsAgentsError) as exc:
        await _client(lambda r: httpx.Response(500, text="boom")).list_phone_numbers()
    assert exc.value.status_code == 500
