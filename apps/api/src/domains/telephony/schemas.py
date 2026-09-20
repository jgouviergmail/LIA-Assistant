"""Telephony Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.constants import (
    PHONE_NUMBER_INPUT_MAX_LENGTH,
    PHONE_VERIFICATION_CODE_INPUT_MAX_LENGTH,
)
from src.domains.shared.phone_domains import PHONE_DOMAINS
from src.domains.telephony.models import CallKind, PhoneCallOutcome, PhoneCallStatus
from src.domains.voice_sessions.session import VoiceSessionMode


class StructuredCallData(BaseModel):
    """Minimal, typed structured outcome extracted from a call (D-8).

    Only these fields are persisted (never the raw transcript). All optional — a
    call may yield none of them. Unknown keys from the extraction are ignored so
    a richer transcript never breaks ingestion.
    """

    model_config = ConfigDict(extra="ignore")

    agreed: bool | None = Field(default=None, description="Did the callee agree to the ask?")
    proposed_datetime: str | None = Field(
        default=None, description="ISO-8601 datetime proposed during the call, if any."
    )
    location: str | None = Field(default=None, description="Location proposed/agreed, if any.")
    notes: str | None = Field(default=None, description="Short free-text note, minimized.")
    additional_costs: str | None = Field(
        default=None,
        description="Any extra cost, surcharge, price change or fee mentioned on the call, "
        "with its amount (e.g. 'extra cheese +3€'). None if no cost was discussed.",
    )
    pending_user_decision: str | None = Field(
        default=None,
        description="Anything left UNCONFIRMED for the user to decide — an option, upsell, "
        "surcharge or new information outside the assistant's mandate that it did not accept "
        "and flagged for a call-back. None if nothing was deferred.",
    )


class SelfCallData(BaseModel):
    """What the voice agent collects on an OWNER call (lot 4).

    Two fields beside the third-party ones on the same agent: whether the
    person confirmed being the account holder, and what they asked for.
    Both optional; unknown keys are ignored like their sibling's.
    """

    model_config = ConfigDict(extra="ignore")

    owner_confirmed: bool | None = Field(
        default=None, description="Did the callee confirm being the account holder?"
    )
    requests: str | None = Field(
        default=None, description="Everything the person asked for or told, as a faithful list."
    )


class SelfCallRelay(BaseModel):
    """Structured output of the relay synthesis after an owner call (lot 4).

    ``relay_message`` is what the person would have typed — it becomes their
    own turn in the chat; ``summary`` is the calls-list recap; the owner flag
    gates the relay: nothing is relayed for a call the account holder did not
    answer.
    """

    owner_confirmed: bool = Field(
        ..., description="True when the account holder was the person on the line."
    )
    relay_message: str = Field(
        default="",
        description=(
            "The message the person would have typed, first person, absolute dates; "
            "EMPTY when nothing is worth relaying."
        ),
    )
    summary: str = Field(..., description="Neutral third-person recap of the call.")


class ReturnProposal(BaseModel):
    """Structured output of the post-call return synthesis (P4.2, extended T01).

    ``summary`` is the factual record persisted on the ``PhoneCall`` row; the raw
    transcript is never stored (D-8). ``proposal_text`` is the first-person
    message delivered to the user via the notification dispatcher.

    T01 (UX Actions program): the debrief fields below are OUR synthesis
    LLM's output — NOT extracted from the vendor payload (that is
    ``StructuredCallData``'s job). All additive with empty defaults, so a
    model that returns only the two historical fields still validates.
    """

    summary: str = Field(..., description="Neutral factual recap of the call outcome.")
    proposal_text: str = Field(
        ..., description="First-person report + optional next step for the user."
    )
    key_points: list[str] = Field(
        default_factory=list,
        description=(
            "The concrete FINDINGS or answers obtained on the call, relative to "
            "the objective, one short factual point each. This is what an "
            "INFORMATION-gathering call produces (e.g. availability, opening "
            "hours, someone's plans) — populate it whenever the call returned "
            "facts worth structuring, even when nothing is actionable. Empty "
            "only when the call connected but yielded no usable information."
        ),
    )
    commitments: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete commitments made ON the call, one short sentence each, "
            "naming WHO committed (the callee or the assistant). Empty if none."
        ),
    )
    follow_up_tasks: list[str] = Field(
        default_factory=list,
        description=(
            "Actionable follow-up TASKS for the user implied by the outcome, "
            "one short imperative sentence each. Empty if none."
        ),
    )
    follow_up_reminders: list[str] = Field(
        default_factory=list,
        description=(
            "Time-bound REMINDERS worth setting (with their absolute date/time "
            "when known), one short sentence each. Empty if none."
        ),
    )
    follow_up_draft: str | None = Field(
        default=None,
        description=(
            "Short draft of a follow-up message (SMS/email) to the callee when "
            "the outcome calls for one. None otherwise."
        ),
    )
    uncertainties: list[str] = Field(
        default_factory=list,
        description=(
            "Points left UNCONFIRMED or to double-check (deferred options, "
            "unverified costs, ambiguous dates), one short sentence each."
        ),
    )

    def debrief_dict(self) -> dict[str, object]:
        """The persistable debrief (JSONB) — only the T01 fields, no text dupes."""
        return self.model_dump(
            include={
                "key_points",
                "commitments",
                "follow_up_tasks",
                "follow_up_reminders",
                "follow_up_draft",
                "uncertainties",
            },
            exclude_none=True,
        )


class PhoneNumberInfo(BaseModel):
    """A phone number available in the user's ElevenLabs workspace (GET phone-numbers)."""

    model_config = ConfigDict(extra="ignore")

    phone_number_id: str = Field(..., description="ElevenLabs phone number id.")
    phone_number: str = Field(..., description="E.164 phone number.")
    provider: str | None = Field(default=None, description="twilio | sip_trunk | exotel.")
    assigned_agent: str | None = Field(
        default=None, description="Agent assigned to this number (inbound only)."
    )


class OutboundCallResult(BaseModel):
    """Result of an outbound-call initiation (twilio/outbound-call response)."""

    model_config = ConfigDict(extra="ignore")

    success: bool = Field(..., description="Whether the call was accepted for dialing.")
    conversation_id: str | None = Field(default=None, description="ElevenLabs conversation id.")
    call_sid: str | None = Field(default=None, description="Twilio call SID.")
    message: str | None = Field(default=None, description="Human-readable status/error.")


class KeyValidationResult(BaseModel):
    """Outcome of validating a user-supplied ElevenLabs API key."""

    is_valid: bool = Field(..., description="Whether the key authenticated successfully.")
    message: str = Field(..., description="Validation detail (localized by the caller).")


class TelephonyKeyValidateRequest(BaseModel):
    """Body for the wizard's key-validation step."""

    api_key: str = Field(..., min_length=8, max_length=512, description="ElevenLabs API key.")


class TelephonyKeyValidateResponse(BaseModel):
    """Result of key validation + the numbers available in the workspace."""

    is_valid: bool = Field(..., description="Whether the key authenticated.")
    message: str = Field(..., description="Validation detail.")
    numbers: list[PhoneNumberInfo] = Field(
        default_factory=list, description="Workspace phone numbers (empty if key invalid)."
    )


class TelephonyActivateRequest(BaseModel):
    """Body for the wizard's activation step."""

    api_key: str = Field(..., min_length=8, max_length=512)
    agent_phone_number_id: str = Field(
        ..., min_length=1, description="Chosen ElevenLabs number id."
    )
    webhook_secret: str = Field(
        ..., min_length=1, description="HMAC secret of the workspace post-call webhook."
    )
    caller_number_display: str | None = Field(
        default=None, description="Human-readable caller number for the UI."
    )


class TelephonyConnectorResponse(BaseModel):
    """Public view of the activated telephony connector (no secrets)."""

    status: str = Field(..., description="Connector status, e.g. 'active'.")
    agent_id: str = Field(..., description="LIA-controlled ElevenLabs agent id.")
    agent_phone_number_id: str = Field(..., description="Bound phone number id.")


class TelephonyCallUsage(BaseModel):
    """What a call cost, cumulated (lot 8): its live lookups, its synthesis, its
    relayed turn — one run id, one summary row, the chat meter's vocabulary."""

    model_config = ConfigDict(from_attributes=True)

    tokens_in: int = Field(..., description="Prompt tokens, cached ones excluded.")
    tokens_out: int = Field(..., description="Completion tokens.")
    tokens_cache: int = Field(..., description="Cached prompt tokens.")
    cost_eur: float = Field(
        ...,
        description="Every euro the platform paid for the call: model, Maps Platform "
        "lookups and generated images (the summary row's billed total).",
    )
    google_api_requests: int = Field(..., description="Maps/Places requests made for the call.")


class TelephonyCallSummary(BaseModel):
    """Public view of a past call for the calls surface.

    Deliberately OMITS ``callee_phone`` (encrypted PII) — the UI only ever needs
    the display name, status and outcome.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Call id (also the webhook reconciliation key).")
    callee_display: str = Field(..., description="Human-readable callee name.")
    objective: str = Field(..., description="What LIA was asked to accomplish.")
    status: PhoneCallStatus = Field(..., description="Terminal or in-flight call status.")
    call_mode: VoiceSessionMode = Field(
        default="direct",
        description=(
            "The mode an owner call ran under (ADR-301): delegated (Live) or direct; a "
            "third-party call is direct."
        ),
    )
    outcome: PhoneCallOutcome | None = Field(
        default=None, description="Semantic outcome, if completed."
    )
    summary: str | None = Field(default=None, description="Factual recap (null once purged).")
    debrief: dict[str, object] | None = Field(
        default=None,
        description=(
            "T01 structured debrief (commitments, follow-up tasks/reminders, "
            "draft, uncertainties). Null before T01 calls and once purged."
        ),
    )
    structured_data: StructuredCallData | None = Field(
        default=None,
        description=(
            "Minimal typed outcome extracted from the call: what was agreed, "
            "what date and place were PROPOSED, what it would cost, and what "
            "was left for the user to decide. Persisted since D-8 and shown "
            "since the debrief became actionable — a surcharge or an option "
            "the callee offered is a decision the user has to make, and one "
            "they could not make while the field stayed invisible. Null before "
            "the call completed, and again once retention purged it."
        ),
    )
    call_seconds: float | None = Field(default=None, description="Call duration in seconds.")
    created_at: datetime = Field(..., description="When the call was created.")
    completed_at: datetime | None = Field(default=None, description="When the call ended.")
    call_kind: CallKind = Field(
        default=CallKind.THIRD_PARTY,
        description="Which mandate the call ran under (third party, the person, verification).",
    )
    usage: TelephonyCallUsage | None = Field(
        default=None,
        description="The call's cumulated bill (lot 8); null while nothing was spent.",
    )
    relay_outcome: str | None = Field(
        default=None,
        description=(
            "For an owner call: how its words reached the chat (answered, waiting) or "
            "why they did not (empty, not_owner, pending_question, busy, quota_blocked, "
            "failed). Null while the relay runs, and for every other kind."
        ),
    )

    @field_validator("call_kind", mode="before")
    @classmethod
    def _kind_defaults_to_third_party(cls, value: object) -> object:
        """A row built in memory (never flushed) carries no kind yet: read it as
        the baked mandate, which is what every row before lot 2 was."""
        return CallKind.THIRD_PARTY if value is None else value

    @field_validator("call_mode", mode="before")
    @classmethod
    def _mode_defaults_to_direct(cls, value: object) -> object:
        """Same reading for the mode (ADR-301): unflushed, a row ran direct."""
        return "direct" if value is None else value

    @model_validator(mode="before")
    @classmethod
    def _relay_outcome_from_payload(cls, value: object) -> object:
        """Read the relay verdict off the outbox payload the settle wrote."""
        payload = getattr(value, "notification_payload", None)
        if isinstance(payload, dict) and payload.get("relay_outcome"):
            outcome = payload["relay_outcome"]
            if isinstance(value, dict):
                return {**value, "relay_outcome": outcome}
            data = {name: getattr(value, name) for name in cls.model_fields if hasattr(value, name)}
            data["relay_outcome"] = outcome
            return data
        return value


class TelephonyIdentityResponse(BaseModel):
    """The person's own phone identity, as the settings page shows it (lot 1).

    The number is the person's own and is shown whole: a masked number cannot
    be checked for the typo that would send an owner call to a stranger.
    """

    phone_number: str | None = Field(default=None, description="Declared number in E.164, if any.")
    verified: bool = Field(..., description="Whether LIA heard the person answer this number.")
    verified_at: datetime | None = Field(default=None, description="When the number was verified.")
    disabled_domains: list[str] = Field(
        default_factory=list,
        description="Phone domains the person switched off for their own calls (lot 8).",
    )
    available_domains: list[str] = Field(
        default_factory=list,
        description="Every domain the phone may read, in the register's vocabulary.",
    )
    rich_context_enabled: bool = Field(
        ..., description="Whether an owner call carries the chat's context beyond free/busy."
    )
    verification_pending: bool = Field(
        default=False,
        description="Whether a spoken verification code is still waiting to be typed.",
    )
    call_mode: VoiceSessionMode = Field(
        default="delegated",
        description=(
            "How the person chose their own calls to run (ADR-301): delegated (Live) "
            "or direct (Live direct)."
        ),
    )
    call_mode_effective: VoiceSessionMode = Field(
        default="delegated",
        description="What a call placed now runs: the choice, or direct when Live is unavailable.",
    )
    live_available: bool = Field(
        default=True,
        description="Whether this instance can run a Live call (the vendor can call it back).",
    )
    live_unavailable_reason: str | None = Field(
        default=None,
        description="Why Live is unavailable, as a stable code the page translates; None when it is.",
    )


class TelephonyIdentityVerifyResponse(BaseModel):
    """What the page learns when the verification call leaves."""

    call_id: UUID | None = Field(default=None, description="The placed verification call.")
    expires_in_seconds: int = Field(..., description="How long the spoken code stays valid.")


class TelephonyIdentityConfirmRequest(BaseModel):
    """Body for typing the spoken code back."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=PHONE_VERIFICATION_CODE_INPUT_MAX_LENGTH,
        description="The code the call read aloud, as typed.",
    )


class TelephonyIdentityNumberRequest(BaseModel):
    """Body for declaring the person's number."""

    phone_number: str = Field(
        ...,
        min_length=1,
        max_length=PHONE_NUMBER_INPUT_MAX_LENGTH,
        description="The number as typed; normalised to E.164 server-side.",
    )


class TelephonyIdentityUpdateRequest(BaseModel):
    """Body for the identity switches — each optional, at least one given."""

    rich_context_enabled: bool | None = Field(
        default=None,
        description="Whether an owner call carries the chat's context beyond free/busy.",
    )
    disabled_domains: list[str] | None = Field(
        default=None,
        max_length=len(PHONE_DOMAINS),
        description="The phone domains to switch off for the person's own calls (lot 8).",
    )
    call_mode: VoiceSessionMode | None = Field(
        default=None,
        description="How the person's own calls run (ADR-301): delegated (Live) or direct.",
    )

    @model_validator(mode="after")
    def _at_least_one_switch(self) -> TelephonyIdentityUpdateRequest:
        if (
            self.rich_context_enabled is None
            and self.disabled_domains is None
            and self.call_mode is None
        ):
            raise ValueError(
                "Nothing to update: give rich_context_enabled, disabled_domains or call_mode."
            )
        return self
