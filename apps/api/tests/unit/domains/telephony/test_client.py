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
    # No tts_model_id given -> no tts block (English-only default upstream)
    assert "tts" not in captured["body"]["conversation_config"]


@pytest.mark.unit
async def test_create_agent_sets_tts_model_for_non_english():
    """Non-English agents REQUIRE a turbo/flash v2.5 TTS model (vendor 400 otherwise)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"agent_id": "ag_tts"})

    await _client(handler).create_agent(
        name="n",
        system_prompt="s",
        first_message="f",
        language="fr",
        tts_model_id="eleven_flash_v2_5",
    )
    assert captured["body"]["conversation_config"]["tts"] == {"model_id": "eleven_flash_v2_5"}


@pytest.mark.unit
async def test_create_agent_enables_end_call_and_caps_duration():
    """Without the end_call system tool the agent can NEVER hang up (observed:
    the line stayed open after the goodbyes); the duration cap bounds runaway
    calls vendor-side and the voice overrides the English default voice."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"agent_id": "ag_sys"})

    await _client(handler).create_agent(
        name="n",
        system_prompt="s",
        first_message="f",
        language="fr",
        llm_model="gpt-4o-mini",
        tts_model_id="eleven_flash_v2_5",
        voice_id="voice_fr_1",
        audio_format="ulaw_8000",
        max_duration_seconds=600,
    )
    prompt_cfg = captured["body"]["conversation_config"]["agent"]["prompt"]
    assert "end_call" in prompt_cfg["built_in_tools"]
    assert "voicemail_detection" in prompt_cfg["built_in_tools"]
    # LLM pinned: the platform default (gemini-2.5-flash, thinking) recited its
    # English reasoning aloud on a real call — never left to the default.
    assert prompt_cfg["llm"] == "gpt-4o-mini"
    assert captured["body"]["conversation_config"]["conversation"] == {"max_duration_seconds": 600}
    # Telephony-native audio on BOTH directions (Twilio requires ulaw_8000;
    # a mismatch is the vendor's documented cause of garbled call audio).
    assert captured["body"]["conversation_config"]["tts"] == {
        "model_id": "eleven_flash_v2_5",
        "voice_id": "voice_fr_1",
        "agent_output_audio_format": "ulaw_8000",
    }
    assert captured["body"]["conversation_config"]["asr"] == {
        "user_input_audio_format": "ulaw_8000"
    }


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
async def test_update_agent_patches_same_config_shape():
    """update_agent PATCHes /agents/{id} with the SAME body as create (lazy sync)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    await _client(handler).update_agent(
        "ag_1",
        name="n",
        system_prompt="s",
        first_message="f",
        language="fr",
        tts_model_id="eleven_turbo_v2_5",
        audio_format="ulaw_8000",
        max_duration_seconds=600,
    )
    assert captured["method"] == "PATCH"
    assert captured["path"].endswith("/agents/ag_1")
    prompt_cfg = captured["body"]["conversation_config"]["agent"]["prompt"]
    assert "end_call" in prompt_cfg["built_in_tools"]
    assert (
        captured["body"]["conversation_config"]["tts"]["agent_output_audio_format"] == "ulaw_8000"
    )


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
