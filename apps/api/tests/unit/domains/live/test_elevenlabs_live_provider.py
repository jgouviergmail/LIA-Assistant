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
    ELEVENLABS_LIVE_TOOL_TIMEOUT_MAX_SECONDS,
    ELEVENLABS_LIVE_TOOLS_METADATA_KEY,
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


class _Vendor:
    """The agents API as a MockTransport handler, recording every call."""

    def __init__(self, agent: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, str, Any]] = []
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
        if request.method == "PATCH" and request.url.path == f"/v1/convai/agents/{AGENT}":
            return httpx.Response(200, json={})
        if request.method == "POST" and request.url.path == "/v1/convai/tools":
            self.created += 1
            return httpx.Response(200, json={"id": f"tool_lia_{self.created}"})
        if request.method == "DELETE" and request.url.path.startswith("/v1/convai/tools/"):
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"detail": "unknown"})

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


def test_the_setup_is_the_initiation_frame_with_the_prompt_alone() -> None:
    setup = ElevenLabsLiveProvider().build_setup(_inputs())
    assert setup["type"] == INITIATION_TYPE
    assert setup["conversation_config_override"] == {
        "agent": {"prompt": {"prompt": "You are LIA's voice."}}
    }
    # The greeting, the language, the voice: the portal's, never overridden.
    assert "first_message" not in json.dumps(setup)
    assert "tts" not in setup["conversation_config_override"]
    # No `source_info`: measured 2026-09-19, the vendor validates it against its
    # own SDK names and closes 1008 on any other word — after the metadata.
    assert "source_info" not in setup


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


# -- the agent sync ------------------------------------------------------------------------


async def test_the_sync_grants_the_prompt_override_merged_and_attaches_the_tools() -> None:
    vendor = _Vendor()
    provider = _provider(vendor)
    metadata = {"agent_id": AGENT, "other": "kept"}
    synced = await provider.sync_agent("k", metadata, _inputs())
    # A NEW dict, the input untouched (the JSONB rule).
    assert synced is not metadata and metadata == {"agent_id": AGENT, "other": "kept"}
    assert synced["other"] == "kept"
    assert synced[ELEVENLABS_LIVE_OVERRIDE_METADATA_KEY] == [AGENT]
    fingerprint = tools_fingerprint([DELEGATION])
    assert synced[ELEVENLABS_LIVE_TOOLS_METADATA_KEY] == {fingerprint: ["tool_lia_1"]}
    patches = [body for method, path, body in vendor.calls if method == "PATCH"]
    # The permission PATCH keeps the person's own permissions and sets the prompt's.
    assert patches[0] == {
        "platform_settings": {
            "overrides": {
                "conversation_config_override": {
                    "tts": {"voice_id": True},
                    "agent": {"prompt": {"prompt": True}},
                },
                "custom_llm_extra_body": True,
            }
        }
    }
    # The tool PATCH keeps the person's own tool and adds LIA's.
    assert patches[1] == {
        "conversation_config": {"agent": {"prompt": {"tool_ids": ["tool_theirs", "tool_lia_1"]}}}
    }
    created = [body for method, path, body in vendor.calls if path == "/v1/convai/tools"]
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
    vendor.agent["conversation_config"]["agent"]["prompt"]["tool_ids"] = [
        "tool_theirs",
        "tool_lia_1",
    ]
    before = len(vendor.calls)
    again = await provider.sync_agent("k", first, _inputs())
    assert again == first
    # One GET of the agent, nothing granted, created or patched again.
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
        "conversation_config": {"agent": {"prompt": {"tool_ids": ["tool_theirs", "tool_lia_2"]}}}
    }
    created = [body for _m, path, body in vendor.calls if path == "/v1/convai/tools"]
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
    # The old set was taken off the agent BEFORE its tools were deleted.
    last_patch = [body for method, _p, body in vendor.calls if method == "PATCH"][-1]
    assert last_patch == {
        "conversation_config": {"agent": {"prompt": {"tool_ids": ["tool_theirs", "tool_lia_3"]}}}
    }
    delete_at = next(i for i, c in enumerate(vendor.calls) if c[0] == "DELETE")
    patch_at = max(i for i, c in enumerate(vendor.calls) if c[0] == "PATCH")
    assert patch_at < delete_at
    # A set the metadata holds under a bare fingerprint (the shape before the
    # kinds were recorded) is reused when it matches, never re-created.
    legacy = {ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {tools_fingerprint([EVENTS]): ["tool_old"]}}
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
    # The same refusal on a set the metadata already names deletes nothing.
    deleted.clear()
    known = {ELEVENLABS_LIVE_TOOLS_METADATA_KEY: {tools_fingerprint([DELEGATION]): ["tool_old"]}}
    with pytest.raises(ElevenLabsAgentsError):
        await provider.sync_agent("k", known, _inputs())
    assert vendor.created == 1
    assert deleted == []


async def test_a_refusal_cancels_the_creations_still_running_before_the_rollback() -> None:
    """Measured 2026-09-19 on dev: `gather` raised on the third refusal while fifty
    creations went on; the rollback iterated a dict they kept filling and every
    tool created after it was an orphan. With a TaskGroup the siblings are
    cancelled first: nothing is created after the rollback ran."""
    import asyncio

    events: list[str] = []
    from src.domains.telephony.client import ElevenLabsAgentsError

    class _SlowClient:
        async def create_tool(self, body: dict[str, Any]) -> str:
            name = body["tool_config"]["name"]
            # "a" lands before the refusal, "b" to "d" would land after it.
            if name == "refused":
                await asyncio.sleep(0.02)
                raise ElevenLabsAgentsError(422, "no")
            await asyncio.sleep(0.005 if name == "a" else 0.06)
            events.append(f"created:{name}")
            return f"id_{name}"

        async def delete_tool(self, tool_id: str) -> None:
            events.append(f"deleted:{tool_id}")

    from src.domains.live.providers.elevenlabs_live import _create_client_tools

    bodies = [{"tool_config": {"name": n}} for n in ("a", "refused", "b", "c", "d")]
    with pytest.raises(ElevenLabsAgentsError):
        await _create_client_tools(_SlowClient(), bodies)  # type: ignore[arg-type]
    await asyncio.sleep(0.15)
    # "a" was created before the refusal and rolled back; the others were
    # cancelled and never created — nothing lands after the rollback.
    assert events == ["created:a", "deleted:id_a"]


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
