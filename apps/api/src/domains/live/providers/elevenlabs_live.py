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

import asyncio
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
    LIVE_DELEGATION_TOOL_NAME,
    TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY,
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
    ToolRelease,
)
from src.domains.telephony.workspace_tools import (
    VENDOR_FAILURES,
    agent_tool_ids,
    create_tools,
    read_workspace_tools,
    repair_set,
)
from src.domains.voice.cue_prompt import palette
from src.domains.voice.expressive_cues import CueDialect, dialect_named
from src.domains.voice_sessions.expression import (
    PERSON_CUES,
    agent_dialect,
    expression_of,
    palette_block,
)
from src.domains.voice_sessions.mandate import neutralise_vendor_syntax
from src.infrastructure.llm.providers.elevenlabs_live_listing import list_agents
from src.infrastructure.observability.metrics_live import (
    live_agent_tools_swept_total,
    live_cue_palette_synced_total,
)

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


def tools_fingerprint(bodies: list[dict[str, Any]]) -> str:
    """One digest of everything the workspace must hold for a set, in its order.

    Read on the BODIES the workspace is sent, as the phone does: a changed
    description, a parameter, a timeout an operator raised — any byte LIA sends —
    names another set, which is created and replaces the old one.
    """
    canonical = json.dumps(bodies, sort_keys=True, separators=(",", ":"))
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


def set_bodies(inputs: LiveSetupInputs) -> list[dict[str, Any]]:
    """The workspace bodies of a setup's set, in the declarations' order.

    The timeout is the wire's: the delegation waits for a whole chat turn
    (``LIVE_DELEGATION_TIMEOUT_SECONDS``), a direct lookup for one tool
    (``TELEPHONY_LIVE_TOOL_TIMEOUT_SECONDS``).
    """
    timeout = (
        settings.live_delegation_timeout_seconds
        if inputs.tool_declaration is not None
        else settings.telephony_live_tool_timeout_seconds
    )
    return [client_tool_body(d, timeout_seconds=timeout) for d in declarations_of(inputs)]


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


async def _hold_set(
    client: ElevenLabsAgentsClient,
    recorded: list[str] | None,
    bodies: list[dict[str, Any]],
) -> tuple[list[str], list[str], dict[str, dict[str, Any]] | None]:
    """The set this setup needs, exactly as LIA sends it, in the workspace.

    A set never recorded (or recorded under another shape) is created whole —
    exact by construction. A recorded one is held against what the workspace
    serves today: a tool edited on the portal is rewritten in place, a lost one
    re-created (owner decision 2026-11-11: never an agent with tools out of date
    or incomplete); a workspace that cannot be read refuses the start.

    Returns:
        The set's ids, the ids created by this call (removed if the attach is
        refused), and the client tools the workspace served (None when no
        listing was read).
    """
    if recorded is None or len(recorded) != len(bodies):
        created = await create_tools(client, bodies)
        logger.info("elevenlabs_live_tools_created", tool_count=len(created))
        return created, created, None
    listing = await read_workspace_tools(client, "client")
    repair = await repair_set(client, recorded, bodies, listing, surface="live")
    return list(repair.ids), list(repair.recreated), listing


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

    async def expression_dialect(self, api_key: str, model: str) -> CueDialect:
        """The cues the AGENT's speaking engine performs, read from its stored config.

        ``model`` is the agent's id. A realtime model, or a v3/v4 TTS whose
        expressive mode is on, performs audio tags (ADR-373); anything else
        speaks words alone.
        """
        return agent_dialect(await self._client(api_key).get_agent(model))

    def build_setup(self, inputs: LiveSetupInputs) -> dict[str, Any]:
        """The initiation frame: LIA's prompt over the agent's, and an empty greeting.

        The tools are not here — they are attached to the agent by
        :meth:`sync_agent` (the vendor refuses ``tool_ids`` in an override),
        which also grants the two overrides this frame carries. The language,
        the voice and the reflexes stay the portal's.
        No ``source_info``: measured 2026-09-19 on the owner's agent, the field
        is validated against the vendor's OWN SDK names (``js_sdk`` …) and any
        other word closes the conversation 1008 — AFTER the metadata, so the
        session opened and died at once; omitted, the conversation stays open.
        The vendor reads ``{{name}}`` in a prompt as a dynamic variable it must be
        given: LIA renders the whole prompt itself, so a doubled brace in it can
        only come from a value (a personality, a memory, the context) and is
        neutralised, as on the phone.
        """
        return {
            "type": INITIATION_TYPE,
            "conversation_config_override": {
                # An EMPTY greeting (ADR-373): the portal's canned first sentence is
                # the one a personality could never reach; empty, the agent lets the
                # person speak first (the vendor's override contract), and every word
                # it says comes from the mandate.
                "agent": {
                    "prompt": {"prompt": neutralise_vendor_syntax(inputs.system_instruction)},
                    "first_message": "",
                }
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
        """Prepare the person's agent for this session: permissions, expression, tools.

        Idempotent by what the AGENT holds, read once: the two overrides the
        frame carries (the prompt and the greeting) are granted when the agent
        does not allow them — merged into the agent's OWN overrides block,
        never replacing it, the vendor replacing omitted booleans with false —
        and a refusal there refuses the start (the vendor would refuse the
        frame). The expression LIA owns (ADR-373) is written when it drifted —
        the vendor's default persona dropped, and on an engine that performs
        cues, LIA's palette — best effort, part by part: a refusal costs that
        part, never the session.

        The agent's tools are LIA's referential (ADR-373): its ``tool_ids``
        are set to EXACTLY this session's set, recorded once per fingerprint
        of the bodies LIA sends (:func:`tools_fingerprint`) — the person's own
        tools and LIA's other set are detached, never deleted (a delegated
        session never sees the read-only tools, and vice versa). Before the
        agent is handed a recorded set, the set is held against what the
        workspace serves (:func:`_hold_set`, amendment 2026-11-11): every
        opening — start, wake, reconnection — finds the tools exactly as LIA
        sends them today, or does not open. A new fingerprint of a KIND (a
        renamed description, a tool a release added, a raised timeout) retires
        the set that kind held before, so at most one set per kind lives in the
        workspace. Once detached, what LIA left on this agent is released
        without force (:func:`_sweep`). A refused attach deletes the tools
        this call created (the metadata naming them is stored by the caller,
        once this returns) and re-raises.

        Args:
            api_key: The person's key.
            metadata: The connector's metadata as stored.
            inputs: The session's setup inputs (the agent id, the declarations).

        Returns:
            The metadata to store — a NEW dict (the JSONB rule).
        """
        client = self._client(api_key)
        agent_id = inputs.model
        # The retired « granted » marker is dropped: the agent itself is read.
        updated: dict[str, Any] = {
            key: value
            for key, value in metadata.items()
            if key != ELEVENLABS_LIVE_OVERRIDE_METADATA_KEY
        }
        agent = await client.get_agent(agent_id)
        await _grant_overrides(client, agent_id, agent)
        await _write_expression(client, agent_id, agent, dialect_named(inputs.cue_dialect))
        bodies = set_bodies(inputs)
        fingerprint = tools_fingerprint(bodies)
        held, kinds = _held_sets(updated)
        recorded = held.get(fingerprint)
        # A set recorded under another shape is replaced whole: its old ids are
        # released below like a retired set's.
        reshaped = recorded if recorded is not None and len(recorded) != len(bodies) else []
        held[fingerprint], created, listing = await _hold_set(client, recorded, bodies)
        # The set this kind held before, when it is another one: released
        # below, once the agent no longer names it.
        retired_ids = [*_retire_previous(held, kinds, set_kind_of(inputs), fingerprint), *reshaped]
        carried = agent_tool_ids(agent)
        if held[fingerprint] != carried:
            try:
                await client.set_agent_tool_ids(agent_id, held[fingerprint])
            except VENDOR_FAILURES:
                # The caller stores the metadata only once this returns: a tool
                # created by THIS call would be named by nothing, and the next
                # start would create it again — one orphan per attempt.
                for tool_id in created:
                    await client.delete_tool(tool_id)
                raise
        updated[ELEVENLABS_LIVE_TOOLS_METADATA_KEY] = held
        updated[ELEVENLABS_LIVE_TOOL_KINDS_METADATA_KEY] = kinds
        current = _lia_tool_ids(updated)
        await _sweep(
            client,
            [
                tool_id
                for tool_id in dict.fromkeys([*carried, *retired_ids])
                if tool_id not in current
            ],
            recorded=set(retired_ids),
            listing=listing,
        )
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
            client = self._client(api_key)
            # The frame replayed is the REAL one: the agent must allow what it
            # overrides before the conversation opens, or the vendor refuses it.
            await _grant_overrides(client, inputs.model, await client.get_agent(inputs.model))
            url = await client.signed_url(inputs.model)
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


def _lia_tool_names() -> frozenset[str]:
    """The names LIA gives the client tools it creates: the delegation, every live lookup."""
    from src.domains.agents.telephony.live_tools import live_tool_specs

    return frozenset({LIVE_DELEGATION_TOOL_NAME, *(spec.name for spec in live_tool_specs())})


def _named_as_lia(config: dict[str, Any], names: frozenset[str]) -> bool:
    """Whether a workspace tool's config is a CLIENT tool named as one of LIA's."""
    return config.get("type") == "client" and config.get("name") in names


async def _sweep(
    client: ElevenLabsAgentsClient,
    candidates: list[str],
    *,
    recorded: set[str],
    listing: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Release from the workspace what LIA left on this agent, never what another agent uses.

    ``candidates`` are detached by now: the ids the agent carried outside
    LIA's current sets, and the set this call retired. One is LIA's when LIA
    recorded it, or when its workspace tool is a CLIENT tool named as one of
    LIA's — an orphan of an earlier release, or of a sibling instance on the
    same key; the person's own tools stay in their workspace. Each is deleted
    WITHOUT force: a tool another agent still uses is kept and counted. Scoped
    to this agent — a workspace-wide scan by name would free the set a
    sibling instance holds detached. The listing the set was verified on
    serves here too; read otherwise, best effort: an unreadable workspace
    skips the sweep, never the session.
    """
    if not candidates:
        return
    if listing is None:
        try:
            listing = await read_workspace_tools(client, "client")
        except VENDOR_FAILURES as exc:
            logger.warning("elevenlabs_live_tool_sweep_skipped", error_type=type(exc).__name__)
            return
    names = _lia_tool_names()
    doomed = [
        tool_id
        for tool_id in candidates
        if tool_id in listing and (tool_id in recorded or _named_as_lia(listing[tool_id], names))
    ]
    outcomes = await _release_all(client, doomed)
    for outcome in outcomes:
        live_agent_tools_swept_total.labels(outcome=outcome).inc()
    if doomed:
        logger.info(
            "elevenlabs_live_tools_swept",
            freed=outcomes.count("freed"),
            in_use=outcomes.count("in_use"),
            refused=outcomes.count("refused"),
            left=len(candidates) - len(doomed),
        )


async def _release_all(client: ElevenLabsAgentsClient, tool_ids: list[str]) -> list[ToolRelease]:
    """Release each tool, concurrently under the provisioning bound, outcomes in order."""
    outcomes: dict[int, ToolRelease] = {}
    gate = asyncio.Semaphore(TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY)

    async def _release(index: int, tool_id: str) -> None:
        async with gate:
            outcomes[index] = await client.release_tool(tool_id)

    async with asyncio.TaskGroup() as group:
        for index, tool_id in enumerate(tool_ids):
            group.create_task(_release(index, tool_id))
    return [outcomes[index] for index in range(len(tool_ids))]


def _child(parent: dict[str, Any], key: str) -> dict[str, Any]:
    """``parent[key]`` as a dict, created (or replaced, when not a dict) in place."""
    value = parent.get(key)
    if not isinstance(value, dict):
        value = parent[key] = {}
    return value


def _override_grant(agent: dict[str, Any]) -> dict[str, Any] | None:
    """The PATCH granting the two overrides LIA's frame carries, or None when both are allowed.

    The prompt and the greeting (``build_setup``). The vendor replaces every
    omitted boolean of the block with false (measured on the phone,
    2026-09-16), so the block is read from the agent and sent back whole with
    the two fields LIA needs set — the person's own permissions survive.
    """
    stored = _mapping(_mapping(agent.get("platform_settings")).get("overrides"))
    allowed = _mapping(_mapping(stored.get("conversation_config_override")).get("agent"))
    if (
        _mapping(allowed.get("prompt")).get("prompt") is True
        and allowed.get("first_message") is True
    ):
        return None
    overrides: dict[str, Any] = json.loads(json.dumps(stored))  # a deep copy
    agent_block = _child(_child(overrides, "conversation_config_override"), "agent")
    _child(agent_block, "prompt")["prompt"] = True
    agent_block["first_message"] = True
    return {"platform_settings": {"overrides": overrides}}


async def _grant_overrides(
    client: ElevenLabsAgentsClient, agent_id: str, agent: dict[str, Any]
) -> None:
    """Allow what the frame overrides; a refusal propagates (the frame would be refused)."""
    grant = _override_grant(agent)
    if grant is not None:
        await client.patch_agent(agent_id, grant)


def _expression_patches(
    agent: dict[str, Any], dialect: CueDialect
) -> list[tuple[str, dict[str, Any]]]:
    """What LIA writes so the agent's voice is the personality's (ADR-373), part by part.

    The vendor's default persona is dropped (``ignore_default_personality``),
    whatever the engine: its « helpful » lines would fight the personality
    the prompt carries. On an engine that performs cues, LIA's palette
    replaces the agent's: each tag described by what it sounds like — a
    description written as a trigger was obeyed as one (measured
    2026-11-07). Nothing LIA does not own changes: the speaking block
    travels whole, as stored (:func:`palette_block`).

    Returns:
        ``(part, conversation_config PATCH)`` for each part that drifted — the
        persona, then the palette: two writes, so a vendor refusing the
        speaking block never costs the persona.
    """
    patches: list[tuple[str, dict[str, Any]]] = []
    config = _mapping(agent.get("conversation_config"))
    prompt = _mapping(_mapping(config.get("agent")).get("prompt"))
    if prompt.get("ignore_default_personality") is not True:
        persona = {"agent": {"prompt": {"ignore_default_personality": True}}}
        patches.append(("persona", {"conversation_config": persona}))
    if expression_of(dialect) == "cues":
        tts = palette_block(agent, palette(dialect, PERSON_CUES))
        if tts is not None:
            patches.append(("palette", {"conversation_config": {"tts": tts}}))
    return patches


async def _write_expression(
    client: ElevenLabsAgentsClient, agent_id: str, agent: dict[str, Any], dialect: CueDialect
) -> None:
    """Write :func:`_expression_patches`, best effort: a refusal costs its part, never the session."""
    for part, body in _expression_patches(agent, dialect):
        try:
            await client.patch_agent(agent_id, body)
        except ElevenLabsAgentsError as exc:
            logger.warning(
                "elevenlabs_live_expression_sync_failed", part=part, status_code=exc.status_code
            )
            outcome = "refused"
        else:
            outcome = "written"
        if part == "palette":
            live_cue_palette_synced_total.labels(surface="live", outcome=outcome).inc()


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
