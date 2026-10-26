"""Versioned wire projections and internal authority state are separate types."""

import unicodedata
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

from pydantic import ConfigDict, Field, TypeAdapter, field_validator, with_config

from src.domains.world.avatar import AvatarAppearance
from src.domains.world.wire_models import (
    StrictModel,
    VersionedModel,
)
from src.domains.world.wire_models import (
    explicit_consent as validate_consent,
)


@with_config(ConfigDict(extra="forbid", strict=True, allow_inf_nan=False))
class Position(TypedDict):
    x: Annotated[float, Field(description="Horizontal ground coordinate in authored world tiles.")]
    y: Annotated[float, Field(description="Vertical ground coordinate in authored world tiles.")]


class MoveCommand(VersionedModel):
    type: Literal["move"] = Field(description="Discriminated World wire message or command type.")
    version: Literal[1] = Field(description="Explicit supported wire or preference schema version.")
    seq: int = Field(
        ge=1,
        le=2**31 - 1,
        description="Monotonic per-controller sequence; stale and duplicate commands have no movement effect.",
    )
    dx: float = Field(
        ge=-1,
        le=1,
        description="Requested horizontal ground direction, normalized and speed-limited by the server.",
    )
    dy: float = Field(
        ge=-1,
        le=1,
        description="Requested vertical ground direction, normalized and speed-limited by the server.",
    )
    active: bool = Field(
        default=False,
        description="Explicit user activity signal for the idle deadline, independent of visibility.",
    )
    running: bool = Field(
        default=False,
        description="Explicit run intent; server timing, speed and collision bounds still apply.",
    )
    epoch: str = Field(
        min_length=36,
        max_length=36,
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence.",
    )


class TicketRequest(StrictModel):
    alias: str | None = Field(
        default=None,
        min_length=1,
        max_length=24,
        deprecated=True,
        description="Bounded public account display name; never an email or private profile inference.",
    )
    consent: Literal[True] = Field(
        description="Literal permission to publish the account name, selected avatar and coarse World presence to accepted peers."
    )

    @field_validator("alias")
    @classmethod
    def clean_alias(cls, value: str | None) -> str | None:
        """Normalize the deprecated alias input and reject controls or out-of-bounds names."""
        if value is None:
            return None
        value = unicodedata.normalize("NFC", value.strip())
        if not 1 <= len(value) <= 24 or any(
            unicodedata.category(char) in {"Cc", "Cf"} for char in value
        ):
            raise ValueError("invalid_alias")
        return value

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value: object) -> object:
        """Require literal permission before a public World session is created."""
        return validate_consent(value)


class AuthFrame(VersionedModel):
    version: Literal[1] = Field(description="Explicit supported wire or preference schema version.")
    type: Literal["authenticate"] = Field(
        description="Discriminated World wire message or command type."
    )
    scene: str = Field(
        min_length=1,
        max_length=80,
        description="Authored scene identifier and version; mismatched clients cannot be admitted.",
    )
    ticket: str = Field(
        min_length=32,
        max_length=128,
        description="Short-lived single-use bearer accepted only in the first World authentication frame.",
    )
    resume: str | None = Field(
        default=None,
        min_length=16,
        max_length=128,
        description="Prior controller used in first-frame authentication or its replacement in the ready response.",
    )


class HeartbeatCommand(VersionedModel):
    version: Literal[1] = Field(description="Explicit supported wire or preference schema version.")
    type: Literal["heartbeat"] = Field(
        description="Discriminated World wire message or command type."
    )
    epoch: str = Field(
        min_length=36,
        max_length=36,
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence.",
    )
    visible: bool = Field(
        description="Whether this tab is visible; hidden tabs do not renew visible-presence leases."
    )
    active: bool = Field(
        default=False,
        description="Explicit user activity signal for the idle deadline, independent of visibility.",
    )


class PoseCommand(VersionedModel):
    version: Literal[1] = Field(description="Explicit supported wire or preference schema version.")
    type: Literal["pose"] = Field(description="Discriminated World wire message or command type.")
    epoch: str = Field(
        min_length=36,
        max_length=36,
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence.",
    )
    seq: int = Field(
        ge=1,
        le=2**31 - 1,
        description="Monotonic per-controller sequence; stale and duplicate commands have no movement effect.",
    )
    slot: str | None = Field(
        min_length=1,
        max_length=96,
        description="Requested authored pose slot, or null to stand up.",
    )


PoseResult = Literal["accepted", "occupied", "out_of_reach", "invalid"]


class ControlCommand(VersionedModel):
    version: Literal[1] = Field(description="Explicit supported wire or preference schema version.")
    type: Literal["takeover", "leave", "accept"] = Field(
        description="Discriminated World wire message or command type."
    )
    epoch: str = Field(
        min_length=36,
        max_length=36,
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence.",
    )


WorldCommand = Annotated[
    MoveCommand | HeartbeatCommand | ControlCommand | PoseCommand,
    Field(discriminator="type"),
]
COMMAND_ADAPTER: TypeAdapter[WorldCommand] = TypeAdapter(WorldCommand)


class PublicActor(StrictModel):
    appearance: AvatarAppearance = Field(
        default_factory=AvatarAppearance,
        description="Explicitly selected, catalogue-validated public avatar appearance.",
    )
    pose: str | None = Field(
        default=None,
        description="Occupied authored furniture slot identifier, or null while standing.",
    )
    id: str = Field(
        description="Opaque public actor identifier; never the native account identifier."
    )
    alias: str = Field(
        description="Bounded public account display name; never an email or private profile inference."
    )
    position: Position = Field(description="Ground position in authored world coordinates.")
    facing: int = Field(
        default=1,
        description="Authored isometric facing index used by the public actor renderer.",
    )
    walking: bool = Field(
        default=False,
        description="Recent server-confirmed movement; stale motion is projected as stopped.",
    )


class ActorState(StrictModel):
    appearance: AvatarAppearance = Field(
        default_factory=AvatarAppearance,
        description="Explicitly selected, catalogue-validated public avatar appearance.",
    )
    appearance_revision: int = Field(
        default=0,
        ge=0,
        description="Latest accepted avatar preference revision; stale updates cannot replace it.",
    )
    pose: str | None = Field(
        default=None,
        description="Occupied authored furniture slot identifier, or null while standing.",
    )
    pose_result: PoseResult | None = Field(
        default=None,
        description="Outcome of the latest authoritative pose command, or null before a result.",
    )
    account_id: str = Field(
        description="Native account identifier; internal except on owner-scoped ticket responses."
    )
    public_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Opaque public actor identifier, separate from the native account identifier.",
    )
    alias: str = Field(
        description="Bounded public account display name; never an email or private profile inference."
    )
    language: str = Field(
        description="Canonical backend language code for this account or translated view."
    )
    controller: str = Field(
        description="Opaque controlling-tab fence; never a URL credential or public identity."
    )
    binding: str = Field(
        default="",
        description="Digest of the native session cookie; raw cookie material is never serialized here.",
    )
    position: Position = Field(description="Ground position in authored world coordinates.")
    facing: int = Field(
        default=1,
        description="Authored isometric facing index used by the public actor renderer.",
    )
    seq: int = Field(
        default=0,
        description="Monotonic per-controller sequence; stale and duplicate commands have no movement effect.",
    )
    moved_at: float = Field(
        description="Redis Unix timestamp of the latest accepted movement command, in seconds."
    )
    expires_at: float = Field(
        description="Unix-seconds expiry; expired actors, offers or correspondence are not served."
    )
    activity_at: float = Field(
        description="Redis Unix timestamp of the latest accepted user activity, in seconds."
    )
    walking: bool = Field(
        default=False,
        description="Recent server-confirmed movement; stale motion is projected as stopped.",
    )


class Waiter(StrictModel):
    account_id: str = Field(
        description="Native account identifier; internal except on owner-scoped ticket responses."
    )
    controller: str = Field(
        default="",
        description="Opaque controlling-tab fence; never a URL credential or public identity.",
    )
    binding: str = Field(
        default="",
        description="Digest of the native session cookie; raw cookie material is never serialized here.",
    )
    expires_at: float = Field(
        description="Unix-seconds expiry; expired actors, offers or correspondence are not served."
    )
    offered_until: float | None = Field(
        default=None,
        description="Unix-seconds expiry of the waiter offer, or null while still queued.",
    )


class PresenceLease(StrictModel):
    controller: str = Field(description="Current controlling-tab fence; never published to peers.")
    binding: str = Field(description="Native cookie digest used to fence an idle reconnect.")
    expires_at: float = Field(
        description="Redis time deadline of the last real connection heartbeat."
    )
    activity_at: float = Field(
        description="Redis time of the last accepted activity; heartbeats do not reset it."
    )
    at_home: bool = Field(
        description="Coarse home status shared only with accepted, unblocked relations."
    )


class WorldState(VersionedModel):
    version: Literal[1] = Field(
        default=1, description="Explicit supported wire or preference schema version."
    )
    epoch: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence.",
    )
    revision: int = Field(
        default=0,
        description="Monotonic state or preference revision used to fence concurrent edits.",
    )
    actors: dict[str, ActorState] = Field(
        default_factory=dict,
        max_length=10,
        description="Bounded actors in authoritative state or the recipient-filtered snapshot.",
    )
    queue: list[Waiter] = Field(
        default_factory=list,
        max_length=128,
        description="Bounded FIFO waiters; never included in another account public snapshot.",
    )
    presences: dict[str, PresenceLease] = Field(
        default_factory=dict,
        max_length=128,
        description="Private bounded connection leases, independent of capacity and absent from public snapshots.",
    )


class WorldView(VersionedModel):
    pose_result: PoseResult | None = Field(
        default=None,
        description="Outcome of the latest authoritative pose command, or null before a result.",
    )
    version: Literal[1] = Field(
        default=1, description="Explicit supported wire or preference schema version."
    )
    type: Literal["snapshot"] = Field(
        default="snapshot",
        description="Discriminated World wire message or command type.",
    )
    epoch: str = Field(
        description="Authoritative scene lifetime identifier fencing stale commands and correspondence."
    )
    revision: int = Field(
        description="Monotonic state or preference revision used to fence concurrent edits."
    )
    status: Literal["active", "waiting", "absent"] = Field(
        description="Explicit lifecycle outcome; pending and uncertain never imply completed delivery."
    )
    actors: list[PublicActor] = Field(
        default_factory=list,
        description="Bounded actors in authoritative state or the recipient-filtered snapshot.",
    )
    you: PublicActor | None = Field(
        default=None,
        description="This account public actor projection, or null when not actively admitted.",
    )
    ack: int = Field(
        default=0,
        description="Highest accepted movement or pose sequence for this controller.",
    )
    position: int | None = Field(
        default=None,
        description="One-based FIFO queue position, or null when not waiting.",
    )
    offer_until: float | None = Field(
        default=None,
        description="Unix-seconds expiry of this account entry offer, or null when none exists.",
    )
    idle_until: float | None = Field(
        default=None,
        description="Unix-seconds inactivity deadline for this account, or null outside active admission.",
    )
    controlling: bool = Field(
        default=False,
        description="Whether this connection currently owns the actor or queue controller.",
    )


class TicketResponse(VersionedModel):
    account_id: str = Field(
        description="Native account identifier; internal except on owner-scoped ticket responses."
    )
    ticket: str = Field(
        min_length=32,
        max_length=128,
        description="Short-lived single-use bearer accepted only in the first World authentication frame.",
    )
    ttl_seconds: int = Field(
        ge=1,
        le=60,
        description="Declared lifetime in seconds for this ticket or ephemeral mailbox content.",
    )


class ReadyFrame(VersionedModel):
    type: Literal["ready"] = Field(
        default="ready", description="Discriminated World wire message or command type."
    )
    scene: str = Field(
        min_length=1,
        max_length=80,
        description="Authored scene identifier and version; mismatched clients cannot be admitted.",
    )
    resume: str = Field(
        min_length=16,
        max_length=128,
        description="Prior controller used in first-frame authentication or its replacement in the ready response.",
    )
