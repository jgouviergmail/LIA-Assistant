"""What a live provider must offer LIA (ADR-299, spec A2): a session, not a wire.

The two providers the design names share a shape — a session opened by the
browser on a short-lived credential LIA mints, a mandate, ONE delegation
function, a transcription, interruptions — and nothing of the wire protocol
(JSON over a raw WebSocket for Gemini; WebRTC and a data channel for OpenAI).
This protocol therefore describes the SESSION and leaves the wire to the
browser transport of each provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from src.domains.connectors.models import ConnectorType
from src.domains.live.preferences import LivePreferences, read_live_preferences
from src.domains.live.schemas import LiveModel, LiveVendorBill, LiveVoicesResponse


@dataclass(frozen=True, slots=True)
class LiveCredential:
    """The short-lived secret the browser opens ONE connection with."""

    name: str
    expires_at: datetime
    connect_deadline_at: datetime


@dataclass(frozen=True, slots=True)
class LiveModelCapabilities:
    """What ONE model of a provider can do — read by the browser, never a provider id.

    Attributes:
        async_delegation: The model keeps talking while a delegated request
            runs (documented 2026-09-19: unsupported on Gemini 3.1 Flash Live,
            which waits for the tool response).
        delivery_scheduling: The provider accepts a delivery mode on a result
            (Gemini ``scheduling`` — refused on Extended Thinking).
        reports_idle: The provider says when the task is done
            (``interactionStatus``): a ``turnComplete`` per utterance is then
            not the end of anything.
        cancels_on_interruption: The provider cancels pending delegations when
            the person interrupts the model (Gemini); the client cancels alone
            otherwise (GPT-Live).
        configurable_vad: The setup carries the person's end-of-speech and
            interruption reflexes.
        resumes: A dropped connection can resume with a handle.
        thinking: A thinking level is REQUIRED (the ADR-245 ladder is non-empty).
        direct_tools: The model can hold LIA's read-only tools itself — a
            function-calling wire with declarations (Gemini, ElevenLabs);
            false where the wire carries no tool schema (GPT-Live's native
            delegation). Gates the DIRECT session (ADR-300 wave 4).
    """

    async_delegation: bool
    delivery_scheduling: bool
    reports_idle: bool
    cancels_on_interruption: bool
    configurable_vad: bool
    resumes: bool
    thinking: bool
    #: The wire carries a tool schema: a DIRECT session can declare LIA's
    #: read-only tools on it (ADR-300 wave 4).
    direct_tools: bool = False
    #: The voice — and every reflex — is administered on the provider's portal,
    #: for the agent: the form offers no voice and no sample (ADR-300 wave 4).
    portal_voice: bool = False
    #: The platform prices nothing of a session on this model (the provider's
    #: ``billing`` is ``vendor``): the meter shows the clock alone, no spend
    #: ceiling can be set, and the vendor's own bill comes with the end.
    vendor_billed: bool = False


@dataclass(frozen=True, slots=True)
class LiveSetupInputs:
    """Everything a provider renders into its session setup.

    Attributes:
        tool_declaration: The delegation function (``send_to_lia``), or None
            on a DIRECT session, which delegates nothing.
        direct_tools: The read-only tools a DIRECT session declares (ADR-300
            wave 4), provider-neutral declarations; empty on a delegated one.
    """

    model: str
    voice: str
    thinking_level: str | None
    system_instruction: str
    tool_declaration: dict[str, Any] | None
    preferences: LivePreferences
    trigger_tokens: int
    target_tokens: int
    direct_tools: tuple[dict[str, Any], ...] = ()


def setup_inputs_to_dict(inputs: LiveSetupInputs) -> dict[str, Any]:
    """The setup inputs as the session record stores them (JSON-safe)."""
    payload = asdict(inputs)
    payload["preferences"] = inputs.preferences.model_dump()
    return payload


def setup_inputs_from_dict(record_inputs: dict[str, Any]) -> LiveSetupInputs:
    """Rebuild the setup inputs a session record kept (for a reconnection).

    The pair with :func:`setup_inputs_to_dict` is pinned by a round-trip
    equality test over every field: a DIRECT session keeps no delegation
    declaration and its tools instead.
    """
    declaration = record_inputs.get("tool_declaration")
    return LiveSetupInputs(
        model=str(record_inputs["model"]),
        voice=str(record_inputs["voice"]),
        thinking_level=record_inputs.get("thinking_level"),
        system_instruction=str(record_inputs["system_instruction"]),
        tool_declaration=dict(declaration) if declaration is not None else None,
        preferences=read_live_preferences(record_inputs.get("preferences")),
        trigger_tokens=int(record_inputs["trigger_tokens"]),
        target_tokens=int(record_inputs["target_tokens"]),
        direct_tools=tuple(dict(tool) for tool in record_inputs.get("direct_tools") or ()),
    )


#: How the browser opens the connection: with the provider's own credential
#: (``token`` — Gemini's ephemeral token), or by handing LIA an SDP offer that
#: the API exchanges on the person's key (``offer`` — GPT-Live over WebRTC).
LiveConnection = Literal["token", "offer"]
#: Who prices a session's meter: the platform's tariff table, or the vendor alone.
LiveBilling = Literal["tariff", "vendor"]
#: How the model delegates: through a declared function the browser answers
#: (``tool`` — Gemini's ``send_to_lia``), or by its own act the browser is
#: told of (``native`` — GPT-Live's ``session.delegation.created``).
LiveDelegationWire = Literal["tool", "native"]


class LiveProvider(Protocol):
    """One provider of live sessions."""

    provider_id: str
    connector_type: ConnectorType
    connection: LiveConnection
    delegation_wire: LiveDelegationWire
    #: The preselection of the connector form — a default, not a claim.
    default_model: str
    #: Who prices the session's meter. ``tariff``: the platform's tariff table
    #: names the model (Gemini, GPT-Live) and the banner's indicative meter
    #: multiplies the provider's usage reports by it — a model with no row never
    #: starts. ``vendor``: the platform prices NOTHING of it (ElevenLabs Agents:
    #: the agents API on the person's own key, its own price grid), the meter
    #: shows the clock alone and the vendor's own bill is read at the end
    #: (``VendorBilling``) — owner rule 2026-09-20: what runs on the person's
    #: key is displayed from the vendor and never priced by us.
    billing: LiveBilling

    async def list_models(self, api_key: str) -> list[LiveModel]:
        """The conversational live models the key may open, with their ladders."""
        ...

    async def list_voices(self, api_key: str) -> LiveVoicesResponse:
        """The voices, with where the list comes from."""
        ...

    def knows_voice(self, name: str) -> bool:
        """Whether ``name`` is one of the voices the provider is known to serve."""
        ...

    def thinking_levels_of(self, model: str) -> tuple[str, ...]:
        """The thinking ladder the model offers (empty: the model reasons on its own terms)."""
        ...

    def capabilities_of(self, model: str) -> LiveModelCapabilities:
        """What the model can do, from the provider's documented rules."""
        ...

    def build_setup(self, inputs: LiveSetupInputs) -> dict[str, Any]:
        """The setup message the browser sends first, as documented JSON."""
        ...

    async def mint(
        self,
        api_key: str,
        inputs: LiveSetupInputs,
        *,
        expires_at: datetime,
        connect_deadline_at: datetime,
    ) -> LiveCredential:
        """A single-use credential for one connection, locked to the model."""
        ...

    async def sample_voice(self, api_key: str, voice: str, text: str) -> bytes:
        """A short utterance in ``voice``, as 16-bit mono PCM at ``sample_rate``, on the person's key."""
        ...

    @property
    def sample_rate(self) -> int:
        """The sample rate of what ``sample_voice`` returns."""
        ...

    async def probe(
        self, api_key: str, inputs: LiveSetupInputs, *, timeout: float
    ) -> tuple[bool, str]:
        """Open a session on the REAL setup and close it: (accepted, the provider's words).

        The probe replays what a session would send — model, thinking level,
        the delegation tool — because the provider judges the pair, not the
        model alone (measured 2026-09-18: Extended Thinking refuses a setup
        without a thinking level).
        """
        ...


@runtime_checkable
class VendorBilling(Protocol):
    """A provider that states, once a conversation ended, what IT billed the person for it.

    Read on the person's key and SHOWN to them — never recorded: the platform
    bills nothing of a session on their own key (``cost_bearers``), and a
    figure it re-bills nobody for belongs in no ledger. A ``vendor``-billed
    provider owes this: it is the only figure the person will ever see.
    """

    async def conversation_bill(
        self, api_key: str, conversation_id: str, *, timeout: float
    ) -> LiveVendorBill | None:
        """The vendor's bill of one conversation, or None when it cannot be read."""
        ...


@runtime_checkable
class AgentSyncing(Protocol):
    """A provider whose sessions run on an AGENT of the person's that LIA must prepare.

    The tools a session declares are attached to the agent, never named per
    session (measured on the phone, ADR-290: the vendor refuses ``tool_ids``
    inside an override), and a per-session prompt needs the agent's
    permission. What LIA holds on the agent is kept on the connector's
    metadata, so the sync is idempotent and the metadata a NEW dict.
    """

    async def sync_agent(
        self, api_key: str, metadata: dict[str, Any], inputs: LiveSetupInputs
    ) -> dict[str, Any]:
        """Prepare the agent for THIS session's setup; returns the metadata to store."""
        ...


@runtime_checkable
class OfferExchanging(Protocol):
    """A provider whose ``connection`` is ``offer``: it exchanges the browser's SDP."""

    async def exchange_offer(
        self, api_key: str, inputs: LiveSetupInputs, offer_sdp: str, *, timeout: float
    ) -> str:
        """The provider's SDP answer for the browser's offer, on the person's key."""
        ...
