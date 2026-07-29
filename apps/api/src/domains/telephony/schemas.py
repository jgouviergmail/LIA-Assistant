"""Telephony Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus


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
    call_seconds: float | None = Field(default=None, description="Call duration in seconds.")
    created_at: datetime = Field(..., description="When the call was created.")
    completed_at: datetime | None = Field(default=None, description="When the call ended.")
