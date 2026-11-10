"""ElevenLabs Agents as a live provider (ADR-300 wave 4) — without the network.

The person's own agent stands where a model stands; LIA sends the prompt
override and attaches its client tools to the agent by fingerprint; the
credential is a signed URL; the probe reads the agent's audio formats and
refuses in words what LIA cannot serve. The HTTP side runs on
``httpx.MockTransport`` through the real agents client; the socket is a fake
handed through the provider's thin door.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.core.config import settings
from src.core.constants import (
    ELEVENLABS_LIVE_OVERRIDE_METADATA_KEY,
    ELEVENLABS_LIVE_PORTAL_VOICE,
    ELEVENLABS_LIVE_SIGNED_URL_TTL_SECONDS,
    ELEVENLABS_LIVE_TOOL_KINDS_METADATA_KEY,
    ELEVENLABS_LIVE_TOOL_TIMEOUT_MAX_SECONDS,
    ELEVENLABS_LIVE_TOOLS_METADATA_KEY,
    LIVE_DELEGATION_TOOL_NAME,
)
from src.domains.connectors.models import ConnectorType
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers import (
    PROVIDERS,
    AgentSyncing,
    VendorBilling,
    provider_by_id,
)
from src.domains.live.providers.elevenlabs_live import (
    INITIATION_METADATA_TYPE,
    INITIATION_TYPE,
    ElevenLabsLiveProvider,
    ElevenLabsLiveRefused,
    client_tool_body,
    output_rate_of,
    tools_fingerprint,
)
from src.domains.live.providers.protocol import LiveSetupInputs
from src.domains.telephony.client import ElevenLabsAgentsClient
from src.domains.voice.cue_prompt import palette
from src.domains.voice.expressive_cues import ELEVENLABS_AGENT_TAGS
from src.domains.voice_sessions.expression import PERSON_CUES
from src.domains.voice_sessions.mandate import neutralise_vendor_syntax

pytestmark = pytest.mark.unit

MODULE = "src.domains.live.providers.elevenlabs_live"
LISTING = "src.infrastructure.llm.providers.elevenlabs_live_listing"

AGENT = "agent_0123456789abcdef"
SIGNED = (
    "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=agent_x&conversation_signature=sig"
)
DELEGATION = {
    "name": "send_to_lia",
    "description": "Hand the request to LIA.",
    "parameters": {
        "type": "object",
        "properties": {"request": {"type": "string", "description": "words"}},
        "required": ["request"],
    },
    "behavior": "NON_BLOCKING",
}
EVENTS = {
    "name": "get_events_tool",
    "description": "Reads the agenda.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def _inputs(**overrides: object) -> LiveSetupInputs:
    base: dict[str, object] = {
        "model": AGENT,
        "voice": ELEVENLABS_LIVE_PORTAL_VOICE,
        "thinking_level": None,
        "system_instruction": "You are LIA's voice.",
        "tool_declaration": DELEGATION,
        "preferences": LivePreferences(),
        "trigger_tokens": 25_000,
        "target_tokens": 8_000,
    }
    base.update(overrides)
    return LiveSetupInputs(**base)  # type: ignore[arg-type]


def _merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    """A PATCH as the vendor applies it (measured 2026-09-16): merged, a list replaced."""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value


@pytest.fixture(autouse=True)
def _lia_live_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    """The live lookups LIA names its client tools after, pinned for these tests.

    The production list is derived once per process from the catalogue; pinned
    here, a sweep never memoises whatever the registry held at that moment.
    """
    from src.domains.agents.telephony import live_tools

    monkeypatch.setattr(
        live_tools, "_SPECS", (live_tools.LiveToolSpec("get_events_tool", "event", "event", ()),)
    )


def _carried(agent: dict[str, Any]) -> list[str]:
    """The tool ids an agent references."""
    return list(agent["conversation_config"]["agent"]["prompt"].get("tool_ids") or [])


class _Vendor:
    """The agents API as a MockTransport handler, recording every call."""

    def __init__(self, agent: dict[str, Any] | None = None, *, replace_tts: bool = False) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        # The workspace's tools by id: the person's own client tool, attached to
        # the agent on the portal, is there from the start.
        self.tools: dict[str, dict[str, Any]] = {
            "tool_theirs": {"type": "client", "name": "book_a_table"}
        }
        # Tools another agent of the workspace references: kept by a delete
        # that is not forced (409), as the vendor keeps them.
        self.used_elsewhere: set[str] = set()
        self.forced: list[str] = []
        # A vendor whose PATCH REPLACES the speaking block instead of merging it
        # (never measured either way): what LIA does not send is then lost.
        self.replace_tts = replace_tts
        self.agent = agent or {
            "agent_id": AGENT,
            "name": "Assistant",
            "conversation_config": {
                "agent": {"prompt": {"tool_ids": ["tool_theirs"], "llm": "gemini-3.6-flash"}},
                "tts": {"model_id": "eleven_v3_conversational", "voice_id": "v"},
            },
            "platform_settings": {
                "overrides": {
                    "conversation_config_override": {"tts": {"voice_id": True}},
                    "custom_llm_extra_body": True,
                }
            },
        }
        self.created = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/v1/convai/agents":
            return httpx.Response(
                200,
                json={
                    "agents": [
                        {"agent_id": AGENT, "name": "Assistant"},
                        {"agent_id": "agent_2", "name": "Support"},
                    ]
                },
            )
        if request.method == "GET" and request.url.path == f"/v1/convai/agents/{AGENT}":
            return httpx.Response(200, json=self.agent)
        if request.method == "GET" and request.url.path == "/v1/convai/agents/agent_2":
            # A second agent whose configuration names no voice model.
            return httpx.Response(200, json={"agent_id": "agent_2", "conversation_config": {}})
        if request.method == "GET" and request.url.path.startswith("/v1/convai/conversations/"):
            conversation_id = request.url.path.rsplit("/", 1)[1]
            if conversation_id == "conv_settling":
                return httpx.Response(200, json={"status": "processing", "metadata": {}})
            if conversation_id == "conv_gone":
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=CONVERSATION)
        if request.url.path == "/v1/convai/conversation/get-signed-url":
            assert request.url.params["agent_id"] == AGENT
            return httpx.Response(200, json={"signed_url": SIGNED})
        if request.url.path == "/v1/convai/conversation/token":
            assert request.url.params["agent_id"] == AGENT
            return httpx.Response(200, json={"token": "livekit-token", "conversation_id": "conv_1"})
        if request.method == "PATCH" and request.url.path == f"/v1/convai/agents/{AGENT}":
            prompt = (((body or {}).get("conversation_config") or {}).get("agent") or {}).get(
                "prompt"
            ) or {}
            if any(tool_id not in self.tools for tool_id in prompt.get("tool_ids") or []):
                # The vendor refuses to attach a tool its workspace no longer holds.
                return httpx.Response(422, json={"detail": "Tool not found"})
            tts = ((body or {}).get("conversation_config") or {}).get("tts")
            if self.replace_tts and isinstance(tts, dict):
                self.agent["conversation_config"]["tts"] = json.loads(json.dumps(tts))
            _merge(self.agent, body or {})
            return httpx.Response(200, json={})
        if request.method == "POST" and request.url.path == "/v1/convai/tools":
            self.created += 1
            tool_id = f"tool_lia_{self.created}"
            self.tools[tool_id] = dict((body or {}).get("tool_config") or {})
            return httpx.Response(200, json={"id": tool_id})
        if request.method == "GET" and request.url.path == "/v1/convai/tools":
            listed = [
                {"id": tool_id, "tool_config": config}
                for tool_id, config in self.tools.items()
                if config.get("type") in request.url.params.get_list("types")
            ]
            return httpx.Response(200, json={"tools": listed, "has_more": False})
        if request.method == "DELETE" and request.url.path.startswith("/v1/convai/tools/"):
            return self._delete(request)
        return httpx.Response(404, json={"detail": "unknown"})

    def _delete(self, request: httpx.Request) -> httpx.Response:
        tool_id = request.url.path.rsplit("/", 1)[1]
        if request.url.params.get("force") == "true":
            self.forced.append(tool_id)
            self.tools.pop(tool_id, None)
            return httpx.Response(200, json={})
        if tool_id not in self.tools:
            return httpx.Response(404, json={"detail": "not found"})
        if tool_id in self.used_elsewhere or tool_id in _carried(self.agent):
            return httpx.Response(409, json={"detail": "still in use"})
        del self.tools[tool_id]
        return httpx.Response(204)

    def deleted(self) -> list[str]:
        """The workspace tools the sync removed, in order."""
        return [
            path.rsplit("/", 1)[1]
            for method, path, _body in self.calls
            if method == "DELETE" and path.startswith("/v1/convai/tools/")
        ]


#: A settled conversation as the vendor returns it (the API reference, 2026-09-20).
CONVERSATION: dict[str, Any] = {
    "status": "done",
    "metadata": {
        "call_duration_secs": 95,
        "cost": 12,
        "cost_fiat": 0.1234,
        "charging": {
            "llm_charge": 4,
            "call_charge": 8,
            "platform_charge": 0,
            "llm_price": 0.03,
            "llm_usage": {
                "irreversible_generation": {
                    "model_usage": {
                        "gemini-3.6-flash": {
                            "input": {"tokens": 5000},
                            "output_total": {"tokens": 400},
                        }
                    }
                }
            },
            "tts_usage": {"primary_tts_model": "eleven_v3_conversational"},
        },
    },
}


def _provider(vendor: _Vendor) -> ElevenLabsLiveProvider:
    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(vendor)
    )
    return provider


# -- registration and the seam's declarations --------------------------------------


def test_the_provider_is_registered_as_a_token_connection_with_a_tool_wire() -> None:
    provider = provider_by_id("elevenlabs")
    assert isinstance(provider, ElevenLabsLiveProvider)
    assert PROVIDERS[ConnectorType.ELEVENLABS_LIVE] is provider
    assert provider.connection == "token" and provider.delegation_wire == "tool"
    assert isinstance(provider, AgentSyncing)
    # The agents API runs on the person's own key: the platform prices nothing
    # of it and the vendor states its bill after the conversation (owner rule
    # 2026-09-20). Gemini Live is priced by the platform's tariff table.
    assert isinstance(provider, VendorBilling)
    assert provider.billing == "vendor"
    gemini = provider_by_id("gemini")
    assert gemini is not None and gemini.billing == "tariff"


async def test_the_vendors_bill_is_read_from_the_conversation_and_shown_as_stated() -> None:
    vendor = _Vendor()
    provider = _provider(vendor)
    with patch(
        f"{MODULE}.ElevenLabsAgentsClient",
        lambda key, timeout_seconds: ElevenLabsAgentsClient(
            key, transport=httpx.MockTransport(vendor)
        ),
    ):
        bill = await provider.conversation_bill("k", "conv_1", timeout=5.0)
        settling = await provider.conversation_bill("k", "conv_settling", timeout=5.0)
        gone = await provider.conversation_bill("k", "conv_gone", timeout=5.0)
    assert bill is not None
    assert bill.provider == "elevenlabs"
    assert bill.cost_usd == 0.1234 and bill.credits == 12
    assert (bill.llm_credits, bill.call_credits, bill.platform_credits) == (4, 8, 0)
    assert bill.llm_model == "gemini-3.6-flash"
    assert bill.tts_model == "eleven_v3_conversational"
    assert bill.duration_seconds == 95
    # A conversation the vendor has not settled, or refuses, reads as no bill —
    # the person keeps the meter's estimate, never a wrong figure.
    assert settling is None and gone is None


def test_the_capabilities_say_a_blocking_tool_wire_and_a_portal_voice() -> None:
    caps = ElevenLabsLiveProvider().capabilities_of(AGENT)
    assert caps.direct_tools is True and caps.portal_voice is True
    assert caps.async_delegation is False and caps.resumes is False
    assert caps.configurable_vad is False and caps.thinking is False


def _listing_client(vendor: _Vendor) -> Any:
    """The listing seam on the vendor fake: `connectors` never imports `telephony`."""
    return lambda **_kw: httpx.AsyncClient(
        base_url="https://api.elevenlabs.io/v1", transport=httpx.MockTransport(vendor)
    )


async def test_the_models_are_the_agents_named_after_themselves() -> None:
    vendor = _Vendor()
    with patch(f"{LISTING}.http_client", _listing_client(vendor)):
        models = await _provider(vendor).list_models("k")
    assert [(m.name, m.label) for m in models] == [(AGENT, "Assistant"), ("agent_2", "Support")]
    assert all(m.capabilities.portal_voice for m in models)
    assert vendor.calls[0][:2] == ("GET", "/v1/convai/agents")
    # Each agent's configuration was read for INFORMATION — the voice model and
    # the LLM the portal names — never for a tariff: the vendor bills both.
    assert [(m.voice_model, m.llm) for m in models] == [
        ("eleven_v3_conversational", "gemini-3.6-flash"),
        (None, None),
    ]
    assert all(m.capabilities.vendor_billed for m in models)


async def test_the_voice_is_the_portals_no_list_no_sample() -> None:
    provider = ElevenLabsLiveProvider()
    listing = await provider.list_voices("k")
    assert listing.provenance == "portal" and listing.voices == []
    assert provider.knows_voice(ELEVENLABS_LIVE_PORTAL_VOICE)
    assert not provider.knows_voice("Kore")
    assert provider.thinking_levels_of(AGENT) == ()
    with pytest.raises(ElevenLabsLiveRefused):
        await provider.sample_voice("k", ELEVENLABS_LIVE_PORTAL_VOICE, "Hello")


def test_the_setup_is_the_initiation_frame_with_the_prompt_and_an_empty_greeting() -> None:
    setup = ElevenLabsLiveProvider().build_setup(_inputs())
    assert setup["type"] == INITIATION_TYPE
    # The portal's canned greeting is the one sentence a personality could
    # never reach: empty, the agent lets the person speak first (the vendor's
    # override contract), and every word it says is the mandate's (ADR-373).
    assert setup["conversation_config_override"] == {
        "agent": {"prompt": {"prompt": "You are LIA's voice."}, "first_message": ""}
    }
    # The language and the voice: the portal's, never overridden.
    assert "language" not in json.dumps(setup)
    assert "tts" not in setup["conversation_config_override"]
    # No `source_info`: measured 2026-09-19, the vendor validates it against its
    # own SDK names and closes 1008 on any other word — after the metadata.
    assert "source_info" not in setup


def test_a_doubled_brace_in_the_prompt_reaches_the_vendor_as_text() -> None:
    """The vendor reads ``{{name}}`` as a dynamic variable it must be given at the
    start; the browser's prompt is LIA's, rendered whole on the server, so a
    doubled brace in it can only come from a value — a personality, a memory, an
    e-mail subject in the context — and must stay text, as on the phone."""
    instruction = "You are LIA's voice.\nPersonality: answer {{user_name}} in {{tone}} fashion."
    setup = ElevenLabsLiveProvider().build_setup(_inputs(system_instruction=instruction))

    prompt = setup["conversation_config_override"]["agent"]["prompt"]["prompt"]
    assert "{{" not in prompt and "}}" not in prompt
    assert prompt == neutralise_vendor_syntax(instruction)


# -- the credential -----------------------------------------------------------------------


async def test_the_credential_is_a_signed_url_within_the_vendors_window() -> None:
    now = datetime.now(UTC)
    credential = await _provider(_Vendor()).mint(
        "k",
        _inputs(),
        expires_at=now + timedelta(minutes=30),
        connect_deadline_at=now + timedelta(hours=1),
    )
    assert credential.name == SIGNED
    assert credential.expires_at == now + timedelta(minutes=30)
    # LIA's own window is an hour; the vendor's is shorter and wins.
    assert credential.connect_deadline_at <= now + timedelta(
        seconds=ELEVENLABS_LIVE_SIGNED_URL_TTL_SECONDS + 5
    )
    short = await _provider(_Vendor()).mint(
        "k",
        _inputs(),
        expires_at=now + timedelta(minutes=30),
        connect_deadline_at=now + timedelta(seconds=60),
    )
    assert short.connect_deadline_at == now + timedelta(seconds=60)


async def test_webrtc_credential_is_a_token_on_the_same_agent() -> None:
    vendor = _Vendor()
    now = datetime.now(UTC)
    credential = await _provider(vendor).mint(
        "k",
        _inputs(audio_transport="webrtc"),
        expires_at=now + timedelta(minutes=30),
        connect_deadline_at=now + timedelta(seconds=60),
    )
    assert credential.name == "livekit-token"
    assert credential.connect_deadline_at == now + timedelta(seconds=60)
    assert ("GET", "/v1/convai/conversation/token", None) in vendor.calls


# -- the agent sync ------------------------------------------------------------------------


async def test_the_sync_grants_the_prompt_override_merged_and_attaches_the_tools() -> None:
    vendor = _Vendor()
    provider = _provider(vendor)
    metadata = {"agent_id": AGENT, "other": "kept"}
    synced = await provider.sync_agent("k", metadata, _inputs())
    # A NEW dict, the input untouched (the JSONB rule).
    assert synced is not metadata and metadata == {"agent_id": AGENT, "other": "kept"}
    assert synced["other"] == "kept"
    # The permission is read on the agent itself, never remembered: a marker
    # the portal could contradict is dropped from the connector.
    assert ELEVENLABS_LIVE_OVERRIDE_METADATA_KEY not in synced
    fingerprint = tools_fingerprint([DELEGATION])
    assert synced[ELEVENLABS_LIVE_TOOLS_METADATA_KEY] == {fingerprint: ["tool_lia_1"]}
    patches = [body for method, path, body in vendor.calls if method == "PATCH"]
    # The permission PATCH keeps the person's own permissions and sets the two
    # fields LIA's frame overrides: its prompt and its (empty) greeting.
    assert patches[0] == {
        "platform_settings": {
            "overrides": {
                "conversation_config_override": {
                    "tts": {"voice_id": True},
                    "agent": {"prompt": {"prompt": True}, "first_message": True},
                },
                "custom_llm_extra_body": True,
            }
        }
    }
    # Words alone (the default wire): the vendor's default persona is dropped,
    # the person's palette is left alone (ADR-373).
    assert patches[1] == {
        "conversation_config": {"agent": {"prompt": {"ignore_default_personality": True}}}
    }
    # The tool PATCH carries EXACTLY LIA's set (ADR-373): the person's own tool
    # is detached — never deleted, it is theirs.
    assert patches[2] == {
        "conversation_config": {"agent": {"prompt": {"tool_ids": ["tool_lia_1"]}}}
    }
    assert vendor.deleted() == [] and "tool_theirs" in vendor.tools
    created = [
        body
        for method, path, body in vendor.calls
        if method == "POST" and path == "/v1/convai/tools"
    ]
    assert created == [
        client_tool_body(DELEGATION, timeout_seconds=settings.live_delegation_timeout_seconds)
    ]
    assert created[0]["tool_config"]["type"] == "client"
    assert created[0]["tool_config"]["expects_response"] is True
    assert "behavior" not in json.dumps(created[0])


async def test_the_sync_is_idempotent_and_swaps_the_set_on_a_new_fingerprint() -> None:
    vendor = _Vendor()
    provider = _provider(vendor)
    first = await provider.sync_agent("k", {}, _inputs())
    assert _carried(vendor.agent) == ["tool_lia_1"]
    before = len(vendor.calls)
    again = await provider.sync_agent("k", first, _inputs())
    assert again == first
    # One GET of the agent, nothing granted, created, patched or listed again.
    assert [c[0] for c in vendor.calls[before:]] == ["GET"]

    # A DIRECT session: another fingerprint, its own tools, the delegation one detached.
    direct = await provider.sync_agent(
        "k", again, _inputs(tool_declaration=None, direct_tools=(EVENTS,))
    )
    held = direct[ELEVENLABS_LIVE_TOOLS_METADATA_KEY]
    assert set(held) == {tools_fingerprint([DELEGATION]), tools_fingerprint([EVENTS])}
    assert held[tools_fingerprint([EVENTS])] == ["tool_lia_2"]
    last_patch = [body for method, _p, body in vendor.calls if method == "PATCH"][-1]
    assert last_patch == {
        "conversation_config": {"agent": {"prompt": {"tool_ids": ["tool_lia_2"]}}}
    }
    # The delegation set is detached, never deleted: it is the other kind's.
    assert "tool_lia_1" in vendor.tools and vendor.deleted() == []
    created = [body for _m, path, body in vendor.calls if path == "/v1/convai/tools" and body]
    assert created[-1]["tool_config"]["response_timeout_secs"] == min(
        settings.telephony_live_tool_timeout_seconds, ELEVENLABS_LIVE_TOOL_TIMEOUT_MAX_SECONDS
    )


async def test_a_set_superseded_by_a_new_fingerprint_of_its_kind_is_removed() -> None:
    # The phone deletes the old set on drift (`ensure_vendor_live_tools`); the
    # live session must too, or every change of a description (the person's
    # name, a tool added by a release) leaves a whole set — fifty-odd tools —
    # orphaned in the person's workspace for ever. One set per KIND survives:
    # the delegation's and the direct one's, never two of one kind.
    vendor = _Vendor()
    provider = _provider(vendor)
    first = await provider.sync_agent("k", {}, _inputs())
    direct = await provider.sync_agent(
        "k", first, _inputs(tool_declaration=None, direct_tools=(EVENTS,))
    )
    renamed = {**DELEGATION, "description": "Hand Alex's request to LIA."}
    renewed = await provider.sync_agent("k", direct, _inputs(tool_declaration=renamed))
    held = renewed[ELEVENLABS_LIVE_TOOLS_METADATA_KEY]
    # The renamed delegation set replaced the old one; the direct set stays.
    assert set(held) == {tools_fingerprint([renamed]), tools_fingerprint([EVENTS])}
    assert held[tools_fingerprint([renamed])] == ["tool_lia_3"]
    assert vendor.deleted() == ["tool_lia_1"]
    # Released WITHOUT force: a tool another agent still used would be kept.
    assert vendor.forced == [] and "tool_lia_1" not in vendor.tools
    # The old set was taken off the agent BEFORE its tools were deleted.
    last_patch = [body for method, _p, body in vendor.calls if method == "PATCH"][-1]
    assert last_patch == {
        "conversation_config": {"agent": {"prompt": {"tool_ids": ["tool_lia_3"]}}}
    }
    delete_at = next(i for i, c in enumerate(vendor.calls) if c[0] == "DELETE")
    patch_at = max(i for i, c in enumerate(vendor.calls) if c[0] == "PATCH")
    assert patch_at < delete_at
    # A set the metadata holds under a bare fingerprint (the shape before the
    # kinds were recorded) is reused when it matches, never re-created.
    legacy = {ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {tools_fingerprint([EVENTS]): ["tool_old"]}}
    vendor.tools["tool_old"] = {"type": "client", "name": "get_events_tool"}
    before = vendor.created
    kept = await provider.sync_agent(
        "k", legacy, _inputs(tool_declaration=None, direct_tools=(EVENTS,))
    )
    assert vendor.created == before
    assert kept[ELEVENLABS_LIVE_TOOLS_METADATA_KEY][tools_fingerprint([EVENTS])] == ["tool_old"]


async def test_a_partial_tool_creation_is_rolled_back_and_the_start_refused() -> None:
    # Two tools to create, the second refused by the vendor: the first is
    # deleted (forced) and nothing is recorded — no orphan in the workspace.
    vendor = _Vendor()
    deleted: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/convai/tools":
            vendor.created += 1
            if vendor.created == 2:
                return httpx.Response(500, json={"detail": "boom"})
            return httpx.Response(200, json={"id": f"tool_lia_{vendor.created}"})
        if request.method == "DELETE":
            deleted.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={})
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    from src.domains.telephony.client import ElevenLabsAgentsError

    with pytest.raises(ElevenLabsAgentsError):
        await provider.sync_agent(
            "k", {}, _inputs(tool_declaration=None, direct_tools=(EVENTS, DELEGATION))
        )
    assert deleted == ["tool_lia_1"]


async def test_a_refused_agent_patch_deletes_the_set_it_just_created() -> None:
    # The set is recorded in the metadata the CALLER stores, once the whole
    # sync returned: a vendor refusal on the agent patch would leave the tools
    # created just before it in the workspace with nothing naming them, and
    # the next start would create the set again — one orphan set per attempt.
    # A set that existed before the call is kept: it is named by the metadata.
    vendor = _Vendor()
    deleted: list[str] = []
    patches = 0

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal patches
        if request.method == "PATCH" and request.url.path == f"/v1/convai/agents/{AGENT}":
            patches += 1
            body = json.loads(request.content)
            if "tool_ids" in ((body.get("conversation_config") or {}).get("agent") or {}).get(
                "prompt", {}
            ):
                return httpx.Response(500, json={"detail": "boom"})
        if request.method == "DELETE":
            deleted.append(request.url.path.rsplit("/", 1)[-1])
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    from src.domains.telephony.client import ElevenLabsAgentsError

    with pytest.raises(ElevenLabsAgentsError):
        await provider.sync_agent("k", {}, _inputs())
    assert vendor.created == 1
    assert deleted == ["tool_lia_1"]
    # The same refusal on a set the metadata already names — alive in the
    # workspace, so no dead id caused it — deletes and re-creates nothing.
    deleted.clear()
    vendor.tools["tool_old"] = {"type": "client", "name": "send_to_lia"}
    known = {ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {tools_fingerprint([DELEGATION]): ["tool_old"]}}
    with pytest.raises(ElevenLabsAgentsError):
        await provider.sync_agent("k", known, _inputs())
    assert vendor.created == 1
    assert deleted == []


async def test_a_refusal_cancels_the_creations_still_running_before_the_rollback() -> None:
    """Measured 2026-09-19 on dev: `gather` raised on the third refusal while fifty
    creations went on; the rollback iterated a dict they kept filling and every
    tool created after it was an orphan. With a TaskGroup the siblings are
    cancelled first: nothing is created after the rollback ran.

    Sequenced by events, never by the clock: the refusal lands once "a" was
    created and "b" to "d" are mid-flight, and their creations can only finish
    if nobody cancels them. Timed with sleeps, a starved event loop woke the
    refusal and the siblings in the same iteration, and they landed anyway.
    """
    import asyncio

    from src.domains.agents.telephony.live_tools import LIVE_TOOL_PROVISIONING_CONCURRENCY
    from src.domains.live.providers.elevenlabs_live import _create_client_tools
    from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError

    siblings = ("b", "c", "d")
    bodies = [{"tool_config": {"name": n}} for n in ("a", "refused", *siblings)]
    # Every creation must be in flight at once for "mid-flight" to mean anything.
    assert len(bodies) <= LIVE_TOOL_PROVISIONING_CONCURRENCY
    events: list[str] = []
    a_created = asyncio.Event()
    in_flight: set[str] = set()
    siblings_in_flight = asyncio.Event()
    released = asyncio.Event()  # set only after the call returned: a late creation shows

    class _SequencedClient(ElevenLabsAgentsClient):
        async def create_tool(self, body: dict[str, Any]) -> str:
            name = body["tool_config"]["name"]
            if name == "a":
                events.append("created:a")
                a_created.set()
                return "id_a"
            if name == "refused":
                await a_created.wait()
                await siblings_in_flight.wait()
                raise ElevenLabsAgentsError(422, "no")
            in_flight.add(name)
            if in_flight == set(siblings):
                siblings_in_flight.set()
            try:
                await released.wait()
            except asyncio.CancelledError:
                events.append(f"cancelled:{name}")
                raise
            events.append(f"created:{name}")
            return f"id_{name}"

        async def delete_tool(self, tool_id: str) -> None:
            events.append(f"deleted:{tool_id}")

    async with asyncio.timeout(10):  # a hang guard, never an oracle
        with pytest.raises(ElevenLabsAgentsError):
            await _create_client_tools(_SequencedClient("test-key"), bodies)
        released.set()
        for _ in range(10):  # let any sibling still running land, if one survived
            await asyncio.sleep(0)

    # "a" was created before the refusal and rolled back; the siblings were
    # cancelled before the rollback, and none was created after it.
    assert events[0] == "created:a"
    assert sorted(events[1:-1]) == [f"cancelled:{name}" for name in siblings]
    assert events[-1] == "deleted:id_a"


def test_the_fingerprint_reads_the_declaration_and_ignores_the_wire_behaviour() -> None:
    without = {k: v for k, v in DELEGATION.items() if k != "behavior"}
    assert tools_fingerprint([DELEGATION]) == tools_fingerprint([without])
    assert tools_fingerprint([DELEGATION]) != tools_fingerprint(
        [{**DELEGATION, "description": "changed"}]
    )
    assert tools_fingerprint([EVENTS, DELEGATION]) != tools_fingerprint([DELEGATION, EVENTS])


# -- the probe --------------------------------------------------------------------------------


class _Socket:
    """A fake aiohttp WebSocket: the frames it answers, what it received."""

    def __init__(
        self,
        frames: list[dict[str, Any]],
        *,
        close_code: int | None = None,
        close_reason: str = "",
    ) -> None:
        import aiohttp

        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.close_code = close_code
        self._queue = [
            aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, json.dumps(frame), None) for frame in frames
        ]
        if close_code is not None:
            self._queue.append(aiohttp.WSMessage(aiohttp.WSMsgType.CLOSE, close_code, close_reason))

    async def send_str(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def receive(self) -> Any:
        if not self._queue:
            import asyncio

            await asyncio.sleep(3600)
        return self._queue.pop(0)

    async def close(self, code: int = 1000) -> None:
        self.closed = True

    def exception(self) -> Exception:
        return RuntimeError("boom")


class _Session:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _short_settle(monkeypatch: pytest.MonkeyPatch) -> None:
    """The verdict window after the metadata, shortened for the tests."""
    from src.domains.live.providers import elevenlabs_live as module

    monkeypatch.setattr(module, "ELEVENLABS_LIVE_PROBE_SETTLE_SECONDS", 0.05)


def _probing(vendor: _Vendor, socket: _Socket) -> tuple[ElevenLabsLiveProvider, _Session]:
    provider = _provider(vendor)
    session = _Session()

    async def _open(url: str, *, timeout: float) -> tuple[_Session, _Socket]:
        assert url == SIGNED
        return session, socket

    provider._open_socket = _open  # type: ignore[method-assign]
    return provider, session


def _metadata(**overrides: object) -> dict[str, Any]:
    event: dict[str, Any] = {
        "conversation_id": "conv_1",
        "agent_output_audio_format": "pcm_24000",
        "user_input_audio_format": "pcm_16000",
    }
    event.update(overrides)
    return {"type": INITIATION_METADATA_TYPE, "conversation_initiation_metadata_event": event}


async def test_the_probe_sends_the_initiation_and_accepts_a_pcm_agent() -> None:
    socket = _Socket([{"type": "ping", "ping_event": {"event_id": 1}}, _metadata()])
    provider, session = _probing(_Vendor(), socket)
    assert await provider.probe("k", _inputs(), timeout=2) == (True, "ok")
    assert socket.sent == [provider.build_setup(_inputs())]
    assert socket.closed and session.closed


async def test_the_probe_refuses_in_words_what_lia_cannot_serve() -> None:
    ulaw = _Socket([_metadata(agent_output_audio_format="ulaw_8000")])
    provider, _ = _probing(_Vendor(), ulaw)
    accepted, words = await provider.probe("k", _inputs(), timeout=2)
    assert accepted is False and "ulaw_8000" in words and "PCM" in words
    other_input = _Socket([_metadata(user_input_audio_format="pcm_44100")])
    provider, _ = _probing(_Vendor(), other_input)
    accepted, words = await provider.probe("k", _inputs(), timeout=2)
    assert accepted is False and "pcm_44100" in words and "pcm_16000" in words


async def test_the_probe_waits_for_the_verdict_after_the_metadata() -> None:
    """Measured 2026-09-19 on the owner's agent: the metadata comes FIRST and the
    1008 on a refused initiation only afterwards — a probe returning on the
    metadata said « ok » about a session that died at once."""
    late_close = _Socket(
        [_metadata()],
        close_code=1008,
        close_reason="Invalid message received: 1 validation error … source_info.source",
    )
    provider, _ = _probing(_Vendor(), late_close)
    accepted, words = await provider.probe("k", _inputs(), timeout=2)
    assert accepted is False
    assert words.startswith("closed_1008") and "source_info.source" in words


async def test_the_probe_reports_the_providers_refusal_a_close_and_a_silence() -> None:
    refused = _Socket([{"type": "error", "code": 1008, "message": "override not allowed"}])
    provider, _ = _probing(_Vendor(), refused)
    assert await provider.probe("k", _inputs(), timeout=2) == (
        False,
        "1008: override not allowed",
    )
    closed = _Socket([], close_code=1008)
    provider, _ = _probing(_Vendor(), closed)
    accepted, words = await provider.probe("k", _inputs(), timeout=2)
    assert accepted is False and words.startswith("closed_1008")
    silent = _Socket([])
    provider, _ = _probing(_Vendor(), silent)
    assert await provider.probe("k", _inputs(), timeout=0.2) == (
        False,
        "the provider did not answer in time",
    )


async def test_the_probe_reports_a_vendor_http_refusal_before_any_socket() -> None:
    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"detail": {"status": "invalid_api_key"}})
        ),
    )
    provider._open_socket = AsyncMock(side_effect=AssertionError("no socket"))  # type: ignore[method-assign]
    accepted, words = await provider.probe("k", _inputs(), timeout=2)
    assert accepted is False and words.startswith("http_401")


def test_output_rate_reads_the_pcm_format_and_nothing_else() -> None:
    assert output_rate_of("pcm_24000") == 24000
    assert output_rate_of("pcm_16000") == 16000
    assert output_rate_of("ulaw_8000") is None
    assert output_rate_of("pcm_") is None


# -- the connector side ---------------------------------------------------------------------


async def test_the_key_verifier_lists_the_agents() -> None:
    from src.domains.connectors.api_key_verifiers import API_KEY_FUNCTIONAL_VERIFIERS

    verify = API_KEY_FUNCTIONAL_VERIFIERS[ConnectorType.ELEVENLABS_LIVE]
    vendor = _Vendor()
    with patch(f"{LISTING}.http_client", _listing_client(vendor)):
        ok, message = await verify("k", None)
    assert ok is True and "2 agent" in message
    # The key travels in the vendor's own header, never as a bearer.
    assert vendor.calls[0][:2] == ("GET", "/v1/convai/agents")
    with patch(
        f"{LISTING}.http_client",
        lambda **_kw: httpx.AsyncClient(
            base_url="https://api.elevenlabs.io/v1",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"detail": {"status": "x"}})
            ),
        ),
    ):
        ok, message = await verify("k", None)
    assert ok is False and "401" in message


async def test_the_agents_speaking_engine_decides_whether_cues_are_offered() -> None:
    """ADR-373: the agent's stored engine, read on the person's key, never guessed."""
    from src.domains.voice.expressive_cues import ELEVENLABS_AGENT_TAGS, NO_CUES

    vendor = _Vendor()
    provider = _provider(vendor)
    assert await provider.expression_dialect("k", AGENT) is ELEVENLABS_AGENT_TAGS
    assert ("GET", f"/v1/convai/agents/{AGENT}", None) in vendor.calls
    vendor.agent["conversation_config"]["tts"] = {"model_id": "eleven_flash_v2_5"}
    assert await provider.expression_dialect("k", AGENT) is NO_CUES


# -- what LIA writes on the agent so its voice is the personality's (ADR-373) ---------------


def _patches(vendor: _Vendor) -> list[dict[str, Any]]:
    return [body for method, _path, body in vendor.calls if method == "PATCH"]


def _palettes(outcome: str) -> float:
    from prometheus_client import REGISTRY

    labels = {"surface": "live", "outcome": outcome}
    return REGISTRY.get_sample_value("live_cue_palette_synced_total", labels) or 0.0


async def test_an_engine_that_performs_cues_gets_lias_palette() -> None:
    vendor = _Vendor()
    written = _palettes("written")
    await _provider(vendor).sync_agent("k", {}, _inputs(cue_dialect=ELEVENLABS_AGENT_TAGS.name))
    assert _palettes("written") - written == 1.0
    # The persona and the palette are two writes: one refused never costs the other.
    assert _patches(vendor)[1:3] == [
        {"conversation_config": {"agent": {"prompt": {"ignore_default_personality": True}}}},
        {
            "conversation_config": {
                "tts": {
                    "model_id": "eleven_v3_conversational",
                    "voice_id": "v",
                    "suggested_audio_tags": palette(ELEVENLABS_AGENT_TAGS, PERSON_CUES),
                }
            }
        },
    ]


async def test_a_refused_palette_keeps_the_vendors_persona_dropped() -> None:
    """The speaking block travels whole: if the vendor refuses it, the persona still drops."""
    vendor = _Vendor()

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH" and b"suggested_audio_tags" in request.content:
            return httpx.Response(422, json={"detail": "unsupported"})
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    refused = _palettes("refused")
    await provider.sync_agent("k", {}, _inputs(cue_dialect=ELEVENLABS_AGENT_TAGS.name))
    assert vendor.agent["conversation_config"]["agent"]["prompt"]["ignore_default_personality"]
    assert _palettes("refused") - refused == 1.0


async def test_the_persons_voice_survives_the_palette_whatever_the_vendors_merge() -> None:
    """The speaking block is sent back whole: a vendor replacing it keeps the voice."""
    vendor = _Vendor(replace_tts=True)
    vendor.agent["conversation_config"]["tts"].update(expressive_mode=True, stability=0.4)
    await _provider(vendor).sync_agent("k", {}, _inputs(cue_dialect=ELEVENLABS_AGENT_TAGS.name))
    assert vendor.agent["conversation_config"]["tts"] == {
        "model_id": "eleven_v3_conversational",
        "voice_id": "v",
        "expressive_mode": True,
        "stability": 0.4,
        "suggested_audio_tags": palette(ELEVENLABS_AGENT_TAGS, PERSON_CUES),
    }


async def test_a_settled_agent_is_patched_for_nothing_but_what_drifted() -> None:
    vendor = _Vendor()
    provider = _provider(vendor)
    cues = _inputs(cue_dialect=ELEVENLABS_AGENT_TAGS.name)
    first = await provider.sync_agent("k", {}, cues)
    before = len(vendor.calls)
    again = await provider.sync_agent("k", first, cues)
    assert again == first
    assert [method for method, *_ in vendor.calls[before:]] == ["GET"]
    # The person rewrites the palette on the portal: the next start writes it back,
    # and nothing else.
    vendor.agent["conversation_config"]["tts"]["suggested_audio_tags"] = [
        {"tag": "Avec enthousiasme", "description": "at the start and during the discussion"}
    ]
    before = len(vendor.calls)
    await provider.sync_agent("k", again, cues)
    assert [body for method, _p, body in vendor.calls[before:] if method == "PATCH"] == [
        {
            "conversation_config": {
                "tts": {
                    "model_id": "eleven_v3_conversational",
                    "voice_id": "v",
                    "suggested_audio_tags": palette(ELEVENLABS_AGENT_TAGS, PERSON_CUES),
                }
            }
        }
    ]


async def test_a_refused_expression_patch_never_refuses_the_session() -> None:
    """The palette is colour: a vendor refusing it costs the cues, never the session."""
    vendor = _Vendor()

    def _handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if request.method == "PATCH" and "ignore_default_personality" in json.dumps(body):
            vendor.calls.append((request.method, request.url.path, body))
            return httpx.Response(422, json={"detail": "unsupported"})
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    synced = await provider.sync_agent("k", {}, _inputs(cue_dialect=ELEVENLABS_AGENT_TAGS.name))
    # The tools were still attached: the session starts.
    assert synced[ELEVENLABS_LIVE_TOOLS_METADATA_KEY]
    assert _carried(vendor.agent) == ["tool_lia_1"]


async def test_a_refused_permission_patch_refuses_the_start() -> None:
    """Without the permission the vendor refuses LIA's frame: the start must say so."""
    from src.domains.telephony.client import ElevenLabsAgentsError

    vendor = _Vendor()

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH" and b"platform_settings" in request.content:
            return httpx.Response(422, json={"detail": "no"})
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    with pytest.raises(ElevenLabsAgentsError):
        await provider.sync_agent("k", {}, _inputs())


async def test_the_probe_grants_what_its_frame_overrides_before_it_opens() -> None:
    """Activation probes the REAL frame; the agent must already allow it."""
    vendor = _Vendor()
    socket = _Socket([_metadata()])
    provider, _ = _probing(vendor, socket)
    assert await provider.probe("k", _inputs(), timeout=2) == (True, "ok")
    grant_at = next(i for i, call in enumerate(vendor.calls) if call[0] == "PATCH")
    url_at = next(i for i, call in enumerate(vendor.calls) if "get-signed-url" in call[1])
    assert grant_at < url_at
    overrides = vendor.agent["platform_settings"]["overrides"]["conversation_config_override"]
    assert overrides["agent"] == {"prompt": {"prompt": True}, "first_message": True}
    # Already allowed: nothing is written again.
    before = len(vendor.calls)
    provider, _ = _probing(vendor, _Socket([_metadata()]))
    assert await provider.probe("k", _inputs(), timeout=2) == (True, "ok")
    assert all(call[0] != "PATCH" for call in vendor.calls[before:])


# -- the agent's tools are LIA's (ADR-373): the scoped sweep, the self-heal -------------------


def _swept(outcome: str) -> float:
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value("live_agent_tools_swept_total", {"outcome": outcome}) or 0.0


async def test_what_lia_left_on_the_agent_is_released_and_nothing_else() -> None:
    """Every id the agent carried outside LIA's current sets is detached; of those,
    the CLIENT tools named as LIA's live tools are deleted WITHOUT force — one another
    agent still uses is kept (409) and counted — and nothing else is touched: the
    person's own tool, the other kind's current set, a tool LIA did not name."""
    vendor = _Vendor()
    vendor.tools.update(
        {
            "orphan_delegation": {"type": "client", "name": LIVE_DELEGATION_TOOL_NAME},
            "orphan_shared": {"type": "client", "name": LIVE_DELEGATION_TOOL_NAME},
            "orphan_lookup": {"type": "client", "name": "get_events_tool"},
            "tool_direct": {"type": "client", "name": "get_events_tool"},
            "phone_hook": {"type": "webhook", "name": LIVE_DELEGATION_TOOL_NAME},
        }
    )
    vendor.used_elsewhere.add("orphan_shared")
    carried = [
        "tool_theirs",
        "orphan_delegation",
        "orphan_shared",
        "orphan_lookup",
        "tool_direct",
        "phone_hook",
    ]
    vendor.agent["conversation_config"]["agent"]["prompt"]["tool_ids"] = list(carried)
    # The direct kind's current set is LIA's, recorded: detached, never deleted.
    metadata = {
        ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {tools_fingerprint([EVENTS]): ["tool_direct"]},
        ELEVENLABS_LIVE_TOOL_KINDS_METADATA_KEY: {"direct": tools_fingerprint([EVENTS])},
    }
    freed, in_use = _swept("freed"), _swept("in_use")

    await _provider(vendor).sync_agent("k", metadata, _inputs())

    assert _carried(vendor.agent) == ["tool_lia_1"]
    assert sorted(vendor.deleted()) == ["orphan_delegation", "orphan_lookup", "orphan_shared"]
    assert vendor.forced == []
    assert not {"orphan_delegation", "orphan_lookup"} & set(vendor.tools)
    assert {"orphan_shared", "tool_theirs", "tool_direct", "phone_hook"} <= set(vendor.tools)
    assert (_swept("freed") - freed, _swept("in_use") - in_use) == (2.0, 1.0)
    # Detached BEFORE it is released: a delete that is not forced frees a tool
    # only once no agent references it.
    patch_at = max(i for i, c in enumerate(vendor.calls) if c[0] == "PATCH")
    first_delete = next(i for i, c in enumerate(vendor.calls) if c[0] == "DELETE")
    assert patch_at < first_delete


async def test_a_listing_the_vendor_refuses_skips_the_sweep_never_the_session() -> None:
    vendor = _Vendor()
    vendor.tools["orphan"] = {"type": "client", "name": LIVE_DELEGATION_TOOL_NAME}
    vendor.agent["conversation_config"]["agent"]["prompt"]["tool_ids"] = ["orphan"]

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/convai/tools":
            return httpx.Response(500, json={"detail": "boom"})
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    synced = await provider.sync_agent("k", {}, _inputs())
    assert synced[ELEVENLABS_LIVE_TOOLS_METADATA_KEY] == {
        tools_fingerprint([DELEGATION]): ["tool_lia_1"]
    }
    assert _carried(vendor.agent) == ["tool_lia_1"]
    assert vendor.deleted() == [] and "orphan" in vendor.tools


async def test_a_set_the_workspace_lost_is_healed_and_the_attach_retried_once() -> None:
    """Today a dead id is a session refused for ever: a portal deletion, a sibling
    instance's cleanup or a hand cleanup leaves the metadata naming a tool the
    vendor no longer holds. Only the lost tools are re-created, in their place."""
    vendor = _Vendor()
    lookup = {**EVENTS, "name": "get_weather_tool", "description": "Reads the weather."}
    fingerprint = tools_fingerprint([EVENTS, lookup])
    vendor.tools["tool_events"] = {"type": "client", "name": "get_events_tool"}
    metadata = {
        ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {fingerprint: ["tool_events", "tool_lost"]},
        ELEVENLABS_LIVE_TOOL_KINDS_METADATA_KEY: {"direct": fingerprint},
    }

    synced = await _provider(vendor).sync_agent(
        "k", metadata, _inputs(tool_declaration=None, direct_tools=(EVENTS, lookup))
    )

    assert synced[ELEVENLABS_LIVE_TOOLS_METADATA_KEY] == {
        fingerprint: ["tool_events", "tool_lia_1"]
    }
    assert _carried(vendor.agent) == ["tool_events", "tool_lia_1"]
    created = [body for _m, path, body in vendor.calls if path == "/v1/convai/tools" and body]
    assert [body["tool_config"]["name"] for body in created] == ["get_weather_tool"]
    attaches = [
        body for method, _p, body in vendor.calls if method == "PATCH" and "tool_ids" in str(body)
    ]
    assert len(attaches) == 2  # the refused one, then the retry


async def test_a_refused_attach_no_dead_id_explains_is_raised_and_nothing_re_created() -> None:
    vendor = _Vendor()
    vendor.tools["tool_old"] = {"type": "client", "name": LIVE_DELEGATION_TOOL_NAME}
    known = {ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {tools_fingerprint([DELEGATION]): ["tool_old"]}}

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH" and b"tool_ids" in request.content:
            return httpx.Response(500, json={"detail": "boom"})
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    from src.domains.telephony.client import ElevenLabsAgentsError

    with pytest.raises(ElevenLabsAgentsError):
        await provider.sync_agent("k", known, _inputs())
    assert vendor.created == 0 and vendor.deleted() == []


async def test_a_retry_refused_after_a_heal_removes_what_the_heal_created() -> None:
    vendor = _Vendor()
    known = {ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {tools_fingerprint([DELEGATION]): ["tool_lost"]}}

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH" and b"tool_ids" in request.content:
            vendor.calls.append((request.method, request.url.path, None))
            return httpx.Response(422, json={"detail": "refused"})
        return vendor(request)

    provider = ElevenLabsLiveProvider()
    provider._client = lambda api_key: ElevenLabsAgentsClient(  # type: ignore[method-assign]
        api_key, transport=httpx.MockTransport(_handler)
    )
    from src.domains.telephony.client import ElevenLabsAgentsError

    with pytest.raises(ElevenLabsAgentsError):
        await provider.sync_agent("k", known, _inputs())
    # The one tool the heal created is removed: nothing would name it.
    assert vendor.created == 1 and vendor.forced == ["tool_lia_1"]
    assert "tool_lia_1" not in vendor.tools
