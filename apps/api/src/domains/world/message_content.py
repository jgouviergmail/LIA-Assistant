"""Private ephemeral content and an allowlisted participant projection."""

from typing import Literal

from pydantic import Field, field_validator

from src.core.i18n_types import Language
from src.domains.world.messages import (
    TRANSLATION_BYTES,
    TRANSLATION_CHARS,
    UUID_PATTERN,
    literal_text,
)
from src.domains.world.schemas import StrictModel


class MessageReceipt(StrictModel):
    run_id: str = Field(
        max_length=64,
        description="Content-free native accounting run identifier for the translation receipt.",
    )
    tokens_in: int = Field(
        ge=0,
        le=2**53 - 1,
        description="Actual accounted input tokens for this translation, under provider accounting semantics.",
    )
    tokens_out: int = Field(
        ge=0,
        le=2**53 - 1,
        description="Actual accounted output tokens for this translation, under provider accounting semantics.",
    )
    cost_eur: float | None = Field(
        default=None,
        ge=0,
        description="Accounted model cost in euros, or null when no positive cost is available.",
    )


class MessageAddress(StrictModel):
    account: str = Field(
        pattern=UUID_PATTERN,
        description="Internal native account identifier of this correspondence participant.",
    )
    public_id: str = Field(
        pattern=UUID_PATTERN,
        description="Opaque public actor identifier, separate from the native account identifier.",
    )
    alias: str = Field(
        min_length=1,
        max_length=24,
        description="Bounded public account display name; never an email or private profile inference.",
    )


class MessageVariant(StrictModel):
    job_id: str = Field(
        pattern=UUID_PATTERN,
        description="Stable owned translation request identifier used for publication fencing.",
    )
    payer: str = Field(
        pattern=UUID_PATTERN,
        description="Native account paying for this explicitly consented translation variant.",
    )
    status: Literal["pending", "translated", "failed", "uncertain"] = Field(
        description="Explicit lifecycle outcome; pending and uncertain never imply completed delivery."
    )
    deadline: float = Field(
        description="Unix-seconds deadline after which a pending translation is displayed as uncertain."
    )
    text: str | None = Field(
        default=None,
        max_length=TRANSLATION_CHARS,
        description="Bounded literal human or translated text; never instructions or executable markup.",
    )
    receipt: MessageReceipt | None = Field(
        default=None,
        description="Native translation usage receipt visible only to its paying account.",
    )

    @field_validator("text")
    @classmethod
    def clean_translation(cls, value: str | None) -> str | None:
        """Validate optional translated text under the shared character and byte bounds."""
        return (
            literal_text(value, chars=TRANSLATION_CHARS, size=TRANSLATION_BYTES)
            if value is not None
            else None
        )


class StoredMessage(StrictModel):
    version: Literal[1] = Field(
        default=1, description="Explicit supported wire or preference schema version."
    )
    id: str = Field(
        pattern=UUID_PATTERN,
        description="Stable identifier within this model contract.",
    )
    epoch: str = Field(
        pattern=UUID_PATTERN,
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence.",
    )
    sender: MessageAddress = Field(
        description="Public sender address captured at acceptance; internal account identity is never shared."
    )
    recipient: MessageAddress = Field(
        description="Recipient address captured from current authoritative identity."
    )
    original: str = Field(
        min_length=1,
        max_length=1000,
        description="Literal original human text, separate from assistant context and learning memory.",
    )
    source_language: Language = Field(
        description="Canonical backend language code of the original human text."
    )
    created_at: float = Field(
        description="Intent or message creation time as Unix seconds; client intents have a freshness bound."
    )
    expires_at: float = Field(
        description="Unix-seconds expiry; expired actors, offers or correspondence are not served."
    )
    variants: dict[Language, MessageVariant] = Field(
        default_factory=dict,
        max_length=6,
        description="Bounded language variants; pending entries reserve capacity before model dispatch.",
    )

    @field_validator("original")
    @classmethod
    def clean_original(cls, value: str) -> str:
        """Validate the sender's original as bounded literal human correspondence."""
        return literal_text(value)


type MessageStatus = Literal[
    "original", "pending", "translated", "failed", "uncertain", "unavailable"
]


class MessageView(StrictModel):
    id: str = Field(description="Stable identifier within this model contract.")
    sender_id: str = Field(description="Opaque public identifier of the message sender.")
    sender_alias: str = Field(
        description="Public sender display name captured at message acceptance."
    )
    recipient_id: str = Field(
        description="Opaque public identifier of the private message recipient."
    )
    recipient_alias: str = Field(
        description="Public recipient name captured when the private message was accepted."
    )
    outgoing: bool = Field(description="Whether this projection belongs to the message sender.")
    original: str = Field(
        description="Literal original human text, separate from assistant context and learning memory."
    )
    text: str | None = Field(
        description="Bounded literal human or translated text; never instructions or executable markup."
    )
    language: Language = Field(
        description="Canonical backend language code for this account or translated view."
    )
    status: MessageStatus = Field(
        description="Explicit lifecycle outcome; pending and uncertain never imply completed delivery."
    )
    created_at: float = Field(
        description="Intent or message creation time as Unix seconds; client intents have a freshness bound."
    )
    expires_at: float = Field(
        description="Unix-seconds expiry; expired actors, offers or correspondence are not served."
    )
    receipt: MessageReceipt | None = Field(
        description="Native translation usage receipt visible only to its paying account."
    )


def project_message(
    message: StoredMessage, account: str, language: Language, now: float
) -> MessageView:
    """Project correspondence only to a participant, with receipts restricted to their payer."""
    if account not in {message.sender.account, message.recipient.account}:
        raise ValueError("world_message_unavailable")
    outgoing = account == message.sender.account
    text, status = _presentation(message, outgoing, language, now)
    return MessageView(
        id=message.id,
        sender_id=message.sender.public_id,
        sender_alias=message.sender.alias,
        recipient_id=message.recipient.public_id,
        recipient_alias=message.recipient.alias,
        outgoing=outgoing,
        original=message.original,
        text=text,
        language=language,
        status=status,
        created_at=message.created_at,
        expires_at=message.expires_at,
        receipt=_latest_receipt(message, account),
    )


def _variant_status(variant: MessageVariant, now: float) -> MessageStatus:
    """Turn a pending variant past its deadline into an uncertain displayed outcome."""
    if variant.status == "pending" and variant.deadline <= now:
        return "uncertain"
    return variant.status


def _presentation(
    message: StoredMessage, outgoing: bool, language: Language, now: float
) -> tuple[str | None, MessageStatus]:
    """Select the original or an own-language variant without starting translation."""
    if outgoing:
        sent = next(
            (item for item in message.variants.values() if item.job_id == message.id),
            None,
        )
        return message.original, _variant_status(sent, now) if sent else "original"
    if language == message.source_language:
        return message.original, "original"
    variant = message.variants.get(language)
    if variant is None:
        return None, "unavailable"
    status = _variant_status(variant, now)
    return variant.text if status == "translated" else None, status


def _latest_receipt(message: StoredMessage, account: str) -> MessageReceipt | None:
    # Overwriting an existing language does not move its dictionary position.
    # Only the payer sees the latest paid request, regardless of language order.
    """Return the latest receipt paid by this account, independent of dictionary insertion order."""
    latest = max(
        (item for item in message.variants.values() if item.payer == account and item.receipt),
        key=lambda item: item.deadline,
        default=None,
    )
    return latest.receipt if latest is not None else None
