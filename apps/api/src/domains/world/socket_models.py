"""Socket-only generations, finite social gestures and correlated command receipts."""

from typing import Final, Literal

from pydantic import Field, field_validator
from pydantic_core import from_json

from src.domains.world.receipt_models import CommandReceipt as CommandReceipt
from src.domains.world.receipt_models import EmoteReceipt as EmoteReceipt
from src.domains.world.receipt_models import MoveReceipt as MoveReceipt
from src.domains.world.receipt_models import PoseReceipt as PoseReceipt
from src.domains.world.receipt_models import ReceiptBase as ReceiptBase
from src.domains.world.wire_models import StrictModel, require_integer_version

EmoteKind = Literal["wave", "thanks", "applause", "laugh", "question", "celebrate"]
# The current client frame generation; every client frame model declares exactly
# ``Literal[2]`` (a test pins each one to this value).
SOCKET_PROTOCOL_VERSION: Final = 2


class ClientProtocolUpgradeRequired(Exception):
    """A client frame declares another socket generation: the client must reload, not retry."""


def require_socket_generation(text: str) -> None:
    """Refuse a frame whose envelope names another socket generation, before strict validation.

    Only a JSON object carrying an integer ``version`` claims a generation. Any other
    frame (not an object, unparsable, a missing or non-integer version) is left to the
    strict reader, which refuses it as an ordinary invalid frame.

    Args:
        text: One received frame, already within the socket byte limit.

    Raises:
        ClientProtocolUpgradeRequired: The frame's integer version is not the current one.
    """
    try:
        envelope = from_json(text)
    except ValueError:
        return
    if not isinstance(envelope, dict):
        return
    version = envelope.get("version")
    if type(version) is int and version != SOCKET_PROTOCOL_VERSION:
        raise ClientProtocolUpgradeRequired


class SocketVersionedModel(StrictModel):
    version: Literal[2] = Field(
        default=2,
        description="Explicit generation of the shared scene socket, independent of preferences and correspondence.",
    )

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        """Reject numeric coercion before literal generation validation."""
        return require_integer_version(value)


class EmoteCommand(SocketVersionedModel):
    version: Literal[2] = Field(description="Required explicit supported socket generation.")
    type: Literal["emote"] = Field(
        description="Finite public gesture command, never text or business dispatch."
    )
    epoch: str = Field(
        min_length=36,
        max_length=36,
        description="Current authoritative scene epoch fencing an obsolete controller lifetime.",
    )
    seq: int = Field(
        ge=1,
        le=2**31 - 1,
        description="Monotonic command sequence in the current controller generation.",
    )
    emote: EmoteKind = Field(
        description="One authored social gesture from the closed public catalogue."
    )


class EmoteState(StrictModel):
    emote: EmoteKind = Field(
        description="Current server-accepted public symbol, with no free text or history."
    )
    serial: int = Field(
        ge=1,
        le=2**31 - 1,
        description="Monotonic actor event identity used to prevent replay on later snapshots.",
    )
    expires_at: float = Field(
        ge=0,
        description="Authoritative Redis Unix-seconds deadline; expired symbols are not projected.",
    )
