"""Host-authored, message-owned targets for editable conversational composition.

This projection grants no execution capability. Submission uses the ordinary
chat tools, connector ownership checks and HITL draft policies. No HTML value
supplies the target, and no registry lookup from a later turn can replace it.
"""

from collections.abc import Mapping
from itertools import islice
from typing import Literal, Self
from uuid import UUID

from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.domains.agents.data_registry.models import RegistryItem
from src.domains.reminders.models import ReminderStatus
from src.infrastructure.llm.message_view import CARD_ACTIONS_KEY

MAX_CARD_ACTION_ITEMS = 256


class CardActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    registry_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    kind: Literal["EMAIL", "REMINDER"]
    target_id: str = Field(min_length=1, max_length=2048, pattern=r"^[A-Za-z0-9._~+=/-]+$")
    provider: Literal["google_gmail", "microsoft_outlook"] | None = None
    account_binding: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$"
    )
    label: str = Field(default="", max_length=200)
    actions: list[Literal["reply", "forward", "delete_email", "cancel_reminder"]] = Field(
        max_length=3
    )

    @model_validator(mode="after")
    def supported_actions(self) -> Self:
        expected = ["reply", "forward"] if self.kind == "EMAIL" else ["cancel_reminder"]
        if self.actions != expected and not (
            self.kind == "EMAIL" and self.actions == ["reply", "forward", "delete_email"]
        ):
            raise ValueError("Unsupported composition action for this item")
        if self.kind == "REMINDER" and str(UUID(self.target_id)) != self.target_id.lower():
            raise ValueError("Invalid reminder target")
        if (self.kind == "EMAIL") != (self.provider is not None):
            raise ValueError("Unsupported target provider")
        if (self.kind == "EMAIL") != (self.account_binding is not None):
            raise ValueError("Unsupported target account")
        return self


class CardActionsProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: Literal[1]
    run_id: str = Field(min_length=1, max_length=256)
    items: list[CardActionItem] = Field(min_length=1, max_length=MAX_CARD_ACTION_ITEMS)

    @model_validator(mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if isinstance(value, dict) and type(value.get("version")) is not int:
            raise ValueError("Unsupported action projection version")
        return value

    @model_validator(mode="after")
    def unique_targets(self) -> Self:
        if len({item.registry_id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate card reference")
        return self


def _provider(kind: str, payload: dict[str, object], source: object) -> str | None:
    if kind == "REMINDER":
        return None
    if source != "gmail":
        return None
    marker = payload.get("_provider")
    return (
        {
            None: "google_gmail",
            "google": "google_gmail",
            "microsoft": "microsoft_outlook",
        }.get(marker)
        if isinstance(marker, str | None)
        else None
    )


def _registry_parts(item: object) -> tuple[object, object, object, object]:
    if isinstance(item, RegistryItem):
        return item.type.value, item.payload, item.meta.source, item.meta.display
    if isinstance(item, dict):
        meta = item.get("meta")
        source = meta.get("source") if isinstance(meta, dict) else None
        display = meta.get("display") if isinstance(meta, dict) else None
        return item.get("type"), item.get("payload"), source, display
    return None, None, None, None


def _native_target(
    kind: str, payload: dict[str, object], source: object, provider: str | None
) -> bool:
    if kind == "EMAIL":
        conflict = (
            payload.get("message_id")
            and payload.get("id")
            and payload["message_id"] != payload["id"]
        )
        return provider is not None and not conflict
    return (
        source == "reminders"
        and payload.get("status", ReminderStatus.PENDING.value) == ReminderStatus.PENDING.value
    )


def _target(registry_id: str, item: object) -> CardActionItem | None:
    kind, payload, source, display = _registry_parts(item)
    if kind not in ("EMAIL", "REMINDER") or not isinstance(payload, dict):
        return None
    if not isinstance(kind, str):
        return None
    provider = _provider(kind, payload, source)
    if not _native_target(kind, payload, source, provider):
        return None
    account = (
        display.get("_lia_email_account") if isinstance(display, dict) and kind == "EMAIL" else None
    )
    label = payload.get("subject") if kind == "EMAIL" else payload.get("content")
    try:
        return CardActionItem.model_validate(
            {
                "registry_id": registry_id,
                "kind": kind,
                "target_id": payload.get("message_id") or payload.get("id"),
                "provider": provider,
                "account_binding": account,
                "label": " ".join(label.split())[:200] if isinstance(label, str) else "",
                "actions": (
                    ["reply", "forward", "delete_email"] if kind == "EMAIL" else ["cancel_reminder"]
                ),
            }
        )
    except ValidationError:
        return None


def with_card_actions(
    message: AIMessage, registry: Mapping[str, object] | None, *, run_id: str, enabled: bool
) -> AIMessage:
    kwargs = {
        key: value for key, value in message.additional_kwargs.items() if key != CARD_ACTIONS_KEY
    }
    targets = (
        [
            _target(key, item)
            for key, item in islice((registry or {}).items(), MAX_CARD_ACTION_ITEMS)
        ]
        if enabled
        else []
    )
    valid = [item for item in targets if item is not None]
    if valid:
        kwargs[CARD_ACTIONS_KEY] = CardActionsProjection(
            version=1, run_id=run_id, items=valid
        ).model_dump(mode="json")
    return message.model_copy(update={"additional_kwargs": kwargs})


def card_actions_from_state(state: object, run_id: str) -> dict[str, object] | None:
    messages = state.get("messages") if isinstance(state, dict) else None
    if (
        not isinstance(messages, list)
        or not messages
        or not isinstance(messages[-1], AIMessage)
        or messages[-1].tool_calls
    ):
        return None
    value = messages[-1].additional_kwargs.get(CARD_ACTIONS_KEY)
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value.get("run_id") != run_id
    ):
        return None
    try:
        return CardActionsProjection.model_validate(value).model_dump(mode="json")
    except ValidationError:
        return None


def with_card_action_metadata(
    metadata: dict[str, object], state: object, run_id: str
) -> dict[str, object]:
    snapshot = card_actions_from_state(state, run_id)
    return {**metadata, "run_id": run_id, CARD_ACTIONS_KEY: snapshot} if snapshot else metadata
