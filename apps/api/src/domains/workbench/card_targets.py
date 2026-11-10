"""Account-bound card destinations, signed by their producer (ADR-332/369).

The envelope is a read-only navigation hint, never a provider credential or an
execution grant. Its source is checked again when the person opens the card.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from datetime import date
from enum import Enum
from typing import Annotated, Final, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

from src.core.config import settings
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.features import TOOL_PROVIDERS, WorkbenchTool
from src.domains.workbench.ids import PROVIDER_ID_MAX_CHARS, ProviderId, ProviderName

CARD_TARGET_FIELD: Final = "_lia_card_target"
CARD_KIND_FIELD: Final = "_lia_card_kind"
CARD_TOKEN_MAX_CHARS: Final = 8192
_PROVIDER_ID = TypeAdapter(ProviderId)
_PROVIDER_NAME = TypeAdapter(ProviderName)
_ContainerId = Annotated[
    str | None,
    StringConstraints(
        min_length=1, max_length=PROVIDER_ID_MAX_CHARS, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]


class CardTargetKind(str, Enum):
    """Native records whose cards can open the person's Tools."""

    EMAIL = "email"
    EVENT = "event"
    CALENDAR = "calendar"
    CONTACT = "contact"
    TASK = "task"
    FILE = "file"
    HUE_LIGHT = "hue_light"


CARD_TOOLS: Final[dict[CardTargetKind, WorkbenchTool]] = {
    CardTargetKind.EMAIL: WorkbenchTool.MAIL,
    CardTargetKind.EVENT: WorkbenchTool.CALENDAR,
    CardTargetKind.CALENDAR: WorkbenchTool.CALENDAR,
    CardTargetKind.CONTACT: WorkbenchTool.CONTACTS,
    CardTargetKind.TASK: WorkbenchTool.TASKS,
    CardTargetKind.FILE: WorkbenchTool.FILES,
    CardTargetKind.HUE_LIGHT: WorkbenchTool.LIGHTS,
}
assert set(CARD_TOOLS) == set(CardTargetKind)


class CardToolTarget(BaseModel):
    """Only addresses that the native Tools know how to read."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: CardTargetKind = Field(description="The received record's family")
    item_id: ProviderId = Field(description="The actual provider identifier")
    container_id: _ContainerId = Field(
        default=None, description="Received calendar, task-list or mailbox scope"
    )
    day: str | None = Field(default=None, description="Received event day in the display timezone")
    is_folder: bool = Field(default=False, description="Whether this file is a folder")

    @model_validator(mode="after")
    def _scope_is_complete(self) -> Self:
        if self.kind in {CardTargetKind.EVENT, CardTargetKind.TASK} and not self.container_id:
            raise ValueError("A scoped record requires its received container")
        if self.container_id and self.kind not in {
            CardTargetKind.EMAIL,
            CardTargetKind.EVENT,
            CardTargetKind.TASK,
        }:
            raise ValueError("This record has no container address")
        if self.container_id:
            validator = _PROVIDER_NAME if self.kind == CardTargetKind.EMAIL else _PROVIDER_ID
            validator.validate_python(self.container_id, strict=True)
        if self.day is not None:
            if (
                self.kind != CardTargetKind.EVENT
                or date.fromisoformat(self.day).isoformat() != self.day
            ):
                raise ValueError("Only an event has an ISO day")
        if self.is_folder and self.kind != CardTargetKind.FILE:
            raise ValueError("Only a file can be a folder")
        return self


class SignedCardTarget(BaseModel):
    """Source proof kept in archived HTML, containing no credential secret."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1] = Field(default=1, description="Navigation envelope version")
    target: CardToolTarget = Field(description="Native record address")
    provider: ConnectorType = Field(description="The provider that actually answered")
    source_binding: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="Opaque fingerprint of the answering source"
    )

    @model_validator(mode="after")
    def _provider_serves_target(self) -> Self:
        if self.provider not in TOOL_PROVIDERS[CARD_TOOLS[self.target.kind]]:
            raise ValueError("The provider does not serve this family")
        return self


class CardTargetRequest(BaseModel):
    """An opaque envelope; the browser cannot assert a provider identity."""

    model_config = ConfigDict(extra="forbid", strict=True)
    token: str = Field(
        min_length=1, max_length=CARD_TOKEN_MAX_CHARS, description="Signed card token"
    )


class CardTargetResponse(BaseModel):
    """An admitted address or an explicit reason it cannot be opened."""

    available: bool = Field(description="Whether this exact record can be addressed")
    target: CardToolTarget | None = Field(default=None, description="Admitted native target")
    reason: Literal["historical", "source_changed", "unavailable"] | None = Field(
        default=None, description="Stable translated refusal category"
    )


def _signature(encoded: str, user_id: UUID) -> str:
    message = f"lia:workbench-card:v1:{user_id}:{encoded}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def sign_card_target(target: SignedCardTarget, user_id: UUID) -> str:
    """Bind a source-attested address to its LIA account and deployment."""
    encoded = base64.urlsafe_b64encode(target.model_dump_json().encode()).decode().rstrip("=")
    return f"{encoded}.{_signature(encoded, user_id)}"


def read_card_target(token: str, user_id: UUID) -> SignedCardTarget | None:
    """Refuse malformed, forged, other-account or other-instance envelopes."""
    if len(token) > CARD_TOKEN_MAX_CHARS or not token.isascii():
        return None
    encoded, separator, signature = token.partition(".")
    if not separator or not hmac.compare_digest(_signature(encoded, user_id), signature):
        return None
    try:
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        return SignedCardTarget.model_validate_json(raw)
    except binascii.Error, ValueError:
        return None
