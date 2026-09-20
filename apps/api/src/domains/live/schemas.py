"""Wire shapes of the live mode (ADR-299).

Mirrored by ``apps/web/src/lib/live/types.ts`` — a change on one side is a
change on both.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.constants import (
    CHAT_MESSAGE_MAX_LENGTH,
    LIVE_END_DETAIL_MAX_CHARS,
    LIVE_SESSION_BUDGET_EUR_MAX,
    LIVE_TOOL_CALL_MAX_ARGUMENTS,
)
from src.domains.live.model_settings import LiveModelSettings
from src.domains.live.preferences import LivePreferences
from src.domains.voice_sessions.session import VoiceSessionMode
from src.domains.voice_sessions.summary import VoiceSessionOutcome, VoiceSessionUsage

#: How a session runs: the voice DELEGATES every request to the chat, or holds
#: LIA's read-only tools DIRECTLY and never acts (ADR-300 wave 4). The
#: vocabulary is the voice session's (ADR-301), shared with the phone.
LiveSessionMode = VoiceSessionMode

LiveOutcome = VoiceSessionOutcome


class LiveModelCapabilitiesResponse(BaseModel):
    """What one model can do — the browser reads THIS, never a provider id (spec A11)."""

    async_delegation: bool = Field(
        ..., description="The model keeps talking while a delegated request runs."
    )
    delivery_scheduling: bool = Field(
        ..., description="A result may carry a delivery mode (now / when idle / silent)."
    )
    reports_idle: bool = Field(
        ..., description="The provider says when its task is done (interactionStatus)."
    )
    cancels_on_interruption: bool = Field(
        ..., description="The provider cancels pending delegations when the person interrupts."
    )
    configurable_vad: bool = Field(
        ..., description="The setup carries the end-of-speech and interruption reflexes."
    )
    resumes: bool = Field(..., description="A dropped connection can resume with a handle.")
    thinking: bool = Field(..., description="A thinking level is required by the model.")
    direct_tools: bool = Field(
        False,
        description=(
            "The model can hold LIA's read-only tools itself (a function-calling wire): "
            "the DIRECT session is offered iff true (ADR-300 wave 4)."
        ),
    )
    portal_voice: bool = Field(
        False,
        description=(
            "The voice and every reflex are the provider portal's, for the agent: the "
            "settings offer no voice and no sample (ADR-300 wave 4)."
        ),
    )
    vendor_billed: bool = Field(
        False,
        description=(
            "The platform prices nothing of a session on this model: the meter shows the "
            "clock alone, no spend ceiling can be set, the vendor's own bill comes at the end."
        ),
    )


class LiveModel(BaseModel):
    """A model the person's key may open a live session on."""

    provider: str = Field(..., description="The live provider id the model belongs to.")
    name: str = Field(..., description="Provider model id, without the models/ prefix.")
    label: str | None = Field(
        None,
        description=(
            "A human name the provider gives the model (an agent's name); None when "
            "the id is the name."
        ),
    )
    voice_model: str | None = Field(
        None,
        description=(
            "For an agent: the voice model its configuration names (information — the "
            "vendor prices it, the platform never does); None when the model IS the voice."
        ),
    )
    llm: str | None = Field(
        None,
        description=(
            "For an agent: the LLM its configuration names (information — billed by the "
            "vendor); None when the model IS the LLM."
        ),
    )
    thinking_levels: list[str] = Field(
        default_factory=list,
        description="Levels the person may pick (empty: the model reasons on its own terms).",
    )
    capabilities: LiveModelCapabilitiesResponse = Field(
        ..., description="What the model can do, from the provider's documented rules."
    )


class LiveModelsResponse(BaseModel):
    """The conversational live models of a key — those the tariff table declares."""

    models: list[LiveModel]
    default_model: str = Field(
        ..., description="Preselection in the form — a default, not a claim."
    )
    unpriced: list[str] = Field(
        default_factory=list,
        description=(
            "Models the key discovers but the tariff table does not declare (ADR-300 "
            "wave 3): named, never offered — an administrator declares them under LLM pricing."
        ),
    )


class LiveRates(BaseModel):
    """The tariff of THIS session's model, for the browser's own count (ADR-300 wave 3).

    Published, never enforced: the session runs on the person's key, the
    platform records nothing of it, and the meter it feeds is indicative.
    """

    pricing_unit: str = Field(
        ..., description="per_1m_tokens (text and audio rates) or per_audio_minute/hour."
    )
    input_unit_price: float = Field(..., ge=0, description="USD per the unit, text input.")
    output_unit_price: float = Field(..., ge=0, description="USD per the unit, text output.")
    audio_input_unit_price: float | None = Field(
        None, ge=0, description="USD per 1M audio input tokens; None = not declared."
    )
    audio_output_unit_price: float | None = Field(
        None, ge=0, description="USD per 1M audio output tokens; None = not declared."
    )
    usd_eur_rate: float = Field(..., gt=0, description="The cached USD→EUR rate.")


class LiveVendorBill(BaseModel):
    """What the provider billed the person for the session, in ITS words — shown, never recorded.

    Read on the person's key once the session ended; the platform re-bills
    nothing of it, so it reaches no ledger, no card and no statistic.
    """

    provider: str = Field(..., description="The live provider id the bill comes from.")
    cost_usd: float | None = Field(None, ge=0, description="The vendor's total, in USD.")
    credits: int | None = Field(None, ge=0, description="The vendor's total, in its credits.")
    llm_credits: int | None = Field(None, ge=0, description="The LLM's share, in credits.")
    call_credits: int | None = Field(None, ge=0, description="The call's share, in credits.")
    platform_credits: int | None = Field(
        None, ge=0, description="The platform's share, in credits."
    )
    llm_model: str | None = Field(None, description="The LLM(s) the vendor charged for.")
    tts_model: str | None = Field(None, description="The voice model the vendor charged for.")
    duration_seconds: int | None = Field(None, ge=0, description="The vendor's own duration.")


class LiveDiscoverRequest(BaseModel):
    """Discover the models of a key BEFORE the connector exists."""

    provider: str = Field("gemini", max_length=32, description="The live provider id.")
    api_key: str = Field(
        ..., min_length=8, max_length=512, description="The provider key, verified by the listing."
    )


class LiveVoice(BaseModel):
    """One prebuilt voice."""

    name: str
    characteristic: str = Field("", description="The provider's own one-word description.")


class LiveVoiceSampleRequest(BaseModel):
    """Hear a voice before choosing it (wave 2 spec A4), on the person's key."""

    provider: str = Field("gemini", max_length=32, description="The live provider id.")
    voice: str = Field(..., min_length=1, max_length=64, description="A published voice name.")
    api_key: str | None = Field(
        None,
        min_length=8,
        max_length=512,
        description="The key the form holds (before the connector exists); the stored one otherwise.",
    )


class LiveVoiceSampleResponse(BaseModel):
    """A short WAV the browser plays as is."""

    audio_base64: str = Field(..., description="The WAV file, base64.")
    sample_rate: int = Field(..., description="Samples per second of the PCM inside.")
    format: Literal["wav"] = Field("wav", description="The container: WAV, 16-bit mono.")


class LiveVoicesResponse(BaseModel):
    """The voices a provider offers, with where the list comes from."""

    provider: str = Field(
        ...,
        description=(
            "The live provider the voices belong to — the settings list ONE provider's "
            "voices at a time and must not hand a stale answer to another (wave 2 A10)."
        ),
    )
    voices: list[LiveVoice]
    provenance: Literal["discovered", "published", "portal"] = Field(
        ...,
        description=(
            "discovered = a listing endpoint answered; published = the vendored list "
            "(measured 2026-09-18: Gemini offers no listing and silently accepts an "
            "unknown name, so the form offers the list and refuses a name off it); "
            "portal = the voice is the agent's own, administered on the provider portal "
            "(ADR-300 wave 4), so the list is empty by design."
        ),
    )
    published_at: str | None = Field(
        None, description="Date of the vendored list (published only)."
    )
    source: str | None = Field(None, description="Where the vendored list was read from.")


class LiveConnectorSettings(LiveModelSettings):
    """The current model of a connector and its own settings (stored in connector_metadata).

    A PUT carries every field: the model named becomes the current one and its
    settings are remembered beside the other models' (owner decision 2026-09-19:
    a model's voice and durations survive a switch to another model). The
    budget is the CONNECTOR's, not a model's (owner decision 2026-09-19:
    provider granularity).
    """

    model: str = Field(
        ..., min_length=1, max_length=120, description="Provider model id the sessions open on."
    )
    session_budget_eur: float | None = Field(
        None,
        gt=0,
        le=LIVE_SESSION_BUDGET_EUR_MAX,
        description=(
            "Optional spend ceiling per session, in euros on the person's own key: the "
            "browser's indicative meter ends the session when it is reached (ADR-300 "
            "wave 3). None = no ceiling."
        ),
    )


class LiveConnectorActivateRequest(BaseModel):
    """Activate a live connector: the provider, the key, the person's first choices.

    The durations are not asked here: a new connector runs under the instance
    defaults until the person tunes them per model in the Live mode settings.
    """

    provider: str = Field("gemini", max_length=32, description="The live provider id.")
    model: str = Field(
        ..., min_length=1, max_length=120, description="Provider model id the sessions open on."
    )
    voice: str = Field(
        ..., min_length=1, max_length=64, description="A name of the provider's published list."
    )
    thinking_level: str | None = Field(
        None, max_length=16, description="A level of the model's ADR-245 ladder, or none."
    )
    api_key: str = Field(
        ..., min_length=8, max_length=512, description="The provider key, stored encrypted."
    )


class LiveConnectorResponse(BaseModel):
    """One live connector as the settings show it."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    connector_type: str
    status: str
    settings: LiveConnectorSettings
    model_settings: dict[str, LiveModelSettings] = Field(
        default_factory=dict,
        description=(
            "Every model this connector remembers, by model id — the settings form reads the "
            "voice and durations of the model the person switches to."
        ),
    )
    functionally_verified: bool
    capabilities: LiveModelCapabilitiesResponse = Field(
        ...,
        description="What the connector's chosen model can do (the settings hide what it cannot).",
    )
    active: bool = Field(
        ..., description="Whether the sessions open on THIS provider (the account's choice)."
    )


class LiveConnectorsResponse(BaseModel):
    """Every active live connector of the account, and which one the sessions open on."""

    connectors: list[LiveConnectorResponse]
    active_provider: str | None = Field(
        None, description="The provider id the sessions open on; None without a connector."
    )


class LiveDurationBounds(BaseModel):
    """The range a per-model duration may take, besides the unlimited value."""

    min: int
    max: int


class LiveConfigResponse(BaseModel):
    """Every bound the client honours, published because it is enforced (ADR-184)."""

    session_max_minutes: int = Field(
        ..., description="The instance default for a model whose connector stores none."
    )
    session_max_bounds: LiveDurationBounds
    idle_timeout_bounds: LiveDurationBounds
    session_budget_eur_max: float = Field(
        ..., description="The most a per-session spend ceiling may be set to (euros)."
    )
    unlimited_value: int = Field(
        ..., description="The per-model duration that means « no limit » (0)."
    )
    extension_minutes: int = Field(..., description="Minutes one explicit extension adds.")
    extension_prompt_seconds: int = Field(
        ..., description="Seconds before the cap at which the extension is offered."
    )
    connect_window_seconds: int
    idle_timeout_seconds: int = Field(
        ..., description="The instance default for a model whose connector stores none."
    )
    hidden_grace_seconds: int
    delegation_timeout_seconds: int
    delegation_result_max_tokens: int
    delegation_tool_name: str
    turn_text_max_chars: int
    tone_lines: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "One delivery note per register of the tone vocabulary (ADR-253): the bridge "
            "hands the voice the note of the register the answer declared."
        ),
    )
    delegation_lines: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "The lines a delegation bridge hands the voice as tool results "
            "(timed_out, result_cut, superseded, empty_request, and the server-side "
            "bridge's busy, quota_blocked, failed — ADR-301), from live_lines.txt."
        ),
    )
    direct_lines: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "The lines the browser answers a DIRECT session's model with itself "
            "(lookup_failed), from live_direct_lines.txt (ADR-300 wave 4)."
        ),
    )


class LiveCredentialResponse(BaseModel):
    """A credential for ONE connection of a session — the first, or a reconnection.

    Measured 2026-09-18: a ``uses: 1`` token cannot reopen its session (the
    provider answers « Token has been used too many times »), so every
    reconnection mints a fresh one for the SAME session record.
    """

    credential: str = Field(
        ...,
        description=(
            "Single use: the provider's ephemeral token (connection = token), or LIA's own "
            "nonce the browser hands back with its SDP offer (connection = offer)."
        ),
    )
    credential_expires_at: datetime
    connect_deadline_at: datetime
    connection: Literal["token", "offer"] = Field(
        ...,
        description=(
            "How the browser opens the connection: itself, with the credential (token), "
            "or through POST /live/sessions/{id}/offer, which exchanges its SDP on the "
            "person's key (offer)."
        ),
    )
    setup: dict[str, Any] = Field(
        ..., description="The provider setup the client replays verbatim (token connections)."
    )


class LiveSessionStartRequest(BaseModel):
    """``POST /live/sessions`` — how the session should run."""

    mode: LiveSessionMode = Field(
        "delegated",
        description=(
            "delegated: every request goes to the chat (HITL, actions, registers); "
            "direct: the voice reads LIA's tools itself and never acts (ADR-300 wave 4)."
        ),
    )


class LiveSessionStartResponse(LiveCredentialResponse):
    """``POST /live/sessions`` — everything the browser needs to open the session."""

    session_id: str
    provider: str
    model: str
    run_id: str
    mode: LiveSessionMode = Field(
        "delegated", description="How this session runs; the client routes tool calls on it."
    )
    expires_at: datetime = Field(
        ...,
        description="The session's cap; moved by every extension (explicit, or automatic when unlimited).",
    )
    session_max_minutes: int = Field(
        ...,
        description="This model's cap, 0 = unlimited: the client extends silently instead of asking.",
    )
    idle_timeout_seconds: int = Field(..., description="This model's silence timeout, 0 = never.")
    preferences: LivePreferences
    capabilities: LiveModelCapabilitiesResponse = Field(
        ..., description="What THIS session's model can do; the controller branches on it alone."
    )
    delegation_tool_name: str
    delegation_timeout_seconds: int
    delegation_result_max_tokens: int
    turn_text_max_chars: int
    rates: LiveRates | None = Field(
        None,
        description=(
            "This model's declared tariff, for the banner's indicative meter — a tariff-billed "
            "model with no tariff never starts (model_unpriced). None on a VENDOR-billed "
            "provider (ElevenLabs Agents): the platform prices nothing of it, the meter shows "
            "the clock alone and the vendor's own bill comes with the end."
        ),
    )
    session_budget_eur: float | None = Field(
        None,
        description=(
            "The connector's per-session spend ceiling (euros), if the person set one: the "
            "browser ends the session at it (outcome budget_reached)."
        ),
    )


class LiveToolCallRequest(BaseModel):
    """``POST /live/sessions/{id}/tools`` — a function call the voice made on a DIRECT session."""

    name: str = Field(..., min_length=1, max_length=120, description="The declared tool's name.")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="What the model filled in; validated through the tool's own schema.",
    )

    @field_validator("arguments")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        """A voice fills a handful of parameters; a flood is not a call."""
        if len(value) > LIVE_TOOL_CALL_MAX_ARGUMENTS:
            raise ValueError(f"at most {LIVE_TOOL_CALL_MAX_ARGUMENTS} arguments")
        return value


class LiveToolCallResponse(BaseModel):
    """What the voice reads back: a sentence, whether the lookup ran or was refused."""

    text: str = Field(..., description="The projected result, or the refusal the voice says.")
    ok: bool = Field(..., description="False when the lookup was refused or failed.")


class LiveExtendResponse(BaseModel):
    """``POST /live/sessions/{id}/extend`` — the cap moved, the connection re-credentialed."""

    expires_at: datetime = Field(..., description="The session's new cap.")
    extensions: int = Field(
        ...,
        description=(
            "The person's explicit extensions so far, this one included; a rolling cap's "
            "renewal (a model with no limit) is not counted."
        ),
    )
    credential: LiveCredentialResponse | None = Field(
        None,
        description=(
            "A fresh credential minted to the new cap, when the provider closes an open "
            "connection at its credential's expiry (measured 2026-09-19 on Gemini: 1011 "
            "« auth token has expired »); the client reconnects on it at once."
        ),
    )


class LiveOfferRequest(BaseModel):
    """``POST /live/sessions/{id}/offer`` — the browser's SDP, with the single-use credential."""

    credential: str = Field(
        ..., min_length=8, max_length=128, description="The nonce the session was started with."
    )
    sdp: str = Field(..., min_length=16, max_length=65_536, description="The SDP offer.")


class LiveOfferResponse(BaseModel):
    """The provider's SDP answer, exchanged on the person's key; the audio never transits."""

    sdp: str = Field(..., description="The SDP answer the browser sets as its remote description.")


class LiveTurnRequest(BaseModel):
    """A voice-only exchange, archived at once."""

    # Bounded like a typed message (one bound, read by every door); the row
    # itself is cut at LIVE_TURN_TEXT_MAX_CHARS by the service.
    user_text: str | None = Field(
        None,
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        description="The person's words, as the provider transcribed them.",
    )
    assistant_text: str | None = Field(
        None,
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        description="What the voice said, as the provider transcribed it.",
    )
    started_at: datetime
    ended_at: datetime


class LiveTurnResponse(BaseModel):
    """The archived rows of a voice-only exchange."""

    user_message_id: UUID | None
    assistant_message_id: UUID | None


class LiveEndRequest(BaseModel):
    """How the session ended, as the client saw it.

    The figures of the card are NOT claimed by the client: the delegations are
    the delegated runs found by the stamp and the voice exchanges an aggregate
    over the archived rows — exact, or absent (ADR-185).
    """

    outcome: LiveOutcome
    detail: str | None = Field(
        None,
        max_length=LIVE_END_DETAIL_MAX_CHARS,
        description=(
            "Why, in the client's technical words: the provider's close code and reason "
            "(`close 1007: Request contains an invalid argument.`) or the browser's error. "
            "Logged, never shown; the outcome alone left a provider close unexplained."
        ),
    )
    provider_conversation_id: str | None = Field(
        None,
        max_length=128,
        pattern=r"^[A-Za-z0-9_\-]+$",
        description=(
            "The provider's own id of the conversation, when its wire names one "
            "(ElevenLabs' conversation_initiation_metadata): the closing reads the "
            "vendor's bill under it and shows it, never records it."
        ),
    )


#: LIA's own spend over the session — the voice session's value, on the wire
#: under the name the browser has always read.
LiveUsage = VoiceSessionUsage


class LiveEndResponse(BaseModel):
    """The closed books of a session."""

    summary_message_id: UUID | None
    duration_seconds: int
    delegations: int
    voice_turns: int
    extensions: int = Field(
        0,
        description="How many times the person prolonged the session (rolling renewals excluded).",
    )
    usage: LiveUsage | None
    vendor_bill: LiveVendorBill | None = Field(
        default=None,
        description=(
            "What the provider billed the person for the session, in its own words, when "
            "its wire names the conversation and it could be read; shown, never recorded."
        ),
    )
    relay: str | None = Field(
        default=None,
        description=(
            "A DIRECT session's relay fate at the closing (ADR-301): scheduled — the words "
            "are becoming the person's own turn, off the request path — or empty (nothing "
            "was said); the card is rewritten with the settled fate (answered, waiting, "
            "quota_blocked, failed...). Null for a delegated session."
        ),
    )
