"""One frozen public audience; only an owner's own-language view crosses HTTP."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from src.core.i18n_types import Language
from src.domains.world.message_content import (
    MessageAddress,
    MessageReceipt,
    MessageStatus,
    MessageVariant,
)
from src.domains.world.messages import UUID_PATTERN, TimedMessageRequest, literal_text
from src.domains.world.schemas import StrictModel

PUBLIC_CHARS = 240
PUBLIC_TRANSLATION_CHARS = 720
PUBLIC_RESPONSE_BYTES = 65536


class PublicMessageRequest(TimedMessageRequest):
    audience: Literal["public"] = Field(
        description="Public correspondence discriminator; the recipient set is frozen at send time."
    )
    text: str = Field(
        min_length=1,
        max_length=PUBLIC_CHARS,
        description="Bounded literal human or translated text; never instructions or executable markup.",
    )
    translation_consent: bool = Field(
        default=False,
        description="Explicit permission to spend the sender or recipient native translation quota.",
    )

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        """Validate public human text against the public character and UTF-8 byte budget."""
        return literal_text(value, chars=PUBLIC_CHARS, size=PUBLIC_CHARS * 4)


class PublicRecipient(StrictModel):
    public_id: str = Field(
        pattern=UUID_PATTERN,
        description="Opaque public actor identifier, separate from the native account identifier.",
    )
    controller: str = Field(
        min_length=16,
        max_length=128,
        repr=False,
        description="Opaque controlling-tab fence; never a URL credential or public identity.",
    )
    language: Language = Field(
        description="Canonical backend language code for this account or translated view."
    )
    delivery: Literal["pending", "authorized", "unavailable"] = Field(
        default="pending",
        description="Authorization outcome for this member of the original frozen public audience.",
    )


class PublicVariant(MessageVariant):
    text: str | None = Field(
        default=None,
        max_length=PUBLIC_TRANSLATION_CHARS,
        description="Bounded literal human or translated text; never instructions or executable markup.",
    )


class PublicContent(StrictModel):
    version: Literal[1] = Field(
        default=1, description="Explicit supported wire or preference schema version."
    )
    audience: Literal["public"] = Field(
        default="public",
        description="Public correspondence discriminator; the recipient set is frozen at send time.",
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
    recipients: dict[Annotated[str, Field(pattern=UUID_PATTERN)], PublicRecipient] = Field(
        max_length=10,
        description="Original frozen audience keyed by native account, retained only in private storage.",
    )
    original: str = Field(
        min_length=1,
        max_length=PUBLIC_CHARS,
        description="Literal original human text, separate from assistant context and learning memory.",
    )
    source_language: Language = Field(
        description="Canonical backend language code of the original human text."
    )
    created_at: float = Field(
        ge=0,
        description="Intent or message creation time as Unix seconds; client intents have a freshness bound.",
    )
    expires_at: float = Field(
        ge=0,
        description="Unix-seconds expiry; expired actors, offers or correspondence are not served.",
    )
    status: Literal["original", "pending", "translated", "failed", "uncertain"] = Field(
        default="pending",
        description="Explicit lifecycle outcome; pending and uncertain never imply completed delivery.",
    )
    variants: dict[Language, PublicVariant] = Field(
        default_factory=dict,
        max_length=5,
        description="Bounded language variants; pending entries reserve capacity before model dispatch.",
    )
    receipt: MessageReceipt | None = Field(
        default=None,
        description="Native translation usage receipt visible only to its paying account.",
    )

    @field_validator("original")
    @classmethod
    def clean_original(cls, value: str) -> str:
        """Validate the public original before it can enter ephemeral storage."""
        return literal_text(value, chars=PUBLIC_CHARS, size=PUBLIC_CHARS * 4)


class PublicMessageView(StrictModel):
    audience: Literal["public"] = Field(
        default="public",
        description="Public correspondence discriminator; the recipient set is frozen at send time.",
    )
    id: str = Field(description="Stable identifier within this model contract.")
    sender_id: str = Field(description="Opaque public identifier of the message sender.")
    sender_alias: str = Field(
        description="Public sender display name captured at message acceptance."
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


def _presentation(
    message: PublicContent, account: str, language: Language, now: float
) -> tuple[str | None, MessageStatus]:
    """Choose the sender's original or this recipient's fixed-language authorized variant."""
    if account == message.sender.account:
        status: MessageStatus = message.status
        if (
            status == "pending"
            and message.variants
            and all(v.deadline <= now for v in message.variants.values())
        ):
            status = "uncertain"
        return message.original, status
    return _recipient_presentation(message, account, language, now)


def _recipient_presentation(
    message: PublicContent, account: str, language: Language, now: float
) -> tuple[str | None, MessageStatus]:
    """Refuse foreign/stale audiences and select only an authorized recipient-language variant."""
    recipient = message.recipients.get(account)
    if recipient is None:
        raise ValueError("world_message_unavailable")
    if recipient.language != language or recipient.delivery == "unavailable":
        return None, "unavailable"
    if language == message.source_language:
        return message.original, "original"
    variant = message.variants.get(language)
    if variant is None:
        return None, "pending" if message.status == "pending" else "unavailable"
    if variant.status == "pending" and variant.deadline <= now:
        return None, "uncertain"
    ready = variant.status == "translated" and recipient.delivery == "authorized"
    return variant.text if ready else None, (
        variant.status if not (variant.status == "translated" and not ready) else "unavailable"
    )


def project_public(
    message: PublicContent, account: str, language: Language, now: float
) -> PublicMessageView:
    """Project one frozen-audience message and restrict the usage receipt to its payer."""
    text, status = _presentation(message, account, language, now)
    return PublicMessageView(
        id=message.id,
        sender_id=message.sender.public_id,
        sender_alias=message.sender.alias,
        outgoing=account == message.sender.account,
        original=message.original,
        text=text,
        language=language,
        status=status,
        created_at=message.created_at,
        expires_at=message.expires_at,
        receipt=message.receipt if account == message.sender.account else None,
    )
