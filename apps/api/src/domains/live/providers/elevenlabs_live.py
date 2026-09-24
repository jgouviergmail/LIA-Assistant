"""ElevenLabs Agents as a live provider (ADR-300 wave 4): the person's own agent, LIA's prompt.

The third provider of ADR-299/ADR-300, and the first whose « model » is not a
model: the person picks ONE AGENT of their ElevenLabs workspace (owner
decision 2026-09-19), and everything but the prompt and LIA's tools stays on
the ElevenLabs portal — the model behind the agent, the voice, the language,
the audio formats, the turn-taking. What LIA sends is its own, exactly as on
the phone (ADR-290): a per-session prompt override, and the client tools the
session declares, attached to the agent by fingerprint (measured on the
phone: the vendor refuses ``tool_ids`` inside an override).

The wire, read from the official ``@elevenlabs/client`` 1.25.0 source and
MEASURED on a real agent (2026-09-19: the initiation, the metadata, the
microphone's audio, ``user_transcript`` → ``audio`` → ``agent_response``, two
turns archived — and ``source_info`` closing 1008 after the metadata):

- the browser opens a SIGNED URL (``GET /v1/convai/conversation/get-signed-url``,
  minted on the person's key, valid 15 minutes for ONE conversation) on the
  ``convai`` subprotocol — the ``token`` connection of the seam;
- its first frame is ``conversation_initiation_client_data`` carrying the
  prompt override; the first answer ``conversation_initiation_metadata``
  names the conversation and the agent's audio formats;
- the model delegates by a CLIENT tool (``client_tool_call`` →
  ``client_tool_result``), blocking: the agent waits for the result — the
  ``tool`` delegation wire, with ``async_delegation`` false;
- no resumption, no VAD setting, no delivery scheduling, no idle signal.

The platform prices NOTHING of it (owner rule 2026-09-20): the agents API is
on the person's own key and has its own price grid (a minute of
conversation, the LLM behind the agent on top — nothing the platform's
tariff table, which lists ElevenLabs' SIMPLE API models for the STT and TTS
slots, could state). ``billing = "vendor"``: an agent is offered whatever the
tariff table holds, the meter shows the clock alone, and at the end the
vendor's own bill is read (``GET /v1/convai/conversations/{id}``:
``metadata.cost_fiat``, the LLM and call charges, the models charged for) and
shown — never recorded. The first version priced every agent under one flat
row of ours (``elevenlabs-agents``, 0.10 USD a minute): a guess, retired.
What the listing still reads from each agent's configuration — the voice
model (``tts.model_id``) and the LLM (``prompt.llm``) — is named to the
person, for information.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import structlog

from src.core.config import settings
from src.core.constants import (
    ELEVENLABS_LIVE_INPUT_FORMAT,
    ELEVENLABS_LIVE_OUTPUT_FORMAT_PREFIX,
    ELEVENLABS_LIVE_OVERRIDE_METADATA_KEY,
    ELEVENLABS_LIVE_PORTAL_VOICE,
    ELEVENLABS_LIVE_PROBE_SETTLE_SECONDS,
    ELEVENLABS_LIVE_SAMPLE_RATE,
    ELEVENLABS_LIVE_SIGNED_URL_TTL_SECONDS,
    ELEVENLABS_LIVE_TOOL_KINDS_METADATA_KEY,
    ELEVENLABS_LIVE_TOOL_TIMEOUT_MAX_SECONDS,
    ELEVENLABS_LIVE_TOOLS_METADATA_KEY,
    ELEVENLABS_LIVE_WS_SUBPROTOCOL,
)
from src.domains.connectors.models import ConnectorType
from src.domains.live.providers.protocol import (
    LiveBilling,
    LiveConnection,
    LiveCredential,
    LiveDelegationWire,
    LiveModelCapabilities,
    LiveSetupInputs,
)
from src.domains.live.schemas import (
    LiveModel,
    LiveModelCapabilitiesResponse,
    LiveVendorBill,
    LiveVoicesResponse,
)
from src.domains.telephony.client import (
    ElevenLabsAgentsClient,
    ElevenLabsAgentsError,
    first_refusal,
)
from src.infrastructure.llm.providers.elevenlabs_live_listing import list_agents

logger = structlog.get_logger(__name__)

#: The first frame the browser sends, and the only one the API renders.
INITIATION_TYPE: Final = "conversation_initiation_client_data"
#: The first frame the provider answers a good initiation with.
INITIATION_METADATA_TYPE: Final = "conversation_initiation_metadata"
#: One row for the whole provider (read from the SDK, 2026-09-19): a blocking
#: client tool, the agent's own reflexes, no resumption, no thinking level.
_CAPABILITIES: Final = LiveModelCapabilities(
    async_delegation=False,
    delivery_scheduling=False,
    reports_idle=False,
    cancels_on_interruption=False,
    configurable_vad=False,
    resumes=False,
    thinking=False,
    direct_tools=True,
    portal_voice=True,
    vendor_billed=True,
)


class ElevenLabsLiveRefused(Exception):
    """The provider refused a session: its code and words, never the key."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def declarations_of(inputs: LiveSetupInputs) -> list[dict[str, Any]]:
    """The function declarations a setup carries: the delegation one, or the direct tools."""
    if inputs.tool_declaration is not None:
        return [inputs.tool_declaration]
    return list(inputs.direct_tools)


def tools_fingerprint(declarations: list[dict[str, Any]]) -> str:
    """One digest of what the agent must hold: a changed description re-provisions."""
    canonical = json.dumps(
        [{k: v for k, v in declaration.items() if k != "behavior"} for declaration in declarations],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def client_tool_body(declaration: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    """One provider-neutral declaration as a workspace CLIENT tool body.

    The client answers it (``client_tool_result``) — the browser's tool door
    on a direct session, the delegation bridge on a delegated one — so the
    agent expects a response and waits for it, bounded.
    """
    return {
        "tool_config": {
            "type": "client",
            "name": declaration["name"],
            "description": declaration["description"],
            "parameters": declaration["parameters"],
            "expects_response": True,
            "response_timeout_secs": min(timeout_seconds, ELEVENLABS_LIVE_TOOL_TIMEOUT_MAX_SECONDS),
        }
    }


def voice_model_of(agent: dict[str, Any]) -> str | None:
    """The voice model an agent speaks with (``conversation_config.tts.model_id``), or None."""
    tts = ((agent.get("conversation_config") or {}).get("tts")) or {}
    model = tts.get("model_id")
    return str(model) if isinstance(model, str) and model else None


def llm_of(agent: dict[str, Any]) -> str | None:
    """The LLM behind an agent (``conversation_config.agent.prompt.llm``), or None."""
    prompt = (((agent.get("conversation_config") or {}).get("agent")) or {}).get("prompt") or {}
    llm = prompt.get("llm")
    return str(llm) if isinstance(llm, str) and llm else None


def _number(value: object) -> float | None:
    """A JSON number, or None (a boolean is not a number)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _credits(charging: dict[str, Any], key: str) -> int | None:
    value = _number(charging.get(key))
    return None if value is None else int(value)


def _mapping(value: object) -> dict[str, Any]:
    """The value as a mapping, or an empty one."""
    return value if isinstance(value, dict) else {}


def vendor_bill_of(payload: dict[str, Any], *, provider_id: str) -> LiveVendorBill | None:
    """The vendor's bill of a conversation, from its GET payload; None when it carries none.

    Args:
        payload: The conversation as the vendor returns it.
        provider_id: The provider the bill is named under.

    Returns:
        The bill, or None when neither a fiat cost nor a credit cost is stated
        (a conversation still being settled).
    """
    metadata = _mapping(payload.get("metadata") if isinstance(payload, dict) else None)
    cost_usd = _number(metadata.get("cost_fiat"))
    credits = _number(metadata.get("cost"))
    if cost_usd is None and credits is None:
        return None
    charging = _mapping(metadata.get("charging"))
    model_usage = _mapping(
        _mapping(_mapping(charging.get("llm_usage")).get("irreversible_generation")).get(
            "model_usage"
        )
    )
    tts_model = _mapping(charging.get("tts_usage")).get("primary_tts_model")
    duration = _number(metadata.get("call_duration_secs"))
    return LiveVendorBill(
        provider=provider_id,
        cost_usd=cost_usd,
        credits=None if credits is None else int(credits),
        llm_credits=_credits(charging, "llm_charge"),
        call_credits=_credits(charging, "call_charge"),
        platform_credits=_credits(charging, "platform_charge"),
        llm_model=", ".join(str(name) for name in model_usage) or None,
        tts_model=str(tts_model) if isinstance(tts_model, str) and tts_model else None,
        duration_seconds=None if duration is None else int(duration),
    )


def _lia_tool_ids(metadata: dict[str, Any]) -> set[str]:
    """Every workspace tool id LIA created, across fingerprints."""
    held = metadata.get(ELEVENLABS_LIVE_TOOLS_METADATA_KEY) or {}
    return {str(tool_id) for ids in held.values() if isinstance(ids, list) for tool_id in ids}


def set_kind_of(inputs: LiveSetupInputs) -> str:
    """Which KIND of set a setup declares: the delegation function, or the direct tools."""
    return "delegation" if inputs.tool_declaration is not None else "direct"


def _held_sets(metadata: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, str]]:
    """The tool sets LIA holds on the connector, by fingerprint, and which one each kind holds."""
    held = {
        str(k): [str(i) for i in v]
        for k, v in (metadata.get(ELEVENLABS_LIVE_TOOLS_METADATA_KEY) or {}).items()
        if isinstance(v, list)
    }
    kinds = {
        str(k): str(v)
        for k, v in (metadata.get(ELEVENLABS_LIVE_TOOL_KINDS_METADATA_KEY) or {}).items()
    }
    return held, kinds


def _retire_previous(
    held: dict[str, list[str]], kinds: dict[str, str], kind: str, fingerprint: str
) -> list[str]:
    """Make ``fingerprint`` the set of ``kind``; the ids of the set it held before, if another.

    A set the metadata holds under a bare fingerprint (the shape before the
    kinds were recorded) is simply adopted the first time its kind names it.
    """
    previous = kinds.get(kind)
    kinds[kind] = fingerprint
    if not previous or previous == fingerprint:
        return []
    return held.pop(previous, [])


async def _create_set(
    client: ElevenLabsAgentsClient, inputs: LiveSetupInputs, declarations: list[dict[str, Any]]
) -> list[str]:
    """Create one set of client tools for a setup, under the timeout its wire needs."""
    timeout = (
        settings.live_delegation_timeout_seconds
        if inputs.tool_declaration is not None
        else settings.telephony_live_tool_timeout_seconds
    )
    created = await _create_client_tools(
        client, [client_tool_body(d, timeout_seconds=timeout) for d in declarations]
    )
    logger.info("elevenlabs_live_tools_created", tool_count=len(created))
    return created


class ElevenLabsLiveProvider:
    """ElevenLabs Agents over a signed WebSocket URL, the agent prepared by LIA."""

    provider_id = "elevenlabs"
    connector_type = ConnectorType.ELEVENLABS_LIVE
    connection: LiveConnection = "token"
    delegation_wire: LiveDelegationWire = "tool"
    #: No default: an agent is the person's own, there is none to preselect.
    default_model = ""
    billing: LiveBilling = "vendor"

    # -- thin doors the tests replace ----------------------------------------------------

    def _client(self, api_key: str) -> ElevenLabsAgentsClient:
        return ElevenLabsAgentsClient(api_key, timeout_seconds=settings.live_probe_timeout_seconds)

    async def _open_socket(self, url: str, *, timeout: float) -> Any:
        """An aiohttp WebSocket on the signed URL, the ``convai`` subprotocol named."""
        import aiohttp

        session = aiohttp.ClientSession()
        try:
            ws = await session.ws_connect(
                url,
                protocols=(ELEVENLABS_LIVE_WS_SUBPROTOCOL,),
                timeout=aiohttp.ClientWSTimeout(ws_close=timeout),
            )
        except BaseException:
            await session.close()
            raise
        return session, ws

    # -- the seam --------------------------------------------------------------------------

    async def list_models(self, api_key: str) -> list[LiveModel]:
        """The agents of the workspace: each one a « model », named after itself.

        Each agent's configuration is read too, for information: the voice
        model it speaks with and the LLM behind it — what the portal
        configured, named to the person; nothing here prices anything.
        """
        client = self._client(api_key)
        models: list[LiveModel] = []
        for agent_id, name in await list_agents(api_key):
            agent = await client.get_agent(agent_id)
            models.append(
                LiveModel(
                    provider=self.provider_id,
                    name=agent_id,
                    label=name,
                    voice_model=voice_model_of(agent),
                    llm=llm_of(agent),
                    thinking_levels=[],
                    capabilities=LiveModelCapabilitiesResponse(
                        **asdict(self.capabilities_of(agent_id))
                    ),
                )
            )
        return models

    async def conversation_bill(
        self, api_key: str, conversation_id: str, *, timeout: float
    ) -> LiveVendorBill | None:
        """What the vendor billed for one conversation, on the person's key.

        ``GET /v1/convai/conversations/{id}`` (read from the API reference,
        2026-09-20): ``metadata.cost_fiat`` in USD, ``metadata.cost`` in
        credits, ``metadata.charging.{llm_charge, call_charge,
        platform_charge}`` in credits, ``llm_usage…model_usage`` keyed by
        the LLM's name, ``tts_usage.primary_tts_model``. Best effort: a
        conversation the vendor has not settled yet, or refuses, reads as
        None — the person keeps the meter's estimate, never a wrong figure.
        """
        client = ElevenLabsAgentsClient(api_key, timeout_seconds=timeout)
        try:
            payload = await client.get_conversation(conversation_id)
        except Exception as exc:  # noqa: BLE001 - a bill that cannot be read is shown as none
            logger.info("elevenlabs_live_bill_unavailable", error_type=type(exc).__name__)
            return None
        return vendor_bill_of(payload, provider_id=self.provider_id)

    async def list_voices(self, _api_key: str) -> LiveVoicesResponse:
        """No list: the voice is the agent's own, on the portal (``provenance = portal``)."""
        return LiveVoicesResponse(provider=self.provider_id, voices=[], provenance="portal")

    def knows_voice(self, name: str) -> bool:
        """Only the sentinel: the form never offers a voice for an agent."""
        return name == ELEVENLABS_LIVE_PORTAL_VOICE

    @property
    def sample_rate(self) -> int:
        """The rate LIA captures at (the agent's output rate is the session's own)."""
        return ELEVENLABS_LIVE_SAMPLE_RATE

    def thinking_levels_of(self, model: str) -> tuple[str, ...]:
        """The agent's model reasons as the portal configured it: no ladder here."""
        return ()

    def capabilities_of(self, model: str) -> LiveModelCapabilities:
        """The one documented row of the provider."""
        return replace(_CAPABILITIES)

    def build_setup(self, inputs: LiveSetupInputs) -> dict[str, Any]:
        """The initiation frame: LIA's prompt over the agent's, nothing else overridden.

        The tools are not here — they are attached to the agent by
        :meth:`sync_agent` (the vendor refuses ``tool_ids`` in an override).
        The greeting, the language, the voice and the reflexes stay the portal's.
        No ``source_info``: measured 2026-09-19 on the owner's agent, the field
        is validated against the vendor's OWN SDK names (``js_sdk`` …) and any
        other word closes the conversation 1008 — AFTER the metadata, so the
        session opened and died at once; omitted, the conversation stays open.
        """
        return {
            "type": INITIATION_TYPE,
            "conversation_config_override": {
                "agent": {"prompt": {"prompt": inputs.system_instruction}}
            },
        }

    async def mint(
        self,
        api_key: str,
        inputs: LiveSetupInputs,
        *,
        expires_at: datetime,
        connect_deadline_at: datetime,
    ) -> LiveCredential:
        """A one-conversation credential for the agent, on the person's key.

        WebSocket gets a signed URL; WebRTC gets a LiveKit token. The connect
        deadline is bounded by LIA's own window and the signed URL's window.
        """
        if inputs.audio_transport == "webrtc":
            token = await self._client(api_key).webrtc_token(inputs.model)
        else:
            token = await self._client(api_key).signed_url(inputs.model)
        vendor_deadline = datetime.now(UTC) + timedelta(
            seconds=ELEVENLABS_LIVE_SIGNED_URL_TTL_SECONDS
        )
        return LiveCredential(
            name=token,
            expires_at=expires_at,
            connect_deadline_at=min(connect_deadline_at, vendor_deadline),
        )

    async def sync_agent(
        self, api_key: str, metadata: dict[str, Any], inputs: LiveSetupInputs
    ) -> dict[str, Any]:
        """Prepare the person's agent for this session: the override permission, the tools.

        Idempotent by what the metadata holds: the permission is granted once
        per agent (merged into the agent's OWN overrides block, never
        replacing it — the vendor replaces omitted booleans with false), the
        client tools are created once per fingerprint of the declarations,
        and the agent's ``tool_ids`` are set to the person's own tools plus
        THIS session's set (the other set of LIA's is detached, so a
        delegated session never sees the read-only tools and vice versa).
        A new fingerprint of a KIND (a renamed description, a tool a release
        added) retires the set that kind held before — taken off the agent,
        then deleted from the workspace (forced, best effort) — so at most one
        set per kind lives there: the phone's own rule on drift, where every
        change used to leave a whole set orphaned for ever. A patch the vendor
        refuses deletes the set this call created (the metadata naming it is
        stored by the caller, once this returns) and re-raises.

        Args:
            api_key: The person's key.
            metadata: The connector's metadata as stored.
            inputs: The session's setup inputs (the agent id, the declarations).

        Returns:
            The metadata to store — a NEW dict (the JSONB rule).
        """
        client = self._client(api_key)
        agent_id = inputs.model
        updated: dict[str, Any] = dict(metadata)
        granted = list(updated.get(ELEVENLABS_LIVE_OVERRIDE_METADATA_KEY) or [])
        agent = await client.get_agent(agent_id)
        if agent_id not in granted:
            await client.patch_agent(agent_id, _grant_prompt_override(agent))
            granted.append(agent_id)
            updated[ELEVENLABS_LIVE_OVERRIDE_METADATA_KEY] = granted
        declarations = declarations_of(inputs)
        fingerprint = tools_fingerprint(declarations)
        held, kinds = _held_sets(updated)
        fresh = fingerprint not in held
        if fresh:
            held[fingerprint] = await _create_set(client, inputs, declarations)
        # The set this kind held before, when it is another one: retired
        # below, once the agent no longer names it.
        retired_ids = _retire_previous(held, kinds, set_kind_of(inputs), fingerprint)
        updated[ELEVENLABS_LIVE_TOOLS_METADATA_KEY] = held
        updated[ELEVENLABS_LIVE_TOOL_KINDS_METADATA_KEY] = kinds
        # The person's own tools stay; LIA's other sets — the retired one
        # included — are detached for this session.
        current = _agent_tool_ids(agent)
        mine = _lia_tool_ids(updated) | set(retired_ids)
        wanted = [tool_id for tool_id in current if tool_id not in mine] + held[fingerprint]
        if wanted != current:
            try:
                await client.set_agent_tool_ids(agent_id, wanted)
            except ElevenLabsAgentsError:
                # The caller stores the metadata only once this returns: a set
                # created by THIS call would be named by nothing, and the next
                # start would create it again — one orphan set per attempt.
                if fresh:
                    for tool_id in held[fingerprint]:
                        await client.delete_tool(tool_id)
                raise
        for tool_id in retired_ids:
            await client.delete_tool(tool_id)
        if retired_ids:
            logger.info("elevenlabs_live_tools_retired", tool_count=len(retired_ids))
        return updated

    async def sample_voice(self, api_key: str, voice: str, text: str) -> bytes:
        """No sample: the voice is the agent's own (``portal_voice`` hides the button)."""
        raise ElevenLabsLiveRefused("portal_voice", "the voice is the agent's, on the portal")

    async def probe(
        self, api_key: str, inputs: LiveSetupInputs, *, timeout: float
    ) -> tuple[bool, str]:
        """Open a conversation on the REAL initiation frame and close it.

        The provider judges the agent and the prompt override; LIA judges the
        audio formats it can serve — 16 kHz PCM in (what it captures), any
        PCM rate out (the player follows the metadata). A µ-law agent is
        refused here, in words, rather than heard as noise.
        """
        try:
            url = await self._client(api_key).signed_url(inputs.model)
            metadata = await self._initiate(url, self.build_setup(inputs), timeout=timeout)
        except ElevenLabsLiveRefused as exc:
            return False, f"{exc.code}: {exc.message}"
        except ElevenLabsAgentsError as exc:
            return False, f"http_{exc.status_code}: {exc.detail}"
        except TimeoutError:
            return False, "the provider did not answer in time"
        except Exception as exc:  # noqa: BLE001 - the refusal is the answer we report
            return False, f"{type(exc).__name__}: {exc}"
        return _formats_verdict(metadata)

    async def _initiate(self, url: str, frame: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        """Send the initiation frame, read the metadata, then wait for the verdict.

        The metadata is NOT the verdict: measured 2026-09-19, the provider
        answers it first and closes 1008 on a refused initiation only
        afterwards. The probe therefore keeps listening for
        ``ELEVENLABS_LIVE_PROBE_SETTLE_SECONDS`` after the metadata — a close
        or an ``error`` in that window is the refusal, a ping is not.
        """
        import asyncio

        session, ws = await self._open_socket(url, timeout=timeout)
        try:
            await ws.send_str(json.dumps(frame))
            deadline = asyncio.get_running_loop().time() + timeout
            metadata: dict[str, Any] | None = None
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    if metadata is not None:
                        return metadata
                    raise TimeoutError
                try:
                    message = await asyncio.wait_for(ws.receive(), timeout=remaining)
                except TimeoutError:
                    if metadata is not None:
                        return metadata
                    raise
                found = _metadata_of(ws, message)
                if found is not None and metadata is None:
                    metadata = found
                    # The verdict window: shorter than the timeout, never longer.
                    deadline = min(
                        deadline,
                        asyncio.get_running_loop().time() + ELEVENLABS_LIVE_PROBE_SETTLE_SECONDS,
                    )
        finally:
            if not ws.closed:
                await ws.close(code=1000)
            await session.close()


def _metadata_of(ws: Any, message: Any) -> dict[str, Any] | None:
    """The initiation metadata a message carries; None for a frame that is not the answer yet.

    Raises:
        ElevenLabsLiveRefused: The provider closed, failed, or answered ``error``.
    """
    import aiohttp

    if message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
        # The close frame's reason names the refused field (measured 2026-09-19:
        # « 1 validation error … source_info.source »): it is the answer we report.
        reason = str(getattr(message, "extra", "") or "the provider closed the connection")
        raise ElevenLabsLiveRefused(f"closed_{ws.close_code or 0}", reason[:200])
    if message.type == aiohttp.WSMsgType.ERROR:
        raise ElevenLabsLiveRefused("transport", str(ws.exception()))
    if message.type not in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
        return None
    raw = message.data
    event = json.loads(raw if isinstance(raw, str) else raw.decode())
    if not isinstance(event, dict):
        return None
    kind = event.get("type")
    if kind == INITIATION_METADATA_TYPE:
        metadata = event.get("conversation_initiation_metadata_event")
        return metadata if isinstance(metadata, dict) else {}
    if kind == "error":
        raise ElevenLabsLiveRefused(
            str(event.get("code") or "error"), str(event.get("message") or "")
        )
    # A ping or an early audio frame: not the answer yet.
    return None


async def _create_client_tools(
    client: ElevenLabsAgentsClient, bodies: list[dict[str, Any]]
) -> list[str]:
    """Create every client tool, concurrently under the phone's bound, in the declarations' order.

    Never leaves half a set behind: on a vendor failure what was created is
    removed (forced) before the failure is re-raised — a set the metadata
    never recorded would be orphaned in the person's workspace. The siblings
    are CANCELLED and awaited first (a ``TaskGroup``, never ``gather``):
    measured 2026-09-19 on dev, ``gather`` raised on the third refusal while
    fifty creations went on, the rollback iterated a dict they kept filling
    (« dictionary changed size during iteration ») and every tool created
    after it was an orphan nobody recorded.
    """
    import asyncio

    from src.domains.agents.telephony.live_tools import LIVE_TOOL_PROVISIONING_CONCURRENCY

    created: dict[int, str] = {}
    gate = asyncio.Semaphore(LIVE_TOOL_PROVISIONING_CONCURRENCY)

    async def _create(index: int, body: dict[str, Any]) -> None:
        async with gate:
            created[index] = await client.create_tool(body)

    refused: ElevenLabsAgentsError | None = None
    try:
        async with asyncio.TaskGroup() as group:
            for index, body in enumerate(bodies):
                group.create_task(_create(index, body))
    except* ElevenLabsAgentsError as refusals:
        refused = first_refusal(refusals)
    if refused is not None:
        # Every sibling is finished or cancelled here: the snapshot is complete.
        for tool_id in list(created.values()):
            await client.delete_tool(tool_id)
        raise refused
    return [created[i] for i in range(len(bodies))]


def _agent_tool_ids(agent: dict[str, Any]) -> list[str]:
    """The tool ids the agent holds, as the vendor serves them."""
    prompt = ((agent.get("conversation_config") or {}).get("agent") or {}).get("prompt") or {}
    ids = prompt.get("tool_ids") or []
    return [str(tool_id) for tool_id in ids if isinstance(tool_id, str)]


def _grant_prompt_override(agent: dict[str, Any]) -> dict[str, Any]:
    """The PATCH granting the prompt override, MERGED into the agent's own overrides.

    The vendor replaces every omitted boolean of the block with false
    (measured on the phone, 2026-09-16), so the block is read from the agent
    and sent back whole with the one field LIA needs set — the person's own
    permissions survive.
    """
    stored = ((agent.get("platform_settings") or {}).get("overrides")) or {}
    overrides: dict[str, Any] = json.loads(json.dumps(stored))  # a deep copy
    config = overrides.setdefault("conversation_config_override", {})
    if not isinstance(config, dict):
        config = overrides["conversation_config_override"] = {}
    agent_block = config.setdefault("agent", {})
    if not isinstance(agent_block, dict):
        agent_block = config["agent"] = {}
    prompt_block = agent_block.setdefault("prompt", {})
    if not isinstance(prompt_block, dict):
        prompt_block = agent_block["prompt"] = {}
    prompt_block["prompt"] = True
    return {"platform_settings": {"overrides": overrides}}


def _formats_verdict(metadata: dict[str, Any]) -> tuple[bool, str]:
    """Whether LIA can serve the agent's audio formats, in words when it cannot."""
    input_format = str(metadata.get("user_input_audio_format") or ELEVENLABS_LIVE_INPUT_FORMAT)
    output_format = str(metadata.get("agent_output_audio_format") or "")
    if input_format != ELEVENLABS_LIVE_INPUT_FORMAT:
        return False, (
            f"the agent expects {input_format} input; set its user input format to "
            f"{ELEVENLABS_LIVE_INPUT_FORMAT} on the portal"
        )
    if not output_format.startswith(ELEVENLABS_LIVE_OUTPUT_FORMAT_PREFIX):
        return False, (
            f"the agent speaks {output_format or 'an unknown format'}; set its output "
            "format to a PCM rate on the portal"
        )
    return True, "ok"


def output_rate_of(output_format: str) -> int | None:
    """The sample rate a ``pcm_<rate>`` output format names, or None."""
    if not output_format.startswith(ELEVENLABS_LIVE_OUTPUT_FORMAT_PREFIX):
        return None
    try:
        return int(output_format[len(ELEVENLABS_LIVE_OUTPUT_FORMAT_PREFIX) :])
    except ValueError:
        return None


__all__ = [
    "INITIATION_METADATA_TYPE",
    "INITIATION_TYPE",
    "ElevenLabsLiveProvider",
    "ElevenLabsLiveRefused",
    "client_tool_body",
    "declarations_of",
    "output_rate_of",
    "tools_fingerprint",
]
