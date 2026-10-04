"""Typed, ephemeral selection of an archived card; never execution authority."""

from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

type CardComposeAction = Literal["reply", "forward", "cancel_reminder"]


class CardCompositionUnavailable(ValueError):
    """The selected archived target cannot safely be used in this request."""

    def __init__(self) -> None:
        super().__init__("Card composition is unavailable; select a current card again")


class CardCompositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: Literal[1]
    message_id: str = Field(pattern=r"^[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$")
    run_id: str = Field(min_length=1, max_length=256)
    registry_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    action: CardComposeAction

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Unsupported composition version")
        return value


@dataclass(frozen=True, slots=True)
class CardComposition:
    user_id: UUID
    kind: Literal["EMAIL", "REMINDER"]
    target_id: str
    action: CardComposeAction
    provider: str | None
    account_binding: str | None = None
    source: CardCompositionRequest | None = None


card_composition_ctx: ContextVar[CardComposition | None] = ContextVar(
    "card_composition_ctx", default=None
)

CARD_COMPOSITION_DRAFT_KEY = "_lia_card_composition"
_COMPOSITION_DRAFTS = {
    "reply": ("EMAIL", "email_reply", "message_id"),
    "forward": ("EMAIL", "email_forward", "message_id"),
    "cancel_reminder": ("REMINDER", "reminder_delete", "reminder_id"),
}


def preserve_composition_binding(
    original: dict[str, object], changed: dict[str, object]
) -> dict[str, object]:
    clean = {key: value for key, value in changed.items() if key != CARD_COMPOSITION_DRAFT_KEY}
    if CARD_COMPOSITION_DRAFT_KEY in original:
        clean[CARD_COMPOSITION_DRAFT_KEY] = deepcopy(original[CARD_COMPOSITION_DRAFT_KEY])
    return clean


def bind_composition_draft(content: dict[str, object], draft_type: str) -> dict[str, object]:
    clean = preserve_composition_binding({}, content)
    selected = card_composition_ctx.get()
    if selected is None:
        return clean
    kind, expected, target_key = _COMPOSITION_DRAFTS[selected.action]
    if selected.kind != kind or draft_type not in (
        "email_reply",
        "email_forward",
        "reminder_delete",
    ):
        return clean
    if (
        draft_type != expected
        or content.get(target_key) != selected.target_id
        or selected.source is None
    ):
        raise CardCompositionUnavailable()
    return {**clean, CARD_COMPOSITION_DRAFT_KEY: selected.source.model_dump(mode="json")}


def ensure_composition_draft_target(
    content: dict[str, object], user_id: UUID, action: CardComposeAction
) -> None:
    selected = card_composition_ctx.get()
    if selected is None:
        return
    kind, _, target_key = _COMPOSITION_DRAFTS[action]
    if (
        selected.user_id != user_id
        or selected.kind != kind
        or selected.action != action
        or content.get(target_key) != selected.target_id
    ):
        raise CardCompositionUnavailable()


def ensure_composition_provider(user_id: UUID, category: str, provider: str | None) -> None:
    """Refuse retargeting an email after the account's active provider changed."""
    selected = card_composition_ctx.get()
    if selected is None or selected.kind != "EMAIL" or category != "email":
        return
    canonical = "google_gmail" if provider == "gmail" else provider
    if selected.user_id != user_id or selected.provider != canonical:
        raise CardCompositionUnavailable()


def ensure_composition_account(user_id: UUID, provider: str, account_binding: str | None) -> None:
    if provider not in ("gmail", "google_gmail", "microsoft_outlook"):
        return
    selected = card_composition_ctx.get()
    if selected is None or selected.kind != "EMAIL":
        return
    ensure_composition_provider(user_id, "email", provider)
    if not account_binding or selected.account_binding != account_binding:
        raise CardCompositionUnavailable()
